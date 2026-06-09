#!/usr/bin/env python3
"""
Fix bold-with-trailing-CJK-punctuation in zh/open/**/*.mdx.

Source markdown frequently contains patterns like:
    `**接口频率限制：**`                  ← colon inside bold
    `**《自定义机器人服务及免责条款》，**` ← comma inside bold
    `**直播 > 发起直播。**`               ← period inside bold
    `**步骤一：获取免登授权码**。**`       ← already split, but extra trailing **

Markdown / MDX semantics:
  - `**X，**` is technically valid bold + comma, but many parsers (incl.
    Mintlify's stricter MDX) refuse to close `**` when the preceding char
    is full-width punctuation (no word-boundary). Result: literal `**` shows.
  - Best practice: keep punctuation OUTSIDE the bold marker.

Rewrite:
    `**(inner)([，。：；！？、》])**`  →  `**(inner)**(\\2)`

Fence-aware (skips inside ```...```). Skips table rows (| … |) where bold-cell
boundaries are sensitive (already covered by mdxify GFM-table escape).

Subcommands:
  preview / apply / report
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

FENCE_RE = re.compile(r"^(\s*)```")
TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")

# Bold containing inner text ending with CJK closing punctuation
#   \1 = inner content (non-empty, no `*` inside)
#   \2 = trailing CJK punctuation character
BOLD_CJK_TRAIL_RE = re.compile(
    r"\*\*([^*\n]+?)([，。：；！？、》])\*\*"
)


def process_line(line: str) -> tuple[str, int]:
    new, count = BOLD_CJK_TRAIL_RE.subn(r"**\1**\2", line)
    return new, count


def process_mdx(text: str) -> tuple[str, int]:
    lines = text.splitlines(keepends=False)
    out: list[str] = []
    total = 0
    fence_indent: int | None = None
    for line in lines:
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
            out.append(line)
            continue
        # Skip GFM table rows: cell content is sensitive (mdxify escapes ** there)
        if TABLE_ROW_RE.match(line):
            out.append(line)
            continue
        new_line, n = process_line(line)
        out.append(new_line)
        total += n

    new_text = "\n".join(out)
    if text.endswith("\n"):
        new_text += "\n"
    return new_text, total


def iter_mdx() -> list[Path]:
    return sorted(ZH_OPEN_DIR.rglob("*.mdx"))


def _write_report(path: Path, header: str, records: list[dict]) -> None:
    total = sum(r["fixes"] for r in records)
    changed = [r for r in records if r["fixes"]]
    lines = [f"# {header}\n"]
    lines.append(f"> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"> files: **{len(records)}** total / **{len(changed)}** changed")
    lines.append("")
    lines.append("## 汇总\n")
    lines.append(f"- CJK 标点结尾粗体修正：**{total}** 处")
    lines.append("")
    lines.append("## 前 30 个变更文件\n")
    for r in changed[:30]:
        lines.append(f"- `{r['path']}` — {r['fixes']} 处")
    if len(changed) > 30:
        lines.append(f"- … 另 {len(changed) - 30} 篇")
    path.write_text("\n".join(lines), encoding="utf-8")


def cmd_preview(args) -> int:
    files = iter_mdx()
    records: list[dict] = []
    for fp in files:
        text = fp.read_text(encoding="utf-8")
        _, fixes = process_mdx(text)
        records.append({"path": str(fp.relative_to(REPO)), "fixes": fixes})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / "fix_bold_cjk_punct_preview.md"
    _write_report(p, "fix_bold_cjk_punct — preview", records)
    total = sum(r["fixes"] for r in records)
    changed = sum(1 for r in records if r["fixes"])
    print(f"preview → {p}")
    print(f"  files with change: {changed} / {len(files)}")
    print(f"  fixes: {total}")
    return 0


def cmd_apply(args) -> int:
    files = iter_mdx()
    records: list[dict] = []
    written = 0
    for fp in files:
        text = fp.read_text(encoding="utf-8")
        new_text, fixes = process_mdx(text)
        if fixes:
            fp.write_text(new_text, encoding="utf-8")
            written += 1
        records.append({"path": str(fp.relative_to(REPO)), "fixes": fixes})

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "fix_bold_cjk_punct_changes.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    p = OUT_DIR / "fix_bold_cjk_punct_report.md"
    _write_report(p, "fix_bold_cjk_punct — applied", records)
    total = sum(r["fixes"] for r in records)
    print(f"apply done. wrote {written} mdx files.")
    print(f"  fixes: {total}")
    print(f"  report.md    → {p}")
    return 0


def cmd_report(args) -> int:
    p = OUT_DIR / "fix_bold_cjk_punct_report.md"
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
