#!/usr/bin/env python3
"""扫描 .url 目录树 → 生成 manifest.json。

输入：/Users/yanxin/Downloads/2026_05_28_DingTalk_Docs/钉钉文档.url/
输出：./manifest.json
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

SRC_ROOT = Path('/Users/yanxin/Downloads/2026_05_28_DingTalk_Docs/钉钉文档.url')
DEST_ROOT = Path.home() / 'Downloads' / 'dingtalk-docs-archive'
MANIFEST_PATH = Path(__file__).parent / 'manifest.json'

URL_LINE_RE = re.compile(r'^URL=(.+)$', re.MULTILINE)
NODE_ID_RE = re.compile(r'/i/nodes/([A-Za-z0-9]+)')
DOC_ID_RE = re.compile(r'/docs/([A-Za-z0-9]+)')

# 文件名中的不可见字符：换行、回车、制表、各种零宽空格
SANITIZE_CHARS_RE = re.compile(r'[\n\r\t​‌‍﻿]')


def sanitize_name(name: str) -> str:
    """清理文件名/路径中的不可见字符。"""
    return SANITIZE_CHARS_RE.sub('', name).strip()


def parse_url_file(path: Path) -> str | None:
    """从 .url 文件提取 URL，找不到返回 None。"""
    text = path.read_text(encoding='ascii', errors='replace')
    m = URL_LINE_RE.search(text)
    if not m:
        return None
    return m.group(1).strip()


def extract_node_id(url: str) -> tuple[str | None, str]:
    """从 URL 提取 id 与类型（nodes / docs / unknown）。"""
    m = NODE_ID_RE.search(url)
    if m:
        return m.group(1), 'nodes'
    m = DOC_ID_RE.search(url)
    if m:
        return m.group(1), 'docs'
    return None, 'unknown'


def build_entry(url_file: Path) -> dict | None:
    """单个 .url → manifest entry。"""
    raw_url = parse_url_file(url_file)
    if not raw_url:
        print(f'  ⚠️  无 URL: {url_file}', file=sys.stderr)
        return None

    # 规范化：去掉查询参数
    parsed = urlparse(raw_url)
    clean_url = f'{parsed.scheme}://{parsed.netloc}{parsed.path}'

    node_id, kind = extract_node_id(clean_url)
    if not node_id:
        print(f'  ⚠️  无法识别 id: {raw_url}', file=sys.stderr)
        return None

    # 相对路径（去掉 SRC_ROOT，去掉末尾 .url，逐段 sanitize）
    # 注意：不能用 Path.with_suffix，会把中文文件名中 "2023.07 xxx" 的 ".07 xxx" 误识别为后缀
    rel_raw = url_file.relative_to(SRC_ROOT)
    parts = list(rel_raw.parts)
    # 末段去 .url 后缀（严格字符串匹配）
    if parts[-1].endswith('.url'):
        parts[-1] = parts[-1][:-4]
    clean_parts = [sanitize_name(p) for p in parts]
    rel_str = '/'.join(clean_parts)
    title = clean_parts[-1]
    category = clean_parts[0] if len(clean_parts) > 1 else '_root'

    # output_path 末段加 .md
    output_parts = clean_parts[:-1] + [clean_parts[-1] + '.md']
    output_path = DEST_ROOT.joinpath(*output_parts)

    return {
        'rel_path': rel_str,
        'title': title,
        'category': category,
        'node_id': node_id,
        'id_kind': kind,
        'url': clean_url,
        'source_url_file': str(url_file),   # 原始 .url 文件路径（含特殊字符），用于审计
        'output_path': str(output_path),
        'status': 'pending',
        'attempts': 0,
        'error': None,
        'downloaded_at': None,
        'size_bytes': None,
    }


def main() -> int:
    if not SRC_ROOT.exists():
        print(f'❌ 源目录不存在: {SRC_ROOT}', file=sys.stderr)
        return 1

    url_files = sorted(SRC_ROOT.rglob('*.url'))
    print(f'扫描到 {len(url_files)} 个 .url 文件')

    entries: list[dict] = []
    seen_node_ids: set[str] = set()
    duplicates = 0

    for f in url_files:
        entry = build_entry(f)
        if not entry:
            continue
        if entry['node_id'] in seen_node_ids:
            duplicates += 1
            print(f'  ⚠️  重复 node_id ({entry["node_id"]}): {entry["rel_path"]}', file=sys.stderr)
            continue
        seen_node_ids.add(entry['node_id'])
        entries.append(entry)

    MANIFEST_PATH.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding='utf-8',
    )

    # 统计
    by_kind: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for e in entries:
        by_kind[e['id_kind']] = by_kind.get(e['id_kind'], 0) + 1
        by_category[e['category']] = by_category.get(e['category'], 0) + 1

    print(f'\n✅ manifest.json 已写入 ({len(entries)} 条；重复跳过 {duplicates})')
    print(f'   {MANIFEST_PATH}')
    print(f'\n按 id_kind:')
    for k, v in sorted(by_kind.items()):
        print(f'   {k}: {v}')
    print(f'\n按 category（前 5 大）:')
    top = sorted(by_category.items(), key=lambda x: -x[1])[:10]
    for cat, n in top:
        print(f'   {n:>4}  {cat}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
