#!/usr/bin/env python3
"""
修复纯符号 bold 不渲染：**+** / **...** / **「+」** 等（闭合 ** 前为标点、后接 CJK，
CommonMark 不闭合 → 字面显示星号）。纯符号内容的 **X** → <strong>X</strong>（HTML 必渲染）。

算法：按 `**` 切分每行，奇数段=bold 内容，偶数段=普通文本（正确配对，不受长度限制）。
- 仅当该行 `**` 数为偶数（平衡）才处理，奇数则整行跳过（避免破坏跨行/不平衡 bold）。
- 代码围栏 ``` 区块整体跳过。
- 仅 bold 内容“无字母数字且无 CJK”（纯符号）才转 <strong>，其余原样 **X**。

只作用于 --list 指定的文件集（本次 215 新文件）。

用法：
  python3 scripts/fix_ja_symbol_bold.py --list /tmp/newset.txt           # dry-run
  python3 scripts/fix_ja_symbol_bold.py --list /tmp/newset.txt --apply
"""
from __future__ import annotations
import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MEANINGFUL = re.compile(r"[0-9A-Za-z぀-ヿ㐀-鿿가-힣]")


def fix_line(line: str) -> tuple[str, int]:
    if line.count("**") < 2 or line.count("**") % 2 != 0:
        return line, 0
    parts = line.split("**")
    n = 0
    out = [parts[0]]
    # parts[1],parts[3],... 是 bold 内容；parts[2],parts[4],... 是其后普通文本
    for i in range(1, len(parts), 2):
        content = parts[i]
        after = parts[i + 1] if i + 1 < len(parts) else ""
        if content and not MEANINGFUL.search(content):
            out.append(f"<strong>{content}</strong>")
            n += 1
        else:
            out.append(f"**{content}**")
        out.append(after)
    return "".join(out), n


def fix_text(text: str) -> tuple[str, int]:
    lines = text.split("\n")
    fence = False
    total = 0
    for idx, ln in enumerate(lines):
        if ln.lstrip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        new, n = fix_line(ln)
        if n:
            lines[idx] = new
            total += n
    return "\n".join(lines), total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    files = [l.strip() for l in Path(args.list).read_text().splitlines() if l.strip()]
    total = hit = 0
    for rel in files:
        p = REPO / rel
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        new, n = fix_text(src)
        if n:
            total += n
            hit += 1
            print(f"  [{n}] {rel}")
            if args.apply:
                p.write_text(new, encoding="utf-8")
    print(f"\n{'[applied]' if args.apply else '[dry-run]'} 命中 {total} 处 / {hit} 文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
