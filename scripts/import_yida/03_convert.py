#!/usr/bin/env python3
"""03_convert.py — 宜搭用户手册 HTML → MDX 转换器。

输入: staging/html/<last-slug>.html + output/toc.json
输出: zh/yida/<group>/<last-slug>.mdx + output/convert-report.json

用法: python3 scripts/import_yida/03_convert.py [slug ...]   # 不带参数则全量
"""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

BASE = Path(__file__).parent
REPO = BASE.parent.parent
TOC = json.loads((BASE / "output" / "toc.json").read_text())
STAGING = BASE / "staging" / "html"

# ---- 链接映射 ----
# 完整语雀路径 slug → 新站 page 路径；末段 slug → 新站 page 路径
FULL_MAP = {e["slug"]: "/" + e["file"] for e in TOC}
LAST_MAP = {e["slug"].split("/")[-1]: "/" + e["file"] for e in TOC}

# 已探测确认的死链（05_check_links.py 产出后人工核定）：命中则去链接保留文字
DEAD_LINKS = set(json.loads((BASE / "dead-links.json").read_text())) if (BASE / "dead-links.json").exists() else set()

# 开发者站组件 demo 链接（www.aliwork.com/developer/<name>）→ 已迁移组件文档路径
DEV_DEMO_MAP = {
    "ballon": "advanced/balloon",
    "banner-container": "advanced/bannerContainer",
    "button": "basic/button",
    "childtable-association": "form/tableField",
    "dialog": "basic/dialog",
    "drawer": "basic/drawer",
    "filter": "advanced/filter",
    "html": "advanced/HTML",
    "icon": "basic/icon",
    "iframe": "advanced/Iframe",
    "image": "basic/image",
    "jsx": "advanced/JSX",
    "link": "basic/link",
    "link-block": "basic/linkBlock",
    "menu": "advanced/menu",
    "pagination": "advanced/pagination",
    "progress": "advanced/progress",
    "search": "advanced/search",
    "slider": "advanced/slider",
    "step": "advanced/steps",
    "table-pc": "advanced/table",
    "text": "basic/text",
    "timeline": "advanced/timeLine",
    "tree": "advanced/tree",
    "video": "basic/video",
}

ALERT_MAP = {
    "info": "Note",
    "tips": "Tip",
    "success": "Check",
    "warning": "Warning",
    "danger": "Warning",
    "color4": "Note",
    "color5": "Note",
}

INTRANET_HOSTS = ("alibaba-inc.com", "antfin-inc.com", "yuque.antfin.com")
ZWSP = "\u200b"

# 国际版不适用的页内章节（末段 slug → 需删除的标题列表）：整节删除至下一个同级/更高级标题
SECTION_EXCLUDE = {
    "kab9piibinwhk1zn": ["历史文档（停止维护）"],
}

# 国际版不适用的单个块（末段 slug → 关键词列表）：命中关键词的块整个删除
BLOCK_EXCLUDE = {
    "kab9piibinwhk1zn": ["旧版帮助手册"],
}

# 死链去链后的文案精修（末段 slug → [(old, new)]）：逐处人工审过的上下文改写，
# 未命中会记 fixup-miss 告警（源内容变化时提醒复查）
UNLINK_TEXT_FIXUPS = {
    # 报名链接已失效：条件句改陈述句；书签卡片残留的图标+标题尾巴删除；Step 内孤立标题行并句
    "ch41p3rm3may1smg": [
        (
            "> 如果你也想加入我们，成为行业方案创新加速者，可以点击链接报名。",
            "> 欢迎加入我们，成为行业方案创新加速者。",
        ),
        (
            "，详见👉![](https://yida-support.oss-cn-shanghai.aliyuncs.com/static/png/lALPDssxhxMkj0fM8Mzw_240_240.png)钉钉酷SaaS工厂 | 钉钉酷SaaS工厂",
            "。",
        ),
        (
            "      后续如有计划参与宜搭SaaS工厂，请务必知悉\n\n      钉钉酷SaaS工厂共创须知及内测申请 | 钉钉酷SaaS工厂\n\n      相关内测须知，如果符合申请条件，可提交内测申请表单。",
            "      后续如有计划参与宜搭SaaS工厂，请务必知悉相关内测须知，如果符合申请条件，可提交内测申请表单。",
        ),
    ],
    # 反馈表单已失效；国内企业实例域名改国际版示例占位域名
    "bl2ba424xi3tww36": [
        ("可单击此处进行反馈。", "欢迎向宜搭团队反馈。"),
        ("xmtrf1.aliwork.com", "your-domain.yidaapps.com"),
    ],
    # 目标语雀页已失效，删除残留裸 URL 列表项；进销存 demo 列表项同删
    "dssg6y": [
        ("\n- 可查看业务关联公式常见问题及解法： https://www.yuque.com/yida/support/hf3pm8", ""),
        ("\n- 进销存使用场景搭建可 **点击查看**", ""),
    ],
    # 体验表单已不可达：仅含引导句的 Warning 块整个删除
    "yrofmw": [
        ("\n\n<Warning>\n**字符串处理类函数点击体验效果。**\n</Warning>", ""),
        ("\n\n<Warning>\n**时间处理类函数点击体验效果。**\n</Warning>", ""),
    ],
    # 升级详情页已失效，收拢为陈述句
    "gv4bgx": [
        ("- 旧版搜索存储不支持，新版搜索能力升级详情 **点此查看**", "- 旧版搜索存储不支持，新版搜索能力已升级"),
    ],
    # 书签卡片残留（图标+404页标题）改写；孤立文档名加书名号
    "chrmgzrsthf55vp9": [
        (
            "，如有问题，请查看![](https://yida-support.oss-cn-shanghai.aliyuncs.com/static/png/TB1Ctzd3VP7gK0jSZFjXXc5aXXa-152-152.png)找不到页面 | 钉钉宜搭·帮助中心",
            "，如有问题，请联系宜搭团队。",
        ),
        ("请参考酷应用高频FAQ及典型场景设计指南", "请参考《酷应用高频FAQ及典型场景设计指南》"),
    ],
    "ad8ixp": [
        ("请参考宜搭模板应用快速酷化&上架到钉钉酷应用市场SOP", "请参考《宜搭模板应用快速酷化&上架到钉钉酷应用市场SOP》"),
    ],
    # demo 表单已不可达：去引导尾巴/删引导行
    "gzllee": [
        ("，**表单演示参考**。", "。"),
        ("\n\n点击表单，直接查看步骤条实现效果：**点击查看**", ""),
    ],
    # 升级申请表单已失效，补全渠道语义
    "ez7e7hbgl1fytf78": [
        ("如需升级新存储，请申请；", "如需升级新存储，请联系宜搭团队申请；"),
    ],
}

