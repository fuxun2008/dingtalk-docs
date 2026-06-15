#!/usr/bin/env python3
"""import_ai_minutes_en.py — 把 ~/Downloads/<date>_DingTalk_AI_Minutes/AI听记英文版/*.adoc.md → ai-minutes/<slug>.mdx。

仿 import_drive_en.py，差异：
- 无 "Back to 母文档" 段（删除 TRAILING_BACK_TO_RE 处理）
- 多数 EN 文件 line-1 H1 + line-3 同 H1 重复（7/9），需新增 strip_dup_leading_h1
- TITLE_OVERRIDES: ai-minutes overview 改 'AI Minutes Overview' 避免与 group 同名
- Purchase Guide 父文档 dead-end（267 bytes 仅 2 个跳转链接）不入仓
- 2 group / 8 篇

用法:
    python3 scripts/import_ai_minutes_en.py                    # 默认源 ~/Downloads/2026-06-15_DingTalk_AI_Minutes
    python3 scripts/import_ai_minutes_en.py --source <path>    # 自定义源
    python3 scripts/import_ai_minutes_en.py --dry-run          # 只打印总结

产物:
  - ai-minutes/<slug>.mdx × 8
  - scripts/output/ai_minutes_en/{nav-fragment.json, slug-map.json, report.md}
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
AI_MINUTES_DIR = REPO_ROOT / 'ai-minutes'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'ai_minutes_en'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
LEADING_H1_RE = re.compile(r'\A# (.+?)\n')
ADMONITION_MARKER_RE = re.compile(r'^:::\s*$', re.MULTILINE)
# body 末尾钉钉文档自动加的 "Back to the [**<Group>**](<alidocs>) directory." 段（含前置 --- 横线）
# 当前仅 billing-overview 命中（AI 听记英文版 hub 子集型 Purchase Guide 父级）；保留正则避免下游回归
TRAILING_BACK_TO_RE = re.compile(
    r'\n+---\s*\n+Back to the \[\*\*[^\]]+\*\*\]\(https://alidocs\.dingtalk\.com[^)]+\)\s*directory\.\s*\Z'
)
# 钉钉文档外链 → 仓库内链映射（按 dentry UUID 匹配）
# 当前 1 处：use-ai-minutes 引用「Voiceprint Recognition Guide」外链 → 改 /ai-minutes/voiceprint-recognition
ALIDOCS_INTERNAL_LINK_MAP: dict[str, str] = {
    'YndMj49yWjlAYoxjtXyrjDNnJ3pmz5aA': '/ai-minutes/voiceprint-recognition',
}
ALIDOCS_LINK_RE = re.compile(
    r'\(https://alidocs\.dingtalk\.com/i/(?:nodes|p/[^/]+/docs)/([A-Za-z0-9_]+)(?:\?[^)]*)?\)'
)
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')
# list 行前缀（有序 `1.` / `1)` / 无序 `-` `*` `+`）；用于让 description 跳过 list-heavy 文档的列表首项
MD_LIST_PREFIX_RE = re.compile(r'^\s*(?:\d+[.)]|[-*+])\s+')

# overview slug title 强制覆盖（避免与所在 group 同名）
TITLE_OVERRIDES: dict[str, str] = {
    'ai-minutes': 'AI Minutes Overview',
}

# 8 篇 → 3 group（对齐其他产品都有 Getting Started 第一 group 的惯例）
# 三元组: (slug, source_basename, expected_title)
# source_basename 相对源根目录 (含 'AI听记英文版/' 前缀)
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('Getting Started', [
        ('ai-minutes',
         'AI听记英文版/AI Minutes.adoc.md',
         'AI Minutes'),
        ('start-ai-minutes',
         'AI听记英文版/AI Minutes.adoc - Start AI Minutes.adoc.md',
         'Start AI Minutes'),
        ('view-ai-minutes',
         'AI听记英文版/AI Minutes.adoc - View AI Minutes.adoc.md',
         'View AI Minutes'),
    ]),
    ('Features', [
        ('use-ai-minutes',
         'AI听记英文版/AI Minutes.adoc - Use AI Minutes.adoc.md',
         'Use AI Minutes'),
        ('voiceprint-recognition',
         'AI听记英文版/AI Minutes.adoc - Voiceprint Recognition Feature Overview.adoc.md',
         'Voiceprint Recognition Feature Overview'),
        ('face-to-face-translation',
         'AI听记英文版/AI Minutes.adoc - Face-to-Face Translation Feature Overview.adoc.md',
         'Face-to-Face Translation Feature Overview'),
    ]),
    ('Purchase Guide', [
        ('billing-overview',
         'AI听记英文版/Purchase Guide.adoc - Billing Overview.adoc.md',
         'Billing Overview'),
        ('membership-gifts',
         'AI听记英文版/Purchase Guide.adoc - Membership Gifts and Redemption.adoc.md',
         'Membership Gifts and Redemption'),
    ]),
]


def clean_invisible(text: str) -> str:
    def repl(m: re.Match) -> str:
        return ' ' if m.group(0) == '\xa0' else ''
    return INVISIBLE_CHARS_RE.sub(repl, text)


def strip_dup_leading_h1(body: str, parsed_title: str) -> str:
    """剥 body 开头与 parsed_title 重复的 H1（钉钉文档导出常见，7/9 EN 文件命中）。"""
    m = LEADING_H1_RE.match(body)
    if m and m.group(1).strip() == parsed_title.strip():
        return body[m.end():].lstrip()
    return body


def strip_admonition_markers(body: str) -> str:
    """剥单独成行的 `:::`（钉钉文档 callout 容器开/闭标记，MDX 不识别）。"""
    return ADMONITION_MARKER_RE.sub('', body)


def strip_trailing_back_to(body: str) -> str:
    """剥 body 末尾钉钉文档自动加的 'Back to the [**<Group>**](alidocs) directory.' 段（含前置 --- 横线）。"""
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
    """把 body 内所有正文 H1 (`# Title`) 降级为 H2 (`## Title`)；跳过代码块内的 `# ...`。
    Mintlify 把 frontmatter.title 视为唯一 H1，正文 H1 会导致重复 + 层级跳跃。
    与 scripts/lint/demote_all_h1.py 同逻辑，内置入 import 流程避免重跑回归。
    """
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
        # 跳过 list 行（避免选用 list item 作 description；list-heavy 文档会 fallback 到 page title）
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
        'tab': 'AI Minutes',
        'groups': [
            {
                'group': group_name,
                'pages': [f'ai-minutes/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='AI Minutes EN markdown → mdx 入库')
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
        AI_MINUTES_DIR.mkdir(exist_ok=True)
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
            '# AI Minutes EN Import Report\n',
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
