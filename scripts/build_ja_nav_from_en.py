#!/usr/bin/env python3
"""
docs.json に ja 言語ブロックを構築する（en ブロックをミラー）。

理由：ja コンテンツは en と構造が完全一致（docs 349 / aitable 210 / open 417 / 7 新モジュール）。
zh ブロックは aitable が 144 のため不適。EN ブロックを唯一の構造ソースとする。

処理：
- en 言語ブロックを deepcopy。
- product / tab / group 名を EN→JA マップ（/tmp/nav_names_ja.json）で翻訳。
- すべての page パス文字列に `ja/` プレフィックスを付与。
- language を "ja" に設定し、languages 配列の zh の後ろに挿入。
- json.dump(indent=2, ensure_ascii=False) + 末尾改行（round-trip でバイト一致を確認済み）。

用法：
  python3 scripts/build_ja_nav_from_en.py --dry-run
  python3 scripts/build_ja_nav_from_en.py --write
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_JSON = REPO_ROOT / "docs.json"
NAME_MAP = Path("/tmp/nav_names_ja.json")


def tr(name: str, names: dict[str, str], missing: set) -> str:
    if name in names:
        return names[name]
    missing.add(name)
    return name


def prefix_pages(pages: list, names: dict, missing: set) -> list:
    out = []
    for item in pages:
        if isinstance(item, str):
            out.append(f"ja/{item}")
        elif isinstance(item, dict) and "group" in item:
            ng = copy.deepcopy(item)
            ng["group"] = tr(item["group"], names, missing)
            ng["pages"] = prefix_pages(item.get("pages", []), names, missing)
            out.append(ng)
        else:
            out.append(item)
    return out


def build_ja(en_block: dict, names: dict, missing: set) -> dict:
    ja = copy.deepcopy(en_block)
    ja["language"] = "ja"
    for prod in ja["products"]:
        prod["product"] = tr(prod["product"], names, missing)
        for tab in prod["tabs"]:
            tab["tab"] = tr(tab["tab"], names, missing)
            tab["groups"] = prefix_pages(tab["groups"], names, missing)
    return ja


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
    if "ja" in codes:
        sys.exit("ERROR: ja block already exists; aborting")
    en_block = next(l for l in langs if l["language"] == "en")

    names = json.loads(NAME_MAP.read_text(encoding="utf-8"))
    missing: set = set()
    ja_block = build_ja(en_block, names, missing)

    if missing:
        print(f"[warn] {len(missing)} 个名称未在映射中（保留英文）：")
        for m in sorted(missing):
            print("   -", m)

    print(f"[info] en pages={count_pages(en_block)}  ja pages={count_pages(ja_block)}")
    print(f"[info] ja products={[p['product'] for p in ja_block['products']]}")
    print(f"[info] ja tabs={[t['tab'] for p in ja_block['products'] for t in p['tabs']]}")

    if not args.write:
        print("\n[dry-run] 未写入。确认无误后加 --write")
        return 0

    langs.append(ja_block)
    out = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    DOCS_JSON.write_text(out, encoding="utf-8")
    print(f"\n[done] ja 块已插入 docs.json（languages 现有 {len(langs)} 个：{[l['language'] for l in langs]}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
