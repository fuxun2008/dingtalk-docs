#!/usr/bin/env python3
"""
Remove redundant frontmatter `description` when it equals `title` in zh/open mdx.

Background: commit 2e6a7ef polish_open_platform.py:description_dedup transformer
falls back to `new_desc = title` when first-paragraph is too short, leaving 362
zh/open mdx with `title == description`. Mintlify renders H1 + description-subtitle
side-by-side, so identical text shows twice on the page.

Fix: when frontmatter `title` and `description` are trim-equal, drop the
description line entirely. Mintlify omits the subtitle in absence of description
and auto-fallbacks SEO meta to the first paragraph.

Touches only frontmatter (the leading `---\\n…---\\n` block); body is untouched.

Subcommands:
  preview - dry-run; write scripts/output/open_platform/fix_redundant_desc_preview.md
  apply   - rewrite mdx + write report.md
  report  - print last apply report
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
OUT_DIR = HERE / "output" / "open_platform"
ZH_OPEN_DIR = REPO / "zh" / "open"

# A frontmatter description line, capturing the (optionally quoted) value
DESC_LINE_RE = re.compile(
    r'^description:\s*(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|(.+?))\s*$',
    re.M,
)
TITLE_LINE_RE = re.compile(
    r'^title:\s*(?:"((?:[^"\\]|\\.)*)"|\'((?:[^\'\\]|\\.)*)\'|(.+?))\s*$',
    re.M,
)


def _extract(match: re.Match | None) -> str | None:
    if not match:
        return None
    return next((g for g in match.groups() if g is not None), None)


_JUNK_STRIP_RE = re.compile(r"[\s*\-_=.,!?;:，。！？；：·…]+")


def _is_junk_description(desc: str) -> bool:
    """Detect descriptions extracted from non-prose source (table rows, fragments, etc.)."""
    s = desc.strip()
    if not s:
        return True
    # Contains a pipe — almost certainly a stray GFM table row, e.g. "| | |"
    if "|" in s:
        return True
    # After stripping punctuation/whitespace, fewer than 5 meaningful chars
    cleaned = _JUNK_STRIP_RE.sub("", s)
    if len(cleaned) < 5:
        return True
    return False


def process_mdx(text: str) -> tuple[str, bool]:
    """Return (new_text, removed?) — removed=True when description was stripped.

    Removes the description line when either:
      1) title.strip() == description.strip() (Mintlify subtitle duplicates H1)
      2) description is "junk" (table fragment, too-short, all-punctuation)
    """
    if not text.startswith("---\n"):
        return text, False
    end = text.find("\n---\n", 4)
    if end < 0:
        return text, False
    fm_block = text[4:end]  # inside frontmatter (excluding leading/trailing ---)

    title_m = TITLE_LINE_RE.search(fm_block)
    desc_m = DESC_LINE_RE.search(fm_block)
    title = _extract(title_m)
    desc = _extract(desc_m)
    if title is None or desc is None:
        return text, False
    same = title.strip() == desc.strip()
    junk = _is_junk_description(desc)
    if not (same or junk):
        return text, False

    # Drop the description line in-place (preserve trailing blank lines outside fm)
    fm_lines = fm_block.split("\n")
    new_fm_lines = [ln for ln in fm_lines if not DESC_LINE_RE.match(ln)]
    new_fm = "\n".join(new_fm_lines)
    new_text = "---\n" + new_fm + text[end:]
    return new_text, True


def iter_mdx() -> list[Path]:
    return sorted(ZH_OPEN_DIR.rglob("*.mdx"))


def _write_report(path: Path, header: str, records: list[dict]) -> None:
    removed = [r for r in records if r["removed"]]
    lines = [f"# {header}\n"]
    lines.append(f"> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"> files: **{len(records)}** total / **{len(removed)}** with description removed")
    lines.append("")
    lines.append("## 汇总\n")
    lines.append(f"- 删除 title===description 的冗余 description：**{len(removed)}** 处")
    lines.append("")
    lines.append("## 前 30 个变更文件\n")
    for r in removed[:30]:
        lines.append(f"- `{r['path']}` (title: {r['title']!r})")
    if len(removed) > 30:
        lines.append(f"- … 另 {len(removed) - 30} 篇")
    path.write_text("\n".join(lines), encoding="utf-8")


def cmd_preview(args) -> int:
    files = iter_mdx()
    records: list[dict] = []
    for fp in files:
        text = fp.read_text(encoding="utf-8")
        new_text, removed = process_mdx(text)
        title = ""
        if removed:
            m = TITLE_LINE_RE.search(text[:1000])
            title = _extract(m) or ""
        records.append({"path": str(fp.relative_to(REPO)), "removed": removed, "title": title})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / "fix_redundant_desc_preview.md"
    _write_report(p, "fix_redundant_description — preview", records)
    removed_count = sum(1 for r in records if r["removed"])
    print(f"preview → {p}")
    print(f"  files with description removed: {removed_count} / {len(files)}")
    return 0


def cmd_apply(args) -> int:
    files = iter_mdx()
    records: list[dict] = []
    written = 0
    for fp in files:
        text = fp.read_text(encoding="utf-8")
        new_text, removed = process_mdx(text)
        title = ""
        if removed:
            m = TITLE_LINE_RE.search(text[:1000])
            title = _extract(m) or ""
            fp.write_text(new_text, encoding="utf-8")
            written += 1
        records.append({"path": str(fp.relative_to(REPO)), "removed": removed, "title": title})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "fix_redundant_desc_changes.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    p = OUT_DIR / "fix_redundant_desc_report.md"
    _write_report(p, "fix_redundant_description — applied", records)
    print(f"apply done. wrote {written} mdx files.")
    print(f"  report.md    → {p}")
    return 0


def cmd_report(args) -> int:
    p = OUT_DIR / "fix_redundant_desc_report.md"
    if not p.exists():
        print(f"ERROR: {p} missing. Run apply first.", file=sys.stderr)
        return 2
    print(p.read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("preview", help="dry-run").set_defaults(func=cmd_preview)
    sp.add_parser("apply", help="rewrite mdx").set_defaults(func=cmd_apply)
    sp.add_parser("report", help="print last apply report").set_defaults(func=cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
