#!/usr/bin/env python3
"""
在 docs.json 注册 en / ja / id 语言块「开放平台」product 的「YiDA API」tab。

实现：把 zh 块「开放平台 → 宜搭 API」tab deepcopy
→ 译 tab 名 / group 名（三语映射表，缺失名保留中文并告警）
→ pages 路径 `zh/open/yida/` → `open/yida/`（en）/ `ja/open/yida/`（ja）/ `id/open/yida/`（id）
→ 追加到目标语言块开放平台 product 的 tabs 末尾（与 zh 位置一致）

幂等：目标语言块已有同名 tab 则整体替换。
保留键序、缩进 2、ensure_ascii=False、末尾换行（与 register_yida_navigation.py 一致）。

用法：
  python3 scripts/register_yida_api_navigation.py                 # 预演（不写）
  python3 scripts/register_yida_api_navigation.py --write         # 写入 docs.json
  python3 scripts/register_yida_api_navigation.py --langs en --write
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_JSON = REPO_ROOT / "docs.json"

ZH_PRODUCT = "开放平台"
ZH_TAB = "宜搭 API"

# 各语言开放平台 product 显示名（以 docs.json 实际值为准）
OPEN_PRODUCT = {"en": "Open Platform", "ja": "オープンプラットフォーム", "id": "Platform Terbuka"}

TAB_NAME = {"en": "YiDA API", "ja": "YiDA API", "id": "YiDA API"}

PAGE_PREFIX = {"en": "open/yida/", "ja": "ja/open/yida/", "id": "id/open/yida/"}

# ============================================================
# group 名三语映射（zh → en / ja / id）
# ============================================================

GROUP_NAME_EN: dict[str, str] = {
    "开始使用": "Getting Started",
    "开发指南": "Developer Guide",
    "核心概念": "Core Concepts",
    "自定义组件": "Custom Components",
    "FAQ": "FAQ",
    "API": "API",
    "教程": "Tutorials",
    "组件": "Components",
    "布局组件": "Layout Components",
    "基础组件": "Basic Components",
    "表单组件": "Form Components",
    "高级组件": "Advanced Components",
}

GROUP_NAME_JA: dict[str, str] = {
    "开始使用": "はじめに",
    "开发指南": "開発ガイド",
    "核心概念": "コア概念",
    "自定义组件": "カスタムコンポーネント",
    "FAQ": "FAQ",
    "API": "API",
    "教程": "チュートリアル",
    "组件": "コンポーネント",
    "布局组件": "レイアウトコンポーネント",
    "基础组件": "基本コンポーネント",
    "表单组件": "フォームコンポーネント",
    "高级组件": "高度なコンポーネント",
}

GROUP_NAME_ID: dict[str, str] = {
    "开始使用": "Memulai",
    "开发指南": "Panduan pengembang",
    "核心概念": "Konsep inti",
    "自定义组件": "Komponen kustom",
    "FAQ": "FAQ",
    "API": "API",
    "教程": "Tutorial",
    "组件": "Komponen",
    "布局组件": "Komponen tata letak",
    "基础组件": "Komponen dasar",
    "表单组件": "Komponen formulir",
    "高级组件": "Komponen lanjutan",
}

GROUP_MAPS = {"en": GROUP_NAME_EN, "ja": GROUP_NAME_JA, "id": GROUP_NAME_ID}


def tr(name: str, names: dict[str, str], missing: set) -> str:
    if name in names:
        return names[name]
    missing.add(name)
    return name


def convert_pages(pages: list, lang: str, names: dict, missing: set) -> list:
    prefix = PAGE_PREFIX[lang]
    out = []
    for item in pages:
        if isinstance(item, str):
            if not item.startswith("zh/open/yida/"):
                sys.exit(f"ERROR: 非预期 page 路径（应以 zh/open/yida/ 开头）: {item}")
            out.append(prefix + item[len("zh/open/yida/"):])
        elif isinstance(item, dict) and "group" in item:
            ng = copy.deepcopy(item)
            ng["group"] = tr(item["group"], names, missing)
            ng["pages"] = convert_pages(item.get("pages", []), lang, names, missing)
            out.append(ng)
        else:
            out.append(item)
    return out


def build_tab(zh_tab: dict, lang: str, missing: set) -> dict:
    names = GROUP_MAPS[lang]
    tab = copy.deepcopy(zh_tab)
    tab["tab"] = TAB_NAME[lang]
    new_groups = []
    for g in tab["groups"]:
        ng = copy.deepcopy(g)
        ng["group"] = tr(g["group"], names, missing)
        ng["pages"] = convert_pages(g.get("pages", []), lang, names, missing)
        new_groups.append(ng)
    tab["groups"] = new_groups
    return tab


def count_pages(tab: dict) -> int:
    n = 0

    def walk(pages):
        nonlocal n
        for it in pages:
            if isinstance(it, str):
                n += 1
            elif isinstance(it, dict) and "group" in it:
                walk(it.get("pages", []))

    for g in tab["groups"]:
        walk(g.get("pages", []))
    return n


def verify_pages_exist(tab: dict) -> list[str]:
    missing_files = []

    def walk(pages):
        for it in pages:
            if isinstance(it, str):
                if not (REPO_ROOT / (it + ".mdx")).exists():
                    missing_files.append(it)
            elif isinstance(it, dict) and "group" in it:
                walk(it.get("pages", []))

    for g in tab["groups"]:
        walk(g.get("pages", []))
    return missing_files


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写入 docs.json（默认只预演）")
    ap.add_argument("--langs", default="en,ja,id", help="目标语言，逗号分隔")
    args = ap.parse_args()
    target_langs = [l.strip() for l in args.langs.split(",") if l.strip()]

    data = json.loads(DOCS_JSON.read_text(encoding="utf-8"))
    langs = data["navigation"]["languages"]

    zh_block = next(l for l in langs if l["language"] == "zh")
    zh_open = next(p for p in zh_block["products"] if p["product"] == ZH_PRODUCT)
    zh_tab = next(t for t in zh_open["tabs"] if t.get("tab") == ZH_TAB)
    print(f"[info] zh 宜搭 API tab：groups={len(zh_tab['groups'])} pages={count_pages(zh_tab)}")

    for lang in target_langs:
        block = next((l for l in langs if l["language"] == lang), None)
        if block is None:
            print(f"[skip] {lang} 语言块不存在")
            continue
        product = next((p for p in block["products"] if p["product"] == OPEN_PRODUCT[lang]), None)
        if product is None:
            print(f"[skip] {lang} 缺开放平台 product ({OPEN_PRODUCT[lang]})")
            continue

        missing_names: set = set()
        new_tab = build_tab(zh_tab, lang, missing_names)
        if missing_names:
            print(f"[warn] {lang}: {len(missing_names)} 个分组名未在映射中（保留中文）：")
            for m in sorted(missing_names):
                print("   -", m)

        missing_files = verify_pages_exist(new_tab)
        if missing_files:
            print(f"[warn] {lang}: {len(missing_files)} 个 page 缺对应 mdx（前 10）：")
            for m in missing_files[:10]:
                print("   -", m)

        tabs = product["tabs"]
        existing_idx = next((i for i, t in enumerate(tabs) if t.get("tab") == TAB_NAME[lang]), None)
        action = "replace" if existing_idx is not None else "append"
        if existing_idx is not None:
            tabs[existing_idx] = new_tab
        else:
            tabs.append(new_tab)
        print(
            f"[{lang}] {action} tab {TAB_NAME[lang]!r}: groups={len(new_tab['groups'])} "
            f"pages={count_pages(new_tab)} missing_mdx={len(missing_files)}"
        )

    if not args.write:
        print("\n[dry-run] 未写入。确认无误后加 --write")
        return 0

    DOCS_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n[ok] 已写入 {DOCS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
