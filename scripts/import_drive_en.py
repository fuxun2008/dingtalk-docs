#!/usr/bin/env python3
"""import_drive_en.py — 把 ~/Downloads/<date>_DingTalk_Drive/*.adoc.md → drive/<slug>.mdx。

仿 import_im_en.py / import_mail_en.py，差异：
- 源文件名是 Title Case + 空格 + 标点（如 `What Is DingTalk Drive?.adoc.md`），与 slug 完全脱钩
  → GROUPS 升三元组 (slug, source_basename, expected_title)，find_source 直接按 source_basename 拼路径
- 每篇 line 1 是 `# <Title>` canonical 形态（parse_frontmatter_data 自动抽 + 剥）
  + line 3 是 `---` 分隔线（body 开头残留，需手工剥避免 mdx 误判第二个 frontmatter 块）
- 24 篇 / 4 group（按钉钉文档 hub 真实层级：3 顶层 + Employee User Guide 14（1 overview + 13 子）+ Administrator Guide 5（1 overview + 4 子）+ FAQ 2（1 overview + 1 子））
- 嵌套源路径支持：source_basename 字段可含 `/`（如 `Employee User Guide.adoc/How to Upload Files or Folders.adoc.md`），Path / 操作符天然处理

用法:
    python3 scripts/import_drive_en.py                    # 默认源 ~/Downloads/2026-06-15_DingTalk_Drive
    python3 scripts/import_drive_en.py --source <path>    # 自定义源
    python3 scripts/import_drive_en.py --dry-run          # 只打印总结

产物:
  - drive/<slug>.mdx × 24
  - scripts/output/drive_en/{nav-fragment.json, slug-map.json, report.md}
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

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-15_DingTalk_Drive'
DRIVE_DIR = REPO_ROOT / 'drive'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'drive_en'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
# body 开头残留的 "---" 分隔线（parse_frontmatter_data 剥 H1 后暴露出来）
LEADING_HR_RE = re.compile(r'\A---\s*\n+')
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')

# 24 篇 → 4 group（按钉钉文档 hub 真实层级：3 顶层 + 3 个 file+hasChildren=True 父级各带子文档）
# 三元组: (slug, source_basename, expected_title)
# source_basename 支持嵌套路径形式 '<Parent>.adoc/<Child>.adoc.md'，find_source 用 Path / 拼即可
# overview（父级文档自身）作为 group 第一个 page，对应钉钉文档 hub 折叠菜单的目录文档行为
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('Getting Started', [
        ('what-is-dingtalk-drive',
         'What Is DingTalk Drive_.adoc.md',
         'What Is DingTalk Drive?'),
        ('how-to-access-dingtalk-drive',
         'How to Access DingTalk Drive.adoc.md',
         'How to Access DingTalk Drive'),
        ('dingtalk-drive-home-page-features',
         'What Features Are Available on the DingTalk Drive Home Page_.adoc.md',
         'What Features Are Available on the DingTalk Drive Home Page?'),
    ]),
    ('Employee User Guide', [
        ('employee-user-guide',
         'Employee User Guide.adoc.md',
         'Employee User Guide'),
        ('how-to-upload-files-or-folders',
         'Employee User Guide.adoc/How to Upload Files or Folders.adoc.md',
         'How to Upload Files or Folders'),
        ('how-to-save-chat-files-to-dingtalk-drive',
         'Employee User Guide.adoc/How to Save Chat Files to DingTalk Drive.adoc.md',
         'How to Save Chat Files to DingTalk Drive'),
        ('how-to-create-files-or-folders',
         'Employee User Guide.adoc/How to Create Files or Folders.adoc.md',
         'How to Create Files or Folders'),
        ('how-to-set-or-change-member-permissions',
         'Employee User Guide.adoc/How to Set or Change Member Permissions.adoc.md',
         'How to Set or Change Member Permissions'),
        ('how-to-edit-files-in-dingtalk-drive',
         'Employee User Guide.adoc/How to Edit Files in DingTalk Drive.adoc.md',
         'How to Edit Files in DingTalk Drive'),
        ('how-to-share-files-with-external-people',
         'Employee User Guide.adoc/How to Share Files with External People.adoc.md',
         'How to Share Files with External People'),
        ('how-to-cancel-or-leave-a-shared-folder',
         'Employee User Guide.adoc/How to Cancel or Leave a Shared Folder.adoc.md',
         'How to Cancel or Leave a Shared Folder'),
        ('how-to-quickly-search-for-files-or-folders',
         'Employee User Guide.adoc/How to Quickly Search for Files or Folders.adoc.md',
         'How to Quickly Search for Files or Folders'),
        ('how-to-quickly-find-files-or-folders-in-chats',
         'Employee User Guide.adoc/How to Quickly Find Files or Folders in Chats.adoc.md',
         'How to Quickly Find Files or Folders in Chats'),
        ('how-to-batch-download-move-or-delete-files',
         'Employee User Guide.adoc/How to Batch Download, Move, or Delete DingTalk Drive Files.adoc.md',
         'How to Batch Download, Move, or Delete DingTalk Drive Files'),
        ('how-to-delete-and-recover-files',
         'Employee User Guide.adoc/How to Delete Files and Recover Deleted Files.adoc.md',
         'How to Delete Files and Recover Deleted Files'),
        ('how-to-use-file-picker',
         'Employee User Guide.adoc/How to Use the DingTalk Drive File Picker to Send Files Efficiently.adoc.md',
         'How to Use the DingTalk Drive File Picker to Send Files Efficiently'),
        ('how-to-quickly-find-target-folder',
         'Employee User Guide.adoc/How to Quickly Find the Target Folder.adoc.md',
         'How to Quickly Find the Target Folder'),
    ]),
    ('Administrator Guide', [
        ('administrator-guide',
         'Administrator Guide.adoc.md',
         'Administrator Guide'),
        ('how-to-view-enterprise-storage-space',
         'Administrator Guide.adoc/How to View Enterprise Storage Space.adoc.md',
         'How to View Enterprise Storage Space'),
        ('how-to-manage-enterprise-storage-capacity',
         'Administrator Guide.adoc/How to Manage Enterprise Storage Capacity.adoc.md',
         'How to Manage Enterprise Storage Capacity'),
        ('how-to-configure-capacity-management-by-role',
         'Administrator Guide.adoc/How to Configure Capacity Management by Role in DingTalk Drive.adoc.md',
         'How to Configure Capacity Management by Role in DingTalk Drive'),
        ('how-to-allocate-dedicated-capacity-to-an-app',
         'Administrator Guide.adoc/How to Allocate Dedicated Capacity to an App.adoc.md',
         'How to Allocate Dedicated Capacity to an App'),
    ]),
    ('FAQ', [
        ('faq',
         'FAQ.adoc.md',
         'FAQ'),
        ('dingtalk-drive-qa',
         'FAQ.adoc/DingTalk Drive Q&A.adoc.md',
         'DingTalk Drive Q&A'),
    ]),
]


def clean_invisible(text: str) -> str:
    def repl(m: re.Match) -> str:
        return ' ' if m.group(0) == '\xa0' else ''
    return INVISIBLE_CHARS_RE.sub(repl, text)


def strip_leading_hr(text: str) -> str:
    return LEADING_HR_RE.sub('', text, count=1)


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


def find_source(source_dir: Path, basename: str) -> Path | None:
    candidate = source_dir / basename
    return candidate if candidate.exists() else None


def process_one(source: Path, expected_slug: str, expected_title: str) -> dict:
    raw = source.read_text(encoding='utf-8')
    nbsp_count = raw.count('\xa0')

    cleaned = clean_invisible(raw)
    parsed_title, _orig_desc, body = parse_frontmatter_data(cleaned, source.stem)
    body = strip_leading_hr(body)
    title = parsed_title or expected_title
    description = extract_clean_description(body, fallback=title)

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
        'tab': 'Drive',
        'groups': [
            {
                'group': group_name,
                'pages': [f'drive/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Drive EN markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-06-15_DingTalk_Drive/)')
    ap.add_argument('--dry-run', action='store_true', help='不写文件，只打印总结')
    args = ap.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        print(f'❌ 源目录不存在: {source_dir}', file=sys.stderr)
        return 1

    print(f'源: {source_dir}')
    print(f'目标: {DRIVE_DIR}')
    print(f'dry-run: {args.dry_run}')
    print('=' * 70)

    if not args.dry_run:
        DRIVE_DIR.mkdir(exist_ok=True)
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
                target = DRIVE_DIR / f'{slug}.mdx'
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
            '# Drive EN Import Report\n',
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
        print(f'  mdx:               {DRIVE_DIR}/*.mdx ({len(report_rows)} 个)')
        print(f'  nav-fragment.json: {OUTPUT_DIR}/nav-fragment.json')
        print(f'  slug-map.json:     {OUTPUT_DIR}/slug-map.json')
        print(f'  report.md:         {OUTPUT_DIR}/report.md')

    if missing or total_residual_nbsp > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