# frontmatter description 的同类修复（摘要取自正文首段，可能带入国内版提示语）
DESC_FIXUPS = {
    "acu61g": [("适用于未升级到新版信息架构的组织查看使用手册。", "")],
}

# 标题精简覆盖（末段 slug → 新标题）：侧边栏展示规范中文 ≤15 字，去冗余前后缀；
# CASCADEDATEINTERVAL(V2) 为公式函数名专有名词，不精简
TITLE_OVERRIDES = {
    "ns6sahh7g6nr0exk": "QuickBI 与宜搭如何选择",
    "uc0ixy": "图片裁剪上传（高阶）",
    "eu0e6k": "图片裁剪上传（中阶）",
    "wae8oddztfq167ly": "宜搭服务端 API 限流处理",
    "aql605": "宜搭平台接口",
    "hndctc": "HTML/Iframe 嵌入",
    "asly1w503ereg286": "从AI表格/审批创建表单",
    "tpgibh": "奥数竞赛报名案例",
    "iwq1bg2obuoiocgt": "公开表单获取用户身份信息",
    "iv3cl671fto98g4v": "数据查看权限引用权限矩阵",
    "rrwdug": "宜搭 Open API",
    "ocmxyv": "JS 动作面板",
}

warnings = []  # (slug, kind, detail)


def warn(slug, kind, detail):
    warnings.append({"slug": slug, "kind": kind, "detail": str(detail)[:200]})


# ---------- 文本与转义 ----------

def esc(text, in_table=False):
    """MDX 内联文本转义：< { 必须转义；字面星号防误解析为强调；表格单元格内再转义竖线。"""
    t = text.replace(ZWSP, "")
    t = t.replace("\\", "\\\\").replace("<", "\\<").replace("{", "\\{")
    t = t.replace("`", "\\`").replace("*", "\\*")
    if in_table:
        t = t.replace("|", "\\|")
    return t


def heading_anchor(text):
    """近似 Mintlify(github-slugger) 的锚点规则：小写、空格→-、去常见标点，CJK 保留。"""
    t = text.strip().lower().replace(ZWSP, "")
    t = re.sub(r"[？?！!。．.，,、：:；;（）()《》<>【】\[\]\"'“”‘’/\\]+", "", t)
    t = re.sub(r"\s+", "-", t)
    return t


def fix_url(u):
    """协议相对 URL 补 https 前缀。"""
    return "https:" + u if u.startswith("//") else u


def strip_md(text):
    """去掉内联 markdown 语法，还原为纯文本（用于组件 title 属性）。"""
    t = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", t)
    t = t.replace("**", "").replace("`", "")
    t = t.replace("\\<", "<").replace("\\{", "{").replace("\\\\", "\\")
    return re.sub(r"\s+", " ", t).strip()


def attr_escape(text):
    """JSX 属性值转义（双引号包裹）。"""
    return text.replace('"', "”")


def step_title(text):
    """Step 标题修剪：去尾部句号。"""
    return text.rstrip("。. ")


# 提示框组件自带语义色，去除正文冗余的「说明：」类前缀
ALERT_PREFIX_RE = re.compile(
    r"^\*\*(说明|注意|提示|温馨提示|警告|重要|注|Notes?|Tips?)\s*[:：]?\s*\*\*\s*[:：]?\s*"
)


# ---------- 链接改写 ----------

