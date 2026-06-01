"""fix_post_import.py — 导入后 3 项修正：reorder / titles / links

用法:
  python scripts/fix_post_import.py reorder [--dry-run]
  python scripts/fix_post_import.py titles  [--dry-run]
  python scripts/fix_post_import.py links   [--dry-run]
  python scripts/fix_post_import.py all     [--dry-run]

子命令:
  reorder — 按 archive 1→16 顺序重排 docs.json en/zh Docs tab 的 group；
            并按 archive index 顺序排已知 group 内的嵌套 group。
  titles  — 移除三语 14 份 */index.mdx frontmatter 标题里的数字前缀
            （如 "9. 钉钉文档" → "钉钉文档"）。
  links   — 把 *.dingtalk.com 链接换成 *.dingtalk.io；HEAD 探活（1s）：
            2xx/3xx → 用新 URL；否则 → 把 [text](url) 退化为纯文本。

仅用 stdlib + requests。三语 mdx 同步处理；docs.json 用整块替换写回。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "fix"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

HTTP_CACHE_PATH = OUTPUT_DIR / "link-cleanup-cache.json"
REPORT_PATH = OUTPUT_DIR / "report.md"
DOCS_JSON = REPO_ROOT / "docs.json"


# ---------------------------------------------------------------------------
# reorder
# ---------------------------------------------------------------------------

# 一级 group slug 顺序：archive 1→16（跳过 11），与当前 docs.json 共 15 项一致
GROUP_ORDER: list[str] = [
    "getting-started",   # 1
    "quickstart",        # 2
    "release-notes",     # 3
    "admin-guide",       # 4
    "doc-ai",            # 5
    "customer-stories",  # 6
    "best-practices",    # 7
    "advanced",          # 8
    "dingtalk-docs",     # 9
    "sheets",            # 10
    "mind",              # 12
    "whiteboard",        # 13
    "knowledge-base",    # 14
    "knowledge-group",   # 15
    "templates",         # 16
]

# 嵌套 group 顺序：按 archive index 顺序排（zh 标题作为 key，en 标题作为 key 同步声明）
# 未在 list 内的 group 会按当前顺序追加到末尾。
NESTED_ORDER_ZH: dict[str, list[str]] = {
    "dingtalk-docs": [
        "插入内容", "协作互动", "关联钉钉", "样式排版",
        "快捷键输入", "打印和导出", "使用设置", "常见问题",
    ],
    "sheets": [
        "编辑", "插入内容", "格式", "公式与函数",
        "视图", "智能工具", "导出和另存为模板", "协作互动",
    ],
    "mind": [
        "基础功能", "插入附件", "协作与分享", "其他功能",
    ],
}

NESTED_ORDER_EN: dict[str, list[str]] = {
    "dingtalk-docs": [
        "Insert Content", "Collaboration", "DingTalk Link", "Style & Format",
        "Shortcuts & Input", "Print & Export", "Settings", "FAQ",
    ],
    "sheets": [
        "Edit", "Insert Content", "Format", "Formulas",
        "View", "Smart Tools", "Export & Save Template", "Collaboration",
    ],
    "mind": [
        "Basics", "Insert Attachment", "Collaboration", "Other",
    ],
}


def _sort_key_for_slug(slug: str) -> tuple[int, str]:
    """First-level group sort key: index in GROUP_ORDER, then alpha."""
    try:
        return (GROUP_ORDER.index(slug), slug)
    except ValueError:
        return (len(GROUP_ORDER), slug)


def _extract_group_slug(group_obj: dict) -> Optional[str]:
    """从 group.pages 第一个字符串 page 提取 slug 路径段第二级。"""
    pages = group_obj.get("pages", [])
    for p in pages:
        if isinstance(p, str):
            parts = p.split("/")
            for i, seg in enumerate(parts):
                if seg == "docs" and i + 1 < len(parts):
                    return parts[i + 1]
        elif isinstance(p, dict):
            inner_slug = _extract_group_slug(p)
            if inner_slug:
                return inner_slug
    return None


def _sort_nested_groups(group_obj: dict, lang: str) -> None:
    """对一个一级 group 的 pages 数组中嵌套 group 重排（in-place）。
    扁平 page（字符串）保持原相对位置；嵌套 group 按 NESTED_ORDER_* 排。
    """
    slug = _extract_group_slug(group_obj)
    if not slug:
        return
    order_map = NESTED_ORDER_ZH if lang == "zh" else NESTED_ORDER_EN
    order = order_map.get(slug)
    if not order:
        return

    pages = group_obj.get("pages", [])
    nested = [p for p in pages if isinstance(p, dict)]
    flats = [p for p in pages if not isinstance(p, dict)]

    def sort_key(ng: dict) -> tuple[int, str]:
        t = ng.get("group", "")
        try:
            return (order.index(t), t)
        except ValueError:
            return (len(order), t)

    nested_sorted = sorted(nested, key=sort_key)
    # 重新交错：所有 flat 在前（通常 index 在最前），nested 在后；
    # 当前 docs.json 已是 flat-then-nested 结构，保持。
    group_obj["pages"] = flats + nested_sorted


def cmd_reorder(dry_run: bool) -> None:
    data = json.loads(DOCS_JSON.read_text(encoding="utf-8"))
    changes: list[str] = []

    for lang_block in data["navigation"]["languages"]:
        lang = lang_block.get("language", "?")
        if lang == "ja":
            continue  # 本次 PR 不动 ja 块
        for tab in lang_block.get("tabs", []):
            if tab.get("tab") not in ("Docs", "文档", "ドキュメント"):
                continue
            groups = tab.get("groups", [])
            before = [g.get("group") for g in groups]

            # 给每个 group 加 sort_key、按 slug 排
            def gkey(g: dict) -> tuple[int, str]:
                return _sort_key_for_slug(_extract_group_slug(g) or "")

            sorted_groups = sorted(groups, key=gkey)
            tab["groups"] = sorted_groups
            after = [g.get("group") for g in sorted_groups]
            if before != after:
                changes.append(f"[{lang}] reorder groups:\n  before: {before}\n  after:  {after}")

            # 二级 nested group 重排
            for g in sorted_groups:
                nested_before = [
                    x.get("group") for x in g.get("pages", []) if isinstance(x, dict)
                ]
                _sort_nested_groups(g, lang)
                nested_after = [
                    x.get("group") for x in g.get("pages", []) if isinstance(x, dict)
                ]
                if nested_before != nested_after:
                    slug = _extract_group_slug(g)
                    changes.append(
                        f"[{lang}] reorder nested in {slug!r}:\n  before: {nested_before}\n  after:  {nested_after}"
                    )

    if not changes:
        print("[reorder] no changes")
        return

    print("\n".join(changes))
    print(f"\n[reorder] total {len(changes)} change(s)")

    if dry_run:
        print("[reorder] dry-run, not writing")
        return

    DOCS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[reorder] wrote {DOCS_JSON}")
    _append_report("reorder", changes)


# ---------------------------------------------------------------------------
# titles
# ---------------------------------------------------------------------------

# 三语 14 份 */index.mdx（whiteboard 无前缀，跳过；但脚本无害扫一遍）
TITLE_DIRS = [
    REPO_ROOT / "zh" / "docs",
    REPO_ROOT / "docs",
    REPO_ROOT / "ja" / "docs",
]

# frontmatter title 行的数字前缀正则
# 匹配 title: "9. 钉钉文档" / title: 9. 钉钉文档 / 带 U+00A0 等
TITLE_RE = re.compile(
    r'^(title:\s*)(["\']?)(?:\d+[\.\s ]+)+(.+?)(["\']?\s*)$'
)
# H1 行的同样前缀
H1_RE = re.compile(r'^(# )(?:\d+[\.\s ]+)+(.+)$')


def _strip_title_prefix(text: str) -> tuple[str, bool]:
    """返回 (新内容, 是否修改)。仅扫 frontmatter 块和 H1 行。"""
    lines = text.split("\n")
    changed = False
    in_frontmatter = False
    fm_end_idx = -1
    if lines and lines[0].strip() == "---":
        in_frontmatter = True
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                fm_end_idx = i
                break

    for i, line in enumerate(lines):
        if 1 <= i < fm_end_idx:
            m = TITLE_RE.match(line)
            if m:
                new = f"{m.group(1)}{m.group(2)}{m.group(3)}{m.group(4)}"
                if new != line:
                    lines[i] = new
                    changed = True
        elif i > fm_end_idx:
            m = H1_RE.match(line)
            if m:
                new = f"{m.group(1)}{m.group(2)}"
                if new != line:
                    lines[i] = new
                    changed = True

    return "\n".join(lines), changed


def cmd_titles(dry_run: bool) -> None:
    changes: list[str] = []
    for base in TITLE_DIRS:
        for idx_mdx in sorted(base.glob("*/index.mdx")):
            content = idx_mdx.read_text(encoding="utf-8")
            new_content, changed = _strip_title_prefix(content)
            if not changed:
                continue
            old_title = next(
                (l for l in content.split("\n") if l.startswith("title:")), ""
            )
            new_title = next(
                (l for l in new_content.split("\n") if l.startswith("title:")), ""
            )
            rel = idx_mdx.relative_to(REPO_ROOT)
            changes.append(f"[titles] {rel}\n  - {old_title}\n  + {new_title}")
            if not dry_run:
                idx_mdx.write_text(new_content, encoding="utf-8")

    if not changes:
        print("[titles] no changes")
        return
    print("\n".join(changes))
    print(f"\n[titles] {len(changes)} file(s) {'(dry-run)' if dry_run else 'updated'}")
    if not dry_run:
        _append_report("titles", changes)


# ---------------------------------------------------------------------------
# links
# ---------------------------------------------------------------------------

LINK_DIRS = [REPO_ROOT / "zh" / "docs", REPO_ROOT / "docs", REPO_ROOT / "ja" / "docs"]

# markdown 链接：[text](url)
MD_LINK_RE = re.compile(r'\[([^\]]*)\]\((https?://[^)\s]*?\.dingtalk\.com[^)\s]*)\)')
# 裸 URL：不在 markdown 括号内的 https://*.dingtalk.com/...
# 只匹配 ASCII URL-safe 字符；遇到 CJK / 空白 / 中文标点立即停止
BARE_URL_RE = re.compile(
    r'(?<![\(\["])(https?://[a-z0-9.\-]+\.dingtalk\.com'
    r'[A-Za-z0-9\-._~:/?#@!$&*+;=%]*)'
)
# 代码块（fenced）
CODE_FENCE_RE = re.compile(r'^```')


def _load_cache() -> dict[str, int]:
    if HTTP_CACHE_PATH.exists():
        try:
            return json.loads(HTTP_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict[str, int]) -> None:
    HTTP_CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _probe(url: str, cache: dict[str, int]) -> int:
    if url in cache:
        return cache[url]
    try:
        r = requests.head(url, timeout=1, allow_redirects=True)
        status = r.status_code
    except Exception:
        status = 0
    cache[url] = status
    return status


def _split_code_blocks(text: str) -> list[tuple[bool, str]]:
    """返回 [(is_code, segment)] 列表。is_code=True 的段不修改。"""
    parts: list[tuple[bool, str]] = []
    buf: list[str] = []
    in_code = False
    for line in text.split("\n"):
        if CODE_FENCE_RE.match(line):
            parts.append((in_code, "\n".join(buf)))
            buf = [line]
            in_code = not in_code
            continue
        buf.append(line)
    parts.append((in_code, "\n".join(buf)))
    return parts


def _rewrite_segment(
    seg: str, cache: dict[str, int], stats: dict, samples: list
) -> str:
    """对一个非代码段执行链接重写。"""

    def md_repl(m: re.Match) -> str:
        text, url = m.group(1), m.group(2)
        new_url = url.replace(".dingtalk.com", ".dingtalk.io")
        status = _probe(new_url, cache)
        if 200 <= status < 400:
            stats["md_replaced"] += 1
            samples.append(("md-keep", url, new_url, status))
            return f"[{text}]({new_url})"
        stats["md_stripped"] += 1
        samples.append(("md-strip", url, "", status))
        # 退化为纯文本：去掉 markdown 链接括号，保留 text
        return text

    seg = MD_LINK_RE.sub(md_repl, seg)

    def bare_repl(m: re.Match) -> str:
        url = m.group(1)
        # 内联代码 `...` 内不处理
        # 简化：上下文不易切，只用 cache 决策
        new_url = url.replace(".dingtalk.com", ".dingtalk.io")
        status = _probe(new_url, cache)
        if 200 <= status < 400:
            stats["bare_replaced"] += 1
            samples.append(("bare-keep", url, new_url, status))
            return new_url
        stats["bare_stripped"] += 1
        samples.append(("bare-strip", url, "", status))
        # 裸 URL 探活失败：替换为空
        return ""

    seg = BARE_URL_RE.sub(bare_repl, seg)
    return seg


def cmd_links(dry_run: bool) -> None:
    cache = _load_cache()
    stats = {
        "md_replaced": 0,
        "md_stripped": 0,
        "bare_replaced": 0,
        "bare_stripped": 0,
        "files_changed": 0,
    }
    samples: list[tuple[str, str, str, int]] = []
    changes: list[str] = []

    for base in LINK_DIRS:
        for mdx in sorted(base.rglob("*.mdx")):
            text = mdx.read_text(encoding="utf-8")
            if ".dingtalk.com" not in text:
                continue
            segments = _split_code_blocks(text)
            new_segments: list[str] = []
            for is_code, seg in segments:
                if is_code:
                    new_segments.append(seg)
                else:
                    new_segments.append(_rewrite_segment(seg, cache, stats, samples))
            new_text = "\n".join(new_segments)
            if new_text != text:
                stats["files_changed"] += 1
                rel = mdx.relative_to(REPO_ROOT)
                changes.append(f"  - {rel}")
                if not dry_run:
                    mdx.write_text(new_text, encoding="utf-8")

    _save_cache(cache)

    print(f"[links] files changed: {stats['files_changed']}")
    print(f"  md replaced:    {stats['md_replaced']}")
    print(f"  md stripped:    {stats['md_stripped']}")
    print(f"  bare replaced:  {stats['bare_replaced']}")
    print(f"  bare stripped:  {stats['bare_stripped']}")
    print(f"  http cache size: {len(cache)}")
    if changes:
        print("[links] changed files:\n" + "\n".join(changes[:20]))
        if len(changes) > 20:
            print(f"  ... and {len(changes) - 20} more")
    if samples:
        print("[links] sample decisions (first 15):")
        for kind, old, new, st in samples[:15]:
            print(f"  {kind} [HTTP {st}] {old}{' → ' + new if new else ''}")

    if not dry_run:
        _append_report("links", [
            f"files changed: {stats['files_changed']}",
            f"md replaced/stripped: {stats['md_replaced']}/{stats['md_stripped']}",
            f"bare replaced/stripped: {stats['bare_replaced']}/{stats['bare_stripped']}",
        ])


# ---------------------------------------------------------------------------
# pages — 按官方左侧菜单顺序重排三/四级 pages 数组
# ---------------------------------------------------------------------------

OFFICIAL_MENU_PATH = OUTPUT_DIR / "official-menu-full.json"
LINK_MAP_DIR = REPO_ROOT / "scripts" / "output" / "import"

# 目标 group：official menu 中 depth=1 标题前缀（如 "9.") → docs.json group slug
# 跳过：2/11/13（quickstart/aitable/whiteboard 不重排）
TARGET_GROUPS: list[tuple[str, str]] = [
    # (menu_title_prefix, docs_json_slug)
    ("1.", "getting-started"),
    ("3.", "release-notes"),
    ("4.", "admin-guide"),
    ("5.", "doc-ai"),
    ("6.", "customer-stories"),
    ("7.", "best-practices"),
    ("8.", "advanced"),
    ("9.", "dingtalk-docs"),
    ("10.", "sheets"),
    ("12.", "mind"),
    ("14.", "knowledge-base"),
    ("15.", "knowledge-group"),
    ("16.", "templates"),
]


def _slice_menu_by_group(menu: list[dict], title_prefix: str) -> Optional[list[dict]]:
    """从 official-menu-full.json 切出某 group 的子树（含 depth=1 根本身）。"""
    start = None
    for i, item in enumerate(menu):
        if item["depth"] == 1 and item["title"].lstrip().startswith(title_prefix):
            start = i
            break
    if start is None:
        return None
    end = start + 1
    while end < len(menu) and menu[end]["depth"] > 1:
        end += 1
    return menu[start:end]


_FRONTMATTER_TITLE_RE = re.compile(r'^title:\s*["\']?(.+?)["\']?\s*$', re.MULTILINE)
_NUM_PREFIX_RE = re.compile(r'^\d+\.\s*')
_WHITESPACE_NORM_RE = re.compile(r'[\s ​　]+')


def _norm_title(t: str) -> str:
    """归一化标题：所有空白字符（含 U+00A0 NBSP、U+200B ZWSP、U+3000 全角空格）→ 单个普通空格；首尾 strip。"""
    return _WHITESPACE_NORM_RE.sub(" ", t).strip()


def _build_title_to_zh_slug(
    group_slug: str,
) -> tuple[dict[str, str], list[tuple[str, str, str]]]:
    """扫 zh/docs/<group>/**/*.mdx，提取 frontmatter title → zh slug。

    返回 (title2slug, collisions)。slug 形如 'zh/docs/<group>/.../<name>'（不带 .mdx）。
    title-based 比 link-map 的 docKey-based 覆盖率高得多（66/67 vs 9/67）。
    """
    base = REPO_ROOT / "zh" / "docs" / group_slug
    title2slug: dict[str, str] = {}
    collisions: list[tuple[str, str, str]] = []
    if not base.exists():
        return title2slug, collisions
    for mdx in sorted(base.rglob("*.mdx")):
        txt = mdx.read_text(encoding="utf-8")
        m = _FRONTMATTER_TITLE_RE.search(txt)
        if not m:
            continue
        title = _norm_title(m.group(1))
        slug = str(mdx.relative_to(REPO_ROOT)).removesuffix(".mdx")
        if title in title2slug:
            collisions.append((title, title2slug[title], slug))
        title2slug[title] = slug
    return title2slug, collisions


def _resolve_menu_title(title: str, title2slug: dict[str, str]) -> Optional[str]:
    """按 frontmatter title 匹配（已归一化空白）；优先精确，失败则脱去数字前缀。"""
    t = _norm_title(title)
    if t in title2slug:
        return title2slug[t]
    stripped = _NUM_PREFIX_RE.sub("", t).strip()
    if stripped and stripped in title2slug:
        return title2slug[stripped]
    return None


def _build_subgroup_title_map(
    current_pages: list, lang_prefix: str
) -> dict[str, str]:
    """从当前 docs.json group.pages 提取 子组 URL 前缀 → 标题 映射，保留翻译。

    例：zh/docs/dingtalk-docs/insert-content → '插入内容'
    """
    result: dict[str, str] = {}

    def find_first_page_slug(arr: list) -> Optional[str]:
        for x in arr:
            if isinstance(x, str):
                return x
            if isinstance(x, dict):
                s = find_first_page_slug(x.get("pages", []))
                if s:
                    return s
        return None

    def walk(arr: list) -> None:
        for it in arr:
            if isinstance(it, dict):
                title = it.get("group", "")
                first = find_first_page_slug(it.get("pages", []))
                if first:
                    parts = first.split("/")
                    prefix = "/".join(parts[:-1])
                    result[prefix] = title
                walk(it.get("pages", []))

    walk(current_pages)
    return result


def _collect_all_slugs(arr: list) -> set[str]:
    """递归收集 pages 数组中所有字符串 slug。"""
    out: set[str] = set()
    for x in arr:
        if isinstance(x, str):
            out.add(x)
        elif isinstance(x, dict):
            out |= _collect_all_slugs(x.get("pages", []))
    return out


def _zh_slug_to_lang(zh_slug: str, lang: str) -> str:
    """'zh/docs/...' → 'docs/...'（en）或保持 'zh/docs/...'（zh）。"""
    if lang == "zh":
        return zh_slug
    # en: 去掉前导 'zh/'
    if zh_slug.startswith("zh/"):
        return zh_slug[3:]
    return zh_slug


def _rebuild_group_pages(
    menu_subtree: list[dict],
    title_to_zh_slug: dict[str, str],
    current_pages: list,
    lang: str,
    missing_log: list,
) -> Optional[list]:
    """根据 menu_subtree（DFS 序，第 0 个是 depth=1 group root）重建 pages 数组。

    用 title 作为 docKey → slug 的中介（link-map 覆盖率太低不可用）。
    返回新 pages 数组，或 None 如果 root 无法解析。
    """
    prefix = "zh/" if lang == "zh" else ""
    title_map = _build_subgroup_title_map(current_pages, prefix)

    root = menu_subtree[0]
    root_zh = _resolve_menu_title(root["title"], title_to_zh_slug)
    if not root_zh:
        missing_log.append({"lang": lang, "reason": "root title not in zh mdx", **root})
        return None
    root_index = _zh_slug_to_lang(root_zh, lang)
    if not root_index.endswith("/index"):
        root_index = root_index.rstrip("/") + "/index"

    def consume(start_idx: int, parent_depth: int) -> tuple[list, int]:
        pages: list = []
        i = start_idx
        while i < len(menu_subtree):
            item = menu_subtree[i]
            if item["depth"] <= parent_depth:
                break
            if item["depth"] != parent_depth + 1:
                i += 1
                continue
            zh_slug = _resolve_menu_title(item["title"], title_to_zh_slug)
            if not zh_slug:
                missing_log.append({"lang": lang, "reason": "title not in zh mdx", **item})
                i += 1
                continue
            lang_slug = _zh_slug_to_lang(zh_slug, lang)
            if item["hasChildren"]:
                child_pages, next_i = consume(i + 1, item["depth"])
                sub_pref = lang_slug[:-len("/index")] if lang_slug.endswith("/index") else lang_slug
                idx_slug = sub_pref + "/index"
                title = title_map.get(sub_pref, item["title"])
                pages.append({"group": title, "pages": [idx_slug] + child_pages})
                i = next_i
            else:
                pages.append(lang_slug)
                i += 1
        return pages, i

    children, _ = consume(1, root["depth"])
    return [root_index] + children


def cmd_pages(dry_run: bool) -> None:
    if not OFFICIAL_MENU_PATH.exists():
        print(f"[pages] missing {OFFICIAL_MENU_PATH}; run crawl_official_menu.py first")
        return
    menu = json.loads(OFFICIAL_MENU_PATH.read_text(encoding="utf-8"))
    data = json.loads(DOCS_JSON.read_text(encoding="utf-8"))

    missing_log: list = []
    changes: list[str] = []
    orphan_log: list = []  # slug 在 current 但 menu 未覆盖

    # 索引 current docs.json 的 group：lang → slug → group_obj 引用
    lang_group_index: dict[str, dict[str, dict]] = {}
    for lang_block in data["navigation"]["languages"]:
        lang = lang_block.get("language", "?")
        if lang == "ja":
            continue  # 本次 PR 不动 ja
        idx: dict[str, dict] = {}
        for tab in lang_block.get("tabs", []):
            if tab.get("tab") not in ("Docs", "文档", "ドキュメント"):
                continue
            for g in tab.get("groups", []):
                slug = _extract_group_slug(g)
                if slug:
                    idx[slug] = g
        lang_group_index[lang] = idx

    for menu_prefix, group_slug in TARGET_GROUPS:
        subtree = _slice_menu_by_group(menu, menu_prefix)
        if not subtree:
            print(f"[pages] WARN: menu prefix '{menu_prefix}' for {group_slug} not found")
            continue
        title_map_zh, collisions = _build_title_to_zh_slug(group_slug)
        if not title_map_zh:
            print(f"[pages] WARN: zh/docs/{group_slug} empty or missing; skip")
            continue
        if collisions:
            print(f"[pages] [{group_slug}] title collisions in zh mdx:")
            for t, a, b in collisions:
                print(f"  {t!r}  ←  {a}  AND  {b}")

        for lang in ("en", "zh"):
            group_obj = lang_group_index.get(lang, {}).get(group_slug)
            if not group_obj:
                print(f"[pages] WARN: [{lang}] group {group_slug} not in docs.json")
                continue
            current = group_obj["pages"]
            old_slugs = _collect_all_slugs(current)
            new_pages = _rebuild_group_pages(subtree, title_map_zh, current, lang, missing_log)
            if new_pages is None:
                print(f"[pages] [{lang}] {group_slug}: skipped (root unresolvable)")
                continue
            new_slugs = _collect_all_slugs(new_pages)
            # 落单：current 有但 new 没有 → 追加到尾部（不丢页）
            dropped = old_slugs - new_slugs
            if dropped:
                for s in sorted(dropped):
                    orphan_log.append({"lang": lang, "group": group_slug, "slug": s})
                new_pages.extend(sorted(dropped))
            # 落单反向：new 有但 current 没有 → 新页（理论上 import 阶段都建过，不应有）
            added = new_slugs - old_slugs
            if added:
                for s in sorted(added):
                    print(f"  [{lang}] {group_slug}: NEW slug not in current docs.json: {s}")

            if current != new_pages:
                group_obj["pages"] = new_pages
                changes.append(
                    f"[{lang}] {group_slug}: pages reordered "
                    f"({len(old_slugs)} slugs, {len(dropped)} appended-orphan)"
                )

    if not changes:
        print("[pages] no changes")
    else:
        print("\n".join(changes))
        print(f"\n[pages] total {len(changes)} group(s) changed")

    if missing_log:
        print(f"\n[pages] {len(missing_log)} missing docKey(s) (no link-map entry):")
        for m in missing_log[:20]:
            print(f"  [{m['lang']}] {m['reason']}: depth={m.get('depth')} {m.get('docKey')} '{m.get('title', m.get('name', ''))[:40]}'")
        if len(missing_log) > 20:
            print(f"  ... and {len(missing_log) - 20} more")

    if orphan_log:
        print(f"\n[pages] {len(orphan_log)} orphan slug(s) (in docs.json but not in official menu, appended to end):")
        for o in orphan_log[:20]:
            print(f"  [{o['lang']}] {o['group']}: {o['slug']}")
        if len(orphan_log) > 20:
            print(f"  ... and {len(orphan_log) - 20} more")

    if dry_run:
        print("\n[pages] dry-run, not writing")
        return

    DOCS_JSON.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"\n[pages] wrote {DOCS_JSON}")
    _append_report("pages", changes + [
        f"missing docKeys: {len(missing_log)}",
        f"orphan slugs (appended): {len(orphan_log)}",
    ])


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def _append_report(section: str, lines: list[str]) -> None:
    import datetime
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    body = f"\n## [{ts}] {section}\n\n" + "\n".join(f"- {l}" for l in lines) + "\n"
    if REPORT_PATH.exists():
        body = REPORT_PATH.read_text(encoding="utf-8") + body
    else:
        body = "# fix_post_import 修正报告\n" + body
    REPORT_PATH.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=["reorder", "titles", "links", "pages", "all"],
        help="子命令",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印不写")
    args = parser.parse_args()

    if args.command == "reorder":
        cmd_reorder(args.dry_run)
    elif args.command == "titles":
        cmd_titles(args.dry_run)
    elif args.command == "links":
        cmd_links(args.dry_run)
    elif args.command == "pages":
        cmd_pages(args.dry_run)
    elif args.command == "all":
        cmd_reorder(args.dry_run)
        cmd_titles(args.dry_run)
        cmd_links(args.dry_run)
        cmd_pages(args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
