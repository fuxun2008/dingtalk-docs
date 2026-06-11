#!/usr/bin/env python3
"""
Fix heading-related artifacts in zh/open/**/*.mdx.

Two transformers (both fence-aware — won't touch content inside ``` ... ``` blocks):

  1. strip-bold-in-heading
     `## **xxx**`           → `## xxx`            (heading already bold; ** is redundant)
     `### **xxx**`          → `### xxx`
     `## **xxx** suffix`    → `## xxx suffix`     (only when ** wraps entire content; otherwise skip)

  2. bold-as-heading
     `**xxx**` alone on a line (surrounded by blank lines) → `### xxx`
     Avoids:
       - lines inside fenced code blocks
       - lines inside GFM tables (start/end with `|`)
       - lines inside list items (start with `-` or digit+`.` or `+`)

Subcommands:
  preview - dry-run; write scripts/output/open_platform/fix_heading_preview.md
  apply   - rewrite mdx + write report.md
  report  - print last apply report
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
OUT_DIR = HERE / "output" / "open_platform"
ZH_OPEN_DIR = REPO / "zh" / "open"

FENCE_RE = re.compile(r"^(\s*)```")

# Heading with surrounding `**` wrapping its full content:
#   `## **xxx**`  or  `### **xxx**`  etc.
HEADING_BOLD_RE = re.compile(r"^(#{1,6})\s+\*\*([^*\n]+)\*\*\s*$")

# Standalone bold line (no other prose), candidate for promotion to ### heading
BOLD_LINE_RE = re.compile(r"^[ \t]*\*\*([^*\n]+)\*\*[ \t]*$")


def process_mdx(text: str) -> tuple[str, dict]:
    """Return (new_text, stats)."""
    lines = text.splitlines(keepends=False)
    out: list[str] = []
    stats = {
        "stripped_bold_in_heading": 0,
        "promoted_bold_to_heading": 0,
    }

    fence_indent: int | None = None

    for i, line in enumerate(lines):
        m_fence = FENCE_RE.match(line)
        if m_fence is not None:
            ind = len(m_fence.group(1))
            if fence_indent is None:
                fence_indent = ind
            elif ind == fence_indent:
                fence_indent = None
            out.append(line)
            continue

        if fence_indent is not None:
            # Inside fenced code — leave alone
            out.append(line)
            continue

        # Transformer 1: strip redundant `**…**` inside heading
        mh = HEADING_BOLD_RE.match(line)
        if mh:
            hashes, content = mh.group(1), mh.group(2).strip()
            out.append(f"{hashes} {content}")
            stats["stripped_bold_in_heading"] += 1
            continue

        # Transformer 2: promote standalone bold line to ### heading
        mb = BOLD_LINE_RE.match(line)
        if mb:
            # Require surrounding blank lines (avoid mid-paragraph false positives)
            prev_blank = (i == 0) or (lines[i - 1].strip() == "")
            next_blank = (i + 1 >= len(lines)) or (lines[i + 1].strip() == "")
            # Avoid table rows (won't start with `**` but safety check) + list items
            content = mb.group(1).strip()
            if prev_blank and next_blank:
                out.append(f"### {content}")
                stats["promoted_bold_to_heading"] += 1
                continue

        out.append(line)

    new_text = "\n".join(out)
    if text.endswith("\n"):
        new_text += "\n"
    return new_text, stats


def iter_mdx() -> list[Path]:
    return sorted(ZH_OPEN_DIR.rglob("*.mdx"))


def _write_report(path: Path, header: str, records: list[dict]) -> None:
    total_stripped = sum(r["stripped_bold_in_heading"] for r in records)
    total_promoted = sum(r["promoted_bold_to_heading"] for r in records)
    changed = [r for r in records if r["any_change"]]

    lines = [f"# {header}\n"]
    lines.append(f"> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"> files: **{len(records)}** total / **{len(changed)}** changed")
    lines.append("")
    lines.append("## 汇总\n")
    lines.append(f"- 剥 heading 内冗余 `**`：**{total_stripped}** 处")
    lines.append(f"- `**xxx**` 独占一行升 `### xxx`：**{total_promoted}** 处")
    lines.append("")
    lines.append("## 前 30 个变更文件\n")
    for r in changed[:30]:
        lines.append(
            f"- `{r['path']}` — stripped={r['stripped_bold_in_heading']} "
            f"promoted={r['promoted_bold_to_heading']}"
        )
    if len(changed) > 30:
        lines.append(f"- … 另 {len(changed) - 30} 篇")
    path.write_text("\n".join(lines), encoding="utf-8")


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
            **stats,
        })
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / "fix_heading_preview.md"
    _write_report(p, "fix_heading_hierarchy — preview", records)
    changed = sum(1 for r in records if r["any_change"])
    total_s = sum(r["stripped_bold_in_heading"] for r in records)
    total_p = sum(r["promoted_bold_to_heading"] for r in records)
    print(f"preview → {p}")
    print(f"  files with change: {changed} / {len(files)}")
    print(f"  stripped bold in heading: {total_s}")
    print(f"  promoted bold to heading: {total_p}")
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
            **stats,
        })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "fix_heading_changes.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    p = OUT_DIR / "fix_heading_report.md"
    _write_report(p, "fix_heading_hierarchy — applied", records)
    print(f"apply done. wrote {written} mdx files.")
    print(f"  changes.json → {OUT_DIR / 'fix_heading_changes.json'}")
    print(f"  report.md    → {p}")
    return 0


def cmd_report(args) -> int:
    p = OUT_DIR / "fix_heading_report.md"
    if not p.exists():
        print(f"ERROR: {p} missing. Run apply first.", file=sys.stderr)
        return 2
    print(p.read_text(encoding="utf-8"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sp = p.add_subparsers(dest="cmd", required=True)
    sp.add_parser("preview", help="dry-run, write preview.md").set_defaults(func=cmd_preview)
    sp.add_parser("apply", help="rewrite mdx + write report.md").set_defaults(func=cmd_apply)
    sp.add_parser("report", help="print last apply report").set_defaults(func=cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
