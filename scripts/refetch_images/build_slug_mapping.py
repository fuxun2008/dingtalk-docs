#!/usr/bin/env python3
"""
build_slug_mapping.py — 把 hub manifest 的 title 与仓库 zh/<product>/<slug>.mdx 的 frontmatter title 匹配，
输出 slug-mapping.json + mapping-report.md（人工 review 用）。

用法：
  python3 scripts/refetch_images/build_slug_mapping.py --product mail
  python3 scripts/refetch_images/build_slug_mapping.py --product ai-minutes
  python3 scripts/refetch_images/build_slug_mapping.py --product meetings

输入：
  .claude/import/dingtalk_downloader/output/refetch-images/<product>/manifest.json
  zh/<product>/*.mdx
输出：
  scripts/output/refetch-images/<product>/slug-mapping.json
  scripts/output/refetch-images/<product>/mapping-report.md
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 手动 alias：title 自动匹配失败时的兜底
# product → mdx slug → hub title 关键子串（normalized 后 substring 匹配）
ALIAS_MAP: dict[str, dict[str, str]] = {
    'ai-minutes': {
        'ai-minutes': 'ai听记中文版',  # 仓库 "AI 听记总览" ↔ hub 总览 "AI听记中文版 · DingTalk Docs"
    },
    'meetings': {
        'meeting-ai': '会议ai',         # 仓库 "视频会议AI" ↔ hub leaf "会议AI"
    },
    'mail': {},
}

# 零宽字符 / 不可见 unicode tag（hub title 偶尔带）
ZERO_WIDTH_RE = re.compile(r'[​-‏‪-‮⁠-⁯﻿\U000e0020-\U000e007f]')

# 编号前缀：1. / 1.1 / 1.1.1 / 1、 等
NUM_PREFIX_RE = re.compile(r'^\s*\d+(?:\.\d+)*[\.\s、]+')
# 末尾问号 / 全角问号 / 空白
TRAILING_PUNCT_RE = re.compile(r'[\s\?？！。]+$')
# 括号注释（链接需修改）等
PAREN_NOTE_RE = re.compile(r'[（(][^）)]*[）)]\s*$')


def normalize(title: str) -> str:
    """规范化标题用于匹配：path-like 取末段、去 .adoc 后缀、编号前缀、问号、括号备注、零宽字符、空白。"""
    s = title.strip()
    s = ZERO_WIDTH_RE.sub('', s)
    # hub manifest 的 title 可能是 path-like：`父.adoc / 子.adoc / 孙.adoc`，取最末段
    if ' / ' in s:
        s = s.rsplit(' / ', 1)[-1].strip()
    if s.endswith('.adoc'):
        s = s[:-5]
    s = NUM_PREFIX_RE.sub('', s)
    s = PAREN_NOTE_RE.sub('', s).strip()
    s = TRAILING_PUNCT_RE.sub('', s)
    # 半全角统一
    s = s.replace('／', '/').replace('（', '(').replace('）', ')')
    s = s.replace(' ', '')  # 去空白以兼容 "AI 听记" vs "AI听记"
    return s.strip().lower()


def load_mdx_titles(product: str) -> list[dict]:
    """读 zh/<product>/*.mdx，抽 frontmatter title。返回 [{slug, title, norm}]"""
    out = []
    for p in sorted((ROOT / 'zh' / product).glob('*.mdx')):
        title = ''
        with p.open('r', encoding='utf-8') as f:
            in_fm = False
            for line in f:
                line = line.rstrip('\n')
                if line == '---':
                    if not in_fm:
                        in_fm = True
                        continue
                    break
                if in_fm and line.startswith('title:'):
                    title = line.split(':', 1)[1].strip().strip('"\'')
                    break
        out.append({'slug': p.stem, 'title': title, 'norm': normalize(title)})
    return out


def load_manifest(product: str) -> list[dict]:
    fp = ROOT / '.claude' / 'import' / 'dingtalk_downloader' / 'output' / 'refetch-images' / product / 'manifest.json'
    with fp.open('r', encoding='utf-8') as f:
        m = json.load(f)
    out = []
    for i, e in enumerate(m):
        out.append({
            'index': i,
            'node_id': e.get('node_id') or e.get('dentryId') or e.get('id'),
            'title': e.get('title', ''),
            'category': e.get('category', ''),
            'norm': normalize(e.get('title', '')),
            'output_path': e.get('output_path', ''),
        })
    return out


def match(product: str) -> dict:
    mdx = load_mdx_titles(product)
    hub = load_manifest(product)
    alias = ALIAS_MAP.get(product, {})

    # 构 norm -> hub entry 表
    hub_by_norm: dict[str, list[dict]] = {}
    for e in hub:
        hub_by_norm.setdefault(e['norm'], []).append(e)

    mapping = []
    mdx_only = []
    used_node_ids: set[str] = set()
    conflicts = []

    for m in mdx:
        matches = hub_by_norm.get(m['norm'], [])
        # exact 失败时尝试 ALIAS 子串匹配
        if not matches and m['slug'] in alias:
            needle = alias[m['slug']].lower()
            matches = [e for e in hub if needle in e['norm']]
        if len(matches) == 1:
            e = matches[0]
            mapping.append({
                'slug': m['slug'],
                'mdx_title': m['title'],
                'hub_title': e['title'],
                'hub_category': e['category'],
                'node_id': e['node_id'],
                'output_path': e['output_path'],
            })
            used_node_ids.add(e['node_id'])
        elif len(matches) > 1:
            conflicts.append({
                'slug': m['slug'],
                'mdx_title': m['title'],
                'hub_candidates': [{'title': x['title'], 'node_id': x['node_id'], 'category': x['category']} for x in matches],
            })
        else:
            mdx_only.append({'slug': m['slug'], 'mdx_title': m['title'], 'norm': m['norm']})

    hub_only = []
    for e in hub:
        if e['node_id'] in used_node_ids:
            continue
        hub_only.append({
            'hub_title': e['title'],
            'hub_category': e['category'],
            'node_id': e['node_id'],
            'norm': e['norm'],
        })

    return {
        'product': product,
        'counts': {
            'mdx_total': len(mdx),
            'hub_total': len(hub),
            'matched': len(mapping),
            'mdx_only': len(mdx_only),
            'hub_only': len(hub_only),
            'conflicts': len(conflicts),
        },
        'mapping': mapping,
        'mdx_only': mdx_only,
        'hub_only': hub_only,
        'conflicts': conflicts,
    }


def write_report(result: dict) -> None:
    product = result['product']
    out_dir = ROOT / 'scripts' / 'output' / 'refetch-images' / product
    out_dir.mkdir(parents=True, exist_ok=True)

    with (out_dir / 'slug-mapping.json').open('w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    c = result['counts']
    lines = []
    lines.append(f'# slug-mapping report — {product}\n')
    lines.append(f'- mdx 总数: **{c["mdx_total"]}**')
    lines.append(f'- hub 总数: **{c["hub_total"]}**')
    lines.append(f'- 匹配成功: **{c["matched"]}**')
    lines.append(f'- 仅仓库有 (anomaly 候选): **{c["mdx_only"]}**')
    lines.append(f'- 仅 hub 有 (group/新增): **{c["hub_only"]}**')
    lines.append(f'- 同名冲突: **{c["conflicts"]}**\n')

    if result['mapping']:
        lines.append('## ✓ 匹配成功\n')
        lines.append('| # | slug | mdx title | hub title | hub category |')
        lines.append('|---|---|---|---|---|')
        for i, e in enumerate(result['mapping'], 1):
            lines.append(f'| {i} | `{e["slug"]}` | {e["mdx_title"]} | {e["hub_title"]} | {e["hub_category"]} |')
        lines.append('')

    if result['mdx_only']:
        lines.append('## ⚠️ 仅仓库有（hub 中无对应，将进 anomaly 跳过）\n')
        for e in result['mdx_only']:
            lines.append(f'- `{e["slug"]}` — {e["mdx_title"]}')
        lines.append('')

    if result['hub_only']:
        lines.append('## ℹ️ 仅 hub 有（group 父节点 或 新增页面）\n')
        for e in result['hub_only']:
            lines.append(f'- {e["hub_title"]}（category: {e["hub_category"]}）')
        lines.append('')

    if result['conflicts']:
        lines.append('## ❗ 同名冲突（一个 mdx 对应多个 hub entry）\n')
        for e in result['conflicts']:
            lines.append(f'- `{e["slug"]}` — {e["mdx_title"]}')
            for c2 in e['hub_candidates']:
                lines.append(f'  - {c2["title"]} (category: {c2["category"]}, id: {c2["node_id"]})')
        lines.append('')

    with (out_dir / 'mapping-report.md').open('w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f'\n=== {product} ===')
    print(f'  mdx={c["mdx_total"]} hub={c["hub_total"]} matched={c["matched"]} mdx_only={c["mdx_only"]} hub_only={c["hub_only"]} conflicts={c["conflicts"]}')
    print(f'  → {out_dir}/slug-mapping.json')
    print(f'  → {out_dir}/mapping-report.md')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--product', required=True, choices=['mail', 'ai-minutes', 'meetings'])
    args = ap.parse_args()
    result = match(args.product)
    write_report(result)


if __name__ == '__main__':
    main()
