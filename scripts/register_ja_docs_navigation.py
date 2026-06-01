#!/usr/bin/env python3
"""
一次性脚本：在 docs.json 注册 ja 语言块。

实现：把 zh 块 deepcopy → 译 tab 名 / group 名 → pages 路径 `zh/` → `ja/`。
保留键序、缩进 2、ensure_ascii=False（中日字符直存）。

用法：
  python3 scripts/register_ja_docs_navigation.py            # 预演（不写）
  python3 scripts/register_ja_docs_navigation.py --write    # 写入 docs.json
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_JSON = REPO_ROOT / "docs.json"


# tab 名翻译（文档 tab 用 ドキュメント；AI Table 品牌词保持英文）
TAB_NAME_MAP: dict[str, str] = {
    "文档": "ドキュメント",
    "AI 表格": "AI Table",
}

# group 名翻译（中文 → 日文）
GROUP_NAME_MAP: dict[str, str] = {
    # 文档 tab — 一级
    "新手指南": "はじめに",
    "快速上手": "クイックスタート",
    "功能更新": "リリースノート",
    "管理员指引": "管理者ガイド",
    "文档 AI": "ドキュメント AI",
    "客户案例": "導入事例",
    "最佳实践": "ベストプラクティス",
    "进阶玩法": "高度な使い方",
    "钉钉文档": "DingTalk Docs",
    "钉钉表格": "DingTalk Spreadsheet",
    "钉钉脑图": "DingTalk Mind",
    "钉钉白板": "DingTalk Whiteboard",
    "知识库": "ナレッジベース",
    "知识小组": "ナレッジグループ",
    "模板中心": "テンプレートセンター",
    # 文档 AI 子组
    "入门必读": "入門ガイド",
    "知识库问答助理": "ナレッジベース QA アシスタント",
    "进阶使用": "高度な使い方",
    "场景实践": "ユースケース",
    "更多智能应用": "その他のスマート機能",
    # 最佳实践 子组
    "客户实践": "お客様事例",
    "行业实践": "業界別事例",
    "角色实践": "職種別事例",
    # 钉钉文档 子组
    "插入内容": "コンテンツの挿入",
    "插入 OKR": "OKR を挿入",
    "协作互动": "コラボレーション",
    "关联钉钉": "DingTalk 連携",
    "样式排版": "スタイルとレイアウト",
    "快捷键输入": "ショートカット入力",
    "打印和导出": "印刷とエクスポート",
    "使用设置": "設定",
    "常见问题": "よくある質問",
    # 钉钉表格 子组
    "编辑": "編集",
    "格式": "書式",
    "公式与函数": "数式と関数",
    "视图": "ビュー",
    "智能工具": "スマートツール",
    "导出和另存为模板": "エクスポートとテンプレート保存",
    # 钉钉脑图 子组
    "基础功能": "基本機能",
    "插入附件": "添付ファイルの挿入",
    "协作与分享": "コラボレーションと共有",
    "其他功能": "その他の機能",
    # AI 表格 tab — 一级
    "从这里开始": "はじめに",
    "AI 表格基础操作": "AI Table 基本操作",
    "使用字段": "フィールドの使い方",
    "使用表单": "フォームの使い方",
    "使用视图": "ビューの使い方",
    "使用仪表盘": "ダッシュボードの使い方",
    "自动化工作流": "自動化ワークフロー",
    "更多": "その他",
    "应用模式": "利用モード",
    "公式函数": "数式と関数",
    "高级权限": "高度な権限",
    "插件中心": "プラグインセンター",
    # AI 表格 子组
    "字段类型列表": "フィールドタイプ一覧",
    "仪表盘组件": "ダッシュボードコンポーネント",
    "使用函数": "関数の使い方",
    "函数实践": "関数の活用例",
    "AI表格插件中心-使用指南": "AI Table プラグインセンター — 使い方ガイド",
    "网页采集助手-插件介绍和安装指南": "ウェブクリッパー — プラグインの紹介とインストールガイド",
}


def translate_group_name(name: str) -> str:
    if name in GROUP_NAME_MAP:
        return GROUP_NAME_MAP[name]
    raise KeyError(f"未翻译的 group 名：{name!r}（请在 GROUP_NAME_MAP 中补齐）")


def translate_tab_name(name: str) -> str:
    if name in TAB_NAME_MAP:
        return TAB_NAME_MAP[name]
    raise KeyError(f"未翻译的 tab 名：{name!r}（请在 TAB_NAME_MAP 中补齐）")


def transform_pages(pages: list, lang_from: str = "zh", lang_to: str = "ja") -> list:
    """递归把 pages 数组里所有字符串路径前缀 zh/ → ja/；嵌套 group dict 也递归。"""
    out = []
    for item in pages:
        if isinstance(item, str):
            if item.startswith(f"{lang_from}/"):
                out.append(f"{lang_to}/" + item[len(lang_from) + 1 :])
            else:
                out.append(item)
        elif isinstance(item, dict):
            out.append(transform_group(item, lang_from, lang_to))
        else:
            out.append(item)
    return out


def transform_group(g: dict, lang_from: str, lang_to: str) -> dict:
    """转一个 group 节点：翻译 group 名 + 递归 pages。"""
    new = {}
    for k, v in g.items():
        if k == "group":
            new[k] = translate_group_name(v)
        elif k == "pages":
            new[k] = transform_pages(v, lang_from, lang_to)
        else:
            new[k] = v
    return new


def build_ja_block(zh_block: dict) -> dict:
    """从 zh language block 构造 ja block。"""
    new = copy.deepcopy(zh_block)
    new["language"] = "ja"
    new_tabs = []
    for tab in new["tabs"]:
        new_tab = {}
        for k, v in tab.items():
            if k == "tab":
                new_tab[k] = translate_tab_name(v)
            elif k == "groups":
                new_tab[k] = [transform_group(g, "zh", "ja") for g in v]
            else:
                new_tab[k] = v
        new_tabs.append(new_tab)
    new["tabs"] = new_tabs
    return new


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写入 docs.json（默认只预演）")
    args = ap.parse_args(argv)

    with DOCS_JSON.open(encoding="utf-8") as f:
        data = json.load(f)
    langs = data["navigation"]["languages"]
    existing = [l.get("language") for l in langs]
    if "ja" in existing:
        print(f"[warn] ja 块已存在（index={existing.index('ja')}），跳过。如需重建，先手动删除后再跑。")
        return 1

    zh_block = next(l for l in langs if l.get("language") == "zh")
    ja_block = build_ja_block(zh_block)

    print(f"[info] ja 块构造完成：tabs={len(ja_block['tabs'])}")
    for tab in ja_block["tabs"]:
        print(f"  - tab: {tab['tab']} (groups={len(tab['groups'])})")

    # 插入到 languages 数组末尾
    langs.append(ja_block)

    if not args.write:
        # 预演：把新块的前 1000 字符 print 出来
        preview = json.dumps(ja_block, ensure_ascii=False, indent=2)
        print("\n[preview ja block，前 2000 字符]：")
        print(preview[:2000])
        print(f"\n[hint] 加 --write 才会写入 {DOCS_JSON}")
        return 0

    with DOCS_JSON.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\n[ok] 已写入 {DOCS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
