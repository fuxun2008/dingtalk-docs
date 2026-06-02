"""import_archive.py — 把 dingtalk-docs-archive 中文文档导入 Mintlify 站。

用法:
  python scripts/import_archive.py --archive /Users/yanxin/Downloads/dingtalk-docs-archive --only "9. 钉钉文档" --dry-run
  python scripts/import_archive.py --archive /Users/yanxin/Downloads/dingtalk-docs-archive --only "9. 钉钉文档"
  python scripts/import_archive.py --archive /Users/yanxin/Downloads/dingtalk-docs-archive --all

行为:
  - 扫描 archive 一级目录（16 个分类）→ Docs tab 下的 group
  - 二级目录 → 嵌套 group；二级下 .md → page
  - 一级 / 二级目录里的同名 {N}. xxx.md → group 的 index.mdx
  - (1)(2) 后缀：先 SHA1 对比；同 → 丢弃；异 → 改名 *-extra
  - 写三语：zh/docs/<group>/<slug>.mdx 实文 + docs/<...> / ja/docs/<...> 占位
  - mdx 转义：代码块外 { } → \{ \}；<词 → &lt;词
  - 跨站链接 3 步重写：本次内部 → 相对路径；alidocs→docs.dingtalk.io 探活 → 用新 URL；否则纯文本

输出:
  - zh/docs/<group>/<slug>.mdx (实文)
  - docs/<group>/<slug>.mdx (en 占位)
  - ja/docs/<group>/<slug>.mdx (ja 占位)
  - scripts/output/import/slug-map.json (中→英 slug 稳定映射)
  - scripts/output/import/link-map.json (alidocs URL → 内部 slug 映射)
  - scripts/output/import/nav-fragment-<group>.json (docs.json navigation 片段)
  - scripts/output/import/report-<group>.md (人工 review 报告)
  - scripts/output/import/http-cache.json (域名探活缓存)
  - scripts/output/import/slug-overrides.json (人工填写未翻译词的入口)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "import"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SLUG_MAP_PATH = OUTPUT_DIR / "slug-map.json"
LINK_MAP_PATH = OUTPUT_DIR / "link-map.json"
HTTP_CACHE_PATH = OUTPUT_DIR / "http-cache.json"
SLUG_OVERRIDES_PATH = OUTPUT_DIR / "slug-overrides.json"

# ---------- 16 个一级分类的固定 slug 映射 ----------
GROUP_META: dict[str, dict[str, str]] = {
    "1. 新手指南": {
        "slug": "getting-started", "en": "Getting Started",
        "zh": "新手指南", "ja": "はじめに",
    },
    "2.快速上手": {
        "slug": "quickstart", "en": "Quickstart",
        "zh": "快速上手", "ja": "クイックスタート",
    },
    "3. 功能更新": {
        "slug": "release-notes", "en": "Release Notes",
        "zh": "功能更新", "ja": "リリースノート",
    },
    "4. 管理员指引": {
        "slug": "admin-guide", "en": "Admin Guide",
        "zh": "管理员指引", "ja": "管理者ガイド",
    },
    "5. 文档 AI": {
        "slug": "doc-ai", "en": "Doc AI",
        "zh": "文档 AI", "ja": "ドキュメント AI",
    },
    "6. 客户案例": {
        "slug": "customer-stories", "en": "Customer Stories",
        "zh": "客户案例", "ja": "お客様事例",
    },
    "7. 最佳实践": {
        "slug": "best-practices", "en": "Best Practices",
        "zh": "最佳实践", "ja": "ベストプラクティス",
    },
    "8. 进阶玩法": {
        "slug": "advanced", "en": "Advanced",
        "zh": "进阶玩法", "ja": "上級者向け",
    },
    "9. 钉钉文档": {
        "slug": "dingtalk-docs", "en": "DingTalk Docs",
        "zh": "钉钉文档", "ja": "DingTalk ドキュメント",
    },
    "10. 钉钉表格": {
        "slug": "sheets", "en": "DingTalk Sheets",
        "zh": "钉钉表格", "ja": "DingTalk シート",
    },
    "12. 钉钉脑图": {
        "slug": "mind", "en": "DingTalk Mind",
        "zh": "钉钉脑图", "ja": "DingTalk マインド",
    },
    "13. 钉钉白板": {
        "slug": "whiteboard", "en": "DingTalk Whiteboard",
        "zh": "钉钉白板", "ja": "DingTalk ホワイトボード",
    },
    "14. 知识库": {
        "slug": "knowledge-base", "en": "Knowledge Base",
        "zh": "知识库", "ja": "ナレッジベース",
    },
    "15. 知识小组": {
        "slug": "knowledge-group", "en": "Knowledge Group",
        "zh": "知识小组", "ja": "ナレッジグループ",
    },
    "16. 模板中心": {
        "slug": "templates", "en": "Template Center",
        "zh": "模板中心", "ja": "テンプレートセンター",
    },
}

# 一级分类下二级目录 / 文件名 → slug 的内置词典（用于 group 第二层 + 文件 slug）
# 兜底用 hash6，并写入 slug-overrides.json 等人工补
BUILTIN_SLUG_MAP: dict[str, str] = {
    # 9. 钉钉文档 子目录
    "插入内容": "insert-content",
    "打印和导出": "print-export",
    "样式排版": "style-format",
    "协作互动": "collaboration",
    "关联钉钉": "dingtalk-link",
    "使用设置": "settings",
    "常见问题": "faq",
    "快捷键输入": "shortcuts-input",
    "插入OKR": "insert-okr",
    # 9. 钉钉文档 文件名
    "钉钉文档": "overview",
    "钉钉文档，企业知识资产的数字花园": "digital-garden",
    "安装、使用「钉钉文档闪存」插件": "flash-plugin",
    "插入白板": "insert-whiteboard",
    "插入宜搭": "insert-yida",
    "插入日期": "insert-date",
    "插入公式": "insert-formula",
    "插入表格": "insert-table",
    "插入代码": "insert-code",
    "插入目录": "insert-toc",
    "插入格式": "insert-format",
    "插入音视频": "insert-media",
    "插入表情列表": "insert-emoji",
    "插入文本绘图说明": "insert-text-drawing",
    "插入图片": "insert-image",
    "插入链接": "insert-link",
    "插入附件": "insert-attachment",
    "插入OKR": "insert-okr",
    "插入叮当OKR": "insert-dingdang-okr",
    "插入北极星OKR": "insert-polaris-okr",
    "打印": "print",
    "导出长图": "export-long-image",
    "下载为PDF": "export-pdf",
    "导出Word": "export-word",
    "导出 Markdown 文件": "export-markdown",
    "导入 Markdown 文件": "import-markdown",
    "编辑 Markdown": "edit-markdown",
    "快捷键": "shortcuts",
    "查找替换": "find-replace",
    "Markdown 使用手册": "markdown-guide",
    "双屏模式如何同时编辑两份文档？": "dual-screen-mode",
    "设置文本格式": "text-format",
    "设置文档大纲": "outline",
    "设置段落格式": "paragraph-format",
    "调整页面布局": "page-layout",
    "设置自动调整中英文间距": "auto-spacing",
    "添加或编辑列表": "list-format",
    "划词评论": "inline-comment",
    "演示模式现场互动": "presentation-interaction",
    "评论中如何插入图片": "comment-image",
    "如何快速查看文档协作通知": "collaboration-notifications",
    "钉钉文档如何实现安全协作": "secure-collaboration",
    "如何邀请他人一起进行文档协作": "invite-collaborators",
    "演示模式": "presentation",
    "任务列表生成待办": "todo-from-list",
    "关联钉钉项目看板": "link-project-board",
    "群内聊天记录搜索钉钉文档": "search-in-chat",
    "输入@提及人": "mention",
    "将文档另存为模板": "save-as-template",
    "使用浏览器打开钉钉文档": "open-in-browser",
    "如何修改系统默认浏览器？": "set-default-browser",
    "如何查看编辑历史记录": "edit-history",
    "钉钉文档网页版支持哪些浏览器？": "supported-browsers",
    "钉钉文档有哪些常见功能使用上限？": "feature-limits",
    "知识库内文档被移动后，权限会有何变化？": "moved-doc-permissions",
    "为什么拥有「可查看下载」权限，依然无法复制、下载、打印文档？": "cannot-copy-download-print",
    "常见使用问题": "common-issues",
}

# ----------- 工具函数 -----------

def sha1_of(content: bytes) -> str:
    return hashlib.sha1(content).hexdigest()


def short_hash(text: str, length: int = 6) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


# 去掉 .md 文件名前导编号 / (1)(2) 后缀
_LEADING_NUMBER = re.compile(r"^[0-9]+(\.[0-9]+)*\.?\s*")
_SUFFIX_DUP = re.compile(r"\([0-9]+\)$")


def clean_stem(stem: str) -> str:
    """去掉前导 '9. ' / 后缀 '(1)' 等。"""
    s = _LEADING_NUMBER.sub("", stem).strip()
    s = _SUFFIX_DUP.sub("", s).strip()
    return s


_INVALID_SLUG_CHARS = re.compile(r"[^a-z0-9-]+")
_DASH_RUNS = re.compile(r"-+")


def _ascii_slugify(s: str) -> str:
    s = s.lower()
    s = _INVALID_SLUG_CHARS.sub("-", s)
    s = _DASH_RUNS.sub("-", s).strip("-")
    return s


def to_slug(zh_name: str, overrides: dict[str, str], unresolved: dict[str, str]) -> str:
    """中文名 → 英文 slug。命中 overrides 或 builtin 用之；否则 hash6 兜底并写入 unresolved。"""
    name = clean_stem(zh_name)
    if name in overrides and overrides[name]:
        return _ascii_slugify(overrides[name])
    if name in BUILTIN_SLUG_MAP:
        return _ascii_slugify(BUILTIN_SLUG_MAP[name])
    # 兜底：先试纯 ASCII（如 "Markdown 使用手册" 切片含英文）
    ascii_candidate = _ascii_slugify(name)
    if ascii_candidate and not _INVALID_SLUG_CHARS.search(ascii_candidate.replace("-", "")):
        # 若全去掉中文后还有可读 ASCII（至少 3 字符），用 page-<asciicandidate>-<hash> 兜底
        if len(ascii_candidate) >= 3:
            unresolved[name] = ""
            return f"{ascii_candidate}-{short_hash(name)}"
    # 完全无 ASCII → hash6
    unresolved[name] = ""
    return f"page-{short_hash(name)}"


# ----------- mdx 转义 -----------

_CODE_FENCE = re.compile(r"^[ \t]{0,3}```", re.MULTILINE)


def split_code_blocks(text: str) -> list[tuple[bool, str]]:
    """切分为 [(is_code, chunk), ...]，code 块不动。"""
    parts: list[tuple[bool, str]] = []
    pos = 0
    in_code = False
    while True:
        m = _CODE_FENCE.search(text, pos)
        if not m:
            parts.append((in_code, text[pos:]))
            return parts
        parts.append((in_code, text[pos : m.start()]))
        # 把 ``` 本身留在 chunk 末尾 / 开头
        end = text.find("\n", m.end())
        if end < 0:
            parts.append((True, text[m.start():]))
            return parts
        fence_chunk = text[m.start() : end + 1]
        if in_code:
            # 关闭
            parts.append((True, fence_chunk))
            in_code = False
        else:
            # 打开
            parts.append((True, fence_chunk))
            in_code = True
        pos = end + 1


_BRACE_ESCAPE = re.compile(r"(?<!\\)([{}])")
# 行内 code `..` 内的内容不动
_INLINE_CODE = re.compile(r"(`[^`\n]*`)")
# 已知 HTML 标签白名单（小写），其他小写 `<word>` 都按字面量转义
_KNOWN_HTML = {
    "a", "abbr", "address", "article", "aside", "audio", "b", "bdi", "bdo",
    "blockquote", "body", "br", "button", "canvas", "caption", "cite", "code",
    "col", "colgroup", "data", "datalist", "dd", "del", "details", "dfn",
    "dialog", "div", "dl", "dt", "em", "embed", "fieldset", "figcaption",
    "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "head",
    "header", "hr", "html", "i", "iframe", "img", "input", "ins", "kbd",
    "label", "legend", "li", "link", "main", "map", "mark", "meta", "meter",
    "nav", "noscript", "object", "ol", "optgroup", "option", "output", "p",
    "param", "picture", "pre", "progress", "q", "rp", "rt", "ruby", "s",
    "samp", "script", "section", "select", "small", "source", "span",
    "strong", "style", "sub", "summary", "sup", "svg", "table", "tbody",
    "td", "template", "textarea", "tfoot", "th", "thead", "time", "title",
    "tr", "track", "u", "ul", "var", "video", "wbr",
}
# 匹配 <tagname...> 形式（含 </tagname...>）
_TAG_LIKE = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9-]*)(\s|/|>)")
# HTML void 元素改写为 self-closing（MDX 严格模式要求）
_HTML_VOID = re.compile(r"<(br|hr|img|input|meta|link|col|area|base|source|track|wbr)(\s[^>]*)?\s*/?>", re.IGNORECASE)


def _escape_unknown_tags(text: str) -> str:
    """`<word>` 中 word 不在 HTML 白名单且非大写开头（非 JSX 组件）→ `&lt;word`"""
    def repl(m: re.Match) -> str:
        slash, tag, tail = m.group(1), m.group(2), m.group(3)
        if tag[0].isupper():
            return m.group(0)  # JSX component
        if tag.lower() in _KNOWN_HTML:
            return m.group(0)
        return f"&lt;{slash}{tag}{tail}"
    return _TAG_LIKE.sub(repl, text)


def escape_mdx_chunk(chunk: str) -> str:
    # 先把 HTML void 元素改写为 self-closing（必须早于 inline-code stash，
    # 否则 ``` 三连反引号在内部被解析为「空 + 内容 + 空」三段 inline-code 时
    # 中间段会把 <br> 吞掉，逃过这一步）
    chunk = _HTML_VOID.sub(lambda m: f"<{m.group(1).lower()}{m.group(2) or ''} />", chunk)

    placeholders: list[str] = []

    def stash(m: re.Match) -> str:
        placeholders.append(m.group(0))
        return f"\x00CODE{len(placeholders)-1}\x00"

    body = _INLINE_CODE.sub(stash, chunk)
    body = _BRACE_ESCAPE.sub(r"\\\1", body)
    # 1) `<` 后非字母/斜杠/感叹 → 字面量
    body = re.sub(r"<(?![a-zA-Z/!])", "&lt;", body)
    # 2) `<word>` 不是已知 HTML / 非大写开头 → 字面量
    body = _escape_unknown_tags(body)
    for i, p in enumerate(placeholders):
        body = body.replace(f"\x00CODE{i}\x00", p)
    return body


def escape_mdx(text: str) -> str:
    out = []
    for is_code, chunk in split_code_blocks(text):
        if is_code:
            out.append(chunk)
        else:
            out.append(escape_mdx_chunk(chunk))
    return "".join(out)


# ----------- 链接重写 -----------

_MD_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

ALIDOCS_HOSTS = ("alidocs.dingtalk.com", "docs.dingtalk.com")
ALIDOCS_NEW_HOST = "docs.dingtalk.io"


@dataclass
class LinkRewriteStats:
    internal_hits: int = 0
    domain_swapped: int = 0
    stripped: int = 0
    external_kept: int = 0
    image_kept: int = 0


def is_image_url(url: str) -> bool:
    return any(url.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"))


def is_alidocs_url(url: str) -> bool:
    return any(host in url for host in ALIDOCS_HOSTS)


def http_probe(url: str, cache: dict[str, int]) -> int:
    if url in cache:
        return cache[url]
    try:
        r = requests.head(url, timeout=1.0, allow_redirects=True)
        code = r.status_code
        if code >= 400:
            # 有些站 HEAD 不支持，再试一次 GET
            r2 = requests.get(url, timeout=1.0, allow_redirects=True, stream=True)
            code = r2.status_code
            r2.close()
    except Exception:
        code = 0
    cache[url] = code
    return code


def rewrite_links(
    text: str,
    link_map: dict[str, str],
    http_cache: dict[str, int],
    stats: LinkRewriteStats,
    *,
    skip_http: bool = False,
    lang_prefix: str = "",
) -> str:
    def repl(m: re.Match) -> str:
        label = m.group(1)
        url = m.group(2)
        # 图片占位（与 ![ 共存：实际 markdown 图片是 ![]() 不会被 [] 命中）
        if is_image_url(url):
            stats.image_kept += 1
            return m.group(0)
        if not is_alidocs_url(url):
            stats.external_kept += 1
            return m.group(0)
        # Step A: 内部映射
        # 归一化 URL：去掉 query / fragment 后再查
        bare = url.split("#")[0].split("?")[0]
        if bare in link_map:
            stats.internal_hits += 1
            target = link_map[bare]
            if lang_prefix and target.startswith("/"):
                target = f"/{lang_prefix}{target}"
            return f"[{label}]({target})"
        # Step B: 换域名探活
        if skip_http:
            stats.stripped += 1
            return label
        for host in ALIDOCS_HOSTS:
            if host in url:
                new_url = url.replace(host, ALIDOCS_NEW_HOST)
                code = http_probe(new_url, http_cache)
                if 200 <= code < 400:
                    stats.domain_swapped += 1
                    return f"[{label}]({new_url})"
                break
        # Step C: 退化为纯文本
        stats.stripped += 1
        return label

    return _MD_LINK.sub(repl, text)


# ----------- 解析单篇 .md -----------

@dataclass
class Page:
    group_slug: str          # 一级分类 slug，如 dingtalk-docs
    subgroup_slug: str | None  # 二级目录 slug，None = 顶级
    thirdgroup_slug: str | None = None  # 三级目录 slug，None = 二级直属
    slug: str = ""           # 本页 slug
    is_index: bool = False   # 是否是 group/subgroup/thirdgroup 的 index
    src_path: Path = None    # 源 .md 路径
    zh_name: str = ""        # 原中文文件名（脱后缀，未脱编号）
    title: str = ""          # 解析出的 H1
    description: str = ""    # 首段截 160
    body: str = ""           # 经过 mdx 转义和链接重写后的正文
    sha1: str = ""           # 原文件 SHA1（用于 dedup）
    # 输出路径
    zh_out_relative: str = ""  # zh/docs/<group>/[<subgroup>/[<thirdgroup>/]]<slug>.mdx
    en_out_relative: str = ""
    ja_out_relative: str = ""
    nav_path: str = ""       # 用于 docs.json，如 docs/dingtalk-docs/insert-content/insert-image


_H1 = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def parse_frontmatter_data(text: str, file_stem: str) -> tuple[str, str, str]:
    """返回 (title, description, body_without_h1)。"""
    m = _H1.search(text)
    title = m.group(1).strip() if m else clean_stem(file_stem)
    if m:
        body = text[: m.start()] + text[m.end():]
    else:
        body = text
    # 首段非空文本
    desc = ""
    for line in body.splitlines():
        s = line.strip()
        if not s:
            continue
        # 跳过 markdown 图片 / 链接 / 标题
        if s.startswith("#") or s.startswith("!["):
            continue
        # 简单去掉 markdown 行内 emphasis 和链接
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        s = re.sub(r"[*_`~]", "", s)
        s = s.strip()
        if s:
            desc = s[:160]
            break
    return title, desc, body.lstrip()


def yaml_escape(s: str) -> str:
    """frontmatter 字符串：用双引号 + 转义。"""
    s = s.replace("\\", "\\\\").replace("\"", "\\\"")
    s = s.replace("\n", " ").strip()
    return f'"{s}"'


def build_zh_mdx(title: str, description: str, body: str) -> str:
    fm = f"---\ntitle: {yaml_escape(title)}\ndescription: {yaml_escape(description)}\n---\n\n"
    return fm + body.rstrip() + "\n"


def build_placeholder_mdx(lang: str, title_zh: str, zh_relative: str) -> str:
    if lang == "en":
        title = f"{title_zh} — TODO translate"
        desc = "TODO translate from zh"
        comment = f"TODO: Translate from /Users/yanxin/www/dingtalk-docs/{zh_relative}"
    else:  # ja
        title = f"{title_zh} — TODO 翻訳"
        desc = "TODO: zh 版から翻訳"
        comment = f"TODO: {zh_relative} から翻訳"
    fm = f"---\ntitle: {yaml_escape(title)}\ndescription: {yaml_escape(desc)}\n---\n\n"
    body = f"{{/* {comment} */}}\n"
    return fm + body


# ----------- 主流程 -----------

def scan_group(
    group_dir: Path,
    group_slug: str,
    slug_map: dict[str, str],
    overrides: dict[str, str],
    unresolved: dict[str, str],
) -> list[Page]:
    """扫描一级分类目录，返回所有 Page 元数据（尚未填写 body/link 重写）。"""
    pages: list[Page] = []
    # 1) 顶级 .md：分类索引（{N}. xxx.md → group index） + 散文
    for md_path in sorted(group_dir.glob("*.md")):
        stem = md_path.stem
        cleaned = clean_stem(stem)
        # 顶级"{N}. xxx" 视作 group 索引（同名于一级目录名）
        is_index = (cleaned == clean_stem(group_dir.name))
        slug = "index" if is_index else to_slug(stem, overrides, unresolved)
        if not is_index:
            slug_map.setdefault(cleaned, slug)
        pages.append(Page(
            group_slug=group_slug,
            subgroup_slug=None,
            slug=slug,
            is_index=is_index,
            src_path=md_path,
            zh_name=cleaned,
        ))
    # 2) 二级目录
    for sub in sorted(group_dir.iterdir()):
        if not sub.is_dir():
            continue
        sub_zh = clean_stem(sub.name)
        sub_slug = to_slug(sub.name, overrides, unresolved)
        slug_map.setdefault(sub_zh, sub_slug)
        # 2a) 二级目录下的 .md
        for md_path in sorted(sub.glob("*.md")):
            stem = md_path.stem
            cleaned = clean_stem(stem)
            is_index = (cleaned == sub_zh)
            slug = "index" if is_index else to_slug(stem, overrides, unresolved)
            if not is_index:
                slug_map.setdefault(cleaned, slug)
            pages.append(Page(
                group_slug=group_slug,
                subgroup_slug=sub_slug,
                slug=slug,
                is_index=is_index,
                src_path=md_path,
                zh_name=cleaned,
            ))
        # 2b) 三级目录 → 嵌套 group（Mintlify 支持深度嵌套）
        for third in sorted(sub.iterdir()):
            if not third.is_dir():
                continue
            third_zh = clean_stem(third.name)
            third_slug = to_slug(third.name, overrides, unresolved)
            slug_map.setdefault(third_zh, third_slug)
            for md_path in sorted(third.glob("*.md")):
                stem = md_path.stem
                cleaned = clean_stem(stem)
                is_index = (cleaned == third_zh)
                slug = "index" if is_index else to_slug(stem, overrides, unresolved)
                if not is_index:
                    slug_map.setdefault(cleaned, slug)
                pages.append(Page(
                    group_slug=group_slug,
                    subgroup_slug=sub_slug,
                    thirdgroup_slug=third_slug,
                    slug=slug,
                    is_index=is_index,
                    src_path=md_path,
                    zh_name=cleaned,
                ))
    return pages


def dedupe_by_sha1(pages: list[Page]) -> tuple[list[Page], list[str]]:
    """SHA1 一致的 (1)(2) 副本去掉；冲突且异内容的 slug 加 -extra。"""
    seen_sha1: dict[str, Page] = {}
    by_key: dict[tuple[str, Optional[str], Optional[str], str], list[Page]] = {}
    for p in pages:
        content = p.src_path.read_bytes()
        p.sha1 = sha1_of(content)
        by_key.setdefault((p.group_slug, p.subgroup_slug, p.thirdgroup_slug, p.slug), []).append(p)
    notes: list[str] = []
    kept: list[Page] = []
    for key, group_pages in by_key.items():
        if len(group_pages) == 1:
            kept.append(group_pages[0])
            continue
        # 同 slug 多个：先按 SHA1 dedup
        unique_by_sha1: dict[str, Page] = {}
        for p in group_pages:
            if p.sha1 not in unique_by_sha1:
                unique_by_sha1[p.sha1] = p
        if len(unique_by_sha1) == 1:
            chosen = next(iter(unique_by_sha1.values()))
            kept.append(chosen)
            others = [p for p in group_pages if p is not chosen]
            for o in others:
                notes.append(f"DEDUP-SAME: {o.src_path.name} 与 {chosen.src_path.name} 同 SHA1，丢弃")
        else:
            # 内容不同 → 第一个保 slug，其余加 -extra-<n>
            first = group_pages[0]
            kept.append(first)
            for i, p in enumerate(group_pages[1:], start=1):
                p.slug = f"{first.slug}-extra-{i}"
                kept.append(p)
                notes.append(f"DEDUP-DIFF: {p.src_path.name} SHA1 异于 {first.src_path.name}，改名 {p.slug}")
    return kept, notes


def fill_metadata_and_paths(pages: list[Page]) -> None:
    """填 title/description/body（不含链接重写）+ 输出路径。"""
    for p in pages:
        text = p.src_path.read_text(encoding="utf-8")
        title, description, body = parse_frontmatter_data(text, p.src_path.stem)
        p.title = title or clean_stem(p.src_path.stem)
        p.description = description or p.title
        p.body = body
        # 路径
        segs = [p.group_slug]
        if p.subgroup_slug:
            segs.append(p.subgroup_slug)
        if p.thirdgroup_slug:
            segs.append(p.thirdgroup_slug)
        segs.append(p.slug)
        rel = f"docs/{'/'.join(segs)}.mdx"
        nav = f"docs/{'/'.join(segs)}"
        p.en_out_relative = rel
        p.zh_out_relative = f"zh/{rel}"
        p.ja_out_relative = f"ja/{rel}"
        p.nav_path = nav


def build_link_map(pages: list[Page], group_dir: Path) -> dict[str, str]:
    """从所有 .md 内出现的 alidocs URL → 内部 nav_path 的映射。

    粗策略：扫所有 archive .md，提取 alidocs URL；如果某 URL 的 link label 与某 Page 的 title 或 zh_name 匹配，记为映射。
    """
    link_map: dict[str, str] = {}
    # 建索引：zh_name → page
    by_name: dict[str, Page] = {}
    by_title: dict[str, Page] = {}
    for p in pages:
        by_name.setdefault(p.zh_name, p)
        by_title.setdefault(p.title, p)
    # 扫所有 .md 找链接
    for md_path in group_dir.rglob("*.md"):
        text = md_path.read_text(encoding="utf-8", errors="replace")
        for m in _MD_LINK.finditer(text):
            label = m.group(1).strip()
            url = m.group(2).split("#")[0].split("?")[0]
            if not is_alidocs_url(url):
                continue
            # 清理 label 的 markdown emphasis
            clean_label = re.sub(r"[*_`~+]", "", label).strip()
            clean_label = clean_label.strip("「」【】《》()（）")
            page = by_title.get(clean_label) or by_name.get(clean_label)
            if page is not None:
                link_map[url] = f"/{page.nav_path}"
    return link_map


def rewrite_all_bodies(pages: list[Page], link_map: dict[str, str], http_cache: dict[str, int], *, skip_http: bool) -> LinkRewriteStats:
    stats = LinkRewriteStats()
    for p in pages:
        # body 只用在 zh 文件，链接前缀用 zh
        p.body = rewrite_links(p.body, link_map, http_cache, stats, skip_http=skip_http, lang_prefix="zh")
        p.body = escape_mdx(p.body)
    return stats


def write_outputs(pages: list[Page], *, dry_run: bool) -> tuple[int, int, int]:
    if dry_run:
        return (0, 0, 0)
    zh_n = en_n = ja_n = 0
    for p in pages:
        zh_path = REPO_ROOT / p.zh_out_relative
        en_path = REPO_ROOT / p.en_out_relative
        ja_path = REPO_ROOT / p.ja_out_relative
        zh_path.parent.mkdir(parents=True, exist_ok=True)
        en_path.parent.mkdir(parents=True, exist_ok=True)
        ja_path.parent.mkdir(parents=True, exist_ok=True)
        zh_path.write_text(build_zh_mdx(p.title, p.description, p.body), encoding="utf-8")
        zh_n += 1
        if not en_path.exists():
            en_path.write_text(build_placeholder_mdx("en", p.title, p.zh_out_relative), encoding="utf-8")
            en_n += 1
        if not ja_path.exists():
            ja_path.write_text(build_placeholder_mdx("ja", p.title, p.zh_out_relative), encoding="utf-8")
            ja_n += 1
    return (zh_n, en_n, ja_n)


def _display_name(slug: str, lang: str) -> str:
    """二级/三级 group 的显示名：lang=zh 反查 BUILTIN 中文；en/ja 用 Title Case。"""
    if lang == "zh":
        for zh, s in BUILTIN_SLUG_MAP.items():
            if s == slug:
                return zh
        return slug
    return slug.replace("-", " ").title()


def build_nav_fragment(pages: list[Page], group_slug: str, lang: str) -> dict:
    """生成单语 navigation tab fragment（支持二/三级嵌套）。"""
    meta = next(v for v in GROUP_META.values() if v["slug"] == group_slug)
    group_title = meta[lang]
    prefix = "" if lang == "en" else f"{lang}/"

    # 三层桶：top_items / sub[sub_slug] / sub_thirds[sub_slug][third_slug]
    top_items: list = []  # str（page）或在末尾插嵌套 group
    sub_pages: "OrderedDict[str, list[str]]" = OrderedDict()
    sub_indexes: dict[str, str] = {}
    sub_third_pages: dict[str, "OrderedDict[str, list[str]]"] = {}
    sub_third_indexes: dict[str, dict[str, str]] = {}

    for p in pages:
        nav = f"{prefix}{p.nav_path}"
        if p.subgroup_slug is None:
            if p.is_index:
                top_items.insert(0, nav)
            else:
                top_items.append(nav)
            continue
        sub_pages.setdefault(p.subgroup_slug, [])
        sub_third_pages.setdefault(p.subgroup_slug, OrderedDict())
        sub_third_indexes.setdefault(p.subgroup_slug, {})
        if p.thirdgroup_slug is None:
            if p.is_index:
                sub_indexes[p.subgroup_slug] = nav
            else:
                sub_pages[p.subgroup_slug].append(nav)
        else:
            sub_third_pages[p.subgroup_slug].setdefault(p.thirdgroup_slug, [])
            if p.is_index:
                sub_third_indexes[p.subgroup_slug][p.thirdgroup_slug] = nav
            else:
                sub_third_pages[p.subgroup_slug][p.thirdgroup_slug].append(nav)

    items: list = list(top_items)
    for sub_slug in sub_pages:
        sub_items: list = []
        if sub_slug in sub_indexes:
            sub_items.append(sub_indexes[sub_slug])
        sub_items.extend(sub_pages[sub_slug])
        # 嵌套的三级 group
        for third_slug, third_pages in sub_third_pages.get(sub_slug, {}).items():
            third_items: list = []
            third_idx = sub_third_indexes.get(sub_slug, {}).get(third_slug)
            if third_idx:
                third_items.append(third_idx)
            third_items.extend(third_pages)
            sub_items.append({"group": _display_name(third_slug, lang), "pages": third_items})
        items.append({"group": _display_name(sub_slug, lang), "pages": sub_items})

    return {
        "tab": "Docs" if lang == "en" else ("文档" if lang == "zh" else "ドキュメント"),
        "groups": [{"group": group_title, "pages": items}],
    }


def write_report(group_dir_name: str, group_slug: str, pages: list[Page], notes: list[str], stats: LinkRewriteStats, link_map: dict[str, str], unresolved: dict[str, str]) -> Path:
    path = OUTPUT_DIR / f"report-{group_slug}.md"
    lines = [
        f"# Import Report: {group_dir_name} ({group_slug})",
        "",
        f"- 总页数: **{len(pages)}**",
        f"- top-level: {len([p for p in pages if p.subgroup_slug is None])}",
        f"- sub-grouped: {len([p for p in pages if p.subgroup_slug])}",
        f"- index 页: {len([p for p in pages if p.is_index])}",
        "",
        "## 链接重写",
        f"- 内部命中（→ 相对路径）: **{stats.internal_hits}**",
        f"- 域名换 + 探活 200 → 用新 URL: **{stats.domain_swapped}**",
        f"- 退化为纯文本: **{stats.stripped}**",
        f"- 外站外链保留: {stats.external_kept}",
        f"- 图片链接保留: {stats.image_kept}",
        f"- link-map 总条目: {len(link_map)}",
        "",
        "## 去重 / 改名",
    ]
    if notes:
        for n in notes:
            lines.append(f"- {n}")
    else:
        lines.append("- 无")
    lines += [
        "",
        "## 未解析中文 slug（需要人工填 slug-overrides.json）",
    ]
    if unresolved:
        for zh in sorted(unresolved):
            lines.append(f"- `{zh}`")
    else:
        lines.append("- 无（全部命中 BUILTIN 或 overrides）")
    lines += [
        "",
        "## 页面清单（slug → 源文件）",
    ]
    for p in pages:
        marker = " (INDEX)" if p.is_index else ""
        lines.append(f"- `{p.nav_path}`{marker} ← {p.src_path.name}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def process_group(
    group_dir: Path,
    *,
    dry_run: bool,
    slug_map: dict[str, str],
    overrides: dict[str, str],
    http_cache: dict[str, int],
    skip_http: bool,
) -> dict:
    if group_dir.name not in GROUP_META:
        # 单文件分类 13. 钉钉白板.md → 走单独路径
        return {"skipped": True, "reason": f"目录名 {group_dir.name} 不在 GROUP_META 中"}
    meta = GROUP_META[group_dir.name]
    group_slug = meta["slug"]
    unresolved: dict[str, str] = {}
    pages = scan_group(group_dir, group_slug, slug_map, overrides, unresolved)
    pages, dedup_notes = dedupe_by_sha1(pages)
    fill_metadata_and_paths(pages)
    link_map = build_link_map(pages, group_dir)
    stats = rewrite_all_bodies(pages, link_map, http_cache, skip_http=skip_http)
    counts = write_outputs(pages, dry_run=dry_run)
    # nav fragments
    nav_en = build_nav_fragment(pages, group_slug, "en")
    nav_zh = build_nav_fragment(pages, group_slug, "zh")
    nav_ja = build_nav_fragment(pages, group_slug, "ja")
    save_json(OUTPUT_DIR / f"nav-fragment-{group_slug}.json", {
        "en": nav_en, "zh": nav_zh, "ja": nav_ja,
    })
    save_json(OUTPUT_DIR / f"link-map-{group_slug}.json", link_map)
    report_path = write_report(group_dir.name, group_slug, pages, dedup_notes, stats, link_map, unresolved)
    return {
        "skipped": False,
        "group_slug": group_slug,
        "page_count": len(pages),
        "stats": stats.__dict__,
        "link_map_size": len(link_map),
        "unresolved_count": len(unresolved),
        "dry_run": dry_run,
        "written_zh": counts[0],
        "written_en_placeholder": counts[1],
        "written_ja_placeholder": counts[2],
        "report": str(report_path.relative_to(REPO_ROOT)),
    }


def process_single_file_group(md_path: Path, slug_map: dict[str, str], overrides: dict[str, str], *, dry_run: bool) -> dict:
    """13. 钉钉白板.md 这种单文件分类。"""
    stem = md_path.stem  # "13. 钉钉白板"
    if stem not in GROUP_META:
        return {"skipped": True, "reason": f"单文件 {stem} 不在 GROUP_META 中"}
    meta = GROUP_META[stem]
    group_slug = meta["slug"]
    unresolved: dict[str, str] = {}
    text = md_path.read_text(encoding="utf-8")
    title, description, body = parse_frontmatter_data(text, stem)
    body = escape_mdx(body)
    sha1 = sha1_of(text.encode("utf-8"))
    page = Page(
        group_slug=group_slug, subgroup_slug=None, slug="index",
        is_index=True, src_path=md_path, zh_name=clean_stem(stem),
        title=title or clean_stem(stem),
        description=description or title or clean_stem(stem),
        body=body, sha1=sha1,
    )
    page.en_out_relative = f"docs/{group_slug}/index.mdx"
    page.zh_out_relative = f"zh/docs/{group_slug}/index.mdx"
    page.ja_out_relative = f"ja/docs/{group_slug}/index.mdx"
    page.nav_path = f"docs/{group_slug}"
    counts = write_outputs([page], dry_run=dry_run)
    nav = {
        "en": {"tab": "Docs", "groups": [{"group": meta["en"], "pages": [page.nav_path]}]},
        "zh": {"tab": "文档", "groups": [{"group": meta["zh"], "pages": [f"zh/{page.nav_path}"]}]},
        "ja": {"tab": "ドキュメント", "groups": [{"group": meta["ja"], "pages": [f"ja/{page.nav_path}"]}]},
    }
    save_json(OUTPUT_DIR / f"nav-fragment-{group_slug}.json", nav)
    return {
        "skipped": False, "group_slug": group_slug, "page_count": 1,
        "dry_run": dry_run,
        "written_zh": counts[0], "written_en_placeholder": counts[1], "written_ja_placeholder": counts[2],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Import dingtalk-docs-archive into Mintlify site.")
    parser.add_argument("--archive", required=True, help="Path to dingtalk-docs-archive root")
    parser.add_argument("--only", action="append", help="Only process given top-level dir name (repeatable)")
    parser.add_argument("--all", action="store_true", help="Process all 16 categories")
    parser.add_argument("--dry-run", action="store_true", help="Do not write any mdx files")
    parser.add_argument("--skip-http", action="store_true", help="Skip HTTP domain-swap probing (debug)")
    args = parser.parse_args()

    archive = Path(args.archive).expanduser().resolve()
    if not archive.is_dir():
        sys.exit(f"Archive not found: {archive}")

    if not args.only and not args.all:
        sys.exit("Must specify --only NAME or --all")

    slug_map = load_json(SLUG_MAP_PATH, {})
    overrides = load_json(SLUG_OVERRIDES_PATH, {})
    http_cache = load_json(HTTP_CACHE_PATH, {})

    targets: list[Path] = []
    if args.all:
        for name in GROUP_META:
            p = archive / name
            if p.is_dir():
                targets.append(p)
            elif (archive / f"{name}.md").is_file():
                targets.append(archive / f"{name}.md")
    else:
        for name in args.only:
            p = archive / name
            if p.is_dir():
                targets.append(p)
            elif (archive / f"{name}.md").is_file():
                targets.append(archive / f"{name}.md")
            else:
                print(f"WARN: target not found: {name}")

    results = []
    for target in targets:
        print(f"\n=== {'[DRY]' if args.dry_run else '[WET]'} processing: {target.name} ===")
        t0 = time.time()
        if target.is_file():
            res = process_single_file_group(target, slug_map, overrides, dry_run=args.dry_run)
        else:
            res = process_group(target, dry_run=args.dry_run, slug_map=slug_map,
                                overrides=overrides, http_cache=http_cache,
                                skip_http=args.skip_http)
        res["elapsed_s"] = round(time.time() - t0, 2)
        results.append({"target": target.name, **res})
        print(json.dumps({"target": target.name, **res}, ensure_ascii=False, indent=2))

    # 持久化
    save_json(SLUG_MAP_PATH, slug_map)
    save_json(HTTP_CACHE_PATH, http_cache)
    # 写 overrides 模板（若没存在）
    if not SLUG_OVERRIDES_PATH.exists():
        save_json(SLUG_OVERRIDES_PATH, {})

    save_json(OUTPUT_DIR / "last-run.json", {"results": results, "args": vars(args)})

    print("\n=== summary ===")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
