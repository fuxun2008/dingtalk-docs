"""
fix_back_to_links.py

清理 zh/docs/**/*.mdx 中钉钉编辑器导出的引用块返回链接残骸：
  ▍返回「[X](href) 」目录页
  ▍返回「 **X** 」目录页
  ▍返回「 [**X**](href) 」目录页同办公平台出品 ——
  ...
统一为：
  **返回[X](href)目录页**       （X 是链接时）
  **返回 X 目录页**             （X 是纯文本/纯粗体时）

对齐英文 commit 5075cf3 的 `**Back to [X](href)**` 风格。

用法:
  python3 scripts/lint/fix_back_to_links.py             # dry-run
  python3 scripts/lint/fix_back_to_links.py --apply     # 实际写回
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "zh" / "docs"

# 主模式：捕获 ▍返回「INNER」目录页 后续可能有 trailing junk
MAIN_RE = re.compile(r"▍返回「\s*(.*?)\s*」目录页[^\n]*")


def transform_inner(inner: str) -> str:
    """把「...」内的 X 部分转成 markdown 链接 / 粗体的正常形态。"""
    # [**X**](href) → [X](href)（剥内嵌粗体避免后续整体加粗时嵌套）
    m = re.fullmatch(r"\[\*\*(.+?)\*\*\]\((.+?)\)", inner)
    if m:
        return f"[{m.group(1)}]({m.group(2)})"
    # [X](href) → 保持
    if re.fullmatch(r"\[.+?\]\(.+?\)", inner):
        return inner
    # **X** → X（外层会整体加粗，避免嵌套粗体）
    m = re.fullmatch(r"\*\*(.+?)\*\*", inner)
    if m:
        return m.group(1)
    # 纯文本
    return inner


def replace_line(match: re.Match) -> str:
    inner = match.group(1)
    normalized = transform_inner(inner)
    # 链接形态：紧贴 "返回[X](href)目录页"
    if re.fullmatch(r"\[.+?\]\(.+?\)", normalized):
        return f"**返回{normalized}目录页**"
    # 纯文本/粗体：加空格 "返回 X 目录页"
    return f"**返回 {normalized} 目录页**"


def process(path: Path, apply: bool) -> int:
    text = path.read_text(encoding="utf-8")
    new_text, n = MAIN_RE.subn(replace_line, text)
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
            rel = p.relative_to(ROOT.parent.parent)
            print(f"  {rel}  ({n} hits)")

    print()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] {total_files} files, {total_hits} ▍返回 lines normalized")
    return 0


if __name__ == "__main__":
    sys.exit(main())
