#!/usr/bin/env python3
"""提取指定子产品 4 语言全部 mdx 的 frontmatter title 清单。

用法：python3 scripts/extract_docs_titles.py [--root docs]

输出 scripts/output/docs-titles/<root>-inventory.json：
  { slug: { "group": 导航group路径, "titles": {en,zh,ja,id}, "desc_zh": zh description } }

slug 为不带语言前缀的路径（如 docs/knowledge-base/about）。
导航 group 取自 docs.json zh 语言段（作为分类语境参考）。
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "scripts" / "output" / "docs-titles"

TITLE_RE = re.compile(r'^title:\s*"?(.*?)"?\s*$', re.M)
DESC_RE = re.compile(r'^description:\s*"?(.*?)"?\s*$', re.M)


def build_group_map() -> dict:
    """slug -> 'tab/group[/子group]' （zh 段）"""
    d = json.loads((ROOT / "docs.json").read_text(encoding="utf-8"))
    zh = next(l for l in d["navigation"]["languages"] if l["language"] == "zh")
    result = {}

    def walk(pages, path):
        for p in pages:
            if isinstance(p, dict):
                walk(p.get("pages", []), path + [p.get("group", "?")])
            else:
                slug = p[3:] if p.startswith("zh/") else p
                result[slug] = "/".join(path)

    for prod in zh["products"]:
        for t in prod.get("tabs", []):
            for g in t.get("groups", []):
                walk(g.get("pages", []), [t.get("tab", "?"), g.get("group", "?")])
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="docs", help="子产品目录名（docs/aitable/...）")
    args = ap.parse_args()
    lang_base = {"en": args.root, "zh": f"zh/{args.root}", "ja": f"ja/{args.root}", "id": f"id/{args.root}", "ms": f"ms/{args.root}"}

    group_map = build_group_map()
    inventory = {}
    for lang, base in lang_base.items():
        for f in sorted((ROOT / base).rglob("*.mdx")):
            rel = f.relative_to(ROOT)
            slug = str(rel)[:-4]  # 去 .mdx
            for pre in ("zh/", "ja/", "id/", "ms/"):
                if slug.startswith(pre):
                    slug = slug[len(pre):]
            head = f.read_text(encoding="utf-8")[:800]
            m = TITLE_RE.search(head)
            title = m.group(1) if m else None
            entry = inventory.setdefault(slug, {"group": group_map.get(slug, ""), "titles": {}, "desc_zh": ""})
            entry["titles"][lang] = title
            if lang == "zh":
                dm = DESC_RE.search(head)
                entry["desc_zh"] = dm.group(1)[:80] if dm else ""

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / f"{args.root}-inventory.json" if args.root != "docs" else OUT_DIR / "inventory.json"
    out_file.write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")

    # 摘要
    missing = {s: sorted({"en", "zh", "ja", "id", "ms"} - set(v["titles"])) for s, v in inventory.items()
               if len(v["titles"]) != 4}
    no_group = [s for s, v in inventory.items() if not v["group"]]
    print(f"[done] slug 总数: {len(inventory)}")
    print(f"[check] 四语不齐: {len(missing)} {missing if missing else ''}")
    print(f"[check] 未在导航注册: {len(no_group)} {no_group[:5] if no_group else ''}")


if __name__ == "__main__":
    main()
