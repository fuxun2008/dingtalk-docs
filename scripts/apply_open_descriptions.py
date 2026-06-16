#!/usr/bin/env python3
"""apply_open_descriptions.py — Phase 3 of open/ + zh/open/ description rewrite.

读 scripts/output/open_desc/output_batch_*.json，合并为 slug→{zh, en} dict，
对每篇 mdx 的 frontmatter 单行替换或新增 description。

- 替换：原 description: ... → description: "new"
- 新增（无 description 行）：在 title 行之后插入 description: "new"
- 值统一用双引号包裹，原值内的双引号转义为 \"

只动 frontmatter，body 不动；diff 干净（一行变更 + 可能一行新增）。

用法：
    python3 scripts/apply_open_descriptions.py            # 真改
    python3 scripts/apply_open_descriptions.py --dry-run  # 预演（只打印计数）
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

FRONTMATTER_OPEN_RE = re.compile(r'\A---\s*\n')
DESC_LINE_RE = re.compile(r'^description:\s*.*$', re.MULTILINE)
TITLE_LINE_RE = re.compile(r'^title:\s*.*$', re.MULTILINE)


def yaml_double_quote(value: str) -> str:
    """生成 YAML 双引号字符串：转义 \\ 和 \"。"""
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'


def load_outputs() -> dict[str, dict[str, str]]:
    """合并 14 个 output batch → slug 到 {zh, en} 的映射。"""
    out: dict[str, dict[str, str]] = {}
    files = sorted(OUTPUT_DIR.glob('output_batch_*.json'))
    if not files:
        raise SystemExit(f'No output_batch_*.json found in {OUTPUT_DIR}')
    for p in files:
        d = json.loads(p.read_text(encoding='utf-8'))
        for it in d['items']:
            slug = it['slug']
            zh = (it.get('zh') or '').strip()
            en = (it.get('en') or '').strip()
            if not zh and not en:
                continue
            out[slug] = {'zh': zh, 'en': en}
    return out


def apply_to_mdx(path: Path, new_desc: str) -> tuple[str, str]:
    """返回 (action, message). action ∈ {replaced, inserted, skipped_no_fm, skipped_empty}."""
    if not new_desc:
        return 'skipped_empty', f'no description for {path.name}'
    text = path.read_text(encoding='utf-8')
    m = FRONTMATTER_OPEN_RE.match(text)
    if not m:
        return 'skipped_no_fm', f'no frontmatter in {path}'
    # 找 frontmatter 结束位置
    end_match = re.search(r'\n---\s*\n', text[m.end():])
    if not end_match:
        return 'skipped_no_fm', f'unterminated frontmatter in {path}'
    fm_block_end = m.end() + end_match.start()
    fm_block = text[m.end():fm_block_end]
    body = text[fm_block_end:]  # 包含 \n---\n

    new_line = f'description: {yaml_double_quote(new_desc)}'
    desc_search = DESC_LINE_RE.search(fm_block)
    if desc_search:
        # 替换
        new_fm = fm_block[:desc_search.start()] + new_line + fm_block[desc_search.end():]
        action = 'replaced'
    else:
        # 在 title 行后插入
        title_search = TITLE_LINE_RE.search(fm_block)
        if title_search:
            insert_pos = title_search.end()
            new_fm = fm_block[:insert_pos] + '\n' + new_line + fm_block[insert_pos:]
        else:
            # 没 title 行就在 frontmatter 末尾追加
            sep = '' if fm_block.endswith('\n') else '\n'
            new_fm = fm_block + sep + new_line
        action = 'inserted'

    new_text = text[:m.end()] + new_fm + body
    if new_text != text:
        path.write_text(new_text, encoding='utf-8')
    return action, ''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Only count, do not write')
    args = parser.parse_args()

    outputs = load_outputs()
    print(f'Loaded {len(outputs)} slug entries from output_batch_*.json')

    counts = {'replaced': 0, 'inserted': 0, 'skipped_no_fm': 0, 'skipped_empty': 0, 'missing_file': 0}
    by_lang = {'zh': dict(counts), 'en': dict(counts)}

    for slug, desc_pair in outputs.items():
        # slug 形如 open/development/api-createfilter
        # en 文件： open/development/api-createfilter.mdx
        # zh 文件： zh/open/development/api-createfilter.mdx
        rel = slug[len('open/'):] if slug.startswith('open/') else slug
        en_path = EN_DIR / f'{rel}.mdx'
        zh_path = ZH_DIR / f'{rel}.mdx'

        for lang, path, desc in [('en', en_path, desc_pair['en']), ('zh', zh_path, desc_pair['zh'])]:
            if not path.exists():
                by_lang[lang]['missing_file'] += 1
                continue
            if args.dry_run:
                continue
            action, _ = apply_to_mdx(path, desc)
            by_lang[lang][action] += 1

    if args.dry_run:
        print('[dry-run] no files written')
    else:
        for lang in ('en', 'zh'):
            r = by_lang[lang]
            print(f'{lang}: replaced={r["replaced"]} inserted={r["inserted"]} '
                  f'skipped_no_fm={r["skipped_no_fm"]} skipped_empty={r["skipped_empty"]} '
                  f'missing_file={r["missing_file"]}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