class LinkRewriter:
    def __init__(self, slug, page_headings):
        self.slug = slug  # 完整语雀路径 slug
        self.page_url = f"https://docs.aliwork.com/docs/yida_support/{slug}"
        self.headings = page_headings  # id → 标题文本

    def rewrite(self, href):
        """返回 (new_href|None, unlink: bool)。None+unlink 表示去链接保留文字。"""
        href = (href or "").strip()
        if not href:
            return None, True
        if href.startswith("javascript:") or href.startswith("about:blank"):
            warn(self.slug, "dead-placeholder-url", href)
            return None, True
        if href.startswith("#"):
            frag = href[1:]
            if frag in self.headings:
                return "#" + heading_anchor(self.headings[frag]), False
            warn(self.slug, "anchor-unresolved", href)
            return None, True
        if href.startswith("mailto:") or href.startswith("dingtalk:"):
            return href, False
        if not href.startswith("http"):
            # 站内相对链接，按当前页 URL 解析
            absu = urljoin(self.page_url + "/", href)
            return self._map_absolute(absu, relative=True)
        return self._map_absolute(href, relative=False)

    def _map_absolute(self, url, relative):
        # 预发域名不应外泄，归一到正式域名后走既有映射
        url = url.replace("://pre-docs.aliwork.com", "://docs.aliwork.com")
        # 探测确认的死链：去链接保留文字
        if url.split("#")[0] in DEAD_LINKS:
            warn(self.slug, "dead-link-unlinked", url)
            return None, True
        p = urlparse(url)
        host = p.netloc.lower()
        if any(host.endswith(h) for h in INTRANET_HOSTS):
            warn(self.slug, "intranet-unlinked", url)
            return None, True
        if host == "docs.aliwork.com":
            m = re.match(r"^/docs/yida_support/(.+?)/?$", p.path)
            if m and m.group(1) in FULL_MAP:
                return FULL_MAP[m.group(1)], False
            if m and m.group(1).split("/")[-1] in LAST_MAP:
                return LAST_MAP[m.group(1).split("/")[-1]], False
            # 开发者手册书：对应页已迁移则转站内链接
            md = re.match(r"^/docs/developer/(.+?)/?$", p.path)
            if md:
                return self._map_developer(md.group(1), url)
            if m:
                warn(self.slug, "yida-support-miss", url)
            elif relative:
                warn(self.slug, "relative-other-book", url)
            return url, False  # 其他书籍保留外链（国际版无对应站点，记入报告人工复核）
        if host == "www.yuque.com":
            m = re.match(r"^/yida/support/(.+?)/?$", p.path)
            if m and m.group(1) in LAST_MAP:
                return LAST_MAP[m.group(1)], False
            if m:
                # 语雀原链可能需登录，改写为公开站同 slug 地址；改写产物命中死链则去链接
                target = f"https://docs.aliwork.com/docs/yida_support/{m.group(1)}"
                if target in DEAD_LINKS:
                    warn(self.slug, "dead-link-unlinked", target)
                    return None, True
                warn(self.slug, "yuque-support-miss", url)
                return target, False
            return url, False
        if host in ("oa.dingtalk.com",):
            return url.replace("oa.dingtalk.com", "oa.dingtalk.io"), False
        if host in ("www.dingtalk.com", "dingtalk.com", "tms.dingtalk.com", "h5.dingtalk.com"):
            return url.replace(".dingtalk.com", ".dingtalk.io"), False
        if host == "page.dingtalk.com":
            # page.dingtalk.io 不存在（已探测），保留原域名待人工复核
            warn(self.slug, "dingtalk-keep", url)
            return url, False
        if host.endswith("dingtalk.com"):
            warn(self.slug, "dingtalk-keep", url)  # open/alidocs 等保留待人工复核
            return url, False
        # 开发者站旧域名（developers.aliwork.com / gitee 镜像）→ 站内开发者手册
        if host in ("developers.aliwork.com", "yida-developer.gitee.io"):
            md = re.match(r"^/docs/(.+?)/?$", p.path)
            if md:
                return self._map_developer(md.group(1), url)
            return "/zh/open/yida/index", False
        if host == "www.aliwork.com":
            # 组件 demo 页：国际版无 demo 站，改指已迁移的组件文档
            mdemo = re.match(r"^/developer/([\w-]+)/?$", p.path)
            if mdemo and mdemo.group(1) in DEV_DEMO_MAP:
                return f"/zh/open/yida/components/{DEV_DEMO_MAP[mdemo.group(1)]}", False
            if p.path in ("/developer", "/developer/"):
                return "/zh/open/yida/index", False
            # /o/xxx 应用实例短链：国内环境部署的样例应用，国际版不存在，去链接
            if p.path.startswith("/o/") or p.path.startswith("/APP_"):
                warn(self.slug, "cn-app-instance-unlinked", url)
                return None, True
            # 平台功能页：国际版同构，直替域名
            return url.replace("://www.aliwork.com", "://www.yidaapps.com"), False
        if host.endswith(".aliwork.com") and host not in ("docs.aliwork.com", "qbi.data.aliwork.com"):
            # xmtrf1/xppmcy/ding 等企业实例子域名：国内部署的样例应用/反馈表单，国际版不可达，去链接
            if host == "pingtai.aliwork.com":
                # 宜搭开放平台附件处理服务，国际版域名同构替换
                return url.replace("://pingtai.aliwork.com", "://pingtai.yidaapps.com"), False
            warn(self.slug, "cn-app-instance-unlinked", url)
            return None, True
        return url, False

    def _map_developer(self, doc_path, url):
        """开发者手册文档路径 → /zh/open/yida 站内链接（验证目标 mdx 存在）。"""
        path = re.sub(r"\.html?$", "", doc_path.rstrip("/"))
        if (REPO / f"zh/open/yida/{path}.mdx").exists():
            return f"/zh/open/yida/{path}", False
        warn(self.slug, "developer-doc-miss", url)
        return None, True


# ---------- 内联渲染 ----------

def render_inline(node, rw, in_table=False):
    out = []
    for child in node.children:
        if isinstance(child, NavigableString):
            out.append(esc(str(child), in_table))
            continue
        if not isinstance(child, Tag):
            continue
        name = child.name
        cls = child.get("class") or []
        if name in ("meta", "style", "script", "button", "svg"):
            continue
        if name == "br":
            out.append("<br />" if in_table else "\n")
        elif name in ("strong", "b"):
            inner = render_inline(child, rw, in_table).strip()
            out.append(f"**{inner}**" if inner else "")
        elif name in ("em", "i"):
            inner = render_inline(child, rw, in_table).strip()
            out.append(f"*{inner}*" if inner else "")
        elif name in ("del", "s"):
            inner = render_inline(child, rw, in_table).strip()
            out.append(f"~~{inner}~~" if inner else "")
        elif name == "code" or "ne-code" in cls:
            raw = child.get_text().replace(ZWSP, "")
            if raw:
                fence = "``" if "`" in raw else "`"
                out.append(f"{fence}{raw}{fence}")
        elif name == "a":
            label = render_inline(child, rw, in_table).strip()
            href, unlink = rw.rewrite(child.get("href"))
            if unlink or not href:
                out.append(label)
            elif label:
                out.append(f"[{label}]({href})")
        elif name == "img":
            src = fix_url(child.get("src", ""))
            alt = (child.get("alt") or "").replace("]", "").replace("[", "")
            if src:
                out.append(f"![{alt}]({src})")
        elif name == "span" or name in ("u", "sub", "sup", "font", "mark"):
            out.append(render_inline(child, rw, in_table))
        else:
            # 未知内联元素：递归取内容
            out.append(render_inline(child, rw, in_table))
    return "".join(out)


