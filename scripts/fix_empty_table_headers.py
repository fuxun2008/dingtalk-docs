#!/usr/bin/env python3
"""
Fix GFM table placeholder headers in zh/open/**/*.mdx.

Source markdown (from markdownify HTML→GFM) emits a 3-line pattern that
renders to an empty `<thead>` band above the real title text:

  |  |  |                          ← empty placeholder header (becomes <thead><th></th></thead>)
  | --- | --- |                    ← separator
  | **参数名称** | **说明** |       ← real title row (rendered as first <tbody> row)

GFM requires the FIRST table line to be the header. We can't simply drop the
empty line — that leaves the separator first, which breaks GFM table parsing.
Instead: drop the empty header AND swap the next two lines so the real title
row is promoted into `<thead>`:

  | **参数名称** | **说明** |       ← now the real header
  | --- | --- |                    ← separator
  | data ... |

Subcommands:
  preview - dry-run; write fix_empty_thead_preview.md
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

# Empty header: only `|` and whitespace, e.g. `|  |  |`, `| |`, `|  |  |  |`
EMPTY_HEADER_RE = re.compile(r"^\s*\|(?:\s*\|)+\s*$")

# Separator: e.g. `| --- | --- |`, `| :--- | ---: |`, `|---|---|`
SEPARATOR_RE = re.compile(r"^\s*\|(?:\s*:?-+:?\s*\|)+\s*$")

# Table data row: starts and ends with `|`
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")

# Real header signature: a table row that contains bold markdown `**...**` in
# at least one cell. This is the marker markdownify uses for the actual title
# row when the source HTML lacked <th>. We only promote rows matching this —
# never promote arbitrary first-data rows.
BOLD_TITLE_RE = re.compile(r"\*\*[^*]+\*\*")


def process_mdx(text: str) -> tuple[str, int]:
    """Return (new_text, num_tables_fixed)."""
    lines = text.splitlines(keepends=False)
    out: list[str] = []
    fixed = 0
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        # Match: empty header at line[i] + separator at line[i+1] + table row at line[i+2]
        if (
            i + 2 < n
            and EMPTY_HEADER_RE.match(line)
            and SEPARATOR_RE.match(lines[i + 1])
            and TABLE_ROW_RE.match(lines[i + 2])
            and not EMPTY_HEADER_RE.match(lines[i + 2])  # data row must have content
            and BOLD_TITLE_RE.search(lines[i + 2])        # real title is bolded
        ):
            # Drop line[i] (empty header); swap line[i+1] (sep) and line[i+2] (real title)
            out.append(lines[i + 2])  # real title promoted to header
            out.append(lines[i + 1])  # separator stays just below
            fixed += 1
            i += 3
            continue
        out.append(line)
        i += 1
    new_text = "\n".join(out)
    if text.endswith("\n"):
        new_text += "\n"
    return new_text, fixed


def iter_mdx() -> list[Path]:
    return sorted(ZH_OPEN_DIR.rglob("*.mdx"))


def cmd_preview(args) -> int:
    files = iter_mdx()
    if not files:
        print(f"ERROR: no mdx under {ZH_OPEN_DIR}", file=sys.stderr)
        return 2
    records: list[dict] = []
    total_fixed = 0
    for fp in files:
        text = fp.read_text(encoding="utf-8")
        new_text, fixed = process_mdx(text)
        if fixed:
            records.append({
                "path": str(fp.relative_to(REPO)),
                "tables_fixed": fixed,
            })
            total_fixed += fixed

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / "fix_empty_thead_preview.md"
    lines = ["# fix_empty_table_headers — preview\n"]
    lines.append(f"> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"> scanned: **{len(files)}** mdx")
    lines.append("")
    lines.append("## 汇总\n")
    lines.append(f"- 文件含变更：**{len(records)}** / {len(files)}")
    lines.append(f"- 表格修正（删空 thead + 交换 sep/header）：**{total_fixed}** 张")
    lines.append("")
    lines.append("## 前 30 个变更文件\n")
    for r in records[:30]:
        lines.append(f"- `{r['path']}` — {r['tables_fixed']} 张表")
    if len(records) > 30:
        lines.append(f"- … 另 {len(records) - 30} 篇")
    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"preview → {p}")
    print(f"  files with change: {len(records)} / {len(files)}")
    print(f"  tables fixed:      {total_fixed}")
    return 0


def cmd_apply(args) -> int:
    files = iter_mdx()
    if not files:
        print(f"ERROR: no mdx under {ZH_OPEN_DIR}", file=sys.stderr)
        return 2
    records: list[dict] = []
    written = 0
    total_fixed = 0
    for fp in files:
        text = fp.read_text(encoding="utf-8")
        new_text, fixed = process_mdx(text)
        if fixed:
            fp.write_text(new_text, encoding="utf-8")
            written += 1
            total_fixed += fixed
            records.append({
                "path": str(fp.relative_to(REPO)),
                "tables_fixed": fixed,
            })

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "fix_empty_thead_changes.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    p = OUT_DIR / "fix_empty_thead_report.md"
    lines = ["# fix_empty_table_headers — applied\n"]
    lines.append(f"> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"> rewrote: **{written}** mdx files")
    lines.append("")
    lines.append("## 汇总\n")
    lines.append(f"- 表格修正：**{total_fixed}** 张")
    lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"apply done. wrote {written} mdx files.")
    print(f"  tables fixed:    {total_fixed}")
    print(f"  changes.json → {OUT_DIR / 'fix_empty_thead_changes.json'}")
    print(f"  report.md    → {p}")
    return 0


def cmd_report(args) -> int:
    p = OUT_DIR / "fix_empty_thead_report.md"
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
