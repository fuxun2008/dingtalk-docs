#!/usr/bin/env python3
"""Generate sitemap.xml for help.dingtalk.io from all .mdx files."""

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
# Top-level content directories that are valid doc paths
VALID_TOP_DIRS = {
    "ai-minutes", "aitable", "calendar", "contacts", "docs", "drive",
    "im", "mail", "meetings", "open", "zh", "ja",
}


def collect_mdx_paths():
    """Collect all .mdx file paths relative to DOCS_ROOT."""
    results = []
    for root, dirs, files in os.walk(DOCS_ROOT):
        # Skip ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]

        rel_root = Path(root).relative_to(DOCS_ROOT)
        # Skip if top-level dir is not a valid content dir
        top = rel_root.parts[0] if rel_root.parts else None
        if top and top not in VALID_TOP_DIRS:
            continue

        for f in files:
            if f.endswith(".mdx"):
                full = Path(root) / f
                rel = full.relative_to(DOCS_ROOT)
                results.append(rel)

    return sorted(results)


def mdx_to_url(rel_path: Path) -> str:
    """Convert a relative .mdx path to a sitemap URL."""
    parts = list(rel_path.parts)
    # Remove .mdx extension
    parts[-1] = parts[-1].replace(".mdx", "")
    # index pages map to parent directory URL
    if parts[-1] == "index":
        parts = parts[:-1]
    # Build URL path
    url_path = "/".join(parts)
    if not url_path:
        url_path = ""  # root
    return f"{BASE_URL}/{url_path}"


def main():
    mdx_paths = collect_mdx_paths()
    print(f"Found {len(mdx_paths)} .mdx files")

    # Build XML
    ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
    urlset = ET.Element("urlset", xmlns=ns)
    urlset.set("xmlns:xhtml", "http://www.w3.org/1999/xhtml")

    # Note: lastmod is intentionally omitted to keep sitemap.xml deterministic.
    # The pre-push hook re-runs this script and compares output; including
    # date-based lastmod would cause spurious diffs every day.
    # Google explicitly states it does not strongly trust sitemap lastmod anyway.

    # Add homepage first
    home_el = ET.SubElement(urlset, "url")
    loc = ET.SubElement(home_el, "loc")
    loc.text = f"{BASE_URL}/"
    changefreq = ET.SubElement(home_el, "changefreq")
    changefreq.text = "daily"
    priority = ET.SubElement(home_el, "priority")
    priority.text = "1.0"

    for rel in mdx_paths:
        # Skip root index.mdx — homepage already added with priority 1.0
        if str(rel) == "index.mdx":
            continue
        url_el = ET.SubElement(urlset, "url")
        loc = ET.SubElement(url_el, "loc")
        loc.text = mdx_to_url(rel)
        changefreq = ET.SubElement(url_el, "changefreq")
        changefreq.text = "weekly"
        priority = ET.SubElement(url_el, "priority")
        priority.text = "0.7"

    # Write with XML declaration
    tree = ET.ElementTree(urlset)
    out = DOCS_ROOT / "sitemap.xml"
    ET.indent(tree, space="  ")
    tree.write(str(out), encoding="utf-8", xml_declaration=True)

    # Count by language
    en = sum(1 for p in mdx_paths if not str(p).startswith("zh/") and not str(p).startswith("ja/"))
    zh = sum(1 for p in mdx_paths if str(p).startswith("zh/"))
    ja = sum(1 for p in mdx_paths if str(p).startswith("ja/"))
    print(f"  EN: {en}, ZH: {zh}, JA: {ja}")
    print(f"Written to {out} ({out.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