# ---------- 块级渲染 ----------

def render_list(el, rw, depth=0, slug=None, extras=None):
    lines = []
    ordered = el.name == "ol"
    idx = int(el.get("start") or 1) - 1 if ordered else 0
    for li in el.find_all("li", recursive=False):
        idx += 1
        marker = f"{idx}." if ordered else "-"
        # 任务列表
        chk = li.find("input", attrs={"type": "checkbox"}, recursive=True)
        if chk is not None and not ordered:
            box = "[x]" if chk.has_attr("checked") else "[ ]"
            marker = f"- {box}"
        # li 内块级子元素
        inline_parts = []
        sub_blocks = []
        for child in li.children:
            if isinstance(child, Tag) and child.name in ("ul", "ol"):
                sub_blocks.append(render_list(child, rw, depth + 1, slug, extras))
            elif isinstance(child, Tag) and child.name == "p":
                inline_parts.append(render_inline(child, rw))
            elif isinstance(child, Tag) and child.name == "input":
                continue
            elif isinstance(child, Tag) and block_in_li(child):
                # 表格/提示框/代码块等块级内容不能压入行内，提升到列表之后输出
                if extras is not None:
                    blk = render_block_element(child, rw, slug)
                    if blk:
                        extras.append(blk)
            elif isinstance(child, NavigableString):
                inline_parts.append(esc(str(child)))
            elif isinstance(child, Tag):
                inline_parts.append(render_inline(child, rw))
        text = " ".join(x.strip() for x in inline_parts if x.strip())
        text = text.replace("\n", " ")
        indent = "  " * depth
        lines.append(f"{indent}{marker} {text}".rstrip())
        for sb in sub_blocks:
            lines.append(sb)
    return "\n".join(lines)


def block_in_li(child):
    cls = child.get("class") or []
    if child.name in ("table", "pre", "video", "blockquote"):
        return True
    return any(c in cls for c in ("ne-table", "ne-alert", "ne-codeblock", "ne-video", "ne-quote"))


def render_block_element(el, rw, slug):
    """渲染单个块级元素（供 li 内块级内容提升使用）。"""
    name = el.name
    cls = el.get("class") or []
    if name == "table" or "ne-table" in cls:
        tb = el if name == "table" else el.find("table")
        if tb is None:
            return ""
        return render_table_html(tb, rw) if table_is_complex(tb) else render_table_md(tb, rw)
    if "ne-alert" in cls:
        comp = ALERT_MAP.get(el.get("data-type", "info"), "Note")
        inner = render_blocks(el, rw, slug, 1)
        if inner:
            inner[0] = ALERT_PREFIX_RE.sub("", inner[0])
        body = "\n\n".join(b for b in inner if b.strip()).strip()
        return f"<{comp}>\n{body}\n</{comp}>" if body else ""
    if "ne-codeblock" in cls or name == "pre":
        return render_codeblock(el, rw)
    if name == "video" or "ne-video" in cls:
        v = el if name == "video" else el.find("video")
        return render_video(v, slug) if v is not None else ""
    if name == "blockquote" or "ne-quote" in cls:
        inner = render_blocks(el, rw, slug, 1)
        body = "\n\n".join(inner)
        return "\n".join("> " + l for l in body.split("\n"))
    return ""


def code_lang(el):
    for node in [el] + list(el.parents):
        for c in node.get("class") or []:
            m = re.match(r"^language-(\w+)$", c)
            if m:
                lang = m.group(1)
                return "text" if lang in ("plain", "plaintext") else lang
        if node.name == "div" and "lake-content" in (node.get("class") or []):
            break
    return "text"


def render_codeblock(el, rw):
    pre = el.find("pre") or el
    lines = []
    token_lines = pre.select(".token-line")
    if token_lines:
        for tl in token_lines:
            lines.append(tl.get_text())
    else:
        lines = pre.get_text().split("\n")
    body = "\n".join(l.rstrip() for l in lines).strip("\n")
    lang = code_lang(el)
    fence = "````" if "```" in body else "```"
    return f"{fence}{lang}\n{body}\n{fence}"


def table_is_complex(tb):
    for cell in tb.find_all(["td", "th"]):
        if int(cell.get("colspan", 1) or 1) > 1 or int(cell.get("rowspan", 1) or 1) > 1:
            return True
    return False


def render_cell_md(cell, rw):
    """单元格 → 单行 markdown（块级用 <br /> 连接，列表降级为 • 行）。"""
    parts = []
    for child in cell.children:
        if isinstance(child, NavigableString):
            t = esc(str(child), in_table=True).strip()
            if t:
                parts.append(t)
        elif isinstance(child, Tag):
            if child.name in ("ul", "ol"):
                items = []
                n = 0
                for li in child.find_all("li", recursive=False):
                    n += 1
                    mark = f"{n}." if child.name == "ol" else "•"
                    items.append(f"{mark} {render_inline(li, rw, in_table=True).strip()}")
                parts.append("<br />".join(items))
            elif child.name == "p":
                t = render_inline(child, rw, in_table=True).strip()
                if t:
                    parts.append(t)
            elif child.name == "img":
                src = fix_url(child.get("src", ""))
                if src:
                    parts.append(f"![]({src})")
            else:
                t = render_inline(child, rw, in_table=True).strip()
                if t:
                    parts.append(t)
    return "<br />".join(parts).replace("\n", " ")


