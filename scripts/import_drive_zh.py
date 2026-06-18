#!/usr/bin/env python3
"""import_drive_zh.py — 把 ~/Downloads/<date>_DingTalk_Drive_zh/*.adoc.md → zh/drive/<slug>.mdx。

仿 import_calendar_zh.py，差异：
- 输出到 zh/drive/（与现有 en drive/ 共享 slug 命名做三语 URL 镜像）
- tab 名「钉盘」，4 group 对齐 en drive/ 4-group 划分的中文翻译
- 23 个 slug 与 en drive/ 23 篇一一对应（中文 hub 24 leaf 中「管理员操作手册」概览不入仓 —— 与 en 同步，
  admin overview 仅 4 个跳转链接信息量为 0）
- TRAILING_BACK_TO_RE 适配 drive 特化形态：
  · 「[钉盘](url)」无 ** 加粗（calendar 是 `[**X**](url)`）
  · 「」后直接结尾，无「目录」后缀（calendar 是「...目录页」结尾）
  · alidocs.dingtalk.com 域名（与 calendar/mail 的 notes.dingtalk.com 不同）

用法:
    python3 scripts/import_drive_zh.py                    # 默认源 ~/Downloads/2026-06-18_DingTalk_Drive_zh
    python3 scripts/import_drive_zh.py --source <path>    # 自定义源
    python3 scripts/import_drive_zh.py --dry-run          # 只打印总结

产物:
  - zh/drive/<slug>.mdx × 23
  - scripts/output/drive_zh/{nav-fragment.json, slug-map.json, report.md}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
from import_archive import escape_mdx, parse_frontmatter_data, yaml_escape  # noqa: E402

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-18_DingTalk_Drive_zh'
DRIVE_DIR = REPO_ROOT / 'zh' / 'drive'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'drive_zh'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
LEADING_H1_RE = re.compile(r'\A# (.+?)\n')
ADMONITION_MARKER_RE = re.compile(r'^:::\s*$', re.MULTILINE)
# drive 中文每篇 H1 后紧跟一行「面包屑」段：`[钉盘](url) \> [<parent>](url)\> 当前页面`
# en drive 源 body 是 `\A---\n` 直接 hr 开头，无此面包屑（en 用 LEADING_HR_RE 单步剥）
LEADING_BREADCRUMB_RE = re.compile(r'\A\[钉盘\]\([^)]+\)[^\n]*?当前页面\s*\n+')
# H1（或面包屑）剥掉后正文前的孤立 hr `---`（来自钉钉源「H1 + hr + 正文」结构）
LEADING_HR_RE = re.compile(r'\A---\s*\n+')
# body 末尾钉钉文档自动加的「返回「[钉盘](alidocs-url)」」段（drive 特化）
# 与 calendar/mail 版的差异：
#   1. 域名 alidocs.dingtalk.com（非 notes.dingtalk.com）
#   2. 链接文本 `[钉盘]` 无 ** 加粗（calendar 是 `[**X**]`）
#   3. 末尾直接 `」\Z`，无「目录」/「目录页」后缀
#   4. 「」内有可选 ▍ widget + BOM/零宽
TRAILING_BACK_TO_RE = re.compile(
    r'\n+---\s*\n+(?:[▍▌▲◆])?[\xa0﻿​‌‍⁠]*'
    r'返回[「『]?\s*\[(?:\*\*)?[^\]]+(?:\*\*)?\]\([^)]+\)\s*[」』]?'
    # 「」后允许残留 emphasis(* _) / 中文标点(、，。) / 空白 / 不可见字符（drive 个别篇尾段
    # 有 `**、**` 等碎片 noise，需放宽到 \Z 才能整段剥净；calendar 版纯 `\s*\Z` 即可）
    r'[\s*_`~、，。\xa0﻿​‌‍⁠]*\Z'
)
# 钉钉文档外链 → 仓库内链映射（按 dentry UUID 匹配）
# Drive 23 篇相互无内链引用（trailing 「[钉盘]」段已被 TRAILING_BACK_TO_RE 剥掉），map 留空
ALIDOCS_INTERNAL_LINK_MAP: dict[str, str] = {}
ALIDOCS_LINK_RE = re.compile(
    r'\(https://alidocs\.dingtalk\.com/i/(?:nodes|p/[^/]+/docs)/([A-Za-z0-9_]+)(?:\?[^)]*)?\)'
)
# 钉钉 .com 域名 → .io 国际版品牌对齐（保险管道，仿 calendar/mail_zh）
BARE_DINGTALK_LINK_RE = re.compile(
    r'\((?P<sub>[A-Za-z0-9-]+)\.dingtalk\.com(?P<path>[^)]*)\)'
)
DINGTALK_COM_RE = re.compile(r'\bdingtalk\.com\b')

MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')
MD_LIST_PREFIX_RE = re.compile(r'^\s*(?:\d+[.)]|[-*+])\s+')

# overview slug title 强制覆盖（避免与所在 group 同名等场景）
# - employee-user-guide：与 en `Employee User Guide Overview` 对齐，加「概览」后缀
# - faq：原 H1「常见问题」与 group 名「常见问题」冲突，加「概览」后缀消歧
TITLE_OVERRIDES: dict[str, str] = {
    'employee-user-guide': '员工使用指南概览',
    'faq': '常见问题概览',
}

# frontmatter description 手写覆盖：让 mintlify 副标题是「全页 AI 总结」而非 body 首段重复
# 每条 ≤ 200 chars / ≤ 140 CJK，与 en drive/ 同篇 description 语义镜像；
# 术语遵循 scripts/glossary/zh-en.json（钉盘 / 文件 / 文件夹 / 共享 / 权限 / 容量 / 企业存储）
DESCRIPTION_OVERRIDES: dict[str, str] = {
    'what-is-dingtalk-drive': "钉盘是基于阿里云的企业网盘，融合文件存储、管理与协作——一键保存、精细权限、随时在线编辑、轻松多人协同。",
    'how-to-access-dingtalk-drive': "电脑端进入钉盘的两种方式——左侧菜单点击「钉盘」图标，或使用备用入口，让你在钉钉任意位置都能快速找到自己的文件。",
    'dingtalk-drive-home-page-features': "钉盘首页可搜索文件、新建或上传内容、查看动态，并浏览「我的文件」「团队文件」「群文件」「与我共享」——文件管理的中枢页。",
    'employee-user-guide': "以员工身份开始使用钉盘——个人盘 2 GB 跨电脑/手机实时同步并加密存储，让个人文件更安全更易访问。",
    'how-to-upload-files-or-folders': "电脑端或手机端把文件和文件夹上传到钉盘，让重要的个人和团队文件集中存储、组织有序、跨设备易管理。",
    'how-to-save-chat-files-to-dingtalk-drive': "电脑端/手机端把群聊文件转存钉盘——企业盘首赠 100 GB，「我的文件」「团队文件」「群文件」三类一站式管理。",
    'how-to-create-files-or-folders': "电脑端或手机端直接在钉盘新建文件和文件夹，每端多入口可选，方便个人和团队自主组织文件结构。",
    'how-to-set-or-change-member-permissions': "电脑端或手机端按文件按人精确分配/调整钉盘权限，附边界场景说明——既保护数据资产，又让对的人留在协作中。",
    'how-to-edit-files-in-dingtalk-drive': "在钉盘文件列表点击文件旁的「在线编辑」图标，或直接打开文件即可开始协同编辑——无需下载、无需额外工具。",
    'how-to-share-files-with-external-people': "从钉盘安全地把文件分享给外部协作者——电脑端精细配置权限或手机端发送安全链接，每种方式都有推荐步骤。",
    'how-to-cancel-or-leave-a-shared-folder': "作为文件夹创建者，可在电脑端或手机端取消共享让文件夹回到私有状态；作为成员，可主动离开不再需要的共享文件夹。",
    'how-to-quickly-search-for-files-or-folders': "用钉盘电脑端/手机端的快速搜索在大容量盘里秒级定位文件或文件夹——告别深层目录手翻，提升工作效率。",
    'how-to-quickly-find-files-or-folders-in-chats': "告别群聊历史无尽下拉——用钉盘电脑端/手机端按发送人、文件类型、会话来源快速定位群聊里分享的文件。",
    'how-to-batch-download-move-or-delete-files': "电脑端选中多个钉盘文件或文件夹，一次性批量下载/移动/复制/删除——减少重复操作，让文件整理与知识沉淀更高效。",
    'how-to-delete-and-recover-files': "在电脑端或手机端删除不需要的钉盘文件或文件夹——已删除项进入回收站可恢复，让文件管理既便捷又有兜底。",
    'how-to-use-file-picker': "在聊天框使用「钉盘文件选择器」——点击输入框下方的发文件图标，选择「发送钉盘文件」，直接从盘内挑选已有文件高效发送。",
    'how-to-quickly-find-target-folder': "从钉盘或群文件列表批量下载多文件时，会自动生成以下载日期 + 首个文件名命名的本地文件夹，目标位置一目了然。",
    'how-to-view-enterprise-storage-space': "查看企业盘 100 GB 免费容量使用情况——容量不足时可扩容或定期清理旧文件，无需付费即可解决容量问题。",
    'how-to-manage-enterprise-storage-capacity': "管理员分步指南——从钉盘进入「企业存储容量」页，配置管理细则、删除冗余文件回收空间，并查看页内额外提示。",
    'how-to-configure-capacity-management-by-role': "打开企业管理后台，通过工作台或搜索找到钉盘，按角色配置容量配额——让不同岗位员工分别获得合适的存储分配。",
    'how-to-allocate-dedicated-capacity-to-an-app': "管理员指南——打开管理后台，进入「存储管理」，在目标应用旁点击「分配」，为该应用划拨钉盘专属容量隔离其数据。",
    'faq': "钉盘单聊文件常见问题——文件何时过期、如何提前判断是否将被清理并备份、过期之后是否还能恢复。",
    'dingtalk-drive-qa': "钉盘常见问答：免费容量上限与企业盘位置、群聊文件转存与容量管理扩容、共享文件夹多人协作、数据安全实践。",
}

# 23 篇 → 4 group（对齐 en drive/ 的 4-group 划分，按 docs.json en Drive tab 顺序排列）
# 三元组: (slug, source_basename, expected_title)
# - slug 全部复用 en drive/ 的 kebab-case 命名做三语 URL 镜像
# - source_basename 是 ~/Downloads/2026-06-18_DingTalk_Drive_zh/ 下的实际文件名
#   （含嵌套子目录：员工操作手册.adoc/<file>、管理员操作手册.adoc/<file>、常见问题.adoc/<file>）
#   注意：钉钉源文件名把标题中的 `/` 替换成 `_`，但 H1 字面值仍是 `/`
# - expected_title 用钉钉源 H1 字面值（含中文标点 / 全角问号）
# - admin overview 中文有 `管理员操作手册.adoc.md` 但不入仓（与 en 同步，信息量为 0）
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('开始使用', [
        ('what-is-dingtalk-drive',
         '什么是钉盘？.adoc.md',
         '什么是钉盘？'),
        ('how-to-access-dingtalk-drive',
         '如何进入钉盘？.adoc.md',
         '如何进入钉盘？'),
        ('dingtalk-drive-home-page-features',
         '钉盘首页功能有哪些？.adoc.md',
         '钉盘首页功能有哪些？'),
    ]),
    ('员工使用指南', [
        ('employee-user-guide',
         '员工操作手册.adoc.md',
         '员工操作手册'),
        ('how-to-upload-files-or-folders',
         '员工操作手册.adoc/如何上传文件_文件夹？.adoc.md',
         '如何上传文件/文件夹？'),
        ('how-to-save-chat-files-to-dingtalk-drive',
         '员工操作手册.adoc/如何将聊天文件存储到钉盘？.adoc.md',
         '如何将聊天文件存储到钉盘？'),
        ('how-to-create-files-or-folders',
         '员工操作手册.adoc/如何新建文件_文件夹？.adoc.md',
         '如何新建文件/文件夹？'),
        ('how-to-set-or-change-member-permissions',
         '员工操作手册.adoc/如何设置_更改成员权限？.adoc.md',
         '如何设置/更改成员权限？'),
        ('how-to-edit-files-in-dingtalk-drive',
         '员工操作手册.adoc/如何编辑钉盘中文件.adoc.md',
         '如何编辑钉盘中文件'),
        ('how-to-share-files-with-external-people',
         '员工操作手册.adoc/如何将文件分享给外部人员查看？.adoc.md',
         '如何将文件分享给外部人员查看？'),
        ('how-to-cancel-or-leave-a-shared-folder',
         '员工操作手册.adoc/如何取消_退出分享文件夹？.adoc.md',
         '如何取消/退出分享文件夹？'),
        ('how-to-quickly-search-for-files-or-folders',
         '员工操作手册.adoc/如何快速搜索文件_文件夹？.adoc.md',
         '如何快速搜索文件/文件夹？'),
        ('how-to-quickly-find-files-or-folders-in-chats',
         '员工操作手册.adoc/如何快速找到聊天内的文件_文件夹？.adoc.md',
         '如何快速找到聊天内的文件/文件夹？'),
        ('how-to-batch-download-move-or-delete-files',
         '员工操作手册.adoc/如何批量下载、移动、删除钉盘文件.adoc.md',
         '如何批量下载、移动、删除钉盘文件'),
        ('how-to-delete-and-recover-files',
         '员工操作手册.adoc/如何删除文件及找回误删除的文件？.adoc.md',
         '如何删除文件及找回误删除的文件？'),
        ('how-to-use-file-picker',
         '员工操作手册.adoc/如何使用钉盘文件选择器高效发送文件？.adoc.md',
         '如何使用钉盘文件选择器高效发送文件？'),
        ('how-to-quickly-find-target-folder',
         '员工操作手册.adoc/如何快速查找目标文件夹.adoc.md',
         '如何快速查找目标文件夹'),
    ]),
    ('管理员指南', [
        # admin overview 不入仓（与 en 同步，仅 4 个跳转链接，信息量为 0）
        ('how-to-view-enterprise-storage-space',
         '管理员操作手册.adoc/如何查看企业存储空间？.adoc.md',
         '如何查看企业存储空间？'),
        ('how-to-manage-enterprise-storage-capacity',
         '管理员操作手册.adoc/如何管理企业存储容量？.adoc.md',
         '如何管理企业存储容量？'),
        ('how-to-configure-capacity-management-by-role',
         '管理员操作手册.adoc/钉盘如何按角色设置容量管理.adoc.md',
         '钉盘如何按角色设置容量管理'),
        ('how-to-allocate-dedicated-capacity-to-an-app',
         '管理员操作手册.adoc/如何给应用分配专享容量？.adoc.md',
         '如何给应用分配专享容量？'),
    ]),
    ('常见问题', [
        ('faq',
         '常见问题.adoc.md',
         '常见问题'),
        ('dingtalk-drive-qa',
         '常见问题.adoc/钉钉钉盘使用答疑.adoc.md',
         '钉钉钉盘使用答疑'),
    ]),
]


def clean_invisible(text: str) -> str:
    def repl(m: re.Match) -> str:
        return ' ' if m.group(0) == '\xa0' else ''
    return INVISIBLE_CHARS_RE.sub(repl, text)


def strip_dup_leading_h1(body: str, parsed_title: str) -> str:
    m = LEADING_H1_RE.match(body)
    if m and m.group(1).strip() == parsed_title.strip():
        return body[m.end():].lstrip()
    return body


def strip_leading_breadcrumb(body: str) -> str:
    """剥 H1 后紧跟的「[钉盘](url) > ... > 当前页面」面包屑段（drive 中文源特化）。"""
    return LEADING_BREADCRUMB_RE.sub('', body, count=1)


def strip_leading_hr(body: str) -> str:
    """剥正文前的孤立 hr `---`（来自钉钉源「H1 + hr + 正文」结构）。"""
    return LEADING_HR_RE.sub('', body, count=1)


def strip_admonition_markers(body: str) -> str:
    return ADMONITION_MARKER_RE.sub('', body)


def strip_trailing_back_to(body: str) -> str:
    """剥 body 末尾钉钉文档自动加的「返回「[钉盘](url)」」段（含前置 --- 横线 + 可选 ▍ 前缀）。"""
    return TRAILING_BACK_TO_RE.sub('', body)


def fix_dingtalk_com_to_io(body: str) -> str:
    """统一处理 dingtalk.com → dingtalk.io（国际版品牌对齐）。
    1. markdown 裸域名链接 `(oa.dingtalk.com...)` → `(https://oa.dingtalk.io...)`（补协议头 + 改域名）
    2. 其余字面 `dingtalk.com` → `dingtalk.io`
    """
    body = BARE_DINGTALK_LINK_RE.sub(
        lambda m: f'(https://{m.group("sub")}.dingtalk.io{m.group("path")})',
        body,
    )
    body = DINGTALK_COM_RE.sub('dingtalk.io', body)
    return body


def rewrite_alidocs_links(body: str) -> str:
    """钉钉文档外链按 UUID → 仓库内链替换（仅 ALIDOCS_INTERNAL_LINK_MAP 命中的 UUID）。"""
    def repl(m: re.Match) -> str:
        uuid = m.group(1)
        if uuid in ALIDOCS_INTERNAL_LINK_MAP:
            return f'({ALIDOCS_INTERNAL_LINK_MAP[uuid]})'
        return m.group(0)
    return ALIDOCS_LINK_RE.sub(repl, body)


def demote_body_h1(body: str) -> str:
    """正文 H1 → H2（mintlify 把 frontmatter.title 视为唯一 H1）。跳过代码块。"""
    lines = body.split('\n')
    in_code = False
    for i, l in enumerate(lines):
        if l.startswith('```'):
            in_code = not in_code
            continue
        if in_code:
            continue
        if re.match(r'^# .+', l):
            lines[i] = '#' + l
    return '\n'.join(lines)


def extract_clean_description(body: str, fallback: str) -> str:
    text = MD_INLINE_IMAGE_RE.sub(' ', body)
    for raw_line in text.splitlines():
        s = raw_line.strip()
        if not s or s.startswith('#') or s.startswith('!['):
            continue
        if MD_LIST_PREFIX_RE.match(raw_line):
            continue
        if s.startswith('|') or set(s) <= set('-| :'):
            continue
        s = MD_INLINE_LINK_RE.sub(r'\1', s)
        s = MD_EMPHASIS_CHARS_RE.sub('', s)
        s = re.sub(r'\s+', ' ', s).strip()
        if s:
            return s[:160]
    return fallback


def find_source(source_dir: Path, basename: str) -> Path | None:
    candidate = source_dir / basename
    return candidate if candidate.exists() else None


def process_one(source: Path, expected_slug: str, expected_title: str) -> dict:
    raw = source.read_text(encoding='utf-8')
    nbsp_count = raw.count('\xa0')

    cleaned = clean_invisible(raw)
    parsed_title, _orig_desc, body = parse_frontmatter_data(cleaned, source.stem)
    body = strip_dup_leading_h1(body, parsed_title)
    body = strip_leading_breadcrumb(body)
    body = strip_leading_hr(body)
    body = strip_admonition_markers(body)
    body = strip_trailing_back_to(body)
    body = rewrite_alidocs_links(body)
    body = fix_dingtalk_com_to_io(body)
    body = demote_body_h1(body)

    title = TITLE_OVERRIDES.get(expected_slug) or parsed_title or expected_title
    description = DESCRIPTION_OVERRIDES.get(expected_slug) or extract_clean_description(body, fallback=title)

    escaped = escape_mdx(body)
    mdx = (
        f'---\n'
        f'title: {yaml_escape(title)}\n'
        f'description: {yaml_escape(description)}\n'
        f'---\n\n'
        f'{escaped.rstrip()}\n'
    )

    residual_nbsp = mdx.count('\xa0')

    return {
        'slug': expected_slug,
        'expected_title': expected_title,
        'actual_title': title,
        'title_mismatch': title != expected_title and expected_slug not in TITLE_OVERRIDES,
        'description': description,
        'mdx': mdx,
        'source': str(source),
        'nbsp_before': nbsp_count,
        'nbsp_after': residual_nbsp,
        'mdx_size': len(mdx),
    }


def build_nav_fragment() -> dict:
    return {
        'tab': '钉盘',
        'groups': [
            {
                'group': group_name,
                'pages': [f'zh/drive/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Drive (DingTalk Drive) ZH markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-06-18_DingTalk_Drive_zh/)')
    ap.add_argument('--dry-run', action='store_true', help='不写文件，只打印总结')
    args = ap.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        print(f'❌ 源目录不存在: {source_dir}', file=sys.stderr)
        return 1

    print(f'源: {source_dir}')
    print(f'目标: {DRIVE_DIR}')
    print(f'dry-run: {args.dry_run}')
    print('=' * 70)

    if not args.dry_run:
        DRIVE_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    slug_map: dict[str, dict] = {}
    report_rows: list[dict] = []
    total_nbsp = 0
    total_residual_nbsp = 0
    missing: list[tuple[str, str]] = []
    title_mismatches: list[dict] = []
    expected_total = sum(len(items) for _, items in GROUPS)

    for group_name, items in GROUPS:
        print(f'\n[{group_name}]')
        for slug, source_basename, expected_title in items:
            src = find_source(source_dir, source_basename)
            if not src:
                missing.append((slug, expected_title))
                print(f'  {slug:<58} ❌ 未找到源 (期望 {source_basename})')
                continue
            try:
                info = process_one(src, slug, expected_title)
            except Exception as e:
                print(f'  {slug:<58} ❌ {type(e).__name__}: {e}')
                continue

            slug_map[slug] = {
                'group': group_name,
                'title': info['actual_title'],
                'expected_title': expected_title,
                'source': info['source'],
            }
            total_nbsp += info['nbsp_before']
            total_residual_nbsp += info['nbsp_after']
            if info['title_mismatch']:
                title_mismatches.append({
                    'slug': slug,
                    'expected': expected_title,
                    'actual': info['actual_title'],
                })
            report_rows.append({
                'group': group_name, 'slug': slug, 'title': info['actual_title'],
                'desc_len': len(info['description']), 'nbsp_cleaned': info['nbsp_before'],
                'mdx_size': info['mdx_size'],
            })
            marker = '✓' if not info['title_mismatch'] else '⚠️'
            print(f'  {slug:<58} {marker} {info["mdx_size"]} bytes (NBSP={info["nbsp_before"]})')

            if not args.dry_run:
                target = DRIVE_DIR / f'{slug}.mdx'
                target.write_text(info['mdx'], encoding='utf-8')

    print('\n' + '=' * 70)
    print(f'成功:           {len(report_rows)} / {expected_total}')
    print(f'缺失:           {len(missing)}')
    print(f'title 不一致:   {len(title_mismatches)} (用 H1 解析值落地)')
    print(f'NBSP 清洗总数:  {total_nbsp}')
    print(f'mdx 残留 NBSP:  {total_residual_nbsp} (应该 0)')
    if missing:
        print('\n缺失列表:')
        for s, t in missing:
            print(f'  - {s}: {t}')
    if title_mismatches:
        print('\ntitle 不一致（用 H1 解析值落地）：')
        for m in title_mismatches:
            print(f'  - {m["slug"]}: expected={m["expected"]!r} vs actual={m["actual"]!r}')

    if not args.dry_run:
        nav_fragment = build_nav_fragment()
        (OUTPUT_DIR / 'nav-fragment.json').write_text(
            json.dumps(nav_fragment, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
        )
        (OUTPUT_DIR / 'slug-map.json').write_text(
            json.dumps(slug_map, indent=2, ensure_ascii=False) + '\n', encoding='utf-8'
        )
        lines = [
            '# Drive ZH Import Report\n',
            f'- 成功: **{len(report_rows)} / {expected_total}**',
            f'- 缺失: {len(missing)}',
            f'- title 不一致: {len(title_mismatches)}',
            f'- NBSP 清洗: {total_nbsp}（mdx 残留 {total_residual_nbsp}）',
            '',
            '## 全表',
            '| group | slug | title | desc_len | nbsp_cleaned | size |',
            '|---|---|---|---|---|---|',
        ]
        for r in report_rows:
            lines.append(f'| {r["group"]} | `{r["slug"]}` | {r["title"]} | {r["desc_len"]} | {r["nbsp_cleaned"]} | {r["mdx_size"]} |')
        if title_mismatches:
            lines.append('\n## title 不一致（用 H1 解析值落地）')
            for m in title_mismatches:
                lines.append(f'- `{m["slug"]}`: expected `{m["expected"]}` ≠ actual `{m["actual"]}`')
        (OUTPUT_DIR / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')

        print(f'\n产物:')
        print(f'  mdx:               {DRIVE_DIR}/*.mdx ({len(report_rows)} 个)')
        print(f'  nav-fragment.json: {OUTPUT_DIR}/nav-fragment.json')
        print(f'  slug-map.json:     {OUTPUT_DIR}/slug-map.json')
        print(f'  report.md:         {OUTPUT_DIR}/report.md')

    if missing or total_residual_nbsp > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
