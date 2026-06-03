"""
fix_priority_placeholders.py

把 zh/**/*.mdx 中钉钉编辑器导出的 `[优先级: N]` / `\[优先级: N\]` 编号占位符
转为 markdown 数字列表前缀 `N. `。

输入示例：
  [优先级: 1] 新建一个钉钉文档
  [优先级: 2]点击插入功能里的"快速分栏"
  \[优先级: 1\] 文档管理
输出：
  1. 新建一个钉钉文档
  2. 点击插入功能里的"快速分栏"
  1. 文档管理

对齐英文 commit cae9ac8 的 `[Priority: N]` → markdown 数字列表风格。

用法:
  python3 scripts/lint/fix_priority_placeholders.py             # dry-run
  python3 scripts/lint/fix_priority_placeholders.py --apply     # 实际写回
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "zh"

# 兼容转义 `\[优先级\]` 与非转义 `[优先级]`；冒号兼容半角全角；编号后空格 0 或多个
PRIORITY_RE = re.compile(r"\\?\[优先级\s*[:：]\s*(\d+)\\?\]\s*")


def process(path: Path, apply: bool) -> int:
    text = path.read_text(encoding="utf-8")
    new_text, n = PRIORITY_RE.subn(lambda m: f"{m.group(1)}. ", text)
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
    print(f"[{mode}] {total_files} files, {total_hits} [优先级: N] placeholders normalized")
    return 0


if __name__ == "__main__":
    sys.exit(main())
