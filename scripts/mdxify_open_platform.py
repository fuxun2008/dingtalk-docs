#!/usr/bin/env python3
"""
Convert clean markdown produced by apply_constraints into Mintlify-compatible mdx,
and emit a nav fragment for docs.json injection.

Subcommands:
  convert  - clean/{ns}/{slug}.md → zh/open/{ns}/{slug}.mdx
  nav      - build nav fragment + (optional --inject) inject into docs.json zh block
  report   - regenerate mdxify_report.md from the last convert run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
OUT_DIR = HERE / "output" / "open_platform"
CLEAN_DIR = OUT_DIR / "clean"
MENU_DIR = OUT_DIR / "menu"
ZH_OPEN_DIR = REPO / "zh" / "open"
DOCS_JSON = REPO / "docs.json"

# Reuse description extractor from import_mail_en
sys.path.insert(0, str(HERE))
from import_mail_en import extract_clean_description  # noqa: E402


# --------------- shared helpers ---------------

def split_frontmatter(text: str) -> tuple[dict, str]:
    """Parse the simple `key: "value"` frontmatter our crawl produced."""
    if not text.startswith("---\n"):
        return {}, text
    lines = text.splitlines(keepends=True)
    fm_lines: list[str] = []
    body_start = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\n") == "---":
            body_start = i + 1
            # Consume one trailing blank
            if body_start < len(lines) and lines[body_start].strip() == "":
                body_start += 1
            break
        fm_lines.append(lines[i])
    if body_start is None:
        return {}, text
    fm = parse_simple_yaml(fm_lines)
    body = "".join(lines[body_start:])
    return fm, body


def parse_simple_yaml(lines: list[str]) -> dict:
    """Tiny YAML parser: handles `key: "value"`, `key: 123`, `key: ["a","b"]`."""
    out: dict = {}
    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if not m:
            continue
        k = m.group(1)
        v_str = m.group(2).strip()
        if not v_str:
            out[k] = ""
            continue
        # Try JSON-parse first (handles strings + arrays + numbers + booleans)
        try:
            out[k] = json.loads(v_str)
        except (json.JSONDecodeError, ValueError):
            out[k] = v_str
    return out


def strip_html_tags(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def strip_h1_matching_title(body: str, title: str) -> str:
    """Drop the leading `# {title}` line + following blanks, only if it matches."""
    lines = body.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines):
        return body
    m = re.match(r"^#\s+(.+?)\s*$", lines[i])
    if not m:
        return body
    h1 = m.group(1).strip()
    # Tolerate ** wrappers etc. that markdownify sometimes produces (**Title**)
    h1_norm = re.sub(r"\*", "", h1).strip()
    title_norm = re.sub(r"\*", "", title).strip()
    if h1_norm != title_norm:
        return body
    j = i + 1
    while j < len(lines) and not lines[j].strip():
        j += 1
    return "\n".join(lines[:i] + lines[j:])


# --------------- internal-link rewrite ---------------

_INTERNAL_LINK_RE = re.compile(r"\]\(/document/([a-z][a-z0-9_-]*)/([^)\s#?]+)(?:[#?][^)]*)?\)")

# MDX safety: escape bare `<` that the JSX parser would mis-parse as a tag start.
# Strategy: escape ALL bare `<` outside code, except autolinks `<https://...>`.
# We don't preserve `<Note>` etc. because crawl_open_platform produces pure markdown
# (markdownify already converted HTML to text); preserving tag-like `<` would let
# patterns like `Map<String, Array>` or `< 10ms` break the MDX parser.
_FENCE_RE_LINE = re.compile(r"^```")
# We escape ALL `<` outside fenced code. Mintlify's MDX rejects even autolinks
# `<https://...>` in some contexts (table cells, certain prose positions), so
# preserving them isn't worth the build failures. Users can use `[url](url)`.
_MDX_LT_ALL = re.compile(r"<")
# Backtick split regex: captures inline code spans so we can leave them alone
_INLINE_CODE_RE = re.compile(r"(`+[^`\n]*?`+)")


def _escape_risky(text: str) -> tuple[str, int]:
    text, n_lt = _MDX_LT_ALL.subn("&lt;", text)
    n_brace = text.count("{") + text.count("}")
    text = text.replace("{", "&#123;").replace("}", "&#125;")
    return text, n_lt + n_brace


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and len(s) >= 2


def mdx_safe_escape(body: str) -> tuple[str, int]:
    """Escape MDX-risky chars outside fenced code blocks.

    Targets:
      - `<` (except autolinks `<https?://...>`) → `&lt;`  (otherwise MDX tries JSX tag)
      - `{` `}` → `&#123;` `&#125;`  (otherwise MDX tries JS expression)

    Inline-code spans (``…`` / ```…```) are normally left alone, BUT inside GFM
    table-row lines (`|...|`) we force-escape everything because MDX parses
    cells aggressively as JSX expressions even within backticked spans.

    Returns (new_body, total_escape_count).
    """
    count = 0
    out_lines: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE_RE_LINE.match(line):
            in_fence = not in_fence
            out_lines.append(line)
            continue
        if in_fence:
            out_lines.append(line)
            continue
        # GFM table rows: force-escape the whole line (inline code in cells is
        # unsafe — MDX parses cells too aggressively as JSX expressions).
        if _is_table_row(line):
            new_line, n = _escape_risky(line)
            out_lines.append(new_line)
            count += n
            continue
        # Regular paragraph: split by inline code and only escape outside
        chunks = _INLINE_CODE_RE.split(line)
        for i, chunk in enumerate(chunks):
            if i % 2 == 1:
                continue
            new_chunk, n = _escape_risky(chunk)
            chunks[i] = new_chunk
            count += n
        out_lines.append("".join(chunks))
    return "\n".join(out_lines), count


def rewrite_internal_links(
    body: str, fetched_pairs: set[tuple[str, str]]
) -> tuple[str, int, int]:
    """Rewrite `](/document/ns/slug#frag)` → `](/zh/open/ns/slug)` if (ns, slug) is in fetched_pairs.

    Returns (new_body, rewrite_count, kept_dead_count).
    """
    rewrites = 0
    kept_dead = 0

    def repl(m: re.Match) -> str:
        nonlocal rewrites, kept_dead
        ns, slug = m.group(1), m.group(2)
        if (ns, slug) in fetched_pairs:
            rewrites += 1
            return f"](/zh/open/{ns}/{slug})"
        kept_dead += 1
        return m.group(0)

    new_body = _INTERNAL_LINK_RE.sub(repl, body)
    return new_body, rewrites, kept_dead


# --------------- convert subcommand ---------------

def build_frontmatter(title: str, description: str) -> str:
    return (
        "---\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"description: {json.dumps(description, ensure_ascii=False)}\n"
        "---\n\n"
    )


def load_fetch_list() -> list[dict]:
    p = MENU_DIR / "fetch_list.json"
    if not p.exists():
        print(f"ERROR: {p} missing. Run crawl_open_platform menu first.", file=sys.stderr)
        sys.exit(2)
    return json.loads(p.read_text())


def convert_one(clean_path: Path, fetched_pairs: set) -> tuple[str, dict]:
    text = clean_path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    title = fm.get("title", clean_path.stem)
    namespace = fm.get("namespace", clean_path.parent.name)
    raw_desc = fm.get("short_description", "")
    description = strip_html_tags(raw_desc)
    if not description:
        description = extract_clean_description(body, fallback=title)
    if len(description) > 280:
        description = description[:280].rstrip() + " …"

    body = strip_h1_matching_title(body, title)
    body, rewrites, kept_dead = rewrite_internal_links(body, fetched_pairs)
    body, escape_count = mdx_safe_escape(body)

    # Collapse 3+ blank lines that may appear after H1 strip
    body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"

    out = build_frontmatter(title, description) + body
    return out, {
        "title": title,
        "namespace": namespace,
        "slug": fm.get("slug", clean_path.stem),
        "description_len": len(description),
        "body_len": len(body),
        "rewrites": rewrites,
        "kept_dead": kept_dead,
        "lt_escapes": escape_count,
    }


def cmd_convert(args) -> int:
    if not CLEAN_DIR.exists():
        print(f"ERROR: {CLEAN_DIR} missing. Run apply_constraints apply first.", file=sys.stderr)
        return 2
    fetch_list = load_fetch_list()
    fetched_pairs = {(it["namespace"], it["slug"]) for it in fetch_list}

    files = sorted(CLEAN_DIR.rglob("*.md"))
    if args.limit:
        files = files[: args.limit]
    print(f"convert {len(files)} clean md → zh/open/{{ns}}/{{slug}}.mdx")

    records: list[dict] = []
    for i, p in enumerate(files):
        ns = p.parent.name
        out, rec = convert_one(p, fetched_pairs)
        out_path = ZH_OPEN_DIR / ns / f"{p.stem}.mdx"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(out, encoding="utf-8")
        rec["out_path"] = str(out_path.relative_to(REPO))
        records.append(rec)
        if (i + 1) % 50 == 0 or i + 1 == len(files):
            print(f"  [{i + 1}/{len(files)}]")

    # Write report
    by_ns: dict[str, int] = defaultdict(int)
    total_rewrites = 0
    total_kept_dead = 0
    total_lt_escapes = 0
    desc_empty = 0
    body_too_short = 0
    for r in records:
        by_ns[r["namespace"]] += 1
        total_rewrites += r["rewrites"]
        total_kept_dead += r["kept_dead"]
        total_lt_escapes += r.get("lt_escapes", 0)
        if r["description_len"] == 0:
            desc_empty += 1
        if r["body_len"] < 200:
            body_too_short += 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "mdxify_report.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = ["# mdxify 报告\n"]
    lines.append(f"> 生成：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    lines.append(f"> 输入：`scripts/output/open_platform/clean/` 共 {len(files)} 篇")
    lines.append(f"> 输出：`zh/open/{{ns}}/{{slug}}.mdx`")
    lines.append("")
    lines.append("## 汇总\n")
    lines.append(f"- 转换成功：**{len(records)}** / {len(files)}")
    for ns, n in by_ns.items():
        lines.append(f"  - {ns}: {n}")
    lines.append(f"- 内链重写：**{total_rewrites}** 处")
    lines.append(f"- 保留死链（指向未抓 namespace 或 slug）：**{total_kept_dead}** 处")
    lines.append(f"- MDX 安全转义 `<` → `&lt;`：**{total_lt_escapes}** 处")
    lines.append(f"- description 为空：{desc_empty}")
    lines.append(f"- 正文 < 200 字节：{body_too_short}")
    lines.append("")
    if body_too_short:
        lines.append("## ⚠️ 正文极短文件（< 200 B，可能转换异常）\n")
        for r in records:
            if r["body_len"] < 200:
                lines.append(f"- `{r['out_path']}` ({r['body_len']} B): {r['title']}")
        lines.append("")
    (OUT_DIR / "mdxify_report.md").write_text("\n".join(lines), encoding="utf-8")

    print()
    print(f"=== convert done ===")
    print(f"  files written: {len(records)}")
    print(f"  internal-link rewrites: {total_rewrites}")
    print(f"  kept dead links:        {total_kept_dead}")
    print(f"  report: {OUT_DIR / 'mdxify_report.md'}")
    return 0


# --------------- nav subcommand ---------------

# Order of development modules from the guide md
DEV_MODULE_ORDER = [
    "一、API 调用指南",
    "二、认证与授权",
    "三、通讯录管理",
    "四、IM（即时通信）",
    "五、日历（日程）",
    "六、会议（音视频）",
    "七、AI 表格",
    "八、文档/文件（含文档、知识库、表格、钉盘、搜索）",
]

# Map to friendlier zh group labels for the nav
DEV_GROUP_LABELS = {
    "一、API 调用指南": "API 调用指南",
    "二、认证与授权": "认证与授权",
    "三、通讯录管理": "通讯录管理",
    "四、IM（即时通信）": "即时通信 (IM)",
    "五、日历（日程）": "日历（日程）",
    "六、会议（音视频）": "会议（音视频）",
    "七、AI 表格": "AI 表格",
    "八、文档/文件（含文档、知识库、表格、钉盘、搜索）": "文档与文件",
}


def build_nav_fragment(fetch_list: list[dict], dingstart_meta: dict, written_slugs: set) -> dict:
    """Build the `开放平台` product object for injection into docs.json zh block."""
    # development side: bucket by top-level module from module_path
    dev_buckets: dict[str, list[str]] = defaultdict(list)
    for it in fetch_list:
        if it["namespace"] != "development":
            continue
        if (it["namespace"], it["slug"]) not in written_slugs:
            continue
        # module_path looks like "三、通讯录管理 / 3.5 角色管理" — take first segment as top-level group
        top = it.get("module_path", "").split(" / ")[0].strip()
        dev_buckets[top].append(f"zh/open/development/{it['slug']}")

    dev_groups = []
    for top in DEV_MODULE_ORDER:
        if top in dev_buckets:
            dev_groups.append({
                "group": DEV_GROUP_LABELS.get(top, top),
                "pages": dev_buckets[top],
            })
    # Any unrecognized top buckets (defensive)
    for top, pages in dev_buckets.items():
        if top not in DEV_MODULE_ORDER:
            dev_groups.append({"group": top, "pages": pages})

    # dingstart side: walk meta.json topics — top-level title becomes group, recurse to collect leaves
    def collect_leaves(topics: list, namespace: str) -> list[str]:
        out: list[str] = []
        for t in topics or []:
            if not t:
                continue
            if t.get("type") == "doc":
                slug = t.get("slug")
                if slug and (namespace, slug) in written_slugs:
                    out.append(f"zh/open/{namespace}/{slug}")
            if t.get("children"):
                out.extend(collect_leaves(t["children"], namespace))
        return out

    dingstart_groups = []
    top_topics = sorted(
        (t for t in (dingstart_meta.get("topics") or []) if t),
        key=lambda x: x.get("sort", 0),
    )
    for t in top_topics:
        if t.get("type") != "directory":
            continue
        leaves = collect_leaves(t.get("children", []), "dingstart")
        if leaves:
            dingstart_groups.append({
                "group": t["title"],
                "pages": leaves,
            })

    return {
        "product": "开放平台",
        "icon": "code",
        "tabs": [
            {"tab": "概述", "pages": ["zh/open/index"]},
            {"tab": "服务端 API", "groups": dev_groups},
            {"tab": "开发指南", "groups": dingstart_groups},
        ],
    }


def cmd_nav(args) -> int:
    fetch_list = load_fetch_list()
    dingstart_meta_path = MENU_DIR / "dingstart_meta.json"
    if not dingstart_meta_path.exists():
        print(f"ERROR: {dingstart_meta_path} missing.", file=sys.stderr)
        return 2
    dingstart_meta = json.loads(dingstart_meta_path.read_text())

    # Only include slugs that actually got mdxified (so drop list doesn't end up in nav)
    written_slugs = set()
    for mdx in ZH_OPEN_DIR.rglob("*.mdx"):
        if mdx.parent.name in ("development", "dingstart"):
            written_slugs.add((mdx.parent.name, mdx.stem))

    fragment = build_nav_fragment(fetch_list, dingstart_meta, written_slugs)

    out_path = OUT_DIR / "nav_fragment.json"
    out_path.write_text(json.dumps(fragment, ensure_ascii=False, indent=2), encoding="utf-8")

    # Summary
    dev_pages = sum(len(g["pages"]) for g in fragment["tabs"][1]["groups"])
    ding_pages = sum(len(g["pages"]) for g in fragment["tabs"][2]["groups"])
    print(f"nav fragment written: {out_path}")
    print(f"  服务端 API: {len(fragment['tabs'][1]['groups'])} groups, {dev_pages} pages")
    print(f"  开发指南:   {len(fragment['tabs'][2]['groups'])} groups, {ding_pages} pages")

    if args.inject:
        return _inject_into_docs_json(fragment)
    print()
    print("Dry-run only. To inject into docs.json, re-run with --inject.")
    return 0


def _inject_into_docs_json(fragment: dict) -> int:
    """Edit-style precise replacement of the existing 开放平台 product object."""
    text = DOCS_JSON.read_text(encoding="utf-8")

    # Old object — must be byte-exact match of the current zh 开放平台 product.
    old_obj = (
        '          {\n'
        '            "product": "开放平台",\n'
        '            "icon": "code",\n'
        '            "tabs": [\n'
        '              {\n'
        '                "tab": "概述",\n'
        '                "pages": [\n'
        '                  "zh/open/index"\n'
        '                ]\n'
        '              }\n'
        '            ]\n'
        '          }'
    )
    if text.count(old_obj) != 1:
        print(f"ERROR: expected exactly 1 occurrence of old 开放平台 product block; found {text.count(old_obj)}",
              file=sys.stderr)
        print("Hint: run with --dump-old to inspect; the docs.json may have drifted from plan assumption.",
              file=sys.stderr)
        return 2

    new_obj_lines = json.dumps(fragment, ensure_ascii=False, indent=2).splitlines()
    # Re-indent to 10 spaces (matching nesting depth of product object inside languages[].products[])
    new_obj = "\n".join(("          " + l) if i else "          " + l for i, l in enumerate(new_obj_lines))

    new_text = text.replace(old_obj, new_obj, 1)
    # Sanity: must still be valid JSON
    try:
        json.loads(new_text)
    except json.JSONDecodeError as e:
        print(f"ERROR: post-injection docs.json is invalid JSON: {e}", file=sys.stderr)
        return 2
    DOCS_JSON.write_text(new_text, encoding="utf-8")
    print(f"✓ docs.json injected. Size: {len(text):,} → {len(new_text):,} bytes (+{len(new_text) - len(text):,})")
    return 0


# --------------- report subcommand ---------------


def cmd_report(args) -> int:
    p = OUT_DIR / "mdxify_report.md"
    if not p.exists():
        print(f"ERROR: {p} missing. Run convert first.", file=sys.stderr)
        return 2
    print(p.read_text(encoding="utf-8"))
    return 0


# --------------- entry ---------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sp = p.add_subparsers(dest="cmd", required=True)

    pc = sp.add_parser("convert", help="clean → zh/open mdx")
    pc.add_argument("--limit", type=int, default=0)
    pc.set_defaults(func=cmd_convert)

    pn = sp.add_parser("nav", help="Build nav fragment; --inject writes to docs.json")
    pn.add_argument("--inject", action="store_true")
    pn.set_defaults(func=cmd_nav)

    pr = sp.add_parser("report", help="Print last mdxify_report.md")
    pr.set_defaults(func=cmd_report)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