def render_table_md(tb, rw):
    rows = tb.find_all("tr")
    if not rows:
        return ""
    grid = []
    for tr in rows:
        grid.append([render_cell_md(td, rw) for td in tr.find_all(["td", "th"], recursive=False)])
    width = max(len(r) for r in grid)
    for r in grid:
        r.extend([""] * (width - len(r)))
    lines = ["| " + " | ".join(grid[0]) + " |", "|" + "---|" * width]
    for r in grid[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def render_cell_html(cell, rw):
    """复杂表格单元格 → 干净 HTML 内容。"""
    parts = []
    for child in cell.children:
        if isinstance(child, NavigableString):
            t = esc(str(child)).strip()
            if t:
                parts.append(t)
            continue
        if not isinstance(child, Tag):
            continue
        if child.name == "p":
            t = render_inline(child, rw).strip().replace("\n", " ")
            if t:
                parts.append(t)
        elif child.name in ("ul", "ol"):
            items = "".join(
                f"<li>{render_inline(li, rw).strip()}</li>" for li in child.find_all("li", recursive=False)
            )
            parts.append(f"<{child.name}>{items}</{child.name}>")
        elif child.name == "img":
            src = fix_url(child.get("src", ""))
            if src:
                parts.append(f"![]({src})")
        else:
            t = render_inline(child, rw).strip()
            if t:
                parts.append(t)
    return "<br />".join(parts)


def render_table_html(tb, rw):
    out = ["<table>"]
    for tr in tb.find_all("tr"):
        cells = []
        for td in tr.find_all(["td", "th"], recursive=False):
            attrs = ""
            if int(td.get("colspan", 1) or 1) > 1:
                attrs += f' colSpan={{{td["colspan"]}}}'
            if int(td.get("rowspan", 1) or 1) > 1:
                attrs += f' rowSpan={{{td["rowspan"]}}}'
            cells.append(f"    <{td.name}{attrs}>{render_cell_html(td, rw)}</{td.name}>")
        out.append("  <tr>")
        out.extend(cells)
        out.append("  </tr>")
    out.append("</table>")
    return "\n".join(out)


IMG_ONLY_RE = re.compile(r"^(!\[[^\]]*\]\([^)]+\)\s*)+$")


def frame_if_image(text):
    """纯图片段落包 Frame，提升截图展示效果。"""
    if IMG_ONLY_RE.match(text.strip()):
        imgs = re.findall(r"!\[[^\]]*\]\([^)]+\)", text)
        return "\n\n".join(f"<Frame>\n  {img}\n</Frame>" for img in imgs)
    return text


def ol_is_steps(el):
    """顶层有序列表含截图且 ≥2 项 → 转 Steps 组件。"""
    items = el.find_all("li", recursive=False)
    if len(items) < 2 or len(items) > 20:
        return False
    return any(li.find("img") for li in items)


def render_steps(el, rw, slug, depth):
    parts = ["<Steps>"]
    for n, li in enumerate(el.find_all("li", recursive=False), 1):
        # 首段纯文本可作 Step 标题（无链接/图片且不超长）
        title = f"步骤 {n}"
        first_p = None
        for child in li.children:
            if isinstance(child, Tag) and child.name == "p":
                first_p = child
                break
            if isinstance(child, NavigableString) and str(child).strip():
                break
        if first_p is not None and not first_p.find("a") and not first_p.find("img"):
            plain = re.sub(r"\s+", " ", first_p.get_text().replace(ZWSP, "")).strip()
            if 2 <= len(plain) <= 60:
                title = step_title(plain)
                first_p.decompose()
        body_blocks = render_blocks(li, rw, slug, depth + 1)
        body = "\n\n".join(b for b in body_blocks if b.strip()).strip()
        parts.append(f'  <Step title="{attr_escape(title)}">')
        if body:
            # body 缩进四格，保持组件块可读
            parts.append("\n".join("    " + l if l.strip() else l for l in body.split("\n")))
        parts.append("  </Step>")
    parts.append("</Steps>")
    return "\n".join(parts)


HEADING_RE = re.compile(r"^(#{2,4})\s+(.+)$")

# 单项有序列表块（语雀把每个步骤拆成独立 ol，中间夹截图）
STEP_ITEM_RE = re.compile(r"^\d+\.\s+(.+)$")
STEP_ATTACH_PREFIXES = ("<Frame>", "<video", "<Note>", "<Warning>", "<Tip>", "<Check>")


def _is_step_item(block):
    return "\n" not in block and STEP_ITEM_RE.match(block) is not None


def _build_steps(items):
    parts = ["<Steps>"]
    for n, (text, atts) in enumerate(items, 1):
        plain = strip_md(text)
        if len(plain) <= 60 and "](" not in text and "![" not in text:
            title, body_parts = step_title(plain), list(atts)
        else:
            title, body_parts = f"步骤 {n}", [text] + list(atts)
        parts.append(f'  <Step title="{attr_escape(title)}">')
        body = "\n\n".join(body_parts).strip()
        if body:
            parts.append("\n".join("    " + l if l.strip() else l for l in body.split("\n")))
        parts.append("  </Step>")
    parts.append("</Steps>")
    return "\n".join(parts)


def steps_postprocess(blocks):
    """合并「单项 ol + 截图」序列：含图转 Steps，无图重新编号为连续列表。"""
    out = []
    i = 0
    while i < len(blocks):
        if _is_step_item(blocks[i]):
            j = i
            items = []
            while j < len(blocks) and _is_step_item(blocks[j]):
                text = STEP_ITEM_RE.match(blocks[j]).group(1)
                j += 1
                atts = []
                while j < len(blocks) and blocks[j].startswith(STEP_ATTACH_PREFIXES):
                    atts.append(blocks[j])
                    j += 1
                items.append((text, atts))
            n_att = sum(len(a) for _, a in items)
            if len(items) >= 2 and n_att >= 1:
                out.append(_build_steps(items))
                i = j
                continue
            if len(items) >= 2:
                # 无图的断号序列：合并重新编号
                out.append("\n".join(f"{n}. {t}" for n, (t, _) in enumerate(items, 1)))
                i = j
                continue
        out.append(blocks[i])
        i += 1
    return out


def accordionize(blocks):
    """FAQ 页：同级「问号结尾」标题 ≥2 个时，整节转 AccordionGroup。"""
    heads = []
    for i, b in enumerate(blocks):
        if "\n" in b:
            continue
        m = HEADING_RE.match(b)
        if m:
            heads.append((i, len(m.group(1)), strip_md(m.group(2))))
    questions = [h for h in heads if re.search(r"[？?]\s*$", h[2])]
    if len(questions) < 2:
        return blocks
    level = min(h[1] for h in questions)
    questions = [h for h in questions if h[1] == level]
    if len(questions) < 2:
        return blocks
    qidx = {h[0] for h in questions}
    # 问题节内若包含更深层标题则整页放弃转换（保守策略）
    for qi, _, _ in questions:
        j = qi + 1
        while j < len(blocks) and not (HEADING_RE.match(blocks[j]) and "\n" not in blocks[j] and len(HEADING_RE.match(blocks[j]).group(1)) <= level):
            if HEADING_RE.match(blocks[j]) and "\n" not in blocks[j]:
                return blocks
            j += 1
    out = []
    i = 0
    acc_buf = []

    def flush():
        if acc_buf:
            out.append("<AccordionGroup>\n" + "\n".join(acc_buf) + "\n</AccordionGroup>")
            acc_buf.clear()

    while i < len(blocks):
        if i in qidx:
            m = HEADING_RE.match(blocks[i])
            title = strip_md(m.group(2))
            j = i + 1
            body = []
            while j < len(blocks):
                hm = HEADING_RE.match(blocks[j]) if "\n" not in blocks[j] else None
                if hm and len(hm.group(1)) <= level:
                    break
                body.append(blocks[j])
                j += 1
            body_text = "\n\n".join(body).strip()
            indented = "\n".join("  " + l if l.strip() else l for l in body_text.split("\n"))
            acc_buf.append(f'<Accordion title="{attr_escape(title)}">\n{indented}\n</Accordion>')
            i = j
        else:
            flush()
            out.append(blocks[i])
            i += 1
    flush()
    return out


def render_video(el, slug):
    src = el.get("src") or ""
    source = el.find("source")
    if not src and source is not None:
        src = source.get("src", "")
    src = fix_url(src)
    poster = fix_url(el.get("poster", ""))
    if not src:
        warn(slug, "video-no-src", str(el)[:100])
        return ""
    poster_attr = f' poster="{poster}"' if poster else ""
    return f'<video controls preload="metadata"{poster_attr} src="{src}"></video>'


def render_bookmark(el, rw, slug):
    a = el.find("a")
    if not a:
        return ""
    label = a.get_text().replace(ZWSP, "").strip() or a.get("href", "")
    href, unlink = rw.rewrite(a.get("href"))
    if unlink or not href:
        return esc(label)
    return f'<Card title="{attr_escape(label)}" icon="bookmark" href="{href}" horizontal />'


def render_blocks(container, rw, slug, depth=0):
    """遍历块级子元素，返回 MDX 块列表。"""
    blocks = []
    for el in container.children:
        if isinstance(el, NavigableString):
            t = esc(str(el)).strip()
            if t:
                blocks.append(t)
            continue
        if not isinstance(el, Tag):
            continue
        name = el.name
        cls = el.get("class") or []

        if name in ("meta", "style", "script", "button", "svg"):
            continue
        if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            for hl in el.select("a.hash-link"):
                hl.decompose()
            text = render_inline(el, rw).strip()
            if text:
                blocks.append("#" * int(name[1]) + " " + text)
        elif "ne-alert" in cls:
            comp = ALERT_MAP.get(el.get("data-type", "info"), "Note")
            inner = render_blocks(el, rw, slug, depth + 1)
            if inner:
                inner[0] = ALERT_PREFIX_RE.sub("", inner[0])
            body = "\n\n".join(b for b in inner if b.strip()).strip()
            if body:
                blocks.append(f"<{comp}>\n{body}\n</{comp}>")
        elif "ne-codeblock" in cls or name == "pre":
            blocks.append(render_codeblock(el, rw))
        elif "ne-video" in cls or name == "video":
            v = el if name == "video" else el.find("video")
            if v is not None:
                blocks.append(render_video(v, slug))
        elif name == "table" or "ne-table" in cls:
            tb = el if name == "table" else el.find("table")
            if tb is None:
                continue
            if table_is_complex(tb):
                blocks.append(render_table_html(tb, rw))
            else:
                blocks.append(render_table_md(tb, rw))
        elif name in ("ul", "ol"):
            if name == "ol" and depth == 0 and ol_is_steps(el):
                blocks.append(render_steps(el, rw, slug, depth))
            else:
                extras = []
                blocks.append(render_list(el, rw, slug=slug, extras=extras))
                blocks.extend(extras)
        elif name == "blockquote" or "ne-quote" in cls:
            inner = render_blocks(el, rw, slug, depth + 1)
            body = "\n\n".join(inner)
            blocks.append("\n".join("> " + l for l in body.split("\n")))
        elif name == "hr" or "ne-hr" in cls:
            blocks.append("---")
        elif "ne-card-bookmark" in " ".join(cls) or "ne-localdoc" in cls or "ne-thirdparty" in cls or "ne-card-file" in " ".join(cls):
            link = render_bookmark(el, rw, slug)
            if link:
                blocks.append(link)
            warn(slug, "card-degraded", " ".join(cls))
        elif name == "p":
            text = render_inline(el, rw).strip()
            if text:
                blocks.append(frame_if_image(text))
        elif name == "img":
            src = fix_url(el.get("src", ""))
            if src:
                blocks.append(f"<Frame>\n  ![]({src})\n</Frame>")
        elif name == "details":
            warn(slug, "details-kept-html", "")
            summary = el.find("summary")
            title = summary.get_text().strip() if summary else "详情"
            if summary:
                summary.decompose()
            inner = "\n\n".join(render_blocks(el, rw, slug, depth + 1))
            blocks.append(f'<Accordion title="{title}">\n{inner}\n</Accordion>')
        elif name in ("div", "section", "figure", "article"):
            blocks.extend(render_blocks(el, rw, slug, depth + 1))
        elif name == "span" and (
            el.find(["table", "pre", "video", "ul", "ol", "blockquote"]) is not None
            or el.find(class_=["ne-alert", "ne-codeblock", "ne-video", "ne-table"]) is not None
        ):
            # ne-indent 等 span 容器内可能包裹表格/代码块等块级内容，按块级递归
            blocks.extend(render_blocks(el, rw, slug, depth + 1))
        elif name in ("span", "a", "strong", "em", "code"):
            text = render_inline(el, rw).strip()
            if text:
                blocks.append(frame_if_image(text))
        else:
            warn(slug, "unknown-block", f"{name}.{'.'.join(cls)}")
            text = render_inline(el, rw).strip()
            if text:
                blocks.append(text)
    return blocks


def drop_excluded_sections(blocks, slug):
    """删除配置的页内章节（命中标题起，至下一个同级/更高级标题止）。"""
    titles = SECTION_EXCLUDE.get(slug.split("/")[-1])
    if not titles:
        return blocks
    out = []
    i = 0
    while i < len(blocks):
        m = HEADING_RE.match(blocks[i]) if "\n" not in blocks[i] else None
        if m and strip_md(m.group(2)) in titles:
            level = len(m.group(1))
            warn(slug, "section-excluded", strip_md(m.group(2)))
            i += 1
            while i < len(blocks):
                hm = HEADING_RE.match(blocks[i]) if "\n" not in blocks[i] else None
                if hm and len(hm.group(1)) <= level:
                    break
                i += 1
            continue
        out.append(blocks[i])
        i += 1
    return out


def drop_excluded_blocks(blocks, slug):
    """删除命中关键词的单个块（如国内专属的旧版手册提示）。"""
    keywords = BLOCK_EXCLUDE.get(slug.split("/")[-1])
    if not keywords:
        return blocks
    out = []
    for b in blocks:
        if any(k in b for k in keywords):
            warn(slug, "block-excluded", b[:80])
            continue
        out.append(b)
    return out


# 去链后残留的纯引导 CTA：行内变体（前接逗号，可能被加粗包裹、句号可能在闭合 ** 内）直接收句
# 变体：「**，点击体验效果**。」整段加粗（逗号在开星内侧），需连开星一起吃掉
CTA_INLINE_BOLD_RE = re.compile(
    r"\*\*[，,][ \t]*点击(?:体验效果|立即体验)[ \t]*[。.]?[ \t]*\*\*[ \t]*[。.]?"
)
CTA_INLINE_RE = re.compile(
    r"[，,][ \t]*(?:\*\*)?点击(?:体验效果|立即体验)[ \t]*[。.]?[ \t]*(?:\*\*)?[ \t]*[。.]?"
)
# 括号包裹的引导尾注（如「公式编辑 （ **点此查看** ）」）整个删除
CTA_PAREN_RE = re.compile(r"\s*（\s*\*\*点此查看\*\*\s*）")
# 整行删除：国内存量组织提示 / 无渠道的反馈・认证・咨询 CTA / 孤立体验引导
CTA_DROP_LINE_RES = [
    re.compile(r"^[ \t]*未升级到新版信息架构的组织，请\s*\*{0,2}点此查看\*{0,2}\s*使用手册\s*$"),
    re.compile(r"^[ \t]*\*\*如有建议，您可点此反馈>+\*\*\s*$"),
    re.compile(r"^[ \t]*\*\*>{2,}(?:立即认证|培训咨询)\\?<.*$"),
    re.compile(r"^[ \t]*(?:\*\*)?点击(?:体验效果|立即体验)(?:\*\*)?\s*[。.]?\s*$"),
]
# 调研问卷邀请块：问卷链接已失效，整个 Warning 块删除（tempered 扫描不跨块）
SURVEY_BLOCK_RE = re.compile(
    r"[ \t]*<Warning>(?:(?!</?Warning>)[\s\S])*?调研问卷(?:(?!</?Warning>)[\s\S])*?</Warning>\n*"
)
# CTA 清理后的破碎体验引导块：单行「**xxx。</Warning>」未配对形态，整块删除
BROKEN_CTA_WARNING_RE = re.compile(r"[ \t]*<Warning>\n\*\*[^*\n]{1,40}。\n?</Warning>\n*")
# 内容被清空后只剩标签的空 callout 壳（Warning/Note/Tip/Info/Check）整块删除
EMPTY_CALLOUT_RE = re.compile(
    r"[ \t]*<(Warning|Note|Tip|Info|Check)>\s*</\1>[ \t]*\n?", re.M
)


# 加粗内容以标点/空白开头或结尾时，CommonMark 可能无法闭合（页面裸显 **）；
# 逐行按 ** 配对后将首尾标点/空白移出加粗范围：**路径：**文本 → **路径**：文本。
# 用配对而非正则匹配，避免把闭合星号误判为开星（如「保存」**，此时…）。
_PUNCT = "：:；;，,、。．.！!？?"
_LEAD_RE = re.compile(rf"^([{_PUNCT}\s]+)(.*)$", re.S)
_TAIL_RE = re.compile(rf"^(.*?)([{_PUNCT}\s]+)$", re.S)
_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]")


