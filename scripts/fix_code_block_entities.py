#!/usr/bin/env python3
"""
Fix code-block HTML-entity contamination + language tags + line numbers
in zh/open/**/*.mdx (legacy of mdxify_open_platform.py:119 bug where indented
fences inside numbered lists were not recognized, causing the in-block
`<` `{` `}` to be HTML-entity-escaped along with surrounding prose).

Subcommands:
  preview - dry-run; write scripts/output/open_platform/fix_entities_preview.md
  apply   - rewrite mdx in place + write fix_entities_changes.json + report.md
  report  - print last apply report

Algorithm (per file, line by line):
  1. Detect fenced code via `^(\s*)```(.*)$`; entering fence records indent
     and original info string; closing fence requires same indent.
  2. Inside fence: reverse-escape entities `&lt; &gt; &#123; &#125; &amp;
     &quot; &#39;` → `< > { } & " '` (do `&amp;` last to avoid double-decode).
  3. On fence close, if original info string was empty: detect language
     heuristically (xml / json / java / python / bash / text).
  4. If fence had ≥5 content lines AND info string does not already contain
     `lines`, append ` lines`.
  5. Rewrite the open-fence line: `{indent}```{lang}{ lines?}{other-meta}`.

Safe-by-design:
  - Only touches lines strictly between matching fence pairs.
  - Prose lines (including table rows) are untouched — table cells already
    have `&lt;` escaped on purpose (mdxify forces escape there), reversing
    would break MDX parsing.
  - Pre-existing language tags are preserved (only `lines` may be added).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
OUT_DIR = HERE / "output" / "open_platform"
ZH_OPEN_DIR = REPO / "zh" / "open"

FENCE_RE = re.compile(r"^(\s*)```(.*)$")

ENTITY_REPLACEMENTS = [
    ("&lt;", "<"),
    ("&gt;", ">"),
    ("&#123;", "{"),
    ("&#125;", "}"),
    ("&quot;", '"'),
    ("&#39;", "'"),
    ("&amp;", "&"),  # MUST stay last
]

# Threshold above which we annotate with `lines` for line-number display
LINES_MIN_THRESHOLD = 5


def detect_language(code: str) -> str:
    """Heuristic language detection for plain code blocks (no info string)."""
    if not code.strip():
        return "text"
    head = code.lstrip()
    first_char = head[0] if head else ""

    # XML / HTML — look for tag-like start or common DingTalk SDK XML signatures
    if (
        first_char == "<"
        and (
            head.startswith("<?xml")
            or re.search(r"<(dependency|groupId|artifactId|version|project|configuration|bean)\b", code)
            or re.search(r"</[a-zA-Z][\w-]*>", code)
        )
    ):
        return "xml"

    # JSON — starts with { or [ and contains a quoted key:value
    if first_char in "{[" and re.search(r'"[^"\n]+"\s*:', code):
        return "json"

    # Java
    if re.search(
        r"\b(public\s+(class|static|void)|@Override|import\s+java\.|System\.out\.print|JSONObject)\b",
        code,
    ):
        return "java"

    # Python
    if re.search(r"^\s*#!.*python", code, re.M) or re.search(
        r"^\s*(import\s+\w|from\s+[\w.]+\s+import|def\s+\w+\s*\(|class\s+\w+\s*[:(])",
        code,
        re.M,
    ):
        return "python"

    # Shell / Bash
    if re.search(r"^\s*#!.*\b(bash|sh)\b", code, re.M) or re.search(
        r"^\s*(curl\s|npm\s|pip\s+install|apt-get\s|yarn\s|wget\s|export\s+[A-Z])",
        code,
        re.M,
    ):
        return "bash"

    # HTTP URL line as a one-off (the Webhook example) — falls under text or http
    if re.match(r"^\s*https?://", code) and len(code.splitlines()) <= 2:
        return "text"

    return "text"


def reverse_escape(line: str) -> str:
    for old, new in ENTITY_REPLACEMENTS:
        line = line.replace(old, new)
    return line


def parse_info_string(info: str) -> tuple[str, list[str]]:
    """Return (lang, meta_tokens) from a fence info string like `java title=\"x\" lines`."""
    tokens = info.strip().split()
    if not tokens:
        return "", []
    # Lang is conventionally the first token if it's a bare word (no `=` and no quotes)
    first = tokens[0]
    if "=" in first or first.startswith('"') or first.startswith("'"):
        return "", tokens
    return first, tokens[1:]


def build_info_string(lang: str, other_meta: list[str], add_lines: bool) -> str:
    parts: list[str] = []
    if lang:
        parts.append(lang)
    if add_lines and not any(m == "lines" or m.startswith("lines=") for m in other_meta):
        parts.append("lines")
    parts.extend(other_meta)
    return " ".join(parts)


def process_mdx(text: str) -> tuple[str, dict]:
    """Walk lines; rewrite fenced blocks; return (new_text, stats)."""
    lines = text.splitlines(keepends=False)
    out: list[str] = []
    stats = {
        "fences": 0,
        "entities_decoded": 0,
        "lang_added": Counter(),  # lang -> count
        "lines_added": 0,
        "fences_with_existing_lang": 0,
    }

    fence_indent: int | None = None
    fence_open_idx: int | None = None  # index in `out` of the open-fence line
    fence_info_original: str = ""
    fence_body_lines: list[str] = []  # original (still possibly-encoded) lines, for lang detection of decoded code

    i = 0
    while i < len(lines):
        line = lines[i]
        m = FENCE_RE.match(line)
        if m is not None:
            indent = len(m.group(1))
            info = m.group(2)
            if fence_indent is None:
                # opening fence
                fence_indent = indent
                fence_info_original = info
                fence_body_lines = []
                fence_open_idx = len(out)
                out.append(line)
                i += 1
                continue
            elif indent == fence_indent:
                # closing fence — rebuild open-fence info string
                stats["fences"] += 1
                lang_existing, meta_existing = parse_info_string(fence_info_original)
                if lang_existing:
                    stats["fences_with_existing_lang"] += 1
                    lang = lang_existing
                else:
                    # Detect language from the DECODED body so e.g. `<dependency>` is
                    # recognized as xml even though source had `&lt;dependency>`.
                    decoded_body = "\n".join(reverse_escape(l) for l in fence_body_lines)
                    lang = detect_language(decoded_body)
                    if lang:
                        stats["lang_added"][lang] += 1

                add_lines = len(fence_body_lines) >= LINES_MIN_THRESHOLD
                if add_lines:
                    stats["lines_added"] += 1
                new_info = build_info_string(lang, meta_existing, add_lines)
                rebuilt_open = (" " * fence_indent) + "```" + (new_info if new_info else "")
                if fence_open_idx is not None and rebuilt_open != out[fence_open_idx]:
                    out[fence_open_idx] = rebuilt_open

                # Decode entities in the body lines that were appended via raw passthrough
                # (we previously appended them as-is; rewrite those slots now).
                body_start = (fence_open_idx or 0) + 1
                for j, raw_body_line in enumerate(fence_body_lines):
                    decoded = reverse_escape(raw_body_line)
                    if decoded != raw_body_line:
                        stats["entities_decoded"] += sum(
                            raw_body_line.count(old) for old, _ in ENTITY_REPLACEMENTS
                        )
                    out[body_start + j] = decoded

                fence_indent = None
                fence_open_idx = None
                fence_info_original = ""
                fence_body_lines = []
                out.append(line)
                i += 1
                continue
            else:
                # ``` at a different indent — treat as code content, not a close
                fence_body_lines.append(line)
                out.append(line)
                i += 1
                continue

        if fence_indent is not None:
            fence_body_lines.append(line)
            out.append(line)  # placeholder; will be rewritten on fence close
            i += 1
            continue

        out.append(line)
        i += 1

    new_text = "\n".join(out)
    if text.endswith("\n"):
        new_text += "\n"
    return new_text, stats


def iter_mdx() -> list[Path]:
    return sorted(ZH_OPEN_DIR.rglob("*.mdx"))


# --------------- preview / apply / report ---------------


def write_preview(records: list[dict]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / "fix_entities_preview.md"
    total_files_changed = sum(1 for r in records if r["any_change"])
    total_entities = sum(r["entities_decoded"] for r in records)
    total_lang_added: Counter[str] = Counter()
    total_lines_added = 0
    for r in records:
        total_lang_added.update(r["lang_added"])
        total_lines_added += r["lines_added"]

    lines = ["# fix_code_block_entities — preview\n"]
    lines.append(f"> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"> scanned: **{len(records)}** mdx files under `zh/open/`")
    lines.append("")
    lines.append("## 汇总\n")
    lines.append(f"- 文件含变更：**{total_files_changed}** / {len(records)}")
    lines.append(f"- 反转义 HTML 实体：**{total_entities}** 处")
    lines.append(f"- 加 lines meta：**{total_lines_added}** 个 fence")
    lines.append(f"- 语言探测分布：")
    for lang, n in total_lang_added.most_common():
        lines.append(f"  - `{lang}`: {n}")
    lines.append("")
    lines.append("## 前 30 个变更文件\n")
    changed = [r for r in records if r["any_change"]]
    for r in changed[:30]:
        lines.append(
            f"- `{r['path']}` — entities={r['entities_decoded']} "
            f"fences={r['fences']} lines_added={r['lines_added']} "
            f"langs={dict(r['lang_added'])}"
        )
    if len(changed) > 30:
        lines.append(f"- … {len(changed) - 30} 篇更多见 `fix_entities_changes.json`")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def write_report(records: list[dict]) -> Path:
    """Same shape as preview, used after apply."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / "fix_entities_report.md"
    total_files_changed = sum(1 for r in records if r["any_change"])
    total_entities = sum(r["entities_decoded"] for r in records)
    total_lang_added: Counter[str] = Counter()
    total_lines_added = 0
    for r in records:
        total_lang_added.update(r["lang_added"])
        total_lines_added += r["lines_added"]

    lines = ["# fix_code_block_entities — applied\n"]
    lines.append(f"> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"> rewrote: **{total_files_changed}** mdx files under `zh/open/`")
    lines.append("")
    lines.append("## 汇总\n")
    lines.append(f"- 反转义 HTML 实体：**{total_entities}** 处")
    lines.append(f"- 加 lines meta：**{total_lines_added}** 个 fence")
    lines.append(f"- 语言探测分布：")
    for lang, n in total_lang_added.most_common():
        lines.append(f"  - `{lang}`: {n}")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def cmd_preview(args) -> int:
    files = iter_mdx()
    if not files:
        print(f"ERROR: no mdx under {ZH_OPEN_DIR}", file=sys.stderr)
        return 2
    records: list[dict] = []
    for fp in files:
        text = fp.read_text(encoding="utf-8")
        new_text, stats = process_mdx(text)
        records.append({
            "path": str(fp.relative_to(REPO)),
            "any_change": new_text != text,
            "entities_decoded": stats["entities_decoded"],
            "fences": stats["fences"],
            "lines_added": stats["lines_added"],
            "lang_added": dict(stats["lang_added"]),
        })
    p = write_preview(records)
    print(f"preview → {p}")
    changed = sum(1 for r in records if r["any_change"])
    total_e = sum(r["entities_decoded"] for r in records)
    print(f"  files with change: {changed} / {len(files)}")
    print(f"  entities decoded:  {total_e}")
    return 0


def cmd_apply(args) -> int:
    files = iter_mdx()
    if not files:
        print(f"ERROR: no mdx under {ZH_OPEN_DIR}", file=sys.stderr)
        return 2
    records: list[dict] = []
    written = 0
    for fp in files:
        text = fp.read_text(encoding="utf-8")
        new_text, stats = process_mdx(text)
        if new_text != text:
            fp.write_text(new_text, encoding="utf-8")
            written += 1
        records.append({
            "path": str(fp.relative_to(REPO)),
            "any_change": new_text != text,
            "entities_decoded": stats["entities_decoded"],
            "fences": stats["fences"],
            "lines_added": stats["lines_added"],
            "lang_added": dict(stats["lang_added"]),
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "fix_entities_changes.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    p = write_report(records)
    print(f"apply done. wrote {written} mdx files.")
    print(f"  changes.json → {OUT_DIR / 'fix_entities_changes.json'}")
    print(f"  report.md    → {p}")
    return 0


def cmd_report(args) -> int:
    p = OUT_DIR / "fix_entities_report.md"
    if not p.exists():
        print(f"ERROR: {p} missing. Run apply first.", file=sys.stderr)
        return 2
    print(p.read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("preview", help="dry-run, write preview.md").set_defaults(func=cmd_preview)
    sp.add_parser("apply", help="rewrite mdx + write changes.json + report.md").set_defaults(func=cmd_apply)
    sp.add_parser("report", help="print last apply report").set_defaults(func=cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
