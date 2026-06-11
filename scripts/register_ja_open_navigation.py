#!/usr/bin/env python3
"""
一次性脚本：在 docs.json 注册 ja 语言块（含 Help Center + Open Platform 两个产品）。

适配三层结构：languages[].products[].tabs[].groups[].pages[]

实现：deepcopy zh 块 → 译 product/tab/group 名 → pages 路径 `zh/` → `ja/`。
ja 块当前完全不存在；该脚本一次性补齐。

复用 register_ja_docs_navigation.py 的 Help Center group 映射 + 新增 Open Platform 80+ 条。

用法：
  python3 scripts/register_ja_open_navigation.py            # 预演
  python3 scripts/register_ja_open_navigation.py --write    # 写入
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_JSON = REPO_ROOT / "docs.json"


PRODUCT_NAME_MAP: dict[str, str] = {
    "帮助中心": "ヘルプセンター",
    "开放平台": "オープンプラットフォーム",
}

TAB_NAME_MAP: dict[str, str] = {
    # Help Center
    "文档": "ドキュメント",
    "AI 表格": "AI Table",
    # Open Platform
    "开发指南": "開発ガイド",
    "服务端 API": "サーバー API",
}

GROUP_NAME_MAP: dict[str, str] = {
    # ============ Help Center · 文档 tab ============
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
    # 钉钉表格 子组（部分名复用 — '编辑' / '格式' 等）
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
    # ============ Help Center · AI 表格 tab ============
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
    "字段类型列表": "フィールドタイプ一覧",
    "仪表盘组件": "ダッシュボードコンポーネント",
    "使用函数": "関数の使い方",
    "函数实践": "関数の活用例",
    "AI表格插件中心-使用指南": "AI Table プラグインセンター — 使い方ガイド",
    "网页采集助手-插件介绍和安装指南": "ウェブクリッパー — プラグインの紹介とインストールガイド",

    # ============ Open Platform · 开发指南 tab ============
    "平台简介": "プラットフォーム概要",
    "开发指南": "開発ガイド",  # group 名同 tab 名
    "开发机器人应用": "ボットアプリの開発",
    "企业机器人": "企業向けボット",
    "自定义机器人": "カスタムボット",

    # ============ Open Platform · 服务端 API tab ============
    "API 调用指南": "API 呼び出しガイド",
    "申请 API 权限": "API 権限の申請",
    "认证与授权": "認証と認可",
    "身份验证（免登）": "認証（シングルサインオン）",
    "访问凭证": "アクセス資格情報",
    "用户个人身份凭证": "ユーザー認証情報",
    "应用身份凭证": "アプリ認証情報",
    "JSAPI鉴权": "JSAPI 認証",
    # 通讯录管理
    "通讯录管理": "連絡先管理",
    "使用教程": "チュートリアル",
    "用户管理": "ユーザー管理",
    "部门管理": "部門管理",
    "角色管理": "ロール管理",
    "外部联系人": "社外連絡先",
    "企业账号": "企業アカウント",
    "企业管理": "企業管理",
    "通讯录ID转译": "連絡先 ID 変換",
    "通讯录可见性管理": "連絡先公開範囲管理",
    # 日程
    "日程": "スケジュール",
    "用户访问控制": "ユーザーアクセス制御",
    "日程参与者": "スケジュール参加者",
    "忙闲": "空き状況",
    "日历": "カレンダー",
    "会议室": "会議室",
    # 音视频
    "音视频": "オーディオ・ビデオ",
    "会议": "会議",
    "智能会议室": "スマート会議室",
    "会议室分组": "会議室グループ",
    "自定义屏幕模板": "カスタム画面テンプレート",
    # AI 表格 (Open Platform 下)
    "AI 表格": "AI Table",
    "数据表": "データテーブル",
    "字段": "フィールド",
    "记录": "レコード",
    # 文档/文件
    "文档/文件": "ドキュメント / ファイル",
    "知识库管理": "ナレッジベース管理",
    "知识库目录树管理": "ナレッジベース目次ツリー管理",
    "文档": "ドキュメント",
    "数据结构": "データ構造",
    "表格": "スプレッドシート",
    "工作表": "ワークシート",
    "行列": "行と列",
    "单元格区域": "セル範囲",
    "条件格式": "条件付き書式",
    "筛选": "フィルター",
    "筛选视图": "フィルタービュー",
    "浮动图片": "フローティング画像",
    "云盘（原钉盘）": "クラウドドライブ（旧 DingDrive）",
    "搜索": "検索",
    "群文件": "グループファイル",
    "媒体文件": "メディアファイル",
    "存储管理": "ストレージ管理",
    "应用管理": "アプリ管理",
    "空间管理": "領域管理",
    "文件管理": "ファイル管理",
    "文件传输": "ファイル転送",
    "分片上传": "マルチパートアップロード",
    "权限管理": "権限管理",
    "回收站管理": "ごみ箱管理",
    "任务管理": "タスク管理",
    "事件订阅": "イベント購読",
    # 即时通信
    "即时通信": "インスタントメッセージング",
    "机器人": "ボット",
    "单聊场景使用机器人": "1 対 1 チャットでボットを利用",
    "群聊场景使用机器人": "グループチャットでボットを利用",
    "发送普通消息": "通常メッセージの送信",
    "消息接收": "メッセージ受信",
    "消息查询": "メッセージクエリ",
    "消息撤回": "メッセージ取り消し",
    "机器人管理": "ボット管理",
    "快捷入口管理": "クイックアクセス管理",
    "会话管理": "会話管理",
    "群管理": "グループ管理",
    "消息通知": "メッセージ通知",
    "工作通知": "業務通知",
}


JA_NAVBAR = {
    "links": [{"label": "公式サイト", "href": "https://www.dingtalk.co.jp"}],
    "primary": {"type": "button", "label": "ダウンロード", "href": "https://www.dingtalk.co.jp/download"},
}

JA_FOOTER = {
    "socials": {
        "x": "https://x.com/DingTalkJapan",
        "instagram": "https://www.instagram.com/dingtalkjapan/",
        "linkedin": "https://www.linkedin.com/company/dingtalk",
    }
}


def translate_name(name: str, mapping: dict[str, str], kind: str) -> str:
    if name in mapping:
        return mapping[name]
    raise KeyError(f"未翻译的 {kind} 名：{name!r}（请在对应映射表补齐）")


def transform_pages(pages: list) -> list:
    out = []
    for item in pages:
        if isinstance(item, str):
            if item.startswith("zh/"):
                out.append("ja/" + item[3:])
            else:
                out.append(item)
        elif isinstance(item, dict):
            out.append(transform_group(item))
        else:
            out.append(item)
    return out


def transform_group(g: dict) -> dict:
    new = {}
    for k, v in g.items():
        if k == "group":
            new[k] = translate_name(v, GROUP_NAME_MAP, "group")
        elif k == "pages":
            new[k] = transform_pages(v)
        else:
            new[k] = v
    return new


def transform_tab(tab: dict) -> dict:
    new = {}
    for k, v in tab.items():
        if k == "tab":
            new[k] = translate_name(v, TAB_NAME_MAP, "tab")
        elif k == "groups":
            new[k] = [transform_group(g) for g in v]
        else:
            new[k] = v
    return new


def transform_product(prod: dict) -> dict:
    new = {}
    for k, v in prod.items():
        if k == "product":
            new[k] = translate_name(v, PRODUCT_NAME_MAP, "product")
        elif k == "tabs":
            new[k] = [transform_tab(t) for t in v]
        else:
            new[k] = v
    return new


def build_ja_block(zh_block: dict) -> dict:
    new = copy.deepcopy(zh_block)
    new["language"] = "ja"
    new["products"] = [transform_product(p) for p in new["products"]]
    new["navbar"] = JA_NAVBAR
    new["footer"] = JA_FOOTER
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

    print(f"[info] ja 块构造完成：products={len(ja_block['products'])}")
    for prod in ja_block["products"]:
        print(f"  - product: {prod['product']}")
        for tab in prod["tabs"]:
            print(f"      tab: {tab['tab']}  (groups={len(tab['groups'])})")

    langs.append(ja_block)

    if not args.write:
        preview = json.dumps(ja_block["products"][1] if len(ja_block["products"]) > 1 else ja_block["products"][0],
                             ensure_ascii=False, indent=2)
        print("\n[preview ja Open Platform 节点，前 2500 字符]：")
        print(preview[:2500])
        print(f"\n[hint] 加 --write 才会写入 {DOCS_JSON}")
        return 0

    with DOCS_JSON.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\n[ok] 已写入 {DOCS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
