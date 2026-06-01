"""
fix_frontmatter_nbsp.py

将 zh/docs/**/*.mdx 文件的 frontmatter 块（首两个 --- 之间）内的
不间断空格（U+00A0）替换为普通 ASCII 空格。

YAML 标准要求 key 后面的分隔符必须是 ASCII 空格；NBSP 会让严格解析器
失败，Mintlify 当前虽然容忍但不可依赖。

用法:
  python3 scripts/lint/fix_frontmatter_nbsp.py             # 仅汇总不改
  python3 scripts/lint/fix_frontmatter_nbsp.py --apply     # 实际写回
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

NBSP = " "
ROOT = Path(__file__).resolve().parents[2] / "zh" / "docs"
FM_RE = re.compile(r"^(---\n)(.*?\n)(---\n)", re.S)


def process(path: Path, apply: bool) -> int:
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    if not m:
        return 0
    fm_body = m.group(2)
    if NBSP not in fm_body:
        return 0
    cleaned = fm_body.replace(NBSP, " ")
    count = fm_body.count(NBSP)
    if apply:
        new_text = m.group(1) + cleaned + m.group(3) + text[m.end():]
        path.write_text(new_text, encoding="utf-8")
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    total_files = 0
    total_chars = 0
    for p in sorted(ROOT.rglob("*.mdx")):
        n = process(p, args.apply)
        if n:
            total_files += 1
            total_chars += n
            rel = p.relative_to(ROOT.parent.parent)
            print(f"  {rel}  ({n} NBSP)")

    print()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] {total_files} files, {total_chars} NBSP in frontmatter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