def _norm_bold_line(line):
    parts = line.split("**")
    # 无加粗或未配对（奇数个 **）不动，避免误修
    if len(parts) < 3 or len(parts) % 2 == 0:
        return line
    outer = [parts[0]]
    inners = []
    for i in range(1, len(parts), 2):
        inner, after = parts[i], parts[i + 1]
        prev = outer[-1]
        # 内容全为标点且闭星后紧跟文字（如「以**?**标识」）：无法合法闭合，改用 code span
        if inner.strip() and not _WORD_RE.search(inner) and after[:1] and _WORD_RE.match(after[0]):
            outer[-1] = prev + "`" + inner.strip() + "`" + after
            continue
        # 前导标点/空白移出（仅当开星前紧贴文字才会不合法，但统一外移更稳且渲染一致）
        m = _LEAD_RE.match(inner)
        if m and m.group(2).strip():
            prev += m.group(1)
            inner = m.group(2)
        # 结尾标点/空白：闭星后紧跟文字时不闭合，移出
        m = _TAIL_RE.match(inner)
        if m and m.group(1).strip() and after[:1] and _WORD_RE.match(after[0]):
            inner = m.group(1)
            after = m.group(2) + after
        outer[-1] = prev
        if inner.strip():
            inners.append(inner)
            outer.append(after)
        else:
            # 空加粗对直接丢弃
            outer[-1] += inner + after
    res = outer[0]
    for k, inner in enumerate(inners):
        res += "**" + inner + "**" + outer[k + 1]
    return res


