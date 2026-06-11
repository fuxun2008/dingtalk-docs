#!/usr/bin/env python3
"""
Polish 539 篇 zh/open mdx — 6 transformer 串联 (chained).

  1. dead_links         /document/{ns}/{slug}# → plain text (strict A3 compliance)
  2. notes              **说明** → <Note>; **重要/注意/警告** → <Warning>; **提示** → <Tip>
  3. orphan_lang        "curl\\n\\n```\\n..." → "```bash\\n..."
  4. empty_headings     H1-H6 followed by no real content → drop
  5. image_alts         ![image](url) → ![{nearest_heading|title}](url)
  6. description_dedup  desc == first-para[:80] → mid-segment or fallback title

Subcommands:
  preview  - dry-run, writes polish_preview.md
  apply    - in-place modify zh/open/**/*.mdx
  rules    - list transformers + their default on/off state
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
ZH_OPEN_DIR = REPO / "zh" / "open"
OUT_DIR = HERE / "output" / "open_platform"

sys.path.insert(0, str(HERE))
from mdxify_open_platform import (  # noqa: E402
    split_frontmatter,
    build_frontmatter,
    _FENCE_RE_LINE,
)


# --------------- Transformer 1: dead_links ---------------

_DEAD_LINK_RE = re.compile(
    r"\[(?P<text>[^\]]+)\]\(/document/[a-z][a-z0-9_-]*/[^)\s#?]+(?:#[^)]*)?\)"
)


def transform_dead_links(body: str) -> tuple[str, list[dict]]:
    """Strip `[text](/document/ns/slug#)` to plain `text` (no link)."""
    changes: list[dict] = []

    def repl(m: re.Match) -> str:
        text = m.group("text")
        changes.append({
            "original": m.group(0)[:90],
            "kept_text": text[:60],
        })
        return text

    return _DEAD_LINK_RE.sub(repl, body), changes


# --------------- Transformer 2: notes ---------------

_NOTE_KW_MAP = {
    "说明": "Note",
    "提示": "Tip",
    "重要": "Warning",
    "注意": "Warning",
    "警告": "Warning",
}
_NOTE_HEADER_RE = re.compile(r"^\*\*(说明|提示|重要|注意|警告)\*\*\s*$")
_LIST_MARKER_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s")


def transform_notes(body: str) -> tuple[str, list[dict]]:
    """Convert isolated `**KW**` + next-paragraph to `<Note>`/`<Tip>`/`<Warning>`.

    Skip if header is inside list/table/code fence, or body is list/table/code.
    """
    lines = body.splitlines()
    out: list[str] = []
    changes: list[dict] = []
    i = 0
    in_fence = False
    while i < len(lines):
        line = lines[i]
        if _FENCE_RE_LINE.match(line):
            in_fence = not in_fence
            out.append(line)
            i += 1
            continue
        if in_fence:
            out.append(line)
            i += 1
            continue
        m = _NOTE_HEADER_RE.match(line)
        if not m:
            out.append(line)
            i += 1
            continue
        # Header must be a standalone paragraph (previous output line blank or top)
        if out and out[-1].strip() != "":
            out.append(line)
            i += 1
            continue
        # Find next non-blank line as body start
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines):
            out.append(line)
            i += 1
            continue
        next_line = lines[j]
        # Skip if body starts with list/table/code/another note header
        if (
            next_line.lstrip().startswith("|")
            or _LIST_MARKER_RE.match(next_line)
            or next_line.lstrip().startswith("```")
            or _NOTE_HEADER_RE.match(next_line)
        ):
            out.append(line)
            i += 1
            continue
        # Collect body: from j to next blank line
        body_lines: list[str] = []
        k = j
        while k < len(lines) and lines[k].strip():
            body_lines.append(lines[k])
            k += 1
        if not body_lines:
            out.append(line)
            i += 1
            continue
        kw = m.group(1)
        comp = _NOTE_KW_MAP[kw]
        # Emit JSX component block
        out.append(f"<{comp}>")
        out.extend(body_lines)
        out.append(f"</{comp}>")
        changes.append({
            "keyword": kw,
            "component": comp,
            "body_preview": " / ".join(body_lines)[:80],
        })
        i = k  # skip past body
    return "\n".join(out), changes


# --------------- Transformer 3: orphan_lang ---------------

# Markdownify often outputs `<code class="lang-curl">…</code>` as:
#   curl
#
#   ```
#   <code body>
#   ```
# We collapse the orphan lang line into the fence.
_ORPHAN_LANG_RE = re.compile(
    r"^(?P<lang>curl|java|python|php|json|javascript|js|typescript|ts|"
    r"shell|bash|go|nodejs|node|csharp|c#|ruby|kotlin|scala|yaml|xml|"
    r"html|css|sql|swift|kotlin|dart|rust)\s*\n\s*\n```\s*\n",
    re.MULTILINE,
)

_LANG_NORMALIZE = {
    "js": "javascript",
    "ts": "typescript",
    "nodejs": "javascript",
    "node": "javascript",
    "shell": "bash",
    "c#": "csharp",
}


def transform_orphan_lang(body: str) -> tuple[str, list[dict]]:
    changes: list[dict] = []

    def repl(m: re.Match) -> str:
        raw = m.group("lang")
        norm = _LANG_NORMALIZE.get(raw.lower(), raw.lower())
        changes.append({"lang": raw, "normalized": norm})
        return f"```{norm}\n"

    return _ORPHAN_LANG_RE.sub(repl, body), changes


# --------------- Transformer 4: empty_headings ---------------

_HEAD_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def transform_empty_headings(body: str) -> tuple[str, list[dict]]:
    """Drop H1-H6 headings whose section body (until next ≤level heading or EOF)
    has no meaningful content (only blank lines)."""
    lines = body.splitlines()
    keep = [True] * len(lines)
    changes: list[dict] = []
    in_fence = False
    fence_flags: list[bool] = []
    for line in lines:
        if _FENCE_RE_LINE.match(line):
            in_fence = not in_fence
        fence_flags.append(in_fence)

    for i, line in enumerate(lines):
        if fence_flags[i] and not _FENCE_RE_LINE.match(line):
            continue
        m = _HEAD_RE.match(line)
        if not m:
            continue
        # Don't strip if we're inside a code fence at this line
        # (heading regex shouldn't fire inside fence — `_HEAD_RE` requires line start)
        level = len(m.group(1))
        has_content = False
        j = i + 1
        while j < len(lines):
            cand = lines[j]
            if _FENCE_RE_LINE.match(cand):
                has_content = True
                break
            cm = _HEAD_RE.match(cand)
            if cm and len(cm.group(1)) <= level:
                break
            if cand.strip():
                has_content = True
                break
            j += 1
        if not has_content:
            keep[i] = False
            # Also drop the trailing blank lines we collapsed over
            k = i + 1
            while k < len(lines) and not lines[k].strip():
                keep[k] = False
                k += 1
            changes.append({"level": level, "title": m.group(2)[:60]})
    new_body = "\n".join(l for l, k in zip(lines, keep) if k)
    return new_body, changes


# --------------- Transformer 5: image_alts ---------------

_IMAGE_DEFAULT_ALT_RE = re.compile(r"!\[image\]\((?P<url>[^)]+)\)")


def _normalize_heading_text(s: str) -> str:
    s = re.sub(r"\*+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:40]


def transform_image_alts(body: str, fallback: str) -> tuple[str, list[dict]]:
    """Replace `![image](url)` with `![{nearest_heading|fallback}](url)`."""
    lines = body.splitlines()
    nearest: list[str] = []
    cur_heading = fallback
    in_fence = False
    for line in lines:
        if _FENCE_RE_LINE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            m = _HEAD_RE.match(line)
            if m and 2 <= len(m.group(1)) <= 4:
                cur_heading = _normalize_heading_text(m.group(2)) or fallback
        nearest.append(cur_heading)

    changes: list[dict] = []
    new_lines: list[str] = []
    for i, line in enumerate(lines):
        def repl(m: re.Match, idx: int = i) -> str:
            heading = (nearest[idx] or fallback).replace("]", "")
            changes.append({"line_no": idx + 1, "old_alt": "image", "new_alt": heading})
            return f"![{heading}]({m.group('url')})"

        new_lines.append(_IMAGE_DEFAULT_ALT_RE.sub(repl, line))
    return "\n".join(new_lines), changes


# --------------- Transformer 6: description_dedup ---------------

_MD_INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_MD_INLINE_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_MD_EMPHASIS_RE = re.compile(r"\*+")


def _strip_md_inline(text: str) -> str:
    text = _MD_INLINE_IMG_RE.sub("", text)
    text = _MD_INLINE_LINK_RE.sub(r"\1", text)
    text = _MD_EMPHASIS_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def transform_description_dedup(text: str) -> tuple[str, list[dict]]:
    """If frontmatter description ≈ first-paragraph prefix, replace with mid or title."""
    fm, body = split_frontmatter(text)
    if not fm:
        return text, []
    title = fm.get("title", "")
    desc = fm.get("description", "")
    if not desc or not title:
        return text, []
    body_lines = body.splitlines()
    first_para_lines: list[str] = []
    for line in body_lines:
        if not line.strip():
            if first_para_lines:
                break
            continue
        first_para_lines.append(line)
    first_para = _strip_md_inline(" ".join(first_para_lines))
    if not first_para:
        return text, []
    if desc[:80] != first_para[:80]:
        return text, []
    # Dup detected: pick new desc
    new_desc = ""
    if len(first_para) > 80:
        new_desc = first_para[80:280].strip()
    if len(new_desc) < 20:
        new_desc = title
    if new_desc == desc:
        return text, []
    new_text = build_frontmatter(title, new_desc) + body
    return new_text, [{"old_desc": desc[:60], "new_desc": new_desc[:60]}]


# --------------- driver ---------------

TRANSFORMER_SPECS = [
    # (id, name, default_on, kind) — kind = "body" or "full"
    ("dead_links", "1. 删 /document/ 死链 → 纯文本", True, "body"),
    ("notes", "2. **说明**/**重要** → <Note>/<Warning>", True, "body"),
    ("orphan_lang", "3. 孤立 lang 行合并到 fenced code", True, "body"),
    ("empty_headings", "4. 删空标题（无非空内容到下级）", True, "body"),
    ("image_alts", "5. ![image] → ![{nearest_heading}]", True, "body_with_title"),
    ("description_dedup", "6. desc == 首段 → 取中段或 title", True, "full"),
]


def select_transformers(args) -> list[str]:
    enable = set((args.enable or "").split(",")) - {""}
    disable = set((args.disable or "").split(",")) - {""}
    active: list[str] = []
    for tid, _name, default_on, _kind in TRANSFORMER_SPECS:
        on = default_on
        if tid in enable:
            on = True
        if tid in disable:
            on = False
        if on:
            active.append(tid)
    return active


def apply_transformers_to_text(text: str, active: list[str], fallback_title: str) -> tuple[str, dict]:
    """Apply selected transformers in canonical order. Returns (new_text, per_t_changes)."""
    per_t: dict[str, list[dict]] = {}

    # description_dedup operates on full text incl. frontmatter
    fm, body = split_frontmatter(text)

    body_changes_map: dict[str, list[dict]] = {}
    if "dead_links" in active:
        body, ch = transform_dead_links(body)
        if ch:
            body_changes_map["dead_links"] = ch
    if "notes" in active:
        body, ch = transform_notes(body)
        if ch:
            body_changes_map["notes"] = ch
    if "orphan_lang" in active:
        body, ch = transform_orphan_lang(body)
        if ch:
            body_changes_map["orphan_lang"] = ch
    if "empty_headings" in active:
        body, ch = transform_empty_headings(body)
        if ch:
            body_changes_map["empty_headings"] = ch
    if "image_alts" in active:
        body, ch = transform_image_alts(body, fallback=fallback_title)
        if ch:
            body_changes_map["image_alts"] = ch

    # Rebuild text with updated body
    if fm:
        new_text = build_frontmatter(fm.get("title", fallback_title), fm.get("description", ""))
        new_text += body
    else:
        new_text = body

    # description_dedup on full text (re-parses fm against possibly-new body)
    if "description_dedup" in active:
        new_text2, ch = transform_description_dedup(new_text)
        if ch:
            body_changes_map["description_dedup"] = ch
            new_text = new_text2

    return new_text, body_changes_map


def iter_mdx_files() -> list[Path]:
    files: list[Path] = []
    for ns in ("development", "dingstart"):
        d = ZH_OPEN_DIR / ns
        if d.exists():
            files.extend(sorted(d.glob("*.mdx")))
    return files


def cmd_preview(args) -> int:
    active = select_transformers(args)
    files = iter_mdx_files()
    if args.limit:
        files = files[: args.limit]
    print(f"preview {len(files)} files, active transformers: {active}")

    all_changes: dict[str, list[dict]] = defaultdict(list)
    per_file: dict[str, dict[str, int]] = {}
    sample_per_t: dict[str, list[dict]] = defaultdict(list)

    for i, p in enumerate(files):
        text = p.read_text(encoding="utf-8")
        fm, _ = split_frontmatter(text)
        title = fm.get("title", p.stem) if fm else p.stem
        _, per_t = apply_transformers_to_text(text, active, fallback_title=title)
        rel = f"{p.parent.name}/{p.stem}"
        per_file[rel] = {tid: len(chs) for tid, chs in per_t.items()}
        for tid, chs in per_t.items():
            all_changes[tid].extend(chs)
            for ch in chs:
                if len(sample_per_t[tid]) < 8:
                    sample_per_t[tid].append({"file": rel + ".mdx", **ch})
        if (i + 1) % 100 == 0 or i + 1 == len(files):
            print(f"  [{i + 1}/{len(files)}]")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_preview_report(active, all_changes, sample_per_t, per_file, len(files))
    print()
    print(f"=== preview done ===")
    print(f"  files processed: {len(files)}")
    for tid, _, _, _ in TRANSFORMER_SPECS:
        if tid in active:
            n = len(all_changes.get(tid, []))
            fc = sum(1 for v in per_file.values() if v.get(tid))
            print(f"  {tid:20s} {n:>5} ops in {fc:>3} files")
    print(f"  preview: {OUT_DIR / 'polish_preview.md'}")
    return 0


def _write_preview_report(
    active: list[str],
    all_changes: dict[str, list[dict]],
    samples: dict[str, list[dict]],
    per_file: dict[str, dict[str, int]],
    file_count: int,
) -> None:
    lines: list[str] = ["# polish 预览（dry-run）\n"]
    lines.append(f"> 生成：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"> 输入：`zh/open/{{development,dingstart}}/*.mdx` 共 {file_count} 篇")
    lines.append(f"> 启用 transformer：{', '.join(active)}")
    lines.append("")
    lines.append("## 命中汇总\n")
    lines.append("| ID | 规则 | 命中数 | 受影响文件 |")
    lines.append("|---|---|---:|---:|")
    for tid, name, default_on, _ in TRANSFORMER_SPECS:
        if tid not in active:
            continue
        n = len(all_changes.get(tid, []))
        fc = sum(1 for v in per_file.values() if v.get(tid))
        lines.append(f"| {tid} | {name} | {n} | {fc} |")
    lines.append("")
    lines.append("## 样例（前 8 条 per transformer）\n")
    for tid, name, _, _ in TRANSFORMER_SPECS:
        if tid not in active:
            continue
        ss = samples.get(tid, [])
        if not ss:
            continue
        lines.append(f"### {tid} — {name}\n")
        for s in ss:
            file = s.get("file", "?")
            if tid == "dead_links":
                lines.append(f"- `{file}`: {s.get('original', '')} → `{s.get('kept_text', '')}`")
            elif tid == "notes":
                lines.append(f"- `{file}`: **{s.get('keyword')}** → <{s.get('component')}>: {s.get('body_preview', '')[:70]}")
            elif tid == "orphan_lang":
                lines.append(f"- `{file}`: `{s.get('lang')}` → ```{s.get('normalized')}")
            elif tid == "empty_headings":
                lines.append(f"- `{file}`: H{s.get('level')} `{s.get('title', '')}`")
            elif tid == "image_alts":
                lines.append(f"- `{file}:L{s.get('line_no')}`: alt=`{s.get('old_alt')}` → `{s.get('new_alt')}`")
            elif tid == "description_dedup":
                lines.append(f"- `{file}`: `{s.get('old_desc', '')[:50]}` → `{s.get('new_desc', '')[:50]}`")
        lines.append("")
    (OUT_DIR / "polish_preview.md").write_text("\n".join(lines), encoding="utf-8")


def cmd_apply(args) -> int:
    active = select_transformers(args)
    files = iter_mdx_files()
    if args.limit:
        files = files[: args.limit]
    print(f"apply {len(files)} files, active transformers: {active}")

    total_per_t: Counter = Counter()
    changed = 0
    for i, p in enumerate(files):
        text = p.read_text(encoding="utf-8")
        fm, _ = split_frontmatter(text)
        title = fm.get("title", p.stem) if fm else p.stem
        new_text, per_t = apply_transformers_to_text(text, active, fallback_title=title)
        if new_text != text:
            p.write_text(new_text, encoding="utf-8")
            changed += 1
            for tid, chs in per_t.items():
                total_per_t[tid] += len(chs)
        if (i + 1) % 100 == 0 or i + 1 == len(files):
            print(f"  [{i + 1}/{len(files)}]")

    # Report
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["# polish 应用报告\n"]
    lines.append(f"> 生成：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"> 处理：{len(files)} 篇，改动：{changed} 篇")
    lines.append("")
    lines.append("| transformer | 操作数 |")
    lines.append("|---|---:|")
    for tid, name, _, _ in TRANSFORMER_SPECS:
        if tid in active:
            lines.append(f"| {tid} | {total_per_t.get(tid, 0)} |")
    (OUT_DIR / "polish_report.md").write_text("\n".join(lines), encoding="utf-8")

    print()
    print(f"=== apply done ===")
    print(f"  files modified: {changed} / {len(files)}")
    for tid, _, _, _ in TRANSFORMER_SPECS:
        if tid in active:
            print(f"  {tid:20s} {total_per_t.get(tid, 0):>5} ops")
    return 0


def cmd_rules(args) -> int:
    active = set(select_transformers(args))
    for tid, name, default_on, kind in TRANSFORMER_SPECS:
        on = "ON " if tid in active else "OFF"
        print(f"  [{on}] {tid:20s} {name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sp = p.add_subparsers(dest="cmd", required=True)
    common = lambda s: (
        s.add_argument("--enable", help="Comma-sep transformer IDs to enable"),
        s.add_argument("--disable", help="Comma-sep transformer IDs to disable"),
        s.add_argument("--limit", type=int, default=0, help="Process at most N files"),
    )
    pp = sp.add_parser("preview", help="Dry-run with polish_preview.md output")
    common(pp)
    pp.set_defaults(func=cmd_preview)
    pa = sp.add_parser("apply", help="In-place modify zh/open/**/*.mdx")
    common(pa)
    pa.set_defaults(func=cmd_apply)
    pr = sp.add_parser("rules", help="List transformers + active state")
    common(pr)
    pr.set_defaults(func=cmd_rules)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
