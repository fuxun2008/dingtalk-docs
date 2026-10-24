#!/usr/bin/env python3
"""
从开放平台服务端 API 官方菜单树生成指定模块的抓取清单（fetch_list.json 格式）。

输入：scripts/output/open_platform/menu/official_api_tree.json（getDocInfoList 缓存）
输出：$OPEN_OUT_DIR/menu/fetch_list.json  —— crawl_open_platform.py fetch 消费
      $OPEN_OUT_DIR/menu/module_tree.json —— 保留官方分组 / 顺序，供后续注册导航

用法：
  OPEN_OUT_DIR=scripts/output/open_platform_attend_oa \\
    python3 scripts/build_open_fetch_list.py \\
      --module 九、考勤=QxpOlz8Sdh \\
      --module 十、OA 审批=7hFKPxrVVj \\
      --skip-dir 高级版专享接口
  可选 --check-meta：对照线上 development/meta.json 报告菜单里已下线 / 不在 OSS 的 slug
"""
import argparse
import json
import os
import sys
from pathlib import Path

import httpx

HERE = Path(__file__).parent
TREE_JSON = HERE / "output" / "open_platform" / "menu" / "official_api_tree.json"
OUT_DIR = Path(os.environ.get("OPEN_OUT_DIR") or HERE / "output" / "open_platform")
MENU_DIR = OUT_DIR / "menu"

OSS_BASE = "https://icms-document.oss-cn-beijing.aliyuncs.com/zh-CN/dingtalk/development"
SITE_URL = "https://open.dingtalk.com/document/development/{slug}"


def find_node(nodes: list, doc_id: str):
    for n in nodes:
        if n.get("docId") == doc_id:
            return n
        hit = find_node(n.get("children") or [], doc_id)
        if hit:
            return hit
    return None


def slug_of(node: dict) -> str:
    return (node.get("docUrl") or "").rstrip("/").split("/")[-1]


def walk(node: dict, path: list[str], skip_dirs: set[str]):
    """深度优先产出 (module_path, title, slug)，并返回裁剪后的子树。"""
    items, children = [], []
    for c in sorted(node.get("children") or [], key=lambda x: x.get("sort", 0)):
        if c.get("docType") == 0:
            if c["docName"] in skip_dirs:
                continue
            sub_items, sub_tree = walk(c, path + [c["docName"]], skip_dirs)
            items += sub_items
            children.append(sub_tree)
        else:
            s = slug_of(c)
            items.append((" / ".join(path), c["docName"], s))
            children.append({"title": c["docName"], "slug": s})
    return items, {"group": node["docName"], "children": children}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--module", action="append", required=True,
                    help="<模块路径前缀>=<docId>，可重复")
    ap.add_argument("--skip-dir", action="append", default=[],
                    help="跳过的目录名（任意层级），可重复")
    ap.add_argument("--check-meta", action="store_true",
                    help="对照线上 meta.json 标出不在 OSS 的 slug")
    args = ap.parse_args()

    data = json.loads(TREE_JSON.read_text())
    roots = data["result"] if isinstance(data, dict) else data
    skip = set(args.skip_dir)

    fetch_list, trees = [], []
    for spec in args.module:
        prefix, _, doc_id = spec.rpartition("=")
        node = find_node(roots, doc_id)
        if not node:
            print(f"ERROR: docId {doc_id} not found", file=sys.stderr)
            return 2
        items, tree = walk(node, [prefix], skip)
        trees.append({"module": prefix, "doc_id": doc_id, **tree})
        for module_path, title, slug in items:
            fetch_list.append({
                "namespace": "development",
                "slug": slug,
                "title": title,
                "module_path": module_path,
                "url": f"{OSS_BASE}/topics/{slug}.html",
                "source_url": SITE_URL.format(slug=slug),
                "source": "official_tree",
            })
        print(f"{prefix}: {len(items)} docs")

    if args.check_meta:
        meta = httpx.get(f"{OSS_BASE}/meta.json", headers={"Referer": "https://open.dingtalk.com/"}, timeout=30).json()
        online = set()

        def collect(n):
            if isinstance(n, list):
                for x in n:
                    collect(x)
            elif isinstance(n, dict):
                if n.get("slug"):
                    online.add(n["slug"])
                collect(n.get("topics") or [])
                collect(n.get("children") or [])
        collect(meta)
        missing = [it["slug"] for it in fetch_list if it["slug"] not in online]
        print(f"meta.json: {len(online)} slugs online; not in OSS meta: {len(missing)}")
        for s in missing:
            print(f"  - {s}")

    MENU_DIR.mkdir(parents=True, exist_ok=True)
    (MENU_DIR / "fetch_list.json").write_text(json.dumps(fetch_list, ensure_ascii=False, indent=2) + "\n")
    (MENU_DIR / "module_tree.json").write_text(json.dumps(trees, ensure_ascii=False, indent=2) + "\n")
    print(f"→ {MENU_DIR / 'fetch_list.json'} ({len(fetch_list)} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
