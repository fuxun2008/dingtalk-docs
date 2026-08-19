#!/usr/bin/env python3
"""修复表格"空表头三明治"：钉钉文档导出器把真表头误产成空表头行，
真正的表头文案沦为表格第一行数据。

形态：
    |  |  |
    | --- | --- |
    | **配置项** | **说明** |
    | `CorpId` | ... |

修复后：
    | **配置项** | **说明** |
    | --- | --- |
    | `CorpId` | ... |

只对"看起来像表头"的候选行（单元格短、不以句末标点结尾）做自动提升；
命中但不够 header-like 的（真数据行、长句），只报告不改，留给人工 Edit
补写合适的表头文案。

用法:
    python3 scripts/lint/fix_empty_table_header_sandwich.py --files-from <list.txt>            # dry-run
    python3 scripts/lint/fix_empty_table_header_sandwich.py --files-from <list.txt> --apply     # 实际写盘
"""
import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SEP_RE = re.compile(r'^\s*\|?[\s:\-|]+\|?\s*$')
SENTENCE_END = ('.', '。', '!', '！', '?', '？', '：', ':')
MAX_CELL_LEN = 45


def cells_of(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip('|').split('|')]


def is_empty_header_row(line: str) -> bool:
    s = line.strip()
    if not s.startswith('|') or '-' in s:
        return False
    cells = cells_of(s)
    return len(cells) >= 2 and all(c == '' for c in cells)


def is_separator_row(line: str) -> bool:
    return bool(SEP_RE.match(line)) and '-' in line and '|' in line


def looks_header_like(cells: list[str]) -> bool:
    non_empty = [c for c in cells if c]
    if not non_empty:
        return False
    for c in non_empty:
        text = c.strip('*').strip()
        if not text or len(text) > MAX_CELL_LEN or text.endswith(SENTENCE_END):
            return False
    return True


def process(path: Path):
    """返回 (new_lines or None, promoted: list[(line_no, text)], manual: list[(line_no, text)])."""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    new_lines: list[str] = []
    promoted: list[tuple[int, str]] = []
    manual: list[tuple[int, str]] = []
    changed = False

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if (
            is_empty_header_row(line)
            and i + 2 < n
            and is_separator_row(lines[i + 1])
            and lines[i + 2].strip().startswith('|')
        ):
            candidate = lines[i + 2]
            ccells = cells_of(candidate)
            if looks_header_like(ccells):
                new_lines.append(candidate)
                new_lines.append(lines[i + 1])
                promoted.append((i + 1, candidate.strip()))
                changed = True
                i += 3
                continue
            else:
                manual.append((i + 1, candidate.strip()))
        new_lines.append(line)
        i += 1

    if not changed and not manual:
        return None, [], []
    return ("\n".join(new_lines) if changed else None), promoted, manual


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--files-from", required=True, help="每行一个相对仓库根的路径")
    parser.add_argument("--apply", action="store_true", help="实际写盘（默认 dry-run）")
    args = parser.parse_args()

    rel_paths = [l.strip() for l in Path(args.files_from).read_text(encoding="utf-8").splitlines() if l.strip()]
    files = [REPO_ROOT / p for p in rel_paths]
    missing = [p for p in files if not p.is_file()]
    if missing:
        print(f"[error] {len(missing)} 个文件不存在，例如 {missing[0]}", file=sys.stderr)
        return 1

    mode = "apply" if args.apply else "dry-run"
    print(f"[info] 模式={mode} 文件数={len(files)}\n")

    total_promoted = 0
    total_manual = 0
    changed_files = 0
    manual_report: list[str] = []

    for path in files:
        new_text, promoted, manual = process(path)
        rel = str(path.relative_to(REPO_ROOT))
        if promoted:
            total_promoted += len(promoted)
            changed_files += 1
            if args.apply and new_text is not None:
                path.write_text(new_text, encoding="utf-8")
            for ln, txt in promoted:
                print(f"  [提升] {rel}:{ln}  {txt[:70]}")
        if manual:
            total_manual += len(manual)
            for ln, txt in manual:
                manual_report.append(f"  [需人工] {rel}:{ln}  {txt[:70]}")

    print(f"\n可自动提升: {total_promoted} 处 / {changed_files} 文件")
    print(f"需人工补表头: {total_manual} 处\n")
    if manual_report:
        print("=== 需人工清单 ===")
        for line in manual_report:
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
