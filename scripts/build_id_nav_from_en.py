#!/usr/bin/env python3
"""
docs.json 里构建 id（Bahasa Indonesia）语言块（镜像 en 块）。

理由：id 内容与 en 结构一致（消费者产品逐篇 en→id / zh→id），EN 块为唯一结构源。
与 ja 的区别：**id 范围不含 Open Platform**，只保留 Help Center 一个 product。

处理：
- deepcopy en 语言块，只保留 product == "Help Center"（丢弃 Open Platform）。
- product / tab / group 名用 EN→ID 映射（/tmp/nav_names_id.json）翻译。
- 所有 page 路径字符串加 `id/` 前缀。
- language 设为 "id"，追加到 languages 数组末尾。
- navbar 用印尼语 label（Unduh）；footer socials 复用 en。
- json.dump(indent=2, ensure_ascii=False) + 末尾换行。

用法：
  python3 scripts/build_id_nav_from_en.py            # dry-run
  python3 scripts/build_id_nav_from_en.py --write
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_JSON = REPO_ROOT / "docs.json"
NAME_MAP = Path("/tmp/nav_names_id.json")

KEEP_PRODUCTS = {"Help Center"}  # id 当前范围只含 Help Center


def tr(name: str, names: dict[str, str], missing: set) -> str:
    if name in names:
        return names[name]
    missing.add(name)
    return name


def prefix_pages(pages: list, names: dict, missing: set) -> list:
    out = []
    for item in pages:
        if isinstance(item, str):
            out.append(f"id/{item}")
        elif isinstance(item, dict) and "group" in item:
            ng = copy.deepcopy(item)
            ng["group"] = tr(item["group"], names, missing)
            ng["pages"] = prefix_pages(item.get("pages", []), names, missing)
            out.append(ng)
        else:
            out.append(item)
    return out


def build_id(en_block: dict, names: dict, missing: set) -> dict:
    idb = copy.deepcopy(en_block)
    idb["language"] = "id"
    idb["products"] = [p for p in idb["products"] if p["product"] in KEEP_PRODUCTS]
    for prod in idb["products"]:
        prod["product"] = tr(prod["product"], names, missing)
        for tab in prod["tabs"]:
            tab["tab"] = tr(tab["tab"], names, missing)
            tab["groups"] = prefix_pages(tab["groups"], names, missing)
    # navbar 印尼语 label（若 en 有 navbar）
    if isinstance(idb.get("navbar"), dict):
        primary = idb["navbar"].get("primary")
        if isinstance(primary, dict) and "label" in primary:
            primary["label"] = "Unduh"
    return idb


def count_pages(block: dict) -> int:
    n = 0

    def walk(pages):
        nonlocal n
        for it in pages:
            if isinstance(it, str):
                n += 1
            elif isinstance(it, dict) and "group" in it:
                walk(it.get("pages", []))

    for p in block["products"]:
        for t in p["tabs"]:
            walk(t["groups"])
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    data = json.loads(DOCS_JSON.read_text(encoding="utf-8"))
    langs = data["navigation"]["languages"]
    codes = [l["language"] for l in langs]
    if "id" in codes:
        sys.exit("ERROR: id block already exists; aborting")
    en_block = next(l for l in langs if l["language"] == "en")

    if not NAME_MAP.exists():
        sys.exit(f"ERROR: name map not found: {NAME_MAP}")
    names = json.loads(NAME_MAP.read_text(encoding="utf-8"))
    missing: set = set()
    id_block = build_id(en_block, names, missing)

    if missing:
        print(f"[warn] {len(missing)} 个名称未在映射中（保留英文）：")
        for m in sorted(missing):
            print("   -", m)

    print(f"[info] id products={[p['product'] for p in id_block['products']]}")
    print(f"[info] id tabs={[t['tab'] for p in id_block['products'] for t in p['tabs']]}")
    print(f"[info] id pages={count_pages(id_block)}")

    if not args.write:
        print("\n[dry-run] 未写入。确认无误后加 --write")
        return 0

    langs.append(id_block)
    out = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    DOCS_JSON.write_text(out, encoding="utf-8")
    print(f"\n[done] id 块已插入 docs.json（languages 现有 {len(langs)} 个：{[l['language'] for l in langs]}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
