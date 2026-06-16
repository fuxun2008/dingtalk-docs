#!/usr/bin/env python3
"""audit_descriptions.py — Phase 4 of open/ + zh/open/ description rewrite.

扫 open/ + zh/open/ 全部 mdx，统计：
- 有/无 description 比例
- description 长度分布
- 双语对（同 slug zh + en）长度差异 > 60% 的异常对

用法：
    python3 scripts/audit_descriptions.py
    python3 scripts/audit_descriptions.py --show-anomalies   # 列出长度异常对前 20 条
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EN_DIR = REPO_ROOT / 'open'
ZH_DIR = REPO_ROOT / 'zh' / 'open'

DESC_RE = re.compile(r'^description:\s*"((?:[^"\\]|\\.)*)"\s*$|^description:\s*\'((?:[^\'\\]|\\.)*)\'\s*$|^description:\s*(\S.*)$', re.MULTILINE)


def extract_description(text: str) -> str | None:
    m = DESC_RE.search(text)
    if not m:
        return None
    return m.group(1) or m.group(2) or m.group(3) or None


def length_bucket(n: int) -> str:
    if n == 0:
        return '0 (empty)'
    if n < 40:
        return '1-39'
    if n < 80:
        return '40-79'
    if n < 120:
        return '80-119'
    if n < 160:
        return '120-159'
    if n < 200:
        return '160-199'
    return '200+'


def scan_dir(base: Path, label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    has_desc = 0
    no_desc = 0
    buckets: dict[str, int] = {}
    total = 0
    for p in sorted(base.rglob('*.mdx')):
        total += 1
        text = p.read_text(encoding='utf-8')
        desc = extract_description(text)
        if desc is None:
            no_desc += 1
            continue
        has_desc += 1
        # slug = 相对路径不含 .mdx
        slug = p.relative_to(base).with_suffix('').as_posix()
        result[slug] = desc
        buckets[length_bucket(len(desc))] = buckets.get(length_bucket(len(desc)), 0) + 1

    print(f'\n[{label}] total mdx = {total}')
    print(f'  has description: {has_desc}')
    print(f'  no description : {no_desc}')
    if buckets:
        print('  length buckets:')
        for k in ['0 (empty)', '1-39', '40-79', '80-119', '120-159', '160-199', '200+']:
            v = buckets.get(k, 0)
            if v:
                print(f'    {k:>12} : {v}')
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--show-anomalies', action='store_true', help='List length-anomaly pairs')
    args = parser.parse_args()

    en_descs = scan_dir(EN_DIR, 'open/ (en)')
    zh_descs = scan_dir(ZH_DIR, 'zh/open/ (zh)')

    # 双语对长度差异
    common = sorted(set(en_descs) & set(zh_descs))
    anomalies: list[tuple[str, int, int, float]] = []
    for slug in common:
        en_len = len(en_descs[slug])
        zh_len = len(zh_descs[slug])
        if en_len == 0 or zh_len == 0:
            continue
        # 中英文长度比例：英文通常是中文的 2.0-3.5 倍
        ratio = en_len / zh_len
        if ratio < 1.5 or ratio > 4.0:
            anomalies.append((slug, en_len, zh_len, ratio))

    print(f'\n[Cross-lang pairs] common = {len(common)}')
    print(f'  length ratio anomalies (ratio < 1.5 or > 4.0): {len(anomalies)}')

    if args.show_anomalies and anomalies:
        print('\n  Top anomalies (first 20):')
        for slug, en_len, zh_len, ratio in anomalies[:20]:
            print(f'    {slug}: en={en_len} zh={zh_len} ratio={ratio:.2f}')

    # en-only
    en_only = sorted(set(en_descs) - set(zh_descs))
    zh_only = sorted(set(zh_descs) - set(en_descs))
    print(f'  en-only mdx (no zh): {len(en_only)} {en_only[:5]}')
    print(f'  zh-only mdx (no en): {len(zh_only)} {zh_only[:5]}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
