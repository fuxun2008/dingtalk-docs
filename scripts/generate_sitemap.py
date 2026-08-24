#!/usr/bin/env python3
"""Generate sitemap files for help.dingtalk.io from all .mdx files.

Outputs:
  - sitemap.xml        : legacy combined sitemap (all languages in one file)
  - sitemap-en.xml     : English-only URLs with hreflang alternates
  - sitemap-zh.xml     : Simplified Chinese URLs with hreflang alternates
  - sitemap-ja.xml     : Japanese URLs with hreflang alternates
  - sitemap-id.xml     : Indonesian URLs with hreflang alternates
  - sitemapindex.xml   : index pointing to each per-language sitemap

Each <url> block carries <xhtml:link rel="alternate" hreflang="..."> siblings
that point to its peers. Pages that lack a localization are still listed,
but only with hreflang entries for languages whose .mdx actually exists.

Run manually:  python3 scripts/generate_sitemap.py
Or via hook:  the pre-commit hook runs this automatically when .mdx files change.
"""

import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

BASE_URL = "https://help.dingtalk.io"
DOCS_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = DOCS_ROOT / "public"
IGNORE_DIRS = {
    "node_modules", ".git", ".claude", ".mintlify", "scripts",
    "tools", ".cursor", ".codex", ".qoder", ".agent", ".agents",
    ".aoneci", ".husky", ".vscode", "dev-certs", "ci", "conf",
    "public", "assets",
}
VALID_TOP_DIRS = {
    "ai-minutes", "aitable", "approval", "attendance", "calendar", "contacts",
    "docs", "drive", "im", "mail", "meetings", "oa", "open", "yida",
    "zh", "ja", "id", "ms",
}

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
XHTML_NS = "http://www.w3.org/1999/xhtml"

# Hreflang tags. zh maps to zh-CN (Simplified, mainland);
# ja maps to ja-JP. en, id, and ms stay plain (no regional qualifier).
LANG_TAGS = {"en": "en", "zh": "zh-CN", "ja": "ja-JP", "id": "id", "ms": "ms"}
DEFAULT_LANG = "en"  # what x-default points to
SUPPORTED_LANGS = ("en", "zh", "ja", "id", "ms")

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
    if parts and parts[0] in ("zh", "ja", "id", "ms"):
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
    for alt_lang in SUPPORTED_LANGS:
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


def build_urlset():
    """Build the legacy combined urlset and per-language urlsets."""
    mdx_paths = collect_mdx_paths()

    # base_key -> {lang: True}
    base_lang_map: dict = {}
    for rel in mdx_paths:
        lang, base_parts = classify(rel)
        base_key = "/".join(base_parts)
        base_lang_map.setdefault(base_key, {})[lang] = True

    # Combined sitemap (legacy)
    combined = ET.Element(f"{{{SITEMAP_NS}}}urlset")

    # Per-language sitemaps
    per_lang = {lang: ET.Element(f"{{{SITEMAP_NS}}}urlset") for lang in SUPPORTED_LANGS}

    # Note: lastmod is intentionally omitted to keep sitemap.xml deterministic.
    # The pre-push hook re-runs this script and compares output; date-based
    # lastmod would cause spurious daily diffs. Google does not strongly
    # trust sitemap lastmod anyway.

    # 1) Homepages: en first (priority 1.0 daily — primary), then zh/ja/id/ms.
    home_langs = base_lang_map.get("", {})
    if "en" in home_langs:
        emit(combined, "en", [], home_langs, is_home=True)
    for lang in ("zh", "ja", "id", "ms"):
        if lang in home_langs:
            emit(combined, lang, [], home_langs, is_home=False)

    # Same homepages in per-language sitemaps
    for lang in SUPPORTED_LANGS:
        if lang in home_langs:
            emit(per_lang[lang], lang, [], home_langs, is_home=(lang == "en"))

    # 2) Other pages in deterministic mdx_paths order.
    for rel in mdx_paths:
        lang, base_parts = classify(rel)
        base_key = "/".join(base_parts)
        if base_key == "":
            continue  # homepages already emitted
        emit(combined, lang, base_parts, base_lang_map[base_key], is_home=False)
        emit(per_lang[lang], lang, base_parts, base_lang_map[base_key], is_home=False)

    return mdx_paths, base_lang_map, combined, per_lang