def fix_bold_punct(body):
    parts = re.split(r"(```[\s\S]*?```)", body)
    return "".join(
        p if i % 2 else "\n".join(_norm_bold_line(l) for l in p.split("\n"))
        for i, p in enumerate(parts)
    )


def polish_unlinked_text(body, slug):
    """死链去链后的文案修复：删失效 CTA、收拢句式，再套用 per-slug 精修。"""
    body = SURVEY_BLOCK_RE.sub("", body)
    body = CTA_INLINE_BOLD_RE.sub("。", body)
    body = CTA_INLINE_RE.sub("。", body)
    body = BROKEN_CTA_WARNING_RE.sub("", body)
    body = CTA_PAREN_RE.sub("", body)
    lines = body.split("\n")
    lines = [l for l in lines if not any(r.match(l) for r in CTA_DROP_LINE_RES)]
    body = "\n".join(lines)
    for old, new in UNLINK_TEXT_FIXUPS.get(slug.split("/")[-1], []):
        if old in body:
            body = body.replace(old, new)
        else:
            warn(slug, "fixup-miss", old[:80])
    # CTA/行删后残留的空 callout 壳（只剩标签无内容）整块删除，避免渲染空提示框
    body = EMPTY_CALLOUT_RE.sub("", body)
    # 删行/删块后收敛多余空行
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body


