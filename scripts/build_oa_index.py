#!/usr/bin/env python3
"""build_oa_index.py — 从 27 篇「指路牌」页生成 oa 聚合导航页（双语）。

管理后台 hub 里 27 篇正文仅一行链接、指向仓库已有 contacts/docs/drive 页。
不为它们各建空壳页，而是汇总成 1 个概览页，用 <CardGroup> 按目标产品分组、
每张 <Card href> 走仓内相对路径（en 无前缀 / zh 带 /zh）。

用法:
    python3 scripts/build_oa_index.py            # 写 oa/index.mdx + zh/oa/index.mdx
    python3 scripts/build_oa_index.py --dry-run  # 只打印

产物:
  - oa/index.mdx, zh/oa/index.mdx
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SOURCES = {
    'en': Path.home() / 'Downloads' / '2026-07-29_DingTalk_OA_en',
    'zh': Path.home() / 'Downloads' / '2026-07-29_DingTalk_OA_zh',
}
OUT = {
    'en': REPO_ROOT / 'oa' / 'index.mdx',
    'zh': REPO_ROOT / 'zh' / 'oa' / 'index.mdx',
}

FRONTMATTER = {
    'en': ('Admin Console Overview',
           'A directory of DingTalk Admin Console help topics — jump to member and department management, document and Drive storage administration, and enterprise settings across the Help Center.'),
    'zh': ('管理后台总览',
           '钉钉管理后台帮助主题索引——快速跳转到成员与部门管理、文档与钉盘存储管理、企业设置等帮助中心相关页面。'),
}

# 目标产品前缀（去 /zh 后的首段）→ 分组显示名。按此顺序输出。
GROUP_NAMES = {
    'contacts': {'en': 'Organization & Members', 'zh': '组织与人员'},
    'docs': {'en': 'Document Management', 'zh': '文档管理'},
    'drive': {'en': 'Drive Storage', 'zh': '钉盘存储'},
}
GROUP_ORDER = ['contacts', 'docs', 'drive']

CARD_ICON = {'contacts': 'users', 'docs': 'file-lines', 'drive': 'hard-drive'}

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')


def clean(s: str) -> str:
    s = INVISIBLE_CHARS_RE.sub(' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def parse_redirects(lang: str) -> list[tuple[str, str, str]]:
    """返回 [(target_product, card_title, rel_href), ...]，仅 27 指路牌页。"""
    src = SOURCES[lang]
    out = []
    for f in sorted(src.rglob('*.md')):
        if f.name == 'verify_report.md':
            continue
        txt = f.read_text(encoding='utf-8', errors='replace').strip()
        h1 = re.match(r'#\s*(.+)', txt)
        title = clean(h1.group(1)) if h1 else f.stem
        body = re.sub(r'^#[^\n]*\n?', '', txt).strip()
        residual = re.sub(r'\[[^\]]*\]\([^)]*\)', '',
                          re.sub(r'https?://\S+', '',
                                 re.sub(r'!\[[^\]]*\]\([^)]*\)', '', body)))
        tgt = re.findall(r'https?://help\.dingtalk\.[^\s)\]]+', body)
        if len(re.sub(r'\s+', '', residual)) >= 20 or not tgt:
            continue  # 真实正文页，跳过
        m = re.search(r'help\.dingtalk\.[a-z.]+(/.*)', tgt[0])
        rel = m.group(1) if m else tgt[0]
        # 目标产品 = 去掉可选 /zh 后的第一段
        seg = re.sub(r'^/zh/', '/', rel).lstrip('/').split('/')[0]
        out.append((seg, title, rel))
    return out


def build_mdx(lang: str) -> str:
    title, desc = FRONTMATTER[lang]
    rows = parse_redirects(lang)
    grouped: OrderedDict[str, list] = OrderedDict((g, []) for g in GROUP_ORDER)
    for seg, ctitle, rel in rows:
        grouped.setdefault(seg, []).append((ctitle, rel))

    lines = [
        '---',
        f'title: {title}',
        f'description: {desc}',
        '---',
        '',
    ]
    intro = ('This overview links to Admin Console topics maintained under other Help Center '
             'products. Pick a topic below to open the full guide.') if lang == 'en' else \
            ('本页汇总管理后台相关帮助主题，具体内容维护在帮助中心其他产品下。点击下方主题打开完整指南。')
    lines.append(intro)
    lines.append('')

    for seg in GROUP_ORDER:
        items = grouped.get(seg, [])
        if not items:
            continue
        gname = GROUP_NAMES[seg][lang]
        icon = CARD_ICON.get(seg, 'link')
        lines.append(f'## {gname}')
        lines.append('')
        lines.append('<CardGroup cols={2}>')
        for ctitle, rel in items:
            safe = ctitle.replace('"', "'")
            lines.append(f'  <Card title="{safe}" icon="{icon}" href="{rel}" />')
        lines.append('</CardGroup>')
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def main() -> int:
    ap = argparse.ArgumentParser(description='生成 oa 双语聚合导航页')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    for lang in ('en', 'zh'):
        if not SOURCES[lang].exists():
            print(f'❌ 源目录不存在: {SOURCES[lang]}', file=sys.stderr)
            return 1
        mdx = build_mdx(lang)
        n_cards = mdx.count('<Card ')
        print(f'[{lang}] {n_cards} 张卡片 → {OUT[lang]}')
        if not args.dry_run:
            OUT[lang].parent.mkdir(parents=True, exist_ok=True)
            OUT[lang].write_text(mdx, encoding='utf-8')
    return 0


if __name__ == '__main__':
    sys.exit(main())
