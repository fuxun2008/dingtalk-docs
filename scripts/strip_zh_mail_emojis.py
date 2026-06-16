#!/usr/bin/env python3
"""strip_zh_mail_emojis.py — 清理 zh/mail/ 钉钉文档源装饰 emoji。

钉钉中文文档作者在正文中加的装饰性 emoji（👇 操作指示符 / 👨💼🗣🎯🤝💬 段落或 H2 装饰），
在 mintlify 国际版帮助中心场景中是冗余视觉污染——保留语义符号 ✅（表格"是"列勾），
其余 emoji 全部删除。

黑名单（已实测 zh/mail/ 命中分布）：👇 13 篇 + 🎯👨💬💼🗣🤝 activate-alibaba-enterprise-mail
6 处 + 👨💼 link-an-existing-alibaba-cloud-mailbox 2 处 = 21 处。

用法:
    python3 scripts/strip_zh_mail_emojis.py             # dry-run
    python3 scripts/strip_zh_mail_emojis.py --apply     # 实写
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ZH_MAIL_DIR = REPO_ROOT / 'zh' / 'mail'

# 黑名单 emoji 字符（保留 ✅ — 表格语义符号）
# 每个 emoji 后可能跟 variant selector (U+FE0F) 或 ZWJ (U+200D)
STRIP_EMOJI_RE = re.compile(r'[👇👨👼💬💼🗣🤝🎯][️‍]*\s*')


def process_one(path: Path) -> tuple[int, str]:
    text = path.read_text(encoding='utf-8')
    hits = STRIP_EMOJI_RE.findall(text)
    new_text = STRIP_EMOJI_RE.sub('', text)
    return len(hits), new_text


def main() -> int:
    ap = argparse.ArgumentParser(description='zh/mail/ 装饰 emoji 批清')
    ap.add_argument('--apply', action='store_true', help='实写覆盖（默认 dry-run）')
    args = ap.parse_args()

    total = 0
    affected_files: list[Path] = []

    for path in sorted(ZH_MAIL_DIR.glob('*.mdx')):
        hits, new_text = process_one(path)
        if hits == 0:
            continue
        affected_files.append(path)
        total += hits
        print(f'  {path.relative_to(REPO_ROOT)} — {hits} hits')
        if args.apply:
            path.write_text(new_text, encoding='utf-8')

    print('=' * 60)
    print(f'命中: {total} 处 / {len(affected_files)} 个文件')
    if args.apply:
        print('已实写。')
    else:
        print('dry-run（加 --apply 实写）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
