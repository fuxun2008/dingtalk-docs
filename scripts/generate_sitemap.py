#!/usr/bin/env python3
"""Generate sitemap.xml for help.dingtalk.io from all .mdx files.

Each <url> block carries <xhtml:link rel="alternate" hreflang="..."> siblings
that point to its peers in the trilingual mirror (en / zh-CN / ja-JP), plus
x-default to the en version. Pages that lack a localization are still listed,
but only with hreflang entries for languages whose .mdx actually exists.
"""

import os
import xml.etree.ElementTree as ET
from pathlib import Path

BASE_URL = "https://help.dingtalk.io"
DOCS_ROOT = Path(__file__).resolve().parent.parent
IGNORE_DIRS = {
    "node_modules", ".git", ".claude", ".mintlify", "scripts",
    "tools", ".cursor", ".codex", ".qoder", ".agent", ".agents",
    ".aoneci", ".husky", ".vscode", "dev-certs", "ci", "conf",
    "public", "assets",
}
VALID_TOP_DIRS = {
    "ai-minutes", "aitable", "approval", "attendance", "calendar", "contacts",
    "docs", "drive", "im", "mail", "meetings", "oa", "open", "yida",
    "zh", "ja", "id",
}

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
XHTML_NS = "http://www.w3.org/1999/xhtml"

# Hreflang tags. zh maps to zh-CN (Simplified, mainland);
# ja maps to ja-JP. en and id stay plain (no regional qualifier).
LANG_TAGS = {"en": "en", "zh": "zh-CN", "ja": "ja-JP", "id": "id"}
DEFAULT_LANG = "en"  # what x-default points to

# Register namespaces so ElementTree emits the expected prefixes.
ET.register_namespace("", SITEMAP_NS)
ET.register_namespace("xhtml", XHTML_NS)


def collect_mdx_paths():
    """Collect all .mdx file paths relative to DOCS_ROOT."""
    results = []
    for root, dirs, files in os.walk(DOCS_ROOT):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        rel_root = Path(root).relative_to(DOCS_ROOT)
        top = rel_root.parts[0] if rel_root.parts else None
        if top and top not in VALID_TOP_DIRS:
            continue
        for f in files:
            if f.endswith(".mdx"):
                full = Path(root) / f
                rel = full.relative_to(DOCS_ROOT)
                results.append(rel)
    return sorted(results)


def classify(rel_path: Path):
    """Split a relative .mdx path into (lang, base_parts).

    base_parts is the slug path with the lang prefix stripped, .mdx removed,
    and trailing "index" collapsed (so /im/index.mdx -> ("en", ["im"])).
    """
    parts = list(rel_path.parts)
    if parts and parts[0] in ("zh", "ja", "id"):
        lang = parts[0]
        base_parts = parts[1:]
    else:
        lang = "en"
        base_parts = parts[:]
    if base_parts:
        base_parts[-1] = base_parts[-1].replace(".mdx", "")
        if base_parts[-1] == "index":
            base_parts = base_parts[:-1]
    return lang, base_parts


def url_for(lang: str, base_parts: list) -> str:
    """Build the canonical URL for a (lang, base_parts) tuple."""
    segments = []
    if lang != "en":
        segments.append(lang)
    segments.extend(base_parts)
    path = "/".join(segments)
    if not path:
        return f"{BASE_URL}/"
    return f"{BASE_URL}/{path}"


def _make(parent: ET.Element, ns: str, tag: str, **attrib) -> ET.Element:
    elem = ET.SubElement(parent, f"{{{ns}}}{tag}", attrib=attrib)
    return elem


def emit(urlset: ET.Element, lang: str, base_parts: list,
         langs_present: dict, is_home: bool) -> None:
    url_el = _make(urlset, SITEMAP_NS, "url")
    loc = _make(url_el, SITEMAP_NS, "loc")
    loc.text = url_for(lang, base_parts)

    # hreflang siblings — only for languages whose .mdx actually exists.
    for alt_lang in ("en", "zh", "ja", "id"):
        if alt_lang not in langs_present:
            continue
        _make(
            url_el, XHTML_NS, "link",
            rel="alternate",
            hreflang=LANG_TAGS[alt_lang],
            href=url_for(alt_lang, base_parts),
        )
    # x-default points to en if present (fallback for unknown locales).
    if DEFAULT_LANG in langs_present:
        _make(
            url_el, XHTML_NS, "link",
            rel="alternate",
            hreflang="x-default",
            href=url_for(DEFAULT_LANG, base_parts),
        )

    cf = _make(url_el, SITEMAP_NS, "changefreq")
    cf.text = "daily" if is_home else "weekly"
    pr = _make(url_el, SITEMAP_NS, "priority")
    pr.text = "1.0" if is_home else "0.7"


def main():
    mdx_paths = collect_mdx_paths()
    print(f"Found {len(mdx_paths)} .mdx files")

    # Build base_key -> {lang: True} so emit() knows which alternates exist.
    base_lang_map: dict = {}
    for rel in mdx_paths:
        lang, base_parts = classify(rel)
        base_key = "/".join(base_parts)
        base_lang_map.setdefault(base_key, {})[lang] = True

    urlset = ET.Element(f"{{{SITEMAP_NS}}}urlset")

    # Note: lastmod is intentionally omitted to keep sitemap.xml deterministic.
    # The pre-push hook re-runs this script and compares output; date-based
    # lastmod would cause spurious daily diffs. Google does not strongly
    # trust sitemap lastmod anyway.

    # 1) Homepages: en first (priority 1.0 daily — primary), then zh/ja/id.
    home_langs = base_lang_map.get("", {})
    if "en" in home_langs:
        emit(urlset, "en", [], home_langs, is_home=True)
    for lang in ("zh", "ja", "id"):
        if lang in home_langs:
            emit(urlset, lang, [], home_langs, is_home=False)

    # 2) Other pages in deterministic mdx_paths order.
    for rel in mdx_paths:
        lang, base_parts = classify(rel)
        base_key = "/".join(base_parts)
        if base_key == "":
            continue  # homepages already emitted
        emit(urlset, lang, base_parts, base_lang_map[base_key], is_home=False)

    tree = ET.ElementTree(urlset)
    out = DOCS_ROOT / "sitemap.xml"
    ET.indent(tree, space="  ")
    tree.write(str(out), encoding="utf-8", xml_declaration=True)

    en = sum(1 for p in mdx_paths if classify(p)[0] == "en")
    zh = sum(1 for p in mdx_paths if classify(p)[0] == "zh")
    ja = sum(1 for p in mdx_paths if classify(p)[0] == "ja")
    idn = sum(1 for p in mdx_paths if classify(p)[0] == "id")
    print(f"  EN: {en}, ZH: {zh}, JA: {ja}, ID: {idn}")
    print(f"  Unique base paths: {len(base_lang_map)}")
    print(f"Written to {out} ({out.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
