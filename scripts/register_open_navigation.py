#!/usr/bin/env python3
"""
一次性脚本：在 docs.json 注册 en + ja 语言块的 Open Platform 产品。

实现：把 zh 块 products[1]（含「开发指南」+「服务端 API」两个 tab）deepcopy
→ 译 tab 名 / group 名 / subgroup 名 / subsubgroup 名
→ pages 路径 `zh/open/` → `open/`（en）或 `ja/open/`（ja）
→ 插入到 en / ja 语言块的 products 数组末尾

保留键序、缩进 2、ensure_ascii=False（中日字符直存）。

用法：
  python3 scripts/register_open_navigation.py            # 预演（不写）
  python3 scripts/register_open_navigation.py --write    # 写入 docs.json
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_JSON = REPO_ROOT / "docs.json"


# ============================================================
# TAB / GROUP 名翻译表（中文 → 英文 / 日文）
# ============================================================

PRODUCT_NAME_EN = "Open Platform"
PRODUCT_NAME_JA = "オープンプラットフォーム"

TAB_NAME_EN: dict[str, str] = {
    "开发指南": "Developer Guide",
    "服务端 API": "Server API",
}

TAB_NAME_JA: dict[str, str] = {
    "开发指南": "開発者ガイド",
    "服务端 API": "サーバー API",
}

# 所有 group / subgroup / subsubgroup 共用一个映射表（按现有 register_ja 模式）
GROUP_NAME_EN: dict[str, str] = {
    # ─── 开发指南 一级 group ───
    "平台简介": "Platform overview",
    "开发指南": "Developer guide",
    "开发机器人应用": "Build a bot app",
    # ─── 开发指南 二级 / 三级 ───
    "企业机器人": "Enterprise bot",
    "自定义机器人": "Custom bot",
    # ─── 服务端 API 一级 group ───
    "API 调用指南": "API calling guide",
    "认证与授权": "Authentication & authorization",
    "通讯录管理": "Contacts",
    "日程": "Calendar",
    "音视频": "Conferencing",
    "AI 表格": "AI Table",
    "文档/文件": "Docs & files",
    "即时通信": "IM",
    # ─── 服务端 API 二级 subgroup ───
    "申请 API 权限": "Request API permissions",
    "身份验证（免登）": "Identity authentication (silent login)",
    "访问凭证": "Access credentials",
    "使用教程": "Tutorials",
    "用户管理": "User management",
    "部门管理": "Department management",
    "角色管理": "Role management",
    "外部联系人": "External contacts",
    "企业账号": "Enterprise accounts",
    "企业管理": "Organization management",
    "通讯录ID转译": "Contact ID conversion",
    "通讯录可见性管理": "Contact visibility",
    "用户访问控制": "User access control",
    "日程参与者": "Event attendees",
    "忙闲": "Free/busy",
    "日历": "Calendars",
    "会议室": "Meeting rooms",
    "会议": "Conferences",
    "智能会议室": "Smart meeting rooms",
    "数据表": "Data tables",
    "字段": "Fields",
    "记录": "Records",
    "知识库": "Knowledge Base",
    "文档": "Documents",
    "表格": "Spreadsheets",
    "云盘（原钉盘）": "Drive (formerly DingDrive)",
    "搜索": "Search",
    "群文件": "Group files",
    "媒体文件": "Media files",
    "存储管理": "Storage management",
    "机器人": "Bots",
    "会话管理": "Conversations",
    "消息通知": "Notifications",
    # ─── 三级 subsubgroup ───
    "用户个人身份凭证": "User identity credentials",
    "应用身份凭证": "App identity credentials",
    "JSAPI鉴权": "JSAPI authentication",
    "会议室分组": "Meeting room groups",
    "自定义屏幕模板": "Custom screen templates",
    "知识库管理": "Knowledge base management",
    "知识库目录树管理": "Knowledge base tree management",
    "数据结构": "Data structures",
    "工作表": "Sheets",
    "行列": "Rows & columns",
    "单元格区域": "Cell ranges",
    "条件格式": "Conditional formatting",
    "筛选": "Filters",
    "筛选视图": "Filter views",
    "浮动图片": "Floating images",
    "应用管理": "App management",
    "空间管理": "Space management",
    "文件管理": "File management",
    "文件传输": "File transfer",
    "权限管理": "Permission management",
    "回收站管理": "Recycle bin",
    "任务管理": "Task management",
    "事件订阅": "Event subscription",
    "单聊场景使用机器人": "Bot in one-to-one chats",
    "群聊场景使用机器人": "Bot in group chats",
    "发送普通消息": "Send a plain message",
    "消息接收": "Receive messages",
    "消息查询": "Query messages",
    "消息撤回": "Recall messages",
    "机器人管理": "Bot management",
    "快捷入口管理": "Quick entry management",
    "群管理": "Group management",
    "工作通知": "Work notifications",
    "分片上传": "Multipart upload",
}

GROUP_NAME_JA: dict[str, str] = {
    # ─── 开发指南 一级 group ───
    "平台简介": "プラットフォーム概要",
    "开发指南": "開発者ガイド",
    "开发机器人应用": "ボットアプリの開発",
    # ─── 开发指南 二级 / 三级 ───
    "企业机器人": "社内ボット",
    "自定义机器人": "カスタムボット",
    # ─── 服务端 API 一级 group ───
    "API 调用指南": "API 呼び出しガイド",
    "认证与授权": "認証と認可",
    "通讯录管理": "連絡先管理",
    "日程": "予定",
    "音视频": "会議",
    "AI 表格": "AI Table",
    "文档/文件": "ドキュメント / ファイル",
    "即时通信": "IM",
    # ─── 服务端 API 二级 subgroup ───
    "申请 API 权限": "API 権限のリクエスト",
    "身份验证（免登）": "認証 (サイレントログイン)",
    "访问凭证": "アクセス認証情報",
    "使用教程": "チュートリアル",
    "用户管理": "ユーザー管理",
    "部门管理": "部門管理",
    "角色管理": "ロール管理",
    "外部联系人": "社外連絡先",
    "企业账号": "企業アカウント",
    "企业管理": "組織管理",
    "通讯录ID转译": "連絡先 ID 変換",
    "通讯录可见性管理": "連絡先の可視範囲",
    "用户访问控制": "ユーザーアクセス制御",
    "日程参与者": "予定参加者",
    "忙闲": "フリー/ビジー",
    "日历": "カレンダー",
    "会议室": "会議室",
    "会议": "会議",
    "智能会议室": "スマート会議室",
    "数据表": "データテーブル",
    "字段": "フィールド",
    "记录": "レコード",
    "知识库": "ナレッジベース",
    "文档": "ドキュメント",
    "表格": "スプレッドシート",
    "云盘（原钉盘）": "ドライブ (旧 DingDrive)",
    "搜索": "検索",
    "群文件": "グループファイル",
    "媒体文件": "メディアファイル",
    "存储管理": "ストレージ管理",
    "机器人": "ボット",
    "会话管理": "会話管理",
    "消息通知": "メッセージ通知",
    # ─── 三级 subsubgroup ───
    "用户个人身份凭证": "ユーザー認証情報",
    "应用身份凭证": "アプリ認証情報",
    "JSAPI鉴权": "JSAPI 認証",
    "会议室分组": "会議室グループ",
    "自定义屏幕模板": "カスタム画面テンプレート",
    "知识库管理": "ナレッジベース管理",
    "知识库目录树管理": "ナレッジベースのツリー管理",
    "数据结构": "データ構造",
    "工作表": "シート",
    "行列": "行と列",
    "单元格区域": "セル範囲",
    "条件格式": "条件付き書式",
    "筛选": "フィルター",
    "筛选视图": "フィルタービュー",
    "浮动图片": "フローティング画像",
    "应用管理": "アプリ管理",
    "空间管理": "スペース管理",
    "文件管理": "ファイル管理",
    "文件传输": "ファイル転送",
    "权限管理": "権限管理",
    "回收站管理": "ゴミ箱管理",
    "任务管理": "タスク管理",
    "事件订阅": "イベントサブスクリプション",
    "单聊场景使用机器人": "1 対 1 チャットでのボット",
    "群聊场景使用机器人": "グループチャットでのボット",
    "发送普通消息": "通常メッセージの送信",
    "消息接收": "メッセージの受信",
    "消息查询": "メッセージの照会",
    "消息撤回": "メッセージの取り消し",
    "机器人管理": "ボット管理",
    "快捷入口管理": "クイックエントリ管理",
    "群管理": "グループ管理",
    "工作通知": "業務通知",
    "分片上传": "マルチパートアップロード",
}


# ============================================================
# 转换工具
# ============================================================

def translate_tab(name: str, lang: str) -> str:
    table = TAB_NAME_EN if lang == "en" else TAB_NAME_JA
    if name not in table:
        raise KeyError(f"未翻译的 tab 名 [{lang}]: {name!r}")
    return table[name]


def translate_group(name: str, lang: str) -> str:
    table = GROUP_NAME_EN if lang == "en" else GROUP_NAME_JA
    if name not in table:
        raise KeyError(f"未翻译的 group 名 [{lang}]: {name!r}")
    return table[name]


def transform_path(path: str, lang: str) -> str:
    """zh/open/foo → open/foo (en) 或 ja/open/foo (ja)"""
    if not path.startswith("zh/open/"):
        return path
    rest = path[len("zh/"):]   # open/foo
    if lang == "en":
        return rest
    return f"ja/{rest}"


def transform_pages(pages: list, lang: str) -> list:
    out = []
    for item in pages:
        if isinstance(item, str):
            out.append(transform_path(item, lang))
        elif isinstance(item, dict):
            out.append(transform_group_node(item, lang))
        else:
            out.append(item)
    return out


def transform_group_node(g: dict, lang: str) -> dict:
    new = {}
    for k, v in g.items():
        if k == "group":
            new[k] = translate_group(v, lang)
        elif k == "pages":
            new[k] = transform_pages(v, lang)
        else:
            new[k] = v
    return new


def build_open_product(zh_open_product: dict, lang: str) -> dict:
    new = copy.deepcopy(zh_open_product)
    # 翻 product 显示名
    if "product" in new:
        new["product"] = PRODUCT_NAME_EN if lang == "en" else PRODUCT_NAME_JA
    new_tabs = []
    for tab in new.get("tabs", []):
        new_tab = {}
        for k, v in tab.items():
            if k == "tab":
                new_tab[k] = translate_tab(v, lang)
            elif k == "groups":
                new_tab[k] = [transform_group_node(g, lang) for g in v]
            else:
                new_tab[k] = v
        new_tabs.append(new_tab)
    new["tabs"] = new_tabs
    return new


def find_open_product(lang_block: dict) -> int | None:
    """在一个 language block 的 products 数组里找含 zh/open 或 open/ 路径的 product 的索引。"""
    def has_path_with(node, prefix: str) -> bool:
        if isinstance(node, str): return node.startswith(prefix)
        if isinstance(node, list): return any(has_path_with(x, prefix) for x in node)
        if isinstance(node, dict): return any(has_path_with(v, prefix) for v in node.values())
        return False
    for i, p in enumerate(lang_block.get("products", [])):
        if has_path_with(p, "zh/open") or has_path_with(p, "open/") or has_path_with(p, "ja/open"):
            return i
    return None


# ============================================================
# 主流程
# ============================================================

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写入 docs.json（默认只预演）")
    ap.add_argument("--langs", default="en,ja", help="目标语言，逗号分隔（默认 en,ja）")
    args = ap.parse_args(argv)
    target_langs = [l.strip() for l in args.langs.split(",") if l.strip()]

    with DOCS_JSON.open(encoding="utf-8") as f:
        data = json.load(f)
    langs = data["navigation"]["languages"]

    # 找 zh 块的 open product
    zh_block = next(l for l in langs if l.get("language") == "zh")
    zh_idx = find_open_product(zh_block)
    if zh_idx is None:
        print("[err] zh 块未找到 open product，无法继续")
        return 1
    zh_open = zh_block["products"][zh_idx]
    print(f"[info] 找到 zh open product (products[{zh_idx}])，tabs={len(zh_open.get('tabs',[]))}")

    for lang in target_langs:
        target_block = next((l for l in langs if l.get("language") == lang), None)
        if target_block is None:
            print(f"[skip] {lang} 语言块不存在 — 本批次只替换 en 占位，ja 块缺失留后续 issue 处理")
            continue

        new_product = build_open_product(zh_open, lang)
        print(f"\n[{lang}] 构造 open product OK，tabs:")
        for tab in new_product["tabs"]:
            print(f"  - {tab['tab']} (groups={len(tab['groups'])})")

        existing_idx = find_open_product(target_block)
        products = target_block.setdefault("products", [])
        if existing_idx is None:
            print(f"[{lang}] 追加到 products 末尾（原 count={len(products)} → {len(products)+1}）")
            products.append(new_product)
        else:
            existing = products[existing_idx]
            existing_tab_count = sum(1 for _ in existing.get("tabs", []))
            existing_group_count = sum(len(t.get("groups", [])) for t in existing.get("tabs", []))
            print(f"[{lang}] 检测到 products[{existing_idx}] 已存在 open product（tabs={existing_tab_count} groups={existing_group_count}）")
            if existing_group_count < 5:
                print(f"[{lang}] 判定为占位（groups<5），替换为完整结构")
                products[existing_idx] = new_product
            else:
                print(f"[{lang}] 已存在的不是占位（groups>=5），跳过避免误覆盖。如需强制覆盖请手动清理后重跑")
                continue

    if not args.write:
        # 预演：把每个 lang 新 product 的前 1500 字符 print
        for lang in target_langs:
            target_block = next((l for l in langs if l.get("language") == lang), None)
            if target_block and target_block.get("products"):
                last = target_block["products"][-1]
                preview = json.dumps(last, ensure_ascii=False, indent=2)
                print(f"\n[preview {lang} open product，前 1500 字符]：")
                print(preview[:1500])
        print(f"\n[hint] 加 --write 才会写入 {DOCS_JSON}")
        return 0

    with DOCS_JSON.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\n[ok] 已写入 {DOCS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
