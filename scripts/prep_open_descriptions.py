#!/usr/bin/env python3
"""prep_open_descriptions.py — Phase 1 of open/ + zh/open/ description rewrite.

扫 zh/open/**/*.mdx (锚) 和 open/**/*.mdx，按相对路径配对。
为每对（或孤儿）提取「精简喂料」(≤ ~350 chars/篇)，切 14 batch，写到
scripts/output/open_desc/input_batch_{NN}.json，供 sub-agent 并行总结。

喂料字段：
  slug              → 唯一 key（不含 .mdx，路径相对仓库根，例: open/development/api-createfilter）
  title_zh          → zh frontmatter title
  title_en          → en frontmatter title（可空）
  h1_zh             → zh body 首个 H1（通常和 title 同）
  h2_list_zh        → zh body 前 5 个 H2
  first_para_zh     → zh body 首个非空非标题段落（去 md 语法、≤ 200 chars）
  current_desc_zh   → zh 现有 description（可空）
  current_desc_en   → en 现有 description（可空）
  en_only           → bool, 仅 en 存在（zh 字段全为 null）
  zh_only           → bool, 仅 zh 存在

用法：
    python3 scripts/prep_open_descriptions.py            # 默认切 14 batch
    python3 scripts/prep_open_descriptions.py --batches 14
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EN_DIR = REPO_ROOT / 'open'
ZH_DIR = REPO_ROOT / 'zh' / 'open'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'open_desc'

MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')
FRONTMATTER_RE = re.compile(r'\A---\s*\n(.*?)\n---\s*\n', re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    fm_block, body = m.group(1), text[m.end():]
    out: dict[str, str] = {}
    for line in fm_block.splitlines():
        if ':' not in line:
            continue
        key, _, value = line.partition(':')
        key = key.strip()
        value = value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        out[key] = value
    return out, body


def extract_h1(body: str) -> str:
    for line in body.splitlines():
        s = line.strip()
        if s.startswith('# ') and not s.startswith('## '):
            return s[2:].strip()
    return ''


def extract_h2_list(body: str, limit: int = 5) -> list[str]:
    out: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith('## ') and not s.startswith('### '):
            out.append(s[3:].strip())
            if len(out) >= limit:
                break
    return out


def extract_first_para(body: str, max_chars: int = 200) -> str:
    """Body 首个非空非标题段落，去 md 语法 / 图片 / 链接 / 强调符号。"""
    text = MD_INLINE_IMAGE_RE.sub(' ', body)
    for raw_line in text.splitlines():
        s = raw_line.strip()
        if not s or s.startswith('#') or s.startswith('---'):
            continue
        if s.startswith('|') or s.startswith('>'):
            continue
        s = MD_INLINE_LINK_RE.sub(r'\1', s)
        s = MD_EMPHASIS_CHARS_RE.sub('', s)
        s = re.sub(r'\s+', ' ', s).strip()
        if s:
            return s[:max_chars]
    return ''


def relative_slug(path: Path, base: Path) -> str:
    """相对 REPO_ROOT 的 slug（不含 .mdx 后缀，POSIX 路径），以 open/... 起始。"""
    rel = path.relative_to(base)
    return rel.with_suffix('').as_posix()


def scan_pairs() -> tuple[list[dict], int, int, int, int]:
    """扫 zh/open 和 open，配对返回 items + 统计。"""
    zh_files = {p.relative_to(ZH_DIR): p for p in ZH_DIR.rglob('*.mdx')}
    en_files = {p.relative_to(EN_DIR): p for p in EN_DIR.rglob('*.mdx')}
    all_keys = sorted(set(zh_files) | set(en_files))

    items: list[dict] = []
    n_pair = n_zh_only = n_en_only = 0

    for key in all_keys:
        zh_path = zh_files.get(key)
        en_path = en_files.get(key)
        # slug 用 en 路径风格（不带 zh/ 前缀），方便 apply 阶段两边都能对上
        slug = 'open/' + key.with_suffix('').as_posix()

        item: dict = {
            'slug': slug,
            'title_zh': None,
            'title_en': None,
            'h1_zh': None,
            'h2_list_zh': [],
            'first_para_zh': None,
            'current_desc_zh': None,
            'current_desc_en': None,
            'en_only': False,
            'zh_only': False,
        }

        if zh_path:
            text = zh_path.read_text(encoding='utf-8')
            fm, body = parse_frontmatter(text)
            item['title_zh'] = fm.get('title') or None
            item['current_desc_zh'] = fm.get('description') or None
            item['h1_zh'] = extract_h1(body) or item['title_zh']
            item['h2_list_zh'] = extract_h2_list(body)
            item['first_para_zh'] = extract_first_para(body)

        if en_path:
            text = en_path.read_text(encoding='utf-8')
            fm, body = parse_frontmatter(text)
            item['title_en'] = fm.get('title') or None
            item['current_desc_en'] = fm.get('description') or None
            # 孤儿（en-only）时补 en 喂料
            if not zh_path:
                item['en_only'] = True
                item['h1_zh'] = None
                item['h2_list_zh'] = extract_h2_list(body)
                item['first_para_zh'] = extract_first_para(body)

        if zh_path and en_path:
            n_pair += 1
        elif zh_path:
            n_zh_only += 1
            item['zh_only'] = True
        else:
            n_en_only += 1

        items.append(item)

    return items, len(all_keys), n_pair, n_zh_only, n_en_only


def slice_batches(items: list[dict], n_batches: int) -> list[list[dict]]:
    """均分到 n_batches 个 batch，余数前几批多 1 篇。"""
    total = len(items)
    base = total // n_batches
    extra = total % n_batches
    out: list[list[dict]] = []
    idx = 0
    for i in range(n_batches):
        size = base + (1 if i < extra else 0)
        out.append(items[idx:idx + size])
        idx += size
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--batches', type=int, default=14, help='Number of batches to split into')
    args = parser.parse_args()

    if not ZH_DIR.exists() or not EN_DIR.exists():
        print(f'ERROR: missing {ZH_DIR} or {EN_DIR}', file=sys.stderr)
        return 1

    items, total, n_pair, n_zh_only, n_en_only = scan_pairs()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    batches = slice_batches(items, args.batches)
    for i, batch_items in enumerate(batches, start=1):
        batch_id = f'{i:02d}'
        out_path = OUTPUT_DIR / f'input_batch_{batch_id}.json'
        payload = {
            'batch_id': batch_id,
            'count': len(batch_items),
            'items': batch_items,
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    # 汇总
    summary = {
        'total': total,
        'paired': n_pair,
        'zh_only': n_zh_only,
        'en_only': n_en_only,
        'batches': args.batches,
        'batch_sizes': [len(b) for b in batches],
    }
    (OUTPUT_DIR / 'prep_summary.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8'
    )

    print(f'Total: {total} | Paired: {n_pair} | zh-only: {n_zh_only} | en-only: {n_en_only}')
    print(f'Batches: {args.batches} → sizes {summary["batch_sizes"]}')
    print(f'Output: {OUTPUT_DIR}/input_batch_*.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
