#!/usr/bin/env python3
"""
在 docs.json 注册 en / ja / id 语言块的「宜搭 (Yida)」tab（帮助中心 product）。

实现：把 zh 块「帮助中心 → 宜搭」tab deepcopy
→ 译 tab 名 / group 名（三语映射表，缺失名保留中文并告警）
→ pages 路径 `zh/yida/` → `yida/`（en）/ `ja/yida/`（ja）/ `id/yida/`（id）
→ 追加到目标语言块 Help Center product 的 tabs 末尾（与 zh 位置一致）

幂等：目标语言块已有同名 tab 则整体替换。
保留键序、缩进 2、ensure_ascii=False、末尾换行（与 register_open_navigation.py 一致）。

用法：
  python3 scripts/register_yida_navigation.py                 # 预演（不写）
  python3 scripts/register_yida_navigation.py --write         # 写入 docs.json
  python3 scripts/register_yida_navigation.py --langs en --write
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_JSON = REPO_ROOT / "docs.json"

ZH_PRODUCT = "帮助中心"
ZH_TAB = "宜搭"

# 各语言 Help Center product 显示名
HELP_PRODUCT = {"en": "Help Center", "ja": "ヘルプセンター", "id": "Pusat Bantuan"}

TAB_NAME = {"en": "Yida", "ja": "Yida", "id": "Yida"}

PAGE_PREFIX = {"en": "yida/", "ja": "ja/yida/", "id": "id/yida/"}

# ============================================================
# group 名三语映射（zh → en / ja / id）
# ============================================================

GROUP_NAME_EN: dict[str, str] = {
    "开始使用": "Getting Started",
    "快速开始": "Quick Start",
    "创建第一个应用": "Create Your First App",
    "表单管理": "Form Management",
    "表单介绍": "Form Basics",
    "表单设计": "Form Design",
    "字段属性": "Field Properties",
    "常用字段": "Common Fields",
    "高级字段": "Advanced Fields",
    "行业字段（教育）": "Industry Fields (Education)",
    "公式函数": "Formula Functions",
    "表单自定义": "Form Customization",
    "组件属性": "Component Properties",
    "最佳实践": "Best Practices",
    "表单页面设置": "Form Page Settings",
    "打印设置": "Print Settings",
    "权限设置": "Permission Settings",
    "表单属性": "Form Properties",
    "表单业务规则": "Form Business Rules",
    "数据管理": "Data Management",
    "生成数据管理": "Generate Data Management",
    "流程设计": "Workflow Design",
    "流程节点介绍": "Workflow Nodes",
    "人工节点": "Manual Nodes",
    "分支节点": "Branch Nodes",
    "消息节点": "Message Nodes",
    "流程属性设置": "Workflow Property Settings",
    "流程使用": "Using Workflows",
    "流程中心": "Workflow Center",
    "高级流程": "Advanced Workflows",
    "报表设计": "Report Design",
    "报表组件": "Report Components",
    "字段设置": "Field Settings",
    "聚合表设计": "Aggregate Table Design",
    "门户设计": "Portal Design",
    "门户组件": "Portal Components",
    "自定义页面": "Custom Pages",
    "页面设计": "Page Design",
    "自定义页面设计器简介": "Custom Page Designer Overview",
    "自定义页面组件": "Custom Page Components",
    "集成&自动化": "Integration & Automation",
    "创建集成&自动化": "Create Integration & Automation",
    "触发类型": "Trigger Types",
    "配置集成&自动化": "Configure Integration & Automation",
    "节点介绍": "Node Overview",
    "酷应用": "Cool App",
    "酷应用设计": "Cool App Design",
    "酷SaaS工厂": "Cool SaaS Factory",
    "应用管理": "App Management",
    "创建应用": "Create Apps",
    "应用排序": "Sort Apps",
    "页面管理": "Page Management",
    "应用设置": "App Settings",
    "数据工厂": "Data Factory",
    "应用发布": "Publish Apps",
    "更多操作": "More Actions",
    "应用分发": "App Distribution",
    "平台管理": "Platform Management",
    "基本信息": "Basic Information",
    "宜搭角色管理": "Yida Role Management",
    "连接器工厂": "Connector Factory",
    "上下级组织分发应用": "Distribute Apps Across Organizations",
    "国际化": "Internationalization",
    "专属宜搭": "Yida Dedicated",
    "专属宜搭简介": "About Yida Dedicated",
    "空间管理": "Workspace Management",
    "管理工作空间": "Manage Workspaces",
    "空间 AI 助理": "Workspace AI Assistant",
    "企业效能": "Enterprise Efficiency",
    "互联 QuickBI": "QuickBI Integration",
    "存储配置": "Storage Configuration",
    "设计定制": "Design Customization",
    "管控中心": "Governance Center",
    "管理效率": "Management Efficiency",
    "专属域名": "Custom Domain",
    "应用全局配置": "Global App Configuration",
    "专属集群环境": "Dedicated Cluster Environment",
    "开发者功能": "Developer Features",
    "常见问题": "FAQ",
    "宜搭 Open API": "Yida Open API",
    "JS 动作面板": "JS Action Panel",
}

GROUP_NAME_JA: dict[str, str] = {
    "开始使用": "はじめに",
    "快速开始": "クイックスタート",
    "创建第一个应用": "最初のアプリを作成",
    "表单管理": "フォーム管理",
    "表单介绍": "フォームの概要",
    "表单设计": "フォーム設計",
    "字段属性": "フィールドプロパティ",
    "常用字段": "基本フィールド",
    "高级字段": "高度なフィールド",
    "行业字段（教育）": "業界フィールド（教育）",
    "公式函数": "数式関数",
    "表单自定义": "フォームのカスタマイズ",
    "组件属性": "コンポーネントプロパティ",
    "最佳实践": "ベストプラクティス",
    "表单页面设置": "フォームページ設定",
    "打印设置": "印刷設定",
    "权限设置": "権限設定",
    "表单属性": "フォームプロパティ",
    "表单业务规则": "フォームビジネスルール",
    "数据管理": "データ管理",
    "生成数据管理": "データ管理の生成",
    "流程设计": "ワークフロー設計",
    "流程节点介绍": "ワークフローノード",
    "人工节点": "手動ノード",
    "分支节点": "分岐ノード",
    "消息节点": "メッセージノード",
    "流程属性设置": "ワークフロープロパティ設定",
    "流程使用": "ワークフローの使用",
    "流程中心": "ワークフローセンター",
    "高级流程": "高度なワークフロー",
    "报表设计": "レポート設計",
    "报表组件": "レポートコンポーネント",
    "字段设置": "フィールド設定",
    "聚合表设计": "集計テーブル設計",
    "门户设计": "ポータル設計",
    "门户组件": "ポータルコンポーネント",
    "自定义页面": "カスタムページ",
    "页面设计": "ページ設計",
    "自定义页面设计器简介": "カスタムページデザイナーの概要",
    "自定义页面组件": "カスタムページコンポーネント",
    "集成&自动化": "統合と自動化",
    "创建集成&自动化": "統合と自動化の作成",
    "触发类型": "トリガータイプ",
    "配置集成&自动化": "統合と自動化の設定",
    "节点介绍": "ノードの概要",
    "酷应用": "クールアプリ",
    "酷应用设计": "クールアプリ設計",
    "酷SaaS工厂": "クール SaaS ファクトリー",
    "应用管理": "アプリ管理",
    "创建应用": "アプリの作成",
    "应用排序": "アプリの並べ替え",
    "页面管理": "ページ管理",
    "应用设置": "アプリ設定",
    "数据工厂": "データファクトリー",
    "应用发布": "アプリの公開",
    "更多操作": "その他の操作",
    "应用分发": "アプリ配布",
    "平台管理": "プラットフォーム管理",
    "基本信息": "基本情報",
    "宜搭角色管理": "Yida ロール管理",
    "连接器工厂": "コネクタファクトリー",
    "上下级组织分发应用": "上下組織へのアプリ配布",
    "国际化": "国際化",
    "专属宜搭": "Yida専用版",
    "专属宜搭简介": "Yida専用版の概要",
    "空间管理": "ワークスペース管理",
    "管理工作空间": "ワークスペースの管理",
    "空间 AI 助理": "ワークスペース AI アシスタント",
    "企业效能": "企業効率",
    "互联 QuickBI": "QuickBI 連携",
    "存储配置": "ストレージ設定",
    "设计定制": "デザインカスタマイズ",
    "管控中心": "管理センター",
    "管理效率": "管理効率",
    "专属域名": "専用ドメイン",
    "应用全局配置": "アプリのグローバル設定",
    "专属集群环境": "専用クラスタ環境",
    "开发者功能": "開発者機能",
    "常见问题": "よくある質問",
    "宜搭 Open API": "Yida Open API",
    "JS 动作面板": "JS アクションパネル",
}

GROUP_NAME_ID: dict[str, str] = {
    "开始使用": "Memulai",
    "快速开始": "Mulai Cepat",
    "创建第一个应用": "Buat Aplikasi Pertama Anda",
    "表单管理": "Manajemen Formulir",
    "表单介绍": "Pengenalan Formulir",
    "表单设计": "Desain Formulir",
    "字段属性": "Properti Field",
    "常用字段": "Field Umum",
    "高级字段": "Field Lanjutan",
    "行业字段（教育）": "Field Industri (Pendidikan)",
    "公式函数": "Fungsi Formula",
    "表单自定义": "Kustomisasi Formulir",
    "组件属性": "Properti Komponen",
    "最佳实践": "Praktik Terbaik",
    "表单页面设置": "Pengaturan Halaman Formulir",
    "打印设置": "Pengaturan Cetak",
    "权限设置": "Pengaturan Izin",
    "表单属性": "Properti Formulir",
    "表单业务规则": "Aturan Bisnis Formulir",
    "数据管理": "Manajemen Data",
    "生成数据管理": "Pembuatan Manajemen Data",
    "流程设计": "Desain Alur Kerja",
    "流程节点介绍": "Node Alur Kerja",
    "人工节点": "Node Manual",
    "分支节点": "Node Cabang",
    "消息节点": "Node Pesan",
    "流程属性设置": "Pengaturan Properti Alur Kerja",
    "流程使用": "Penggunaan Alur Kerja",
    "流程中心": "Pusat Alur Kerja",
    "高级流程": "Alur Kerja Lanjutan",
    "报表设计": "Desain Laporan",
    "报表组件": "Komponen Laporan",
    "字段设置": "Pengaturan Field",
    "聚合表设计": "Desain Tabel Agregat",
    "门户设计": "Desain Portal",
    "门户组件": "Komponen Portal",
    "自定义页面": "Halaman Kustom",
    "页面设计": "Desain Halaman",
    "自定义页面设计器简介": "Pengenalan Desainer Halaman Kustom",
    "自定义页面组件": "Komponen Halaman Kustom",
    "集成&自动化": "Integrasi & Otomatisasi",
    "创建集成&自动化": "Buat Integrasi & Otomatisasi",
    "触发类型": "Jenis Pemicu",
    "配置集成&自动化": "Konfigurasi Integrasi & Otomatisasi",
    "节点介绍": "Pengenalan Node",
    "酷应用": "Cool App",
    "酷应用设计": "Desain Cool App",
    "酷SaaS工厂": "Cool SaaS Factory",
    "应用管理": "Manajemen Aplikasi",
    "创建应用": "Buat Aplikasi",
    "应用排序": "Urutkan Aplikasi",
    "页面管理": "Manajemen Halaman",
    "应用设置": "Pengaturan Aplikasi",
    "数据工厂": "Data Factory",
    "应用发布": "Publikasikan Aplikasi",
    "更多操作": "Tindakan Lainnya",
    "应用分发": "Distribusi Aplikasi",
    "平台管理": "Manajemen Platform",
    "基本信息": "Informasi Dasar",
    "宜搭角色管理": "Manajemen Peran Yida",
    "连接器工厂": "Connector Factory",
    "上下级组织分发应用": "Distribusi Aplikasi Antar Organisasi",
    "国际化": "Internasionalisasi",
    "专属宜搭": "Yida Dedicated",
    "专属宜搭简介": "Tentang Yida Dedicated",
    "空间管理": "Manajemen Ruang Kerja",
    "管理工作空间": "Kelola Ruang Kerja",
    "空间 AI 助理": "Asisten AI Ruang Kerja",
    "企业效能": "Efisiensi Perusahaan",
    "互联 QuickBI": "Integrasi QuickBI",
    "存储配置": "Konfigurasi Penyimpanan",
    "设计定制": "Kustomisasi Desain",
    "管控中心": "Pusat Kontrol",
    "管理效率": "Efisiensi Manajemen",
    "专属域名": "Domain Khusus",
    "应用全局配置": "Konfigurasi Global Aplikasi",
    "专属集群环境": "Lingkungan Klaster Dedicated",
    "开发者功能": "Fitur Pengembang",
    "常见问题": "FAQ",
    "宜搭 Open API": "Yida Open API",
    "JS 动作面板": "Panel Aksi JS",
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
            if not item.startswith("zh/yida/"):
                sys.exit(f"ERROR: 非预期 page 路径（应以 zh/yida/ 开头）: {item}")
            out.append(prefix + item[len("zh/yida/"):])
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
    zh_hc = next(p for p in zh_block["products"] if p["product"] == ZH_PRODUCT)
    zh_tab = next(t for t in zh_hc["tabs"] if t.get("tab") == ZH_TAB)
    print(f"[info] zh 宜搭 tab：groups={len(zh_tab['groups'])} pages={count_pages(zh_tab)}")

    for lang in target_langs:
        block = next((l for l in langs if l["language"] == lang), None)
        if block is None:
            print(f"[skip] {lang} 语言块不存在")
            continue
        product = next((p for p in block["products"] if p["product"] == HELP_PRODUCT[lang]), None)
        if product is None:
            print(f"[skip] {lang} 缺 Help Center product ({HELP_PRODUCT[lang]})")
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
