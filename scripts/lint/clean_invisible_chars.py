"""
clean_invisible_chars.py

清理 zh/docs/**/*.mdx 中：
  - 正文 NBSP (U+00A0) → ASCII 空格
  - 零宽字符 (U+200B/200C/200D/FEFF) → 删除
  - 行尾空白 → 删除
  - 末尾多余空行 → 保留单个换行

frontmatter 内已由 fix_frontmatter_nbsp.py 处理过，这里也兼并扫描以防遗漏。
代码块内的字符照样清理（NBSP/零宽在代码中也是噪音，行尾空白同样无意义）。

用法:
  python3 scripts/lint/clean_invisible_chars.py             # dry-run
  python3 scripts/lint/clean_invisible_chars.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "zh" / "docs"

NBSP = " "
ZW_CHARS = re.compile(r"[​‌‍﻿]")
TRAILING_WS = re.compile(r"[ \t]+$", re.M)


def process(path: Path, apply: bool) -> tuple[int, int, int]:
    text = path.read_text(encoding="utf-8")
    nbsp_n = text.count(NBSP)
    zw_n = len(ZW_CHARS.findall(text))
    trailing_n = len(TRAILING_WS.findall(text))
    if not (nbsp_n or zw_n or trailing_n):
        return 0, 0, 0
    cleaned = text.replace(NBSP, " ")
    cleaned = ZW_CHARS.sub("", cleaned)
    cleaned = TRAILING_WS.sub("", cleaned)
    # 收敛末尾换行：保留单个 \n
    cleaned = cleaned.rstrip("\n") + "\n"
    if apply:
        path.write_text(cleaned, encoding="utf-8")
    return nbsp_n, zw_n, trailing_n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    f_files = 0
    sum_nbsp = sum_zw = sum_tr = 0
    for p in sorted(ROOT.rglob("*.mdx")):
        n, z, t = process(p, args.apply)
        if n or z or t:
            f_files += 1
            sum_nbsp += n
            sum_zw += z
            sum_tr += t
            print(f"  {p.relative_to(ROOT.parent.parent)}  NBSP={n} ZW={z} trailing={t}")
    print()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] {f_files} files cleaned  /  NBSP={sum_nbsp} ZW={sum_zw} trailing={sum_tr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
