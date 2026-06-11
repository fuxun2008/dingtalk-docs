#!/usr/bin/env python3
"""
按官方 docCenter API 真相重构 docs.json zh「开放平台」product 的两个 tab。

真相源（playwright 抓 https://open.dingtalk.com/api/docCenter/getDocInfoList?tabCode=...）：
  scripts/output/open_platform/menu/official_api_tree.json    服务端 API（tabCode=4a8AMF6u2A）
  scripts/output/open_platform/menu/official_guide_tree.json  开发指南（tabCode=XOnnmGCTbn）

产出：
  scripts/output/open_platform/nav/zh_guide_tab.json
  scripts/output/open_platform/nav/zh_api_tab.json
  scripts/output/open_platform/nav/restructure_report.md
"""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MENU_DIR = REPO / "scripts/output/open_platform/menu"
OUT_DIR = REPO / "scripts/output/open_platform/nav"

API_TREE_FILE = MENU_DIR / "official_api_tree.json"
GUIDE_TREE_FILE = MENU_DIR / "official_guide_tree.json"


# --------------------------------------------------------------------------
# 解析官方树
# --------------------------------------------------------------------------

def slug_from_url(url: str | None) -> str | None:
    if not url:
        return None
    # 形如 https://open.dingtalk.com/document/<namespace>/<slug>
    m = re.match(r"https?://[^/]+/document/[^/]+/([^/?#]+)", url)
    return m.group(1) if m else None


def namespace_from_url(url: str | None) -> str | None:
    """看 docUrl 落在哪个仓库子目录：development / dingstart / 其他。"""
    if not url:
        return None
    m = re.match(r"https?://[^/]+/document/([^/]+)/", url)
    return m.group(1) if m else None


def mdx_path(namespace: str, slug: str) -> Path:
    return REPO / "zh/open" / namespace / f"{slug}.mdx"


def build_tab(tab_name: str, official_tree: list[dict], default_namespace: str) -> tuple[dict, dict]:
    """递归把官方树映射成 Mintlify nav 嵌套结构，剪掉无本地 mdx 的子树。

    返回 (tab_block, stats)。
    tab_block: { "tab": ..., "groups": [...] }
    stats: { 'pages': int, 'kept_groups': int, 'dropped_groups': int,
             'missing_pages': [...], 'orphan_local_mdx': [...] }
    """
    stats = {
        "pages": 0,
        "kept_groups": 0,
        "dropped_groups": 0,
        "missing_pages": [],
        "used_slugs": set(),
    }

    def walk(node: dict) -> list | str | None:
        """返回 list[pages-and-subgroups] 或 单个 page slug str 或 None（丢弃）。"""
        name = node["docName"]
        children = node.get("children") or []
        if node.get("docType") != 0:
            # 叶子页（docType 1 / 2 均为带 docUrl 的页）
            url = node.get("docUrl")
            ns = namespace_from_url(url) or default_namespace
            slug = slug_from_url(url)
            if not slug:
                stats["missing_pages"].append({"docName": name, "reason": "no docUrl"})
                return None
            path = mdx_path(ns, slug)
            if not path.exists():
                stats["missing_pages"].append({"docName": name, "slug": slug, "ns": ns})
                return None
            stats["pages"] += 1
            stats["used_slugs"].add((ns, slug))
            return f"zh/open/{ns}/{slug}"

        # 目录节点
        items: list = []
        for c in children:
            r = walk(c)
            if r is None:
                continue
            if isinstance(r, str):
                items.append(r)
            elif isinstance(r, list):
                # 子组返回了 [{group:..., pages:[...]}]
                items.extend(r)
            elif isinstance(r, dict):
                items.append(r)

        if not items:
            stats["dropped_groups"] += 1
            return None
        stats["kept_groups"] += 1
        return [{"group": name, "pages": items}]

    groups: list = []
    for top in official_tree:
        r = walk(top)
        if r is None:
            continue
        if isinstance(r, list):
            groups.extend(r)
        elif isinstance(r, dict):
            groups.append(r)
        elif isinstance(r, str):
            # 顶级是裸页（罕见），裹一个 "其他" group
            groups.append({"group": "其他", "pages": [r]})

    tab_block = {"tab": tab_name, "groups": groups}
    return tab_block, stats


# --------------------------------------------------------------------------
# 校验
# --------------------------------------------------------------------------

def collect_local_mdx(namespace: str) -> set[str]:
    base = REPO / "zh/open" / namespace
    if not base.exists():
        return set()
    return {f.stem for f in base.glob("*.mdx")}


