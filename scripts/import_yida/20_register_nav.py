#!/usr/bin/env python3
"""20_register_nav.py — 把宜搭两个 tab 注册进 docs.json 的 zh 语言块（幂等）。

- 帮助中心 product: 追加「宜搭」tab（output/tab-yida.json）
- 开放平台 product: 追加「宜搭开发」tab（output/tab-yida-dev.json）

用法: python3 scripts/import_yida/20_register_nav.py [--dry-run]
"""
import json
import sys
from pathlib import Path

BASE = Path(__file__).parent
DOCS_JSON = BASE.parent.parent / "docs.json"
DRY = "--dry-run" in sys.argv

tab_yida = json.loads((BASE / "output" / "tab-yida.json").read_text())
tab_dev = json.loads((BASE / "output" / "tab-yida-dev.json").read_text())

data = json.loads(DOCS_JSON.read_text())
zh = next(l for l in data["navigation"]["languages"] if l["language"] == "zh")


def upsert(product_name, tab):
    product = next(p for p in zh["products"] if p["product"] == product_name)
    tabs = product["tabs"]
    for i, t in enumerate(tabs):
        if t.get("tab") == tab["tab"]:
            tabs[i] = tab
            return f"replaced tab {tab['tab']!r} in {product_name!r}"
    tabs.append(tab)
    return f"appended tab {tab['tab']!r} to {product_name!r} (now {len(tabs)} tabs)"


print(upsert("帮助中心", tab_yida))
print(upsert("开放平台", tab_dev))

if DRY:
    print("[dry-run] docs.json 未写入")
else:
    DOCS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"docs.json written ({DOCS_JSON.stat().st_size} bytes)")