def write_xml(tree: ET.ElementTree, path: Path) -> None:
    ET.indent(tree, space="  ")
    tree.write(str(path), encoding="utf-8", xml_declaration=True)


def build_sitemapindex() -> ET.ElementTree:
    """Build sitemapindex.xml referencing each per-language sitemap."""
    root = ET.Element(f"{{{SITEMAP_NS}}}sitemapindex")
    for lang in SUPPORTED_LANGS:
        sitemap_el = _make(root, SITEMAP_NS, "sitemap")
        loc = _make(sitemap_el, SITEMAP_NS, "loc")
        loc.text = f"{BASE_URL}/sitemap-{lang}.xml"
    return ET.ElementTree(root)


def build_robots_txt() -> str:
    """Build robots.txt content pointing search engines to sitemapindex.xml.

    We only list sitemapindex.xml here because it already references every
    per-language sitemap. Listing all files would be redundant and can waste
    crawl budget.
    """
    lines = [
        "User-agent: *",
        "Disallow:",
        "",
        f"Sitemap: {BASE_URL}/sitemapindex.xml",
        "",
    ]
    return "\n".join(lines)


def main():
    mdx_paths, base_lang_map, combined, per_lang = build_urlset()
    print(f"Found {len(mdx_paths)} .mdx files")

    # Ensure public/ directory exists for static assets served at site root.
    PUBLIC_DIR.mkdir(exist_ok=True)

    # Write legacy combined sitemap
    write_xml(ET.ElementTree(combined), PUBLIC_DIR / "sitemap.xml")

    # Write per-language sitemaps
    for lang in SUPPORTED_LANGS:
        out_path = PUBLIC_DIR / f"sitemap-{lang}.xml"
        write_xml(ET.ElementTree(per_lang[lang]), out_path)
        url_count = sum(
            1 for p in mdx_paths if classify(p)[0] == lang
        ) + (1 if "" in base_lang_map and lang in base_lang_map[""] else 0)
        print(f"  Written {out_path.name}: {url_count} URLs")

    # Write sitemap index
    index_tree = build_sitemapindex()
    write_xml(index_tree, PUBLIC_DIR / "sitemapindex.xml")
    print(f"  Written sitemapindex.xml")

    # Write robots.txt at repository root (Mintlify serves it from the site root).
    robots_path = DOCS_ROOT / "robots.txt"
    robots_path.write_text(build_robots_txt(), encoding="utf-8")
    print(f"  Written robots.txt")

    en = sum(1 for p in mdx_paths if classify(p)[0] == "en")
    zh = sum(1 for p in mdx_paths if classify(p)[0] == "zh")
    ja = sum(1 for p in mdx_paths if classify(p)[0] == "ja")
    idn = sum(1 for p in mdx_paths if classify(p)[0] == "id")
    print(f"  EN: {en}, ZH: {zh}, JA: {ja}, ID: {idn}")
    print(f"  Unique base paths: {len(base_lang_map)}")

    combined_size = (PUBLIC_DIR / "sitemap.xml").stat().st_size / 1024
    print(f"  sitemap.xml: {combined_size:.1f} KB")


def mdx_changed() -> bool:
    """Check whether any staged .mdx files are about to be committed.

    Used by the pre-commit hook. Returns True if the sitemap should be regenerated.
    """
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM", "--", "*.mdx"],
        capture_output=True, text=True, check=False,
    )
    return bool(result.stdout.strip())


def run_as_hook():
    """Entry point for git pre-commit hook."""
    if not mdx_changed():
        print("[sitemap-hook] no .mdx changes; skipping sitemap regeneration")
        sys.exit(0)

    print("[sitemap-hook] .mdx files changed; regenerating sitemaps...")
    main()

    # Stage regenerated sitemaps (in public/) and robots.txt so they are
    # included in the current commit.
    subprocess.run(
        ["git", "add", "public/sitemap.xml", "public/sitemap-en.xml",
         "public/sitemap-zh.xml", "public/sitemap-ja.xml",
         "public/sitemap-id.xml", "public/sitemapindex.xml", "robots.txt"],
        check=False,
    )
    print("[sitemap-hook] sitemaps and robots.txt regenerated and staged.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--hook":
        run_as_hook()
    else:
        main()
