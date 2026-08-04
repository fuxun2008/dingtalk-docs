#!/usr/bin/env python3
"""import_drive_incremental.py — 双语增量把「钉盘本地同步」4 主题 → drive/ + zh/drive/。

源 hub：`【0731】钉盘英文翻译`（jb9Y4gmKWrx9eo4dC4EPyG7EJGXn6lpz），双语 hub，
8 篇 = 4 组中英对照，主题都是「钉盘本地同步 / DingTalk Drive Local Sync」。

与 import_drive_en.py（上一批 Drive 23 篇全量）的差异：
- 双语：en → drive/<slug>.mdx，zh → zh/drive/<slug>.mdx（slug 中英共用同一套 kebab-case）
- 增量：只产 8 篇，不生成 nav-fragment（docs.json 用 Edit 精确插入）
- 无 Back-to 母文档段（这批 hub 不是折叠目录结构，删 TRAILING_BACK_TO_RE）
- 重复 H1 处理：部分 en 篇 line-1 H1 与 line-3 H1 文本完全相同（如 Can't Open Files
  Locally?），parse_frontmatter_data 抽走 line-1 后 line-3 变孤立重复标题 → 额外剥

用法:
    python3 scripts/import_drive_incremental.py --dry-run
    python3 scripts/import_drive_incremental.py
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))

# import_archive 顶层 import requests（仅其死链探测函数用，本脚本不调用）。
# 系统 Python 无 requests 且 PEP 668 禁装，注入轻量 stub 让模块能加载，零系统副作用。
if 'requests' not in sys.modules:
    import types
    sys.modules['requests'] = types.ModuleType('requests')

from import_archive import escape_mdx, parse_frontmatter_data, yaml_escape  # noqa: E402

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-08-03_DingTalk_Drive_incremental'
DRIVE_EN_DIR = REPO_ROOT / 'drive'
DRIVE_ZH_DIR = REPO_ROOT / 'zh' / 'drive'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'drive_incremental'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
LEADING_HR_RE = re.compile(r'\A---\s*\n+')
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')

# 4 主题：(slug, en_source, en_title, zh_source, zh_title, en_desc, zh_desc)
# slug 中英共用；title/description 各自语言
ITEMS: list[dict] = [
    {
        'slug': 'how-to-sync-files-between-computer-and-dingtalk-drive',
        'group_en': 'Employee User Guide', 'group_zh': '员工使用指南',
        'en_source': 'Sync Files Between Your Computer and DingTalk Drive.adoc.md',
        'en_title': 'Sync Files Between Your Computer and DingTalk Drive',
        'zh_source': '钉盘本地同步使用说明.adoc.md',
        'zh_title': '钉盘本地同步使用说明',
        'en_desc': "Keep files automatically synced across your computer, phone, and tablet with DingTalk Drive Local Sync — enable sync, access DingDrive in File Explorer, check sync status, change the sync path, and manage member access.",
        'zh_desc': "通过钉盘本地同步，让电脑、手机、平板上的文件实时自动同步——开启本地同步、在文件资源管理器访问 DingDrive、查看同步状态、修改同步路径，以及管理员如何限制成员使用。",
    },
    {
        'slug': 'about-the-file-edit-lock',
        'group_en': 'FAQ', 'group_zh': 'FAQ',
        'en_source': 'About the File Edit Lock.adoc.md',
        'en_title': 'About the File Edit Lock',
        'zh_source': '了解本地文件编辑锁.adoc.md',
        'zh_title': '了解本地文件编辑锁',
        'en_desc': "In a DingTalk Drive local sync folder, a file being edited is locked to prevent others on other devices from editing it at the same time, avoiding version conflicts; the lock releases automatically when the file is closed.",
        'zh_desc': "在钉盘本地同步文件夹中，正在被编辑的文件会被锁定，防止其他人在其他设备上同时编辑造成版本冲突；当编辑者退出后文件自动解锁，其他人即可继续打开编辑。",
    },
    {
        'slug': 'cannot-enable-local-sync',
        'group_en': 'FAQ', 'group_zh': 'FAQ',
        'en_source': "Can't Enable Local Sync_.adoc.md",
        'en_title': "Can't Enable Local Sync?",
        'zh_source': '无法开启本地同步功能？.adoc.md',
        'zh_title': '无法开启本地同步功能？',
        'en_desc': "Can't turn on DingTalk Drive Local Sync? Check three things — enable it from the DingTalk desktop app, update your OS and DingTalk client to the latest version, and confirm your enterprise administrator allows you to use local sync.",
        'zh_desc': "无法开启钉盘本地同步？请依次排查三点——在电脑桌面端操作开启、确认操作系统与钉钉客户端已升级到最新版本、确认企业管理员已允许你使用本地同步功能。",
    },
    {
        'slug': 'cannot-open-files-locally',
        'group_en': 'FAQ', 'group_zh': 'FAQ',
        'en_source': "Can't Open Files Locally_.adoc.md",
        'en_title': "Can't Open Files Locally?",
        'zh_source': '为什么文件无法在本地打开？.adoc.md',
        'zh_title': '为什么文件无法在本地打开？',
        'en_desc': "Without download permission, a file can't sync to your local folder or open locally. Common causes: you lack view/download permission, the file has leak protection enabled, or your administrator restricts local downloads for certain files.",
        'zh_desc': "若没有下载权限，文件无法同步到本地文件夹或在本地打开。常见原因：你不具备可查看/下载及以上权限、文件或上级文件夹开启了防泄漏保护、或企业管理员限制了部分文件在本地下载。",
    },
]


def clean_invisible(text: str) -> str:
    def repl(m: re.Match) -> str:
        return ' ' if m.group(0) == '\xa0' else ''
    return INVISIBLE_CHARS_RE.sub(repl, text)


def strip_leading_hr(text: str) -> str:
    return LEADING_HR_RE.sub('', text, count=1)


def strip_duplicate_leading_title(body: str, title: str) -> str:
    """parse_frontmatter_data 抽走 line-1 H1 后，若 body 首个标题行文本与 title 相同则一并剥。

    钉钉文档部分英文篇 line-1 与 line-3 是完全相同的 H1（如 Can't Open Files Locally?），
    抽 line-1 后 line-3 变成正文里孤立重复的一级标题，需删掉。
    """
    lines = body.lstrip('\n').split('\n')
    if not lines:
        return body
    first = lines[0].strip()
    m = re.match(r'^#{1,6}\s+(.*?)\s*$', first)
    if m and m.group(1).strip() == title.strip():
        return '\n'.join(lines[1:]).lstrip('\n')
    return body


def process_one(source: Path, slug: str, title: str, description: str) -> dict:
    raw = source.read_text(encoding='utf-8')
    nbsp_count = raw.count('\xa0')

    cleaned = clean_invisible(raw)
    _parsed_title, _orig_desc, body = parse_frontmatter_data(cleaned, source.stem)
    body = strip_leading_hr(body)
    body = strip_duplicate_leading_title(body, title)

    escaped = escape_mdx(body)
    mdx = (
        f'---\n'
        f'title: {yaml_escape(title)}\n'
        f'description: {yaml_escape(description)}\n'
        f'---\n\n'
        f'{escaped.rstrip()}\n'
    )
    return {
        'slug': slug,
        'title': title,
        'description': description,
        'mdx': mdx,
        'source': str(source),
        'nbsp_before': nbsp_count,
        'nbsp_after': mdx.count('\xa0'),
        'mdx_size': len(mdx),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Drive 本地同步 4 主题双语增量入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE))
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        print(f'❌ 源目录不存在: {source_dir}', file=sys.stderr)
        return 1

    print(f'源:     {source_dir}')
    print(f'目标 en: {DRIVE_EN_DIR}')
    print(f'目标 zh: {DRIVE_ZH_DIR}')
    print(f'dry-run: {args.dry_run}')
    print('=' * 70)

    if not args.dry_run:
        DRIVE_EN_DIR.mkdir(exist_ok=True)
        DRIVE_ZH_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    missing: list[str] = []
    residual_nbsp = 0

    for item in ITEMS:
        slug = item['slug']
        for lang, dir_, src_name, title, desc in [
            ('en', DRIVE_EN_DIR, item['en_source'], item['en_title'], item['en_desc']),
            ('zh', DRIVE_ZH_DIR, item['zh_source'], item['zh_title'], item['zh_desc']),
        ]:
            src = source_dir / src_name
            if not src.exists():
                missing.append(f'{lang}:{src_name}')
                print(f'  [{lang}] {slug:<48} ❌ 未找到源 ({src_name})')
                continue
            info = process_one(src, slug, title, desc)
            residual_nbsp += info['nbsp_after']
            rows.append({'lang': lang, 'group': item[f'group_{lang}'], **info})
            print(f'  [{lang}] {slug:<48} ✓ {info["mdx_size"]} bytes (NBSP={info["nbsp_before"]})')
            if not args.dry_run:
                (dir_ / f'{slug}.mdx').write_text(info['mdx'], encoding='utf-8')

    print('\n' + '=' * 70)
    print(f'成功:          {len(rows)} / {len(ITEMS) * 2}')
    print(f'缺失:          {len(missing)}')
    print(f'mdx 残留 NBSP: {residual_nbsp} (应该 0)')

    if not args.dry_run:
        report = {
            'items': [
                {'slug': i['slug'], 'group_en': i['group_en'], 'group_zh': i['group_zh']}
                for i in ITEMS
            ],
            'rows': [
                {k: r[k] for k in ('lang', 'group', 'slug', 'title', 'mdx_size', 'nbsp_before')}
                for r in rows
            ],
        }
        (OUTPUT_DIR / 'report.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
        )
        print(f'\n产物: {OUTPUT_DIR}/report.json + {len(rows)} 个 mdx')

    return 1 if (missing or residual_nbsp) else 0


if __name__ == '__main__':
    sys.exit(main())
