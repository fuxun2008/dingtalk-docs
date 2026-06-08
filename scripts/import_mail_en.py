#!/usr/bin/env python3
"""import_mail_en.py — 把 ~/Downloads/<date>_DingTalk_Mail/*.md → mail/<slug>.mdx。

一次性脚本：EN 源 → EN tab。不动 zh/ja。

用法:
    python3 scripts/import_mail_en.py                          # 默认源 ~/Downloads/2026-06-07_DingTalk_Mail/
    python3 scripts/import_mail_en.py --source <path>          # 自定义源
    python3 scripts/import_mail_en.py --dry-run                # 只打印总结，不写文件

清洗管道（每篇）：
  1. 不可见字符：NBSP (U+00A0) → 普通空格；零宽空格 / BOM 去掉
  2. 剥 line 1 编号 H1 (`# 01 - <Title>`)（钉钉导出多余的）
  3. 调 import_archive.parse_frontmatter_data 抽 canonical title + description
  4. description 空时 fallback 到 title（FAQ 类文档触发）
  5. body 跑 escape_mdx（{ } / 未知 tag 转义）
  6. 拼 frontmatter + body → mail/<slug>.mdx

产物：
  - mail/<slug>.mdx × 24（按 GROUPS 表）
  - scripts/output/mail_en/{nav-fragment.json, slug-map.json, report.md}
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

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-07_DingTalk_Mail'
MAIL_DIR = REPO_ROOT / 'mail'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'mail_en'

# 不可见字符：NBSP + 零宽 + BOM
INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
# 行首 "# 01 - <whatever>"，只剥一次
LEADING_NUMBERED_H1_RE = re.compile(r'\A\s*#\s+\d+\s*-\s*[^\n]+\n+')
# 行内 markdown image（`![alt](url)`）—— 抽 description 时整段剥成空格，避免 alt text 残留
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')

# 24 篇 → 6 group 映射（顺序 = docs.json pages[] 顺序 = 左侧导航顺序）
GROUPS: list[tuple[str, list[tuple[int, str]]]] = [
    ('Getting Started', [
        (1, 'dingtalk-enterprise-mail'),
        (2, 'customer-story-xinfengwei'),
        (3, 'what-is-dingtalk-mail'),
    ]),
    ('Email Basics', [
        (4, 'send-an-email'),
        (5, 'move-or-delete-emails'),
        (6, 'reply-to-or-forward-emails'),
        (7, 'download-an-email'),
        (8, 'quickly-discuss-an-email'),
    ]),
    ('Settings', [
        (9, 'set-up-automatic-email-replies'),
        (10, 'add-labels-to-emails'),
        (11, 'forward-an-email-to-chat-with-one-click'),
        (12, 'set-up-new-email-notifications'),
        (13, 'create-a-mail-calendar-event'),
        (14, 'export-a-mail-calendar'),
    ]),
    ('Contacts', [
        (15, 'add-contacts'),
        (16, 'create-a-contact-group'),
        (17, 'import-or-export-contacts'),
    ]),
    ('Advanced', [
        (18, 'set-up-automatic-email-forwarding'),
        (19, 'set-up-mail-allowlist-and-blocklist'),
        (20, 'receive-emails-from-other-mailboxes'),
        (21, 'disable-group-members-from-sending-emails-to-a-group'),
    ]),
    ('Enterprise Mail & FAQ', [
        (22, 'activate-alibaba-enterprise-mail'),
        (23, 'link-an-existing-alibaba-cloud-mailbox'),
        (24, 'dingtalk-mail-faq'),
    ]),
]


def clean_invisible(text: str) -> str:
    """NBSP → 普通空格；零宽 / BOM → 去掉。"""
    def repl(m: re.Match) -> str:
        return ' ' if m.group(0) == '\xa0' else ''
    return INVISIBLE_CHARS_RE.sub(repl, text)


def strip_leading_numbered_h1(text: str) -> str:
    """删 line 1 的 '# 01 - <Title>\\n\\n'，无则 noop。"""
    return LEADING_NUMBERED_H1_RE.sub('', text, count=1)


def extract_clean_description(body: str, fallback: str) -> str:
    """从 body 第一非空非 heading 段抽 description，预先剥 markdown inline image / link / emphasis。

    比 import_archive.parse_frontmatter_data 自带的 description 逻辑多两步：
    1. inline image `![alt](url)` 整体替换为空格（避免 alt 残留，如 "the!image.pngicon"）
    2. 折叠连续空格

    无可用文本时返回 fallback (通常是 title)。
    """
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


def slugify(title: str) -> str:
    """title → kebab-case slug。"""
    s = title.lower()
    s = re.sub(r'[^a-z0-9]+', '-', s)
    return s.strip('-')


def find_source(source_dir: Path, number: int) -> Path | None:
    """按编号匹配源文件 '<NN> - <whatever>.adoc.md'。"""
    prefix = f'{number:02d} - '
    matches = list(source_dir.glob(f'{prefix}*.adoc.md'))
    return matches[0] if matches else None


def process_one(source: Path, expected_slug: str) -> dict:
    """单文件清洗 → mdx 内容 + 元信息。"""
    raw = source.read_text(encoding='utf-8')
    nbsp_count = raw.count('\xa0')

    cleaned = clean_invisible(raw)
    body_with_canonical_h1 = strip_leading_numbered_h1(cleaned)

    title, _orig_desc, body = parse_frontmatter_data(body_with_canonical_h1, source.stem)
    # 复用 parse_frontmatter_data 的 title + body（H1 已剥），description 用自己的清洁版抽取
    description = extract_clean_description(body, fallback=title)

    actual_slug = slugify(title)
    slug_mismatch = actual_slug != expected_slug

    escaped = escape_mdx(body)
    mdx = (
        f'---\n'
        f'title: {yaml_escape(title)}\n'
        f'description: {yaml_escape(description)}\n'
        f'---\n\n'
        f'{escaped.rstrip()}\n'
    )

    # 兜底校验：mdx 里不应再有 NBSP
    residual_nbsp = mdx.count('\xa0')

    return {
        'slug': expected_slug,
        'actual_slug': actual_slug,
        'slug_mismatch': slug_mismatch,
        'title': title,
        'description': description,
        'mdx': mdx,
        'source': str(source),
        'nbsp_before': nbsp_count,
        'nbsp_after': residual_nbsp,
        'mdx_size': len(mdx),
    }


def build_nav_fragment() -> dict:
    return {
        'tab': 'Mail',
        'groups': [
            {
                'group': group_name,
                'pages': [f'mail/{slug}' for (_, slug) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Mail EN markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE), help='源目录 (默认 ~/Downloads/2026-06-07_DingTalk_Mail/)')
    ap.add_argument('--dry-run', action='store_true', help='不写文件，只打印总结')
    args = ap.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        print(f'❌ 源目录不存在: {source_dir}', file=sys.stderr)
        return 1

    print(f'源: {source_dir}')
    print(f'目标: {MAIL_DIR}')
    print(f'dry-run: {args.dry_run}')
    print('=' * 70)

    if not args.dry_run:
        MAIL_DIR.mkdir(exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    slug_map: dict[str, dict] = {}
    report_rows: list[dict] = []
    total_nbsp = 0
    total_residual_nbsp = 0
    missing: list[tuple[int, str]] = []
    mismatches: list[dict] = []

    for group_name, items in GROUPS:
        print(f'\n[{group_name}]')
        for number, slug in items:
            src = find_source(source_dir, number)
            if not src:
                missing.append((number, slug))
                print(f'  {number:02d} {slug:<58} ❌ 未找到源 (期望 prefix "{number:02d} - ")')
                continue
            try:
                info = process_one(src, slug)
            except Exception as e:
                print(f'  {number:02d} {slug:<58} ❌ {type(e).__name__}: {e}')
                continue

            slug_map[slug] = {
                'number': number,
                'group': group_name,
                'title': info['title'],
                'source': info['source'],
            }
            total_nbsp += info['nbsp_before']
            total_residual_nbsp += info['nbsp_after']
            if info['slug_mismatch']:
                mismatches.append({'number': number, 'expected': slug, 'derived': info['actual_slug'], 'title': info['title']})
            report_rows.append({
                'number': number, 'group': group_name, 'slug': slug, 'title': info['title'],
                'desc_len': len(info['description']), 'nbsp_cleaned': info['nbsp_before'],
                'mdx_size': info['mdx_size'],
            })
            marker = '✓' if not info['slug_mismatch'] else '⚠️'
            print(f'  {number:02d} {slug:<58} {marker} {info["mdx_size"]} bytes (NBSP={info["nbsp_before"]})')

            if not args.dry_run:
                target = MAIL_DIR / f'{slug}.mdx'
                target.write_text(info['mdx'], encoding='utf-8')

    print('\n' + '=' * 70)
    print(f'成功:           {len(report_rows)} / 24')
    print(f'缺失:           {len(missing)}')
    print(f'slug 不匹配:    {len(mismatches)} (用 expected_slug 落地，info 列在 report)')
    print(f'NBSP 清洗总数:  {total_nbsp}')
    print(f'mdx 残留 NBSP:  {total_residual_nbsp} (应该 0)')
    if missing:
        print('\n缺失列表:')
        for n, s in missing:
            print(f'  - {n:02d} {s}')
    if mismatches:
        print('\nslug 不匹配（用 expected 落地）：')
        for m in mismatches:
            print(f'  - {m["number"]:02d} expected={m["expected"]!r} vs derived={m["derived"]!r} (title={m["title"]!r})')

    if not args.dry_run:
        nav_fragment = build_nav_fragment()
        (OUTPUT_DIR / 'nav-fragment.json').write_text(
            json.dumps(nav_fragment, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
        )
        (OUTPUT_DIR / 'slug-map.json').write_text(
            json.dumps(slug_map, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
        )
        lines = [
            '# Mail EN Import Report\n',
            f'- 成功: **{len(report_rows)} / 24**',
            f'- 缺失: {len(missing)}',
            f'- slug 不匹配: {len(mismatches)}',
            f'- NBSP 清洗: {total_nbsp}（mdx 残留 {total_residual_nbsp}）',
            '',
            '## 全表',
            '| # | group | slug | title | desc_len | nbsp_cleaned | size |',
            '|---|---|---|---|---|---|---|',
        ]
        for r in report_rows:
            lines.append(f'| {r["number"]:02d} | {r["group"]} | `{r["slug"]}` | {r["title"]} | {r["desc_len"]} | {r["nbsp_cleaned"]} | {r["mdx_size"]} |')
        if mismatches:
            lines.append('\n## slug 不匹配（用 expected 落地）')
            for m in mismatches:
                lines.append(f'- `{m["number"]:02d}` expected `{m["expected"]}` ≠ derived `{m["derived"]}` (title: {m["title"]})')
        (OUTPUT_DIR / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

        print(f'\n产物:')
        print(f'  mdx:               {MAIL_DIR}/*.mdx ({len(report_rows)} 个)')
        print(f'  nav-fragment.json: {OUTPUT_DIR}/nav-fragment.json')
        print(f'  slug-map.json:     {OUTPUT_DIR}/slug-map.json')
        print(f'  report.md:         {OUTPUT_DIR}/report.md')

    if missing or total_residual_nbsp > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
