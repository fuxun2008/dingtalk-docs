#!/usr/bin/env python3
"""04_gen_nav.py — 生成 docs.json 宜搭 tab 的 navigation 片段 + 校验。

输入: output/nav-tree.json
输出: output/tab-yida.json（可直接插入 docs.json zh 帮助中心 products[].tabs[]）
"""
import json
from pathlib import Path

BASE = Path(__file__).parent
REPO = BASE.parent.parent

nav = json.loads((BASE / "output" / "nav-tree.json").read_text())

# 校验 nav 引用的每个 page 都有对应 mdx
missing = []


def walk(pages):
    for p in pages:
        if isinstance(p, str):
            if not (REPO / (p + ".mdx")).exists():
                missing.append(p)
        else:
            walk(p["pages"])


for g in nav:
    walk(g["pages"])

tab = {"tab": "宜搭", "icon": "wand-magic-sparkles", "groups": nav}
(BASE / "output" / "tab-yida.json").write_text(json.dumps(tab, ensure_ascii=False, indent=2))

pages_total = 0


def count(pages):
    global pages_total
    for p in pages:
        if isinstance(p, str):
            pages_total += 1
        else:
            count(p["pages"])


for g in nav:
    count(g["pages"])

print(f"groups: {len(nav)}, pages: {pages_total}, missing mdx: {len(missing)}")
if missing:
    print("MISSING:", missing[:20])
