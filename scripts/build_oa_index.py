#!/usr/bin/env python3
"""build_oa_index.py — 生成 oa 聚合导航页（双语），统一收纳全部 46 篇。

管理后台总览页 = 全产品 46 页索引，按 oa 自有 category 分 6 组（与左侧导航一致）：
  - 19 篇真实正文 → <Card href="oa/<slug>">（仓内 oa 页；slug 取自 import_oa_{en,zh}.GROUPS）
  - 27 篇指路牌   → <Card href="/<target>">（正文仅一行链接、指向 contacts/docs/drive 已有页，内链化）

每篇归入其在钉钉 hub 的原始 category（下载目录首段），真实正文与指路牌同 category 合并同组。

用法:
    python3 scripts/build_oa_index.py            # 写 oa/index.mdx + zh/oa/index.mdx
    python3 scripts/build_oa_index.py --dry-run

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
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
import import_oa_en  # noqa: E402
import import_oa_zh  # noqa: E402

SOURCES = {
    'en': Path.home() / 'Downloads' / '2026-07-29_DingTalk_OA_en',
    'zh': Path.home() / 'Downloads' / '2026-07-29_DingTalk_OA_zh',
}
OUT = {
    'en': REPO_ROOT / 'oa' / 'index.mdx',
    'zh': REPO_ROOT / 'zh' / 'oa' / 'index.mdx',
}
GROUPS_MOD = {'en': import_oa_en, 'zh': import_oa_zh}

FRONTMATTER = {
    'en': ('Admin Console Overview',
           'A complete directory of DingTalk Admin Console help topics — every guide across member and department management, enterprise settings, security, app management, and billing, in one place.'),
    'zh': ('管理后台总览',
           '钉钉管理后台帮助主题总索引——组织与人员、企业配置、安全与权限、应用管理、费用与订阅等全部主题一页统管，快速跳转到完整指南。'),
}

# oa 自有 category 输出顺序（en 用 import_oa_en 的 group 名，zh 用中文）
GROUP_ORDER = {
    'en': ['Getting Started', 'Organization & Members', 'Organization Settings',
           'Security & Permission', 'App Management', 'Billing'],
    'zh': ['快速入门', '组织与人员', '企业配置', '安全与权限', '应用管理', '费用与订阅'],
}
GROUP_ICON = {
    'Getting Started': 'rocket', '快速入门': 'rocket',
    'Organization & Members': 'users', '组织与人员': 'users',
    'Organization Settings': 'building', '企业配置': 'building',
    'Security & Permission': 'shield-halved', '安全与权限': 'shield-halved',
    'App Management': 'grid-2', '应用管理': 'grid-2',
    'Billing': 'cart-shopping', '费用与订阅': 'cart-shopping',
}

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')


def clean(s: str) -> str:
    return re.sub(r'\s+', ' ', INVISIBLE_CHARS_RE.sub(' ', s)).strip()


def real_slug_by_source(lang: str) -> dict[str, tuple[str, str]]:
    """source_basename → (group, slug)，来自 import_oa_{lang}.GROUPS（19 真实正文）。"""
    mod = GROUPS_MOD[lang]
    out = {}
    for group_name, items in mod.GROUPS:
        for slug, source_basename, _title in items:
            out[source_basename] = (group_name, slug)
    return out


def collect(lang: str) -> "OrderedDict[str, list[tuple[str, str]]]":
    """按原始 oa category 归组，返回 {group: [(card_title, href), ...]}。"""
    src = SOURCES[lang]
    real_map = real_slug_by_source(lang)
    grouped: OrderedDict[str, list] = OrderedDict((g, []) for g in GROUP_ORDER[lang])

    for f in sorted(src.rglob('*.md')):
        if f.name == 'verify_report.md':
            continue
        rel = f.relative_to(src)
        source_basename = str(rel)
        cat = rel.parts[0]
        txt = f.read_text(encoding='utf-8', errors='replace').strip()
        h1 = re.match(r'#\s*(.+)', txt)
        title = clean(h1.group(1)) if h1 else f.stem
        body = re.sub(r'^#[^\n]*\n?', '', txt).strip()
        residual = re.sub(r'\[[^\]]*\]\([^)]*\)', '',
                          re.sub(r'https?://\S+', '',
                                 re.sub(r'!\[[^\]]*\]\([^)]*\)', '', body)))
        tgt = re.findall(r'https?://help\.dingtalk\.[^\s)\]]+', body)
        is_redirect = len(re.sub(r'\s+', '', residual)) < 20 and tgt

        if is_redirect:
            m = re.search(r'help\.dingtalk\.[a-z.]+(/.*)', tgt[0])
            href = m.group(1) if m else tgt[0]
            group = cat  # 指路牌用原始 category
        else:
            # 真实正文：从 import GROUPS 拿 (group, slug)
            if source_basename not in real_map:
                continue  # 目录/空容器节点，跳过
            group, slug = real_map[source_basename]
            prefix = '' if lang == 'en' else 'zh/'
            href = f'/{prefix}oa/{slug}'

        grouped.setdefault(group, []).append((title, href))
    return grouped


def build_mdx(lang: str) -> str:
    title, desc = FRONTMATTER[lang]
    grouped = collect(lang)
    intro = ('This overview indexes every Admin Console topic — both guides maintained here and '
             'those under other Help Center products. Pick a topic to open its full guide.') if lang == 'en' else \
            ('本页汇总管理后台全部帮助主题——既含本产品维护的指南，也含维护在帮助中心其他产品下的主题。点击主题打开完整指南。')
    lines = ['---', f'title: {title}', f'description: {desc}', '---', '', intro, '']

    for group in GROUP_ORDER[lang]:
        items = grouped.get(group, [])
        if not items:
            continue
        icon = GROUP_ICON.get(group, 'link')
        lines.append(f'## {group}')
        lines.append('')
        lines.append('<CardGroup cols={2}>')
        for ctitle, href in items:
            safe = ctitle.replace('"', "'")
            lines.append(f'  <Card title="{safe}" icon="{icon}" href="{href}" />')
        lines.append('</CardGroup>')
        lines.append('')
    return '\n'.join(lines).rstrip() + '\n'


def main() -> int:
    ap = argparse.ArgumentParser(description='生成 oa 双语聚合导航页（全 46）')
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
