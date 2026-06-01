#!/usr/bin/env python3
"""
strip-en-media.py

一次性脚本：清空 AI Table 英文版 mdx 中所有图片/视频引用，并收敛空行。

策略：
- 整行图片/视频 → 删行（含前置缩进 / 列表标记 / 引用前缀）
- 内联图片（在表格单元格、句末、其他文本中间） → 就地删 ![alt](url) 子串
- URL 中可能包含 (1) (2) 这种圆括号 → 用平衡括号正则
- <video> 标签全是单行 → 同步删行
- 行剩纯空白 → 截断为真正空行
- 仅含 "> " 的孤儿 blockquote → 删行
- 连续 3+ 空行 → 1 个空行

只动 aitable/**/*.mdx，不动 zh/ ja/ docs.json。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "aitable"

# ![alt](url) — 允许 url 内含一层平衡 ()，如 image%20(1)_xxx.png
IMG = re.compile(r'!\[[^\]]*\]\((?:[^()]|\([^()]*\))*\)')

# 整行 <video ...> 或 <video ...></video>
VIDEO_LINE = re.compile(r'^\s*<video\b[^>]*(?:/>|>\s*</video>)\s*$')

# 仅含 ">" + 空白 的孤儿引用行（图片被抽走后剩下）
EMPTY_BLOCKQUOTE = re.compile(r'^\s*>+\s*$')

MULTI_BLANK = re.compile(r'\n{3,}')


def strip_file(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8")
    img_removed = 0
    video_removed = 0
    out_lines: list[str] = []

    for line in text.split("\n"):
        # 1. 删整行 video
        if VIDEO_LINE.match(line):
            video_removed += 1
            continue

        # 2. 内联剥 ![](...) — 一行可能含多张图
        matches = IMG.findall(line)
        if matches:
            img_removed += len(matches)
            line = IMG.sub("", line)

        # 3. 行剩纯空白 → 转为真正空行
        if line.strip() == "":
            out_lines.append("")
            continue

        # 4. 剥完图后剩 "> " 孤儿引用行 → 删
        if EMPTY_BLOCKQUOTE.match(line):
            continue

        out_lines.append(line)

    new_text = "\n".join(out_lines)
    new_text = MULTI_BLANK.sub("\n\n", new_text)

    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
    return img_removed, video_removed


def main() -> None:
    mdx_files = sorted(TARGET.rglob("*.mdx"))
    total_img = 0
    total_video = 0
    touched = 0
    for f in mdx_files:
        img_n, video_n = strip_file(f)
        if img_n or video_n:
            touched += 1
            print(f"  {f.relative_to(ROOT)}: -{img_n} img, -{video_n} video")
            total_img += img_n
            total_video += video_n
    print(f"\n{touched}/{len(mdx_files)} files changed; removed {total_img} images, {total_video} videos")


if __name__ == "__main__":
    main()
