"""
fix_broken_bold.py

把 zh/**/*.mdx 中钉钉编辑器导出的破碎粗体 `**A****B**` 合并为 `**AB**`。

输入示例：
  **需要用到的关键功能：****分栏、高亮块**
  **听说你还在用****PPT****画2025年的业务规划图？？**
  **菜单****—>****格式**
输出：
  **需要用到的关键功能：分栏、高亮块**
  **听说你还在用PPT画2025年的业务规划图？？**
  **菜单—>格式**

策略：把所有 `****` 直接消掉（合并相邻的粗体块），不补空格 —— 中英文混排
的空格问题不属于残骸清理范围。需迭代多轮处理 3+ 段连续 `**A****B****C**`。

用法:
  python3 scripts/lint/fix_broken_bold.py             # dry-run
  python3 scripts/lint/fix_broken_bold.py --apply     # 实际写回
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "zh"

# `****` 出现在非首尾位置时即为破碎粗体。但要避免误伤代码块。
# 简单粗暴：行级处理，排除以 ``` 围栏的代码块。
FENCE_RE = re.compile(r"^```")


def fix_text(text: str) -> tuple[str, int]:
    """返回 (新文本, 替换次数)。逐行处理，跳过 ``` 代码块。"""
    out_lines: list[str] = []
    in_fence = False
    total = 0
    for line in text.splitlines(keepends=True):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue
        # 把所有 **** 消掉；迭代以处理 ******（6 个 *）这种连写
        new_line = line
        while "****" in new_line:
            new_line = new_line.replace("****", "")
            total += 1
        out_lines.append(new_line)
    return "".join(out_lines), total


def process(path: Path, apply: bool) -> int:
    text = path.read_text(encoding="utf-8")
    new_text, n = fix_text(text)
    if n and apply:
        path.write_text(new_text, encoding="utf-8")
    return n


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    total_files = 0
    total_hits = 0
    for p in sorted(ROOT.rglob("*.mdx")):
        n = process(p, args.apply)
        if n:
            total_files += 1
            total_hits += n
            rel = p.relative_to(ROOT.parent)
            print(f"  {rel}  ({n} hits)")

    print()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] {total_files} files, {total_hits} **** broken-bold collapsed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
