#!/usr/bin/env python3
"""import_ai_minutes_zh.py — 把 ~/Downloads/<date>_DingTalk_AI_Minutes/AI听记中文版.adoc.md 及子文档 → zh/ai-minutes/<slug>.mdx。

仿 import_ai_minutes_en.py，差异：
- 输出到 zh/ai-minutes/
- tab 名 'AI 听记'，group 名 'AI 听记' / '购买指南'
- TITLE_OVERRIDES: ai-minutes overview 改 'AI 听记总览' 避免与 group 同名
- 中文版母文档源在源根目录 (AI听记中文版.adoc.md)，子文档在 AI听记中文版.adoc/ 子目录
- ::: admonition 在 ZH 文件多见（4/9），strip_admonition_markers 仍必要

用法:
    python3 scripts/import_ai_minutes_zh.py                    # 默认源 ~/Downloads/2026-06-15_DingTalk_AI_Minutes
    python3 scripts/import_ai_minutes_zh.py --source <path>    # 自定义源
    python3 scripts/import_ai_minutes_zh.py --dry-run          # 只打印总结

产物:
  - zh/ai-minutes/<slug>.mdx × 8
  - scripts/output/ai_minutes_zh/{nav-fragment.json, slug-map.json, report.md}
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

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-15_DingTalk_AI_Minutes'
AI_MINUTES_DIR = REPO_ROOT / 'zh' / 'ai-minutes'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'ai_minutes_zh'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
LEADING_H1_RE = re.compile(r'\A# (.+?)\n')
ADMONITION_MARKER_RE = re.compile(r'^:::\s*$', re.MULTILINE)
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')

# overview slug title 强制覆盖（避免与所在 group 同名）
TITLE_OVERRIDES: dict[str, str] = {
    'ai-minutes': 'AI 听记总览',
}

# 8 篇 → 2 group（slug 与 EN 对称，title/group 中文）
# 三元组: (slug, source_basename, expected_title)
# source_basename 相对源根目录
# 注意：expected_title 用钉钉文档源文件 H1 的字面值（无空格），避免误报 title_mismatch
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('AI 听记', [
        ('ai-minutes',
         'AI听记中文版.adoc.md',
         'AI听记中文版'),
        ('start-ai-minutes',
         'AI听记中文版.adoc/发起AI听记.adoc.md',
         '发起AI听记'),
        ('view-ai-minutes',
         'AI听记中文版.adoc/查看AI听记.adoc.md',
         '查看AI听记'),
        ('use-ai-minutes',
         'AI听记中文版.adoc/使用AI听记.adoc.md',
         '使用AI听记'),
        ('voiceprint-recognition',
         'AI听记中文版.adoc/声纹识别功能介绍.adoc.md',
         '声纹识别功能介绍'),
        ('face-to-face-translation',
         'AI听记中文版.adoc/面对面翻译功能介绍.adoc.md',
         '面对面翻译功能介绍'),
    ]),
    ('购买指南', [
        ('billing-overview',
         'AI听记中文版.adoc/购买指南.adoc - 计费概述.adoc.md',
         '计费概述'),
        ('membership-gifts',
         'AI听记中文版.adoc/购买指南.adoc - 会员赠送与兑换.adoc.md',
         '会员赠送与兑换'),
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
    body = strip_dup_leading_h1(body, parsed_title)
    body = strip_admonition_markers(body)

    title = TITLE_OVERRIDES.get(expected_slug) or parsed_title or expected_title
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
        'tab': 'AI 听记',
        'groups': [
            {
                'group': group_name,
                'pages': [f'zh/ai-minutes/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='AI Minutes ZH markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-06-15_DingTalk_AI_Minutes/)')
    ap.add_argument('--dry-run', action='store_true', help='不写文件，只打印总结')
    args = ap.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        print(f'❌ 源目录不存在: {source_dir}', file=sys.stderr)
        return 1

    print(f'源: {source_dir}')
    print(f'目标: {AI_MINUTES_DIR}')
    print(f'dry-run: {args.dry_run}')
    print('=' * 70)

    if not args.dry_run:
        AI_MINUTES_DIR.mkdir(parents=True, exist_ok=True)
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
                target = AI_MINUTES_DIR / f'{slug}.mdx'
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
            '# AI Minutes ZH Import Report\n',
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
        print(f'  mdx:               {AI_MINUTES_DIR}/*.mdx ({len(report_rows)} 个)')
        print(f'  nav-fragment.json: {OUTPUT_DIR}/nav-fragment.json')
        print(f'  slug-map.json:     {OUTPUT_DIR}/slug-map.json')
        print(f'  report.md:         {OUTPUT_DIR}/report.md')

    if missing or total_residual_nbsp > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