def find_orphan_local_mdx(namespace: str, used_slugs: set[tuple[str, str]]) -> list[str]:
    used = {slug for ns, slug in used_slugs if ns == namespace}
    return sorted(collect_local_mdx(namespace) - used)


def count_nesting(tab_block: dict) -> dict:
    max_depth = 0
    page_count = 0
    group_count = 0

    def walk(x, depth=0):
        nonlocal max_depth, page_count, group_count
        if isinstance(x, str):
            page_count += 1
            max_depth = max(max_depth, depth)
        elif isinstance(x, dict):
            if "group" in x:
                group_count += 1
            for p in x.get("pages", []):
                walk(p, depth + 1)

    for g in tab_block["groups"]:
        walk(g, 0)
    return {
        "top_groups": len(tab_block["groups"]),
        "total_groups": group_count,
        "pages": page_count,
        "max_depth": max_depth,
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    api_tree = json.loads(API_TREE_FILE.read_text())["result"]
    guide_tree = json.loads(GUIDE_TREE_FILE.read_text())["result"]

    api_block, api_stats = build_tab("服务端 API", api_tree, default_namespace="development")
    guide_block, guide_stats = build_tab("开发指南", guide_tree, default_namespace="dingstart")

    # 找孤儿（本地有 mdx 但官方树未引用）
    api_orphans = find_orphan_local_mdx("development", api_stats["used_slugs"])
    guide_orphans = find_orphan_local_mdx("dingstart", guide_stats["used_slugs"])

    (OUT_DIR / "zh_api_tab.json").write_text(
        json.dumps(api_block, ensure_ascii=False, indent=2) + "\n"
    )
    (OUT_DIR / "zh_guide_tab.json").write_text(
        json.dumps(guide_block, ensure_ascii=False, indent=2) + "\n"
    )

    # 报告
    api_n = count_nesting(api_block)
    guide_n = count_nesting(guide_block)
    lines: list[str] = []
    lines.append("# 开放平台 nav 重构报告（官方树版）\n")

    for label, block, stats, nest, orphans, ns in [
        ("服务端 API", api_block, api_stats, api_n, api_orphans, "development"),
        ("开发指南", guide_block, guide_stats, guide_n, guide_orphans, "dingstart"),
    ]:
        lines.append(f"## {label}\n")
        lines.append(f"- 顶级 group 数：{nest['top_groups']}")
        lines.append(f"- 累计 group 数（含嵌套子组）：{nest['total_groups']}")
        lines.append(f"- 总页数：{nest['pages']}")
        lines.append(f"- 最大嵌套深度：{nest['max_depth']}")
        lines.append(f"- 剪掉的空 group（官方有但本地无任何对应页）：{stats['dropped_groups']}")
        lines.append(f"- 官方树有但本地缺 mdx 的页数：{len(stats['missing_pages'])}")
        for m in stats["missing_pages"][:20]:
            lines.append(f"    - {m}")
        if len(stats["missing_pages"]) > 20:
            lines.append(f"    - ... 共 {len(stats['missing_pages'])} 条")
        lines.append(f"- 本地 zh/open/{ns}/ 下未挂入 nav 的孤儿 mdx：{len(orphans)}")
        for o in orphans[:30]:
            lines.append(f"    - zh/open/{ns}/{o}")
        if len(orphans) > 30:
            lines.append(f"    - ... 共 {len(orphans)} 条")
        lines.append("")
        lines.append(f"### {label} — 顶级 group 一览\n")
        for g in block["groups"]:
            sub = sum(1 for x in g["pages"] if isinstance(x, dict))
            page = sum(1 for x in g["pages"] if isinstance(x, str))
            extra = f"  ({sub} 子组)" if sub else ""
            lines.append(f"- **{g['group']}** — 直挂 {page} 页{extra}")
        lines.append("")

    (OUT_DIR / "restructure_report.md").write_text("\n".join(lines))

    print("=" * 60)
    print(f"产出：")
    print(f"  {OUT_DIR / 'zh_api_tab.json'}")
    print(f"  {OUT_DIR / 'zh_guide_tab.json'}")
    print(f"  {OUT_DIR / 'restructure_report.md'}")
    print()
    print(f"服务端 API: {api_n}")
    print(f"  缺页 {len(api_stats['missing_pages'])} / 孤儿 mdx {len(api_orphans)} / 剪空组 {api_stats['dropped_groups']}")
    print(f"开发指南: {guide_n}")
    print(f"  缺页 {len(guide_stats['missing_pages'])} / 孤儿 mdx {len(guide_orphans)} / 剪空组 {guide_stats['dropped_groups']}")


if __name__ == "__main__":
    main()
