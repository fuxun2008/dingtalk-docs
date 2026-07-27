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

# 国际版规范对齐：首组统一为「开始使用」（与文档/AI 表格 tab 一致）
GROUP_TITLE_MAP = {
    "宜搭简介": "开始使用",
}

# 顶层分组 icon（参考文档/AI 表格 tab 的 Font Awesome 图标规范）
GROUP_ICONS = {
    "开始使用": "rocket",
    "快速开始": "bolt",
    "表单管理": "clipboard-list",
    "流程设计": "diagram-project",
    "集成&自动化": "robot",
    "门户设计": "window-restore",
    "报表设计": "chart-column",
    "聚合表设计": "table-cells",
    "自定义页面": "code",
    "酷应用": "wand-magic-sparkles",
    "应用管理": "folder-gear",
    "平台管理": "user-gear",
    "国际化": "globe",
    "专属宜搭": "building-shield",
    "开发者功能": "terminal",
}

# 顶层分组展示顺序（引导类 → 核心搭建 → 页面扩展 → 管理运维 → 高级/开发者）
GROUP_ORDER = [
    "开始使用",
    "快速开始",
    "表单管理",
    "流程设计",
    "报表设计",
    "聚合表设计",
    "门户设计",
    "自定义页面",
    "集成&自动化",
    "酷应用",
    "应用管理",
    "平台管理",
    "国际化",
    "专属宜搭",
    "开发者功能",
]

for g in nav:
    g["group"] = GROUP_TITLE_MAP.get(g["group"], g["group"])
    icon = GROUP_ICONS.get(g["group"])
    if icon:
        # icon 放在 group 之后、pages 之前，与其他 tab 字段顺序一致
        pages = g.pop("pages")
        g["icon"] = icon
        g["pages"] = pages

known = {n: i for i, n in enumerate(GROUP_ORDER)}
unknown = [g["group"] for g in nav if g["group"] not in known]
if unknown:
    print("WARN 未配置排序/图标的分组（追加到末尾）:", unknown)
nav.sort(key=lambda g: known.get(g["group"], len(GROUP_ORDER)))

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
