#!/usr/bin/env python3
"""import_messages_zh.py — 把 ~/Downloads/<date>_DingTalk_Messages/*.adoc.md → zh/im/<slug>.mdx。

仿 import_ai_minutes_zh.py，差异：
- 输出到 zh/im/（与现有 en im/ 共享 slug 命名做三语 URL 镜像）
- tab 名 '消息'，group 名对齐 en im/ 5-group 划分的中文翻译
- 18 个 slug 与 en im/ 的 chats-* 一一对应；中文 hub 实抓 19 leaf，其中「分类目录」是纯导航树（仿 en README 角色）不入仓
- 中文 hub 是平铺单层（无父子嵌套），所有 source 都在源根目录

用法:
    python3 scripts/import_messages_zh.py                    # 默认源 ~/Downloads/2026-06-16_DingTalk_Messages
    python3 scripts/import_messages_zh.py --source <path>    # 自定义源
    python3 scripts/import_messages_zh.py --dry-run          # 只打印总结

产物:
  - zh/im/<slug>.mdx × 18
  - scripts/output/messages_zh/{nav-fragment.json, slug-map.json, report.md}
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

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-16_DingTalk_Messages'
IM_DIR = REPO_ROOT / 'zh' / 'im'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'messages_zh'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
LEADING_H1_RE = re.compile(r'\A# (.+?)\n')
ADMONITION_MARKER_RE = re.compile(r'^:::\s*$', re.MULTILINE)
# body 末尾钉钉文档自动加的 "返回「[**<Group>**](alidocs)」目录" 段（含前置 --- 横线）
# messages 是平铺 hub 无母文档语义，理论上不命中；保留正则避免源里偶尔出现的母文档外链
TRAILING_BACK_TO_RE = re.compile(
    r'\n+---\s*\n+返回[「『]?\[\*\*[^\]]+\*\*\]\(https://alidocs\.dingtalk\.com[^)]+\)[」』]?\s*目录\s*\Z'
)
# 钉钉文档外链 → 仓库内链映射（按 dentry UUID 匹配）
# 实测填充：扫源里 alidocs.dingtalk.com 链接，能映射到本批 19 篇内的填进来
ALIDOCS_INTERNAL_LINK_MAP: dict[str, str] = {}
ALIDOCS_LINK_RE = re.compile(
    r'\(https://alidocs\.dingtalk\.com/i/(?:nodes|p/[^/]+/docs)/([A-Za-z0-9_]+)(?:\?[^)]*)?\)'
)
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')
# list 行前缀（有序 `1.` / `1)` / 无序 `-` `*` `+`）；让 description 跳过 list-heavy 文档的列表首项
MD_LIST_PREFIX_RE = re.compile(r'^\s*(?:\d+[.)]|[-*+])\s+')

# overview slug title 强制覆盖（避免与所在 group 同名等场景）
# chats-overview 中文源标题「即时通讯快速入门」已是独立短语，与 group「开始使用」不撞，无需 override
TITLE_OVERRIDES: dict[str, str] = {}

# frontmatter description 手写覆盖：让 mintlify 副标题是「全页 AI 总结」而非 body 首段截断。
# 长度 < 200 chars，覆盖各页 H2 章节范围。下载完后实测每篇 body 首段是否够干净，按需补 override。
# 先全留空 → dry-run 后看哪些 description 截断不雅再补。
DESCRIPTION_OVERRIDES: dict[str, str] = {}

# 19 篇 → 5 group（对齐 en im/ 的 5-group 划分，按业务相关性排序）
# 三元组: (slug, source_basename, expected_title)
# - slug 优先复用 en im/ 的 chats-* 命名做三语 URL 镜像（18/19 一一对应）
# - 多出的「分类目录」走 chats-categories slug（en 暂无对应篇）
# - source_basename 相对源根目录，全部平铺无嵌套
# - expected_title 用钉钉源 H1 字面值，避免误报 title_mismatch
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('开始使用', [
        ('chats-overview',
         '即时通讯快速入门.adoc.md',
         '即时通讯快速入门'),
    ]),
    ('发送和接收消息', [
        ('chats-direct-message',
         '发起单聊.adoc.md',
         '发起单聊'),
        ('chats-send-message',
         '发送和编辑消息.adoc.md',
         '发送和编辑消息'),
        ('chats-text-formatting',
         '设置消息文本格式.adoc.md',
         '设置消息文本格式'),
        ('chats-rich-messages',
         '发送文件和使用输入框快捷功能.adoc.md',
         '发送文件和使用输入框快捷功能'),
        ('chats-start-video-conference',
         '从聊天中发起视频会议.adoc.md',
         '从聊天中发起视频会议'),
    ]),
    ('会话管理', [
        ('chats-search',
         '搜索聊天记录.adoc.md',
         '搜索聊天记录'),
        ('chats-message-actions',
         '使用消息和会话操作.adoc.md',
         '使用消息和会话操作'),
        ('chats-organize',
         '管理会话列表.adoc.md',
         '管理会话列表'),
        ('chats-notifications',
         '管理消息通知.adoc.md',
         '管理消息通知'),
        ('chats-service-conversation-settings',
         '管理服务会话设置.adoc.md',
         '管理服务会话设置'),
    ]),
    ('群聊', [
        ('chats-group-chat',
         '创建和管理群聊.adoc.md',
         '创建和管理群聊'),
        ('chats-group-management',
         '管理群成员和权限.adoc.md',
         '管理群成员和权限'),
        ('chats-group-settings',
         '配置群设置.adoc.md',
         '配置群设置'),
        ('chats-group-advanced-management',
         '打开高级群管理设置.adoc.md',
         '打开高级群管理设置'),
        ('chats-group-announcement',
         '查看群公告.adoc.md',
         '查看群公告'),
        ('chats-mentions',
         '管理 @所有人 权限.adoc.md',
         '管理 @所有人 权限'),
    ]),
    ('常见问题', [
        ('chats-faq',
         '即时通讯常见问题.adoc.md',
         '即时通讯常见问题'),
    ]),
]


def clean_invisible(text: str) -> str:
    def repl(m: re.Match) -> str:
        return ' ' if m.group(0) == '\xa0' else ''
    return INVISIBLE_CHARS_RE.sub(repl, text)


def strip_dup_leading_h1(body: str, parsed_title: str) -> str:
    m = LEADING_H1_RE.match(body)
    if m and m.group(1).strip() == parsed_title.strip():
        return body[m.end():].lstrip()
    return body


def strip_admonition_markers(body: str) -> str:
    return ADMONITION_MARKER_RE.sub('', body)


def strip_trailing_back_to(body: str) -> str:
    """剥 body 末尾钉钉文档自动加的 '返回「[**<Group>**](alidocs)」目录' 段（含前置 --- 横线）。"""
    return TRAILING_BACK_TO_RE.sub('', body)


def rewrite_alidocs_links(body: str) -> str:
    """钉钉文档外链按 UUID → 仓库内链替换（仅 ALIDOCS_INTERNAL_LINK_MAP 命中的 UUID）。"""
    def repl(m: re.Match) -> str:
        uuid = m.group(1)
        if uuid in ALIDOCS_INTERNAL_LINK_MAP:
            return f'({ALIDOCS_INTERNAL_LINK_MAP[uuid]})'
        return m.group(0)
    return ALIDOCS_LINK_RE.sub(repl, body)


def demote_body_h1(body: str) -> str:
    """正文 H1 → H2（mintlify 把 frontmatter.title 视为唯一 H1）。跳过代码块。"""
    lines = body.split('\n')
    in_code = False
    for i, l in enumerate(lines):
        if l.startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            continue
        if re.match(r'^# .+', l):
            lines[i] = '#' + l
    return '\n'.join(lines)


def extract_clean_description(body: str, fallback: str) -> str:
    text = MD_INLINE_IMAGE_RE.sub(' ', body)
    for raw_line in text.splitlines():
        s = raw_line.strip()
        if not s or s.startswith('#') or s.startswith('!['):
            continue
        if MD_LIST_PREFIX_RE.match(raw_line):
            continue
        # 跳过 markdown 表格行（行首 `|` 或全是 `---|---`）
        if s.startswith('|') or set(s) <= set('-| :'):
            continue
        s = MD_INLINE_LINK_RE.sub(r'\1', s)
        s = MD_EMPHASIS_CHARS_RE.sub('', s)
        s = re.sub(r'\s+', ' ', s).strip()
        if s:
            return s[:160]
    return fallback


def find_source(source_dir: Path, basename: str) -> Path | None:
    candidate = source_dir / basename
    return candidate if candidate.exists() else None


def process_one(source: Path, expected_slug: str, expected_title: str) -> dict:
    raw = source.read_text(encoding='utf-8')
    nbsp_count = raw.count('\xa0')

    cleaned = clean_invisible(raw)
    parsed_title, _orig_desc, body = parse_frontmatter_data(cleaned, source.stem)
    body = strip_dup_leading_h1(body, parsed_title)
    body = strip_admonition_markers(body)
    body = strip_trailing_back_to(body)
    body = rewrite_alidocs_links(body)
    body = demote_body_h1(body)

    title = TITLE_OVERRIDES.get(expected_slug) or parsed_title or expected_title
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
        'title_mismatch': title != expected_title and expected_slug not in TITLE_OVERRIDES,
        'description': description,
        'mdx': mdx,
        'source': str(source),
        'nbsp_before': nbsp_count,
        'nbsp_after': residual_nbsp,
        'mdx_size': len(mdx),
    }


def build_nav_fragment() -> dict:
    return {
        'tab': '消息',
        'groups': [
            {
                'group': group_name,
                'pages': [f'zh/im/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Messages (DingTalk IM) ZH markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-06-16_DingTalk_Messages/)')
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
        IM_DIR.mkdir(parents=True, exist_ok=True)
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
        for slug, source_basename, expected_title in items:
            src = find_source(source_dir, source_basename)
            if not src:
                missing.append((slug, expected_title))
                print(f'  {slug:<42} ❌ 未找到源 (期望 {source_basename})')
                continue
            try:
                info = process_one(src, slug, expected_title)
            except Exception as e:
                print(f'  {slug:<42} ❌ {type(e).__name__}: {e}')
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
            print(f'  {slug:<42} {marker} {info["mdx_size"]} bytes (NBSP={info["nbsp_before"]})')

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
            '# Messages ZH Import Report\n',
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
