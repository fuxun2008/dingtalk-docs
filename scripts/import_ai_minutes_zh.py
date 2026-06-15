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
# body 末尾钉钉文档自动加的 "返回「[**<Group>**](alidocs)」目录" 段（含前置 --- 横线）
# 当前仅 billing-overview 命中（AI 听记中文版 hub 子集型「购买指南」父级）；保留正则避免下游回归
TRAILING_BACK_TO_RE = re.compile(
    r'\n+---\s*\n+返回[「『]?\[\*\*[^\]]+\*\*\]\(https://alidocs\.dingtalk\.com[^)]+\)[」』]?\s*目录\s*\Z'
)
# 钉钉文档外链 → 仓库内链映射（按 dentry UUID 匹配）
# 当前 1 处：use-ai-minutes 引用「声纹识别说明文档」外链 → 改 /zh/ai-minutes/voiceprint-recognition
ALIDOCS_INTERNAL_LINK_MAP: dict[str, str] = {
    'YndMj49yWjlAYoxjtXyrjDNnJ3pmz5aA': '/zh/ai-minutes/voiceprint-recognition',
}
ALIDOCS_LINK_RE = re.compile(
    r'\(https://alidocs\.dingtalk\.com/i/(?:nodes|p/[^/]+/docs)/([A-Za-z0-9_]+)(?:\?[^)]*)?\)'
)
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')
# list 行前缀（有序 `1.` / `1)` / 无序 `-` `*` `+`）；让 description 跳过 list-heavy 文档的列表首项
MD_LIST_PREFIX_RE = re.compile(r'^\s*(?:\d+[.)]|[-*+])\s+')

# overview slug title 强制覆盖（避免与所在 group 同名）
TITLE_OVERRIDES: dict[str, str] = {
    'ai-minutes': 'AI 听记总览',
}

# frontmatter description 手写覆盖：让 mintlify 副标题是「全页 AI 总结」而非 body 首段截断。
# 长度 < 200 chars，覆盖各页 H2 章节范围。
DESCRIPTION_OVERRIDES: dict[str, str] = {
    'ai-minutes': "钉钉 AI 听记产品总览：基于通义大模型的智能记录工具，覆盖会议、培训、访谈、客户拜访等场景，提供实时转写、智能纪要、章节拆分、发言人识别、多语言翻译等能力。",
    'start-ai-minutes': "5 种发起 AI 听记的方式：一键发起录音、模板发起、上传本地音视频、视频会议中发起、从钉钉文档发起；支持手机/Pad/电脑（Windows 与 Mac）多端使用。",
    'view-ai-minutes': "查看 AI 听记的 5 个入口：导航栏搜索、AI 听记助手、历史会议、会议详情页、会议结束页，方便快速找到已生成的听记文件。",
    'use-ai-minutes': "AI 听记文件内的常用功能：智能纪要、章节片段、发言人区分、多语言翻译、关键词搜索、文字编辑、字号调整、文件导出、公开与分享。",
    'voiceprint-recognition': "开启声纹识别后，AI 听记可基于声纹自动识别会上各发言人，让转写原文、待办事项、纪要中的发言人标注准确；含录入流程、应用场景与常见问题。",
    'face-to-face-translation': "AI 听记面对面翻译：实时将双方对话翻译为各自语言，支持双语分屏、语音播报、自动语言识别，适配会议、咖啡厅、商务洽谈等场景；含目标语言设置与 FAQ。",
    'billing-overview': "AI 听记计费方案概览：标准版每月赠 300 分钟转写时长，高级版/旗舰版会员、企业/个人购买、企业时长包等多档选择，配合不同人数与使用场景。",
    'membership-gifts': "AI 听记会员礼包与兑换码使用方式：从「更多 > 我的权益 > 兑换会员」入口激活，包含礼品卡有效期、共享限制、与现有会员叠加的常见问题。",
}

# 8 篇 → 3 group（对齐其他产品都有 Getting Started 第一 group 的惯例）
# 三元组: (slug, source_basename, expected_title)
# source_basename 相对源根目录
# expected_title 用钉钉文档源文件 H1 字面值（无空格），避免误报 title_mismatch
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('开始使用', [
        ('ai-minutes',
         'AI听记中文版.adoc.md',
         'AI听记中文版'),
        ('start-ai-minutes',
         'AI听记中文版.adoc/发起AI听记.adoc.md',
         '发起AI听记'),
        ('view-ai-minutes',
         'AI听记中文版.adoc/查看AI听记.adoc.md',
         '查看AI听记'),
    ]),
    ('功能介绍', [
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
