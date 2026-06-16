#!/usr/bin/env python3
"""import_im_en.py — 把 ~/Downloads/<date>_DingTalk_IM/*.adoc.md → im/<slug>.mdx。

仿 import_mail_en.py，差异：
- 源文件命名是 chats-<topic>.adoc.md（无编号前缀），slug = 文件 stem 去掉 .adoc
- 每篇 line 1 是 `# <filename>` 形态（kebab-case），需先剥；line 3 是真正 canonical H1
- README.adoc.md 是导航树，不入仓（GROUPS 即从 README 提取）

用法:
    python3 scripts/import_im_en.py                    # 默认源 ~/Downloads/2026-06-12_DingTalk_IM
    python3 scripts/import_im_en.py --source <path>    # 自定义源
    python3 scripts/import_im_en.py --dry-run          # 只打印总结

产物:
  - im/<slug>.mdx × 18
  - scripts/output/im_en/{nav-fragment.json, slug-map.json, report.md}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
from import_archive import escape_mdx, parse_frontmatter_data, yaml_escape  # noqa: E402

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-12_DingTalk_IM'
IM_DIR = REPO_ROOT / 'im'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'im_en'

# NBSP + 零宽空格族 + BOM
INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
# 行首 "# <kebab-case-slug-or-README>" 形态，只剥一次
LEADING_FILENAME_H1_RE = re.compile(r'\A\s*#\s+[A-Za-z0-9_-]+\s*\n+')
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')

# 18 篇 → 5 group（按 README.adoc.md 提取，README 本身不入仓）
GROUPS: list[tuple[str, list[tuple[str, str]]]] = [
    ('Getting Started', [
        ('chats-overview', 'Get Started with Messages'),
    ]),
    ('Send and Receive Messages', [
        ('chats-direct-message', 'Start a Direct Message'),
        ('chats-send-message', 'Send and Format Messages'),
        ('chats-text-formatting', 'Format Text in Messages'),
        ('chats-rich-messages', 'Send Files and Use Composer Shortcuts'),
        ('chats-start-video-conference', 'Start a Video Conference from Messages'),
    ]),
    ('Message Management', [
        ('chats-search', 'Search Chat Records'),
        ('chats-message-actions', 'Use Conversation List Actions'),
        ('chats-organize', 'Manage the Conversation List'),
        ('chats-notifications', 'Manage Message Notifications'),
        ('chats-service-conversation-settings', 'Manage Service Conversation Settings'),
    ]),
    ('Group Communication', [
        ('chats-group-chat', 'Create and Manage a Group Chat'),
        ('chats-group-management', 'Manage Group Members and Permissions'),
        ('chats-group-settings', 'Configure Group Chat Settings'),
        ('chats-group-advanced-management', 'Open Advanced Group Management Settings'),
        ('chats-group-announcement', 'View Group Notices'),
        ('chats-mentions', 'Manage @Everyone Permissions'),
    ]),
    ('FAQs', [
        ('chats-faq', 'Messages FAQ'),
    ]),
]


# frontmatter description 手写覆盖：让 mintlify 副标题是「全页 AI 总结」而非 body 首段 160 字符截断
# （多篇命中：chats-direct-message 末尾 "do not need" / chats-overview "past conversation" /
# chats-rich-messages "materials, c" / chats-service-conversation-settings "the service" 等被切在词中）
# 每条 < 200 chars（mintlify 副标题不截断的实用上限），覆盖该页主要 H2 章节范围
# 与 zh/im 同篇 DESCRIPTION_OVERRIDES 语义镜像；术语遵循 scripts/glossary/zh-en.json
DESCRIPTION_OVERRIDES: dict[str, str] = {
    'chats-overview': "Get started with Messages on desktop: open the conversation list, start direct messages or group chats, send formatted text and files, start video conferences, and search past chats.",
    'chats-direct-message': "Start a direct message with a contact on desktop, search within the conversation, manage notifications and pinning, and start a video conference directly from the chat.",
    'chats-send-message': "Send text messages with formatting, attach files or documents, send silently to avoid notifications, lock the message composer to prevent accidental sending, and use composer shortcuts.",
    'chats-text-formatting': "Open the text formatting toolbar in the message composer, apply bold, italic, lists, code blocks or quotes, send formatted messages, and follow tips for clean formatting.",
    'chats-rich-messages': "Send files and documents from a conversation, open the message composer shortcuts for quick actions, see shortcut examples, and browse all files shared in a chat.",
    'chats-start-video-conference': "Start a video conference from the message composer in a direct message, or from the group chat toolbar to bring multiple group members into the meeting.",
    'chats-search': "Search across all DingTalk content from the top search box, narrow the search to a specific conversation, browse files shared in a chat, and apply tips for better search results.",
    'chats-message-actions': "Open the message actions menu to reply, edit, recall, copy or forward a message, view edit history, and use conversation list actions to manage chats from the sidebar.",
    'chats-organize': "Organize the conversation list by pinning chats at the top, marking conversations as unread, muting notifications, hiding conversations, clearing local chat history, and choosing the right action.",
    'chats-notifications': "Manage message notifications by muting or unmuting conversations, marking as unread, opening notification settings, and following tips to balance focus with availability.",
    'chats-service-conversation-settings': "Manage service conversation settings: open the settings panel, mute notifications for service messages, and keep important service conversations at the top of the conversation list.",
    'chats-group-chat': "Create a group chat with multiple contacts, add members directly or via Group Settings, open the Group Settings panel, manage group permissions, and leave a group.",
    'chats-group-management': "View and add group members, appoint group admins, configure group permissions, manage how people join the group, clear messages, and quit a group when no longer needed.",
    'chats-group-settings': "Configure group chat settings: view group information, adjust personal preferences such as nickname and notifications, open Group Management for advanced controls, clear messages, or quit the group.",
    'chats-group-advanced-management': "Open Group Management for advanced group controls, explore the available advanced settings, and configure granular group permission settings.",
    'chats-group-announcement': "Open group notices to view announcements pinned by admins, learn when to send a notice for a group, and configure related notification settings.",
    'chats-mentions': "Manage @Everyone permissions in a group: change who can use @Everyone, understand what changes for members, and adjust related notification settings.",
    'chats-faq': "Common questions about Messages, Group Settings, message notifications, and search — including how to start chats, manage groups, mute conversations, and find shared files.",
}


def clean_invisible(text: str) -> str:
    def repl(m: re.Match) -> str:
        return ' ' if m.group(0) == '\xa0' else ''
    return INVISIBLE_CHARS_RE.sub(repl, text)


def strip_leading_filename_h1(text: str) -> str:
    return LEADING_FILENAME_H1_RE.sub('', text, count=1)


def extract_clean_description(body: str, fallback: str) -> str:
    text = MD_INLINE_IMAGE_RE.sub(' ', body)
    for raw_line in text.splitlines():
        s = raw_line.strip()
        if not s or s.startswith('#') or s.startswith('!['):
            continue
        s = MD_INLINE_LINK_RE.sub(r'\1', s)
        s = MD_EMPHASIS_CHARS_RE.sub('', s)
        s = re.sub(r'\s+', ' ', s).strip()
        if s:
            return s[:160]
    return fallback


def find_source(source_dir: Path, slug: str) -> Path | None:
    candidate = source_dir / f'{slug}.adoc.md'
    return candidate if candidate.exists() else None


def process_one(source: Path, expected_slug: str, expected_title: str) -> dict:
    raw = source.read_text(encoding='utf-8')
    nbsp_count = raw.count('\xa0')

    cleaned = clean_invisible(raw)
    body_with_canonical_h1 = strip_leading_filename_h1(cleaned)

    parsed_title, _orig_desc, body = parse_frontmatter_data(body_with_canonical_h1, source.stem)
    title = parsed_title or expected_title
    description = DESCRIPTION_OVERRIDES.get(expected_slug) or extract_clean_description(body, fallback=title)

    escaped = escape_mdx(body)
    mdx = (
        f'---\n'
        f'title: {yaml_escape(title)}\n'
        f'description: {yaml_escape(description)}\n'
        f'---\n\n'
        f'{escaped.rstrip()}\n'
    )

    residual_nbsp = mdx.count('\xa0')

    return {
        'slug': expected_slug,
        'expected_title': expected_title,
        'actual_title': title,
        'title_mismatch': title != expected_title,
        'description': description,
        'mdx': mdx,
        'source': str(source),
        'nbsp_before': nbsp_count,
        'nbsp_after': residual_nbsp,
        'mdx_size': len(mdx),
    }


def build_nav_fragment() -> dict:
    return {
        'tab': 'IM',
        'groups': [
            {
                'group': group_name,
                'pages': [f'im/{slug}' for (slug, _) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='IM EN markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-06-12_DingTalk_IM/)')
    ap.add_argument('--dry-run', action='store_true', help='不写文件，只打印总结')
    args = ap.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        print(f'❌ 源目录不存在: {source_dir}', file=sys.stderr)
        return 1

    print(f'源: {source_dir}')
    print(f'目标: {IM_DIR}')
    print(f'dry-run: {args.dry_run}')
    print('=' * 70)

    if not args.dry_run:
        IM_DIR.mkdir(exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    slug_map: dict[str, dict] = {}
    report_rows: list[dict] = []
    total_nbsp = 0
    total_residual_nbsp = 0
    missing: list[tuple[str, str]] = []
    title_mismatches: list[dict] = []
    expected_total = sum(len(items) for _, items in GROUPS)

    for group_name, items in GROUPS:
        print(f'\n[{group_name}]')
        for slug, expected_title in items:
            src = find_source(source_dir, slug)
            if not src:
                missing.append((slug, expected_title))
                print(f'  {slug:<58} ❌ 未找到源 (期望 {slug}.adoc.md)')
                continue
            try:
                info = process_one(src, slug, expected_title)
            except Exception as e:
                print(f'  {slug:<58} ❌ {type(e).__name__}: {e}')
                continue

            slug_map[slug] = {
                'group': group_name,
                'title': info['actual_title'],
                'expected_title': expected_title,
                'source': info['source'],
            }
            total_nbsp += info['nbsp_before']
            total_residual_nbsp += info['nbsp_after']
            if info['title_mismatch']:
                title_mismatches.append({
                    'slug': slug,
                    'expected': expected_title,
                    'actual': info['actual_title'],
                })
            report_rows.append({
                'group': group_name, 'slug': slug, 'title': info['actual_title'],
                'desc_len': len(info['description']), 'nbsp_cleaned': info['nbsp_before'],
                'mdx_size': info['mdx_size'],
            })
            marker = '✓' if not info['title_mismatch'] else '⚠️'
            print(f'  {slug:<58} {marker} {info["mdx_size"]} bytes (NBSP={info["nbsp_before"]})')

            if not args.dry_run:
                target = IM_DIR / f'{slug}.mdx'
                target.write_text(info['mdx'], encoding='utf-8')

    print('\n' + '=' * 70)
    print(f'成功:           {len(report_rows)} / {expected_total}')
    print(f'缺失:           {len(missing)}')
    print(f'title 不一致:   {len(title_mismatches)} (用 H1 解析值落地)')
    print(f'NBSP 清洗总数:  {total_nbsp}')
    print(f'mdx 残留 NBSP:  {total_residual_nbsp} (应该 0)')
    if missing:
        print('\n缺失列表:')
        for s, t in missing:
            print(f'  - {s}: {t}')
    if title_mismatches:
        print('\ntitle 不一致（用 H1 解析值落地）：')
        for m in title_mismatches:
            print(f'  - {m["slug"]}: expected={m["expected"]!r} vs actual={m["actual"]!r}')

    if not args.dry_run:
        nav_fragment = build_nav_fragment()
        (OUTPUT_DIR / 'nav-fragment.json').write_text(
            json.dumps(nav_fragment, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
        )
        (OUTPUT_DIR / 'slug-map.json').write_text(
            json.dumps(slug_map, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
        )
        lines = [
            '# IM EN Import Report\n',
            f'- 成功: **{len(report_rows)} / {expected_total}**',
            f'- 缺失: {len(missing)}',
            f'- title 不一致: {len(title_mismatches)}',
            f'- NBSP 清洗: {total_nbsp}（mdx 残留 {total_residual_nbsp}）',
            '',
            '## 全表',
            '| group | slug | title | desc_len | nbsp_cleaned | size |',
            '|---|---|---|---|---|---|',
        ]
        for r in report_rows:
            lines.append(f'| {r["group"]} | `{r["slug"]}` | {r["title"]} | {r["desc_len"]} | {r["nbsp_cleaned"]} | {r["mdx_size"]} |')
        if title_mismatches:
            lines.append('\n## title 不一致（用 H1 解析值落地）')
            for m in title_mismatches:
                lines.append(f'- `{m["slug"]}`: expected `{m["expected"]}` ≠ actual `{m["actual"]}`')
        (OUTPUT_DIR / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

        print(f'\n产物:')
        print(f'  mdx:               {IM_DIR}/*.mdx ({len(report_rows)} 个)')
        print(f'  nav-fragment.json: {OUTPUT_DIR}/nav-fragment.json')
        print(f'  slug-map.json:     {OUTPUT_DIR}/slug-map.json')
        print(f'  report.md:         {OUTPUT_DIR}/report.md')

    if missing or total_residual_nbsp > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
