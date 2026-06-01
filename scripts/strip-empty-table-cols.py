#!/usr/bin/env python3
"""
strip-empty-table-cols.py

strip-en-media.py 把图片删完后，原本放 Screenshot 的整列变成纯空白单元格。
本脚本扫所有 aitable/ 表格：
- 整列数据行全空 → 删该列（header + separator + 所有数据行同步删）
- 全部列都被判定为空 → 删整张表
- 收敛 3+ 空行 → 1 个

不动 zh/ ja/。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "aitable"

TABLE_LINE = re.compile(r'^\s*\|')
SEPARATOR_CELL = re.compile(r'^\s*:?-{3,}:?\s*$')
MULTI_BLANK = re.compile(r'\n{3,}')


def split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return s.split("|")


def is_separator_row(cells: list[str]) -> bool:
    non_empty = [c.strip() for c in cells if c.strip()]
    return bool(non_empty) and all(SEPARATOR_CELL.match(c) for c in non_empty)


def process_table(rows: list[str]) -> list[str]:
    if len(rows) < 3:
        return rows
    parsed = [split_row(r) for r in rows]

    sep_idx = None
    for i in range(1, len(parsed)):
        if is_separator_row(parsed[i]):
            sep_idx = i
            break
    if sep_idx is None:
        return rows

    n_cols = max(len(r) for r in parsed)
    for r in parsed:
        while len(r) < n_cols:
            r.append("")

    data = parsed[sep_idx + 1:]
    if not data:
        return rows

    empty_cols = [c for c in range(n_cols) if all(not row[c].strip() for row in data)]
    if not empty_cols:
        return rows
    if len(empty_cols) == n_cols:
        return []

    keep = [c for c in range(n_cols) if c not in empty_cols]
    out: list[str] = []
    for i, cells in enumerate(parsed):
        kept = [cells[c] for c in keep]
        if i == sep_idx:
            out.append("| " + " | ".join("---" for _ in kept) + " |")
        else:
            out.append("| " + " | ".join(c.strip() for c in kept) + " |")
    return out


def process_file(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    n_tables = 0
    n_dropped = 0
    while i < len(lines):
        if TABLE_LINE.match(lines[i]):
            j = i
            while j < len(lines) and TABLE_LINE.match(lines[j]):
                j += 1
            block = lines[i:j]
            new_block = process_table(block)
            if new_block != block:
                n_tables += 1
                if not new_block:
                    n_dropped += 1
            out.extend(new_block)
            i = j
        else:
            out.append(lines[i])
            i += 1
    new_text = "\n".join(out)
    new_text = MULTI_BLANK.sub("\n\n", new_text)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
    return n_tables, n_dropped


def main() -> None:
    total_t = 0
    total_d = 0
    touched = 0
    files = sorted(TARGET.rglob("*.mdx"))
    for f in files:
        n_t, n_d = process_file(f)
        if n_t:
            print(f"  {f.relative_to(ROOT)}: {n_t} tables modified ({n_d} dropped)")
            total_t += n_t
            total_d += n_d
            touched += 1
    print(f"\n{touched}/{len(files)} files changed; {total_t} tables modified, {total_d} dropped")


if __name__ == "__main__":
    main()