def oa_domain_fix(body):
    """纯文本 oa.dingtalk.com → oa.dingtalk.io，并按国际站规范转为可点击链接（跳过代码块）。"""
    parts = re.split(r"(```[\s\S]*?```)", body)

    def f(seg):
        seg = seg.replace("oa.dingtalk.com", "oa.dingtalk.io")
        seg = re.sub(
            r"(?<!\]\()(?<!\[)https?://oa\.dingtalk\.io/?(?![\w/])",
            "[钉钉管理后台](https://oa.dingtalk.io)",
            seg,
        )
        seg = re.sub(
            r"(?<![/.\w\[])oa\.dingtalk\.io(?![\w/)])",
            "[钉钉管理后台](https://oa.dingtalk.io)",
            seg,
        )
        return seg

    return "".join(p if i % 2 else f(p) for i, p in enumerate(parts))


# ---------- 单页转换 ----------

def yaml_quote(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def convert(entry):
    slug = entry["slug"]
    last = slug.split("/")[-1]
    src = STAGING / f"{last}.html"
    soup = BeautifulSoup(src.read_text(), "lxml")
    md = soup.select_one(".theme-doc-markdown")
    h1 = md.find("h1") if md else None
    title = (h1.get_text().replace(ZWSP, "").strip() if h1 else "") or entry["label"]
    title = TITLE_OVERRIDES.get(last, title)

    desc_meta = md.select_one('meta[name="description"]') if md else None
    description = desc_meta.get("content", "").strip() if desc_meta else ""

    lake = soup.select_one("#yuque-content .lake-content")
    body = ""
    if lake is None:
        warn(slug, "empty-page", "no lake-content")
    else:
        headings = {}
        for h in lake.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            hid = h.get("id")
            if hid:
                headings[hid] = h.get_text().replace(ZWSP, "").strip()
        rw = LinkRewriter(slug, headings)
        blocks = render_blocks(lake, rw, slug)
        blocks = steps_postprocess([b for b in blocks if b.strip()])
        blocks = drop_excluded_sections(blocks, slug)
        blocks = drop_excluded_blocks(blocks, slug)
        blocks = accordionize(blocks)
        body = "\n\n".join(b for b in blocks if b.strip())
        # 相邻 strong 合并产生的空粗体标记
        body = body.replace("****", "")
        # 裸域名紧贴 [ 会被 autolink 误判为死链，插入空格
        body = re.sub(r"(\w\.(?:com|cn|io|net|org))\[", r"\1 [", body)
        body = oa_domain_fix(body)
        body = fix_bold_punct(body)
        body = polish_unlinked_text(body, slug)

    for old, new in DESC_FIXUPS.get(slug.split("/")[-1], []):
        description = description.replace(old, new).strip()

    fm = ["---", f"title: {yaml_quote(title)}"]
    if description:
        fm.append(f"description: {yaml_quote(description)}")
    fm.append("---")

    out = REPO / (entry["file"] + ".mdx")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(fm) + "\n\n" + body + "\n")
    return len(body)


def main():
    only = set(sys.argv[1:])
    done = 0
    empty = []
    for e in TOC:
        last = e["slug"].split("/")[-1]
        if only and last not in only and e["slug"] not in only:
            continue
        try:
            size = convert(e)
            if size < 50:
                empty.append(e["slug"])
            done += 1
        except Exception as ex:  # noqa: BLE001
            warn(e["slug"], "convert-error", repr(ex))
            print("ERROR", e["slug"], repr(ex))
    from collections import Counter

    kinds = Counter(w["kind"] for w in warnings)
    report = {"converted": done, "near_empty": empty, "warning_kinds": dict(kinds), "warnings": warnings}
    (BASE / "output" / "convert-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"converted: {done}, near-empty: {len(empty)}")
    print("warnings:", dict(kinds))


if __name__ == "__main__":
    main()
