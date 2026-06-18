#!/usr/bin/env python3
"""import_contacts_zh.py — 把 ~/Downloads/<date>_DingTalk_Contacts_zh/*.adoc.md → zh/contacts/<slug>.mdx。

仿 import_drive_zh.py，差异：
- 输出到 zh/contacts/（与现有 en contacts/ 共享 slug 命名做三语 URL 镜像）
- tab 名「通讯录」，3 group 对齐 en contacts/ 3-group 划分的中文翻译
- 15 个 slug 与 en contacts/ 15 篇一一对应（中文 hub 15 leaf 全部入仓 + hub overview 节点本身不入仓）
- 源结构比 drive 更干净：H1 后直接进 H2 正文，无 `[钉盘](url) > ... > 当前页面` 面包屑段，
  无 trailing 「返回[xxx]」段；LEADING_BREADCRUMB_RE / TRAILING_BACK_TO_RE 保留兜底（0 命中无害）。
- DINGTALK_COM_RE 加 `(?<!alidocs\.)` 负 lookbehind，避免把 alidocs.dingtalk.com（钉钉文档前台域名，
  无 .io 对应）误转成 alidocs.dingtalk.io 死链。

⚠️ 重跑警告：4 篇有手工 fix 的 `**xxx：**yyy` 加粗冒号紧贴瑕疵（set-member-field-visibility
   / set-department-visibility / batch-add-modify-members×1，文件内多处）；脚本未加固 fix 逻辑，
   重跑前需先 git stash / commit 现状，重跑后重新手工 fix 或 git checkout 拉回。

用法:
    python3 scripts/import_contacts_zh.py                    # 默认源 ~/Downloads/2026-06-18_DingTalk_Contacts_zh
    python3 scripts/import_contacts_zh.py --source <path>    # 自定义源
    python3 scripts/import_contacts_zh.py --dry-run          # 只打印总结

产物:
  - zh/contacts/<slug>.mdx × 15
  - scripts/output/contacts_zh/{nav-fragment.json, slug-map.json, report.md}
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

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-18_DingTalk_Contacts_zh'
CONTACTS_DIR = REPO_ROOT / 'zh' / 'contacts'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'contacts_zh'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
LEADING_H1_RE = re.compile(r'\A# (.+?)\n')
ADMONITION_MARKER_RE = re.compile(r'^:::\s*$', re.MULTILINE)
# 兜底正则：contacts 源 H1 之后直接进 H2，无面包屑段；正则保留 hub 名 [企业通讯录] 做语义匹配，
# 0 命中也无害（参照 drive 模式保留管道完整性）
LEADING_BREADCRUMB_RE = re.compile(r'\A\[企业通讯录\]\([^)]+\)[^\n]*?当前页面\s*\n+')
# H1 / 面包屑剥掉后正文前的孤立 hr `---`（兜底）
LEADING_HR_RE = re.compile(r'\A---\s*\n+')
# 兜底正则：contacts 源末尾无「返回[企业通讯录]」段；正则保留 drive 形态做容错
TRAILING_BACK_TO_RE = re.compile(
    r'\n+---\s*\n+(?:[▍▌▲◆])?[\xa0﻿​‌‍⁠]*'
    r'返回[「『]?\s*\[(?:\*\*)?[^\]]+(?:\*\*)?\]\([^)]+\)\s*[」』]?'
    r'[\s*_`~、，。\xa0﻿​‌‍⁠]*\Z'
)
# 钉钉文档外链 → 仓库内链映射（按 dentry UUID 匹配）
# Contacts 15 篇内链互引在源中已隐含被 trailing 段托管，map 留空
ALIDOCS_INTERNAL_LINK_MAP: dict[str, str] = {}
ALIDOCS_LINK_RE = re.compile(
    r'\(https://alidocs\.dingtalk\.com/i/(?:nodes|p/[^/]+/docs)/([A-Za-z0-9_]+)(?:\?[^)]*)?\)'
)
# 钉钉 .com 域名 → .io 国际版品牌对齐（保险管道，仿 drive_zh）
BARE_DINGTALK_LINK_RE = re.compile(
    r'\((?P<sub>[A-Za-z0-9-]+)\.dingtalk\.com(?P<path>[^)]*)\)'
)
# 排除 alidocs.dingtalk.com —— alidocs 是钉钉文档前台域名，没有 .io 对应，硬转会死链
DINGTALK_COM_RE = re.compile(r'(?<!alidocs\.)\bdingtalk\.com\b')

MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')
MD_LIST_PREFIX_RE = re.compile(r'^\s*(?:\d+[.)]|[-*+])\s+')

# title 强制覆盖：zh 钉钉源 H1 大多是「如何 xxx？」问句式，
# 与 en 命令式陈述句（Set / Enable / Manage / Create / Add）不统一。
# 12 篇改写为陈述句对齐 en；3 篇（quickly-enable-organization / require-friend-verification /
# transfer-enterprise-creator）原 H1 已是陈述句，不覆盖。
TITLE_OVERRIDES: dict[str, str] = {
    'create-departments': '创建部门',
    'add-organization-members': '添加组织成员',
    'batch-add-modify-members': '批量添加成员或修改成员信息',
    'set-enterprise-basic-info': '设置企业基础信息',
    'set-basic-contacts-info': '设置通讯录基础信息',
    'enable-member-invitations': '开启成员邀请',
    'manage-departments': '管理部门与部门群',
    'manage-roles': '管理角色',
    'manage-members': '管理成员',
    'set-department-visibility': '设置部门可见性',
    'set-member-field-visibility': '设置成员信息字段可见性',
    'enable-executive-mode': '开启高管模式',
}

# frontmatter description 手写覆盖：让 mintlify 副标题是「全页 AI 总结」而非 body 首段重复
# 每条 ≤ 200 chars / ≤ 140 CJK，与 en contacts/ 同篇 description 语义镜像；
# 术语遵循 scripts/glossary/zh-en.json（通讯录 / 部门 / 成员 / 角色 / 高管模式 / 主管理员 / 可见范围 等）
DESCRIPTION_OVERRIDES: dict[str, str] = {
    'quickly-enable-organization': "新管理员快速启用钉钉组织的端到端流程——创建企业、搭建部门树、添加成员一气呵成。",
    'create-departments': "在管理后台单建部门或搭建多级组织架构——重命名、调整顺序、嵌套上下级，让组织树映射真实人事架构。",
    'add-organization-members': "电脑端通过单个添加、邀请链接或批量导入把员工加入组织，并分配到对应部门——管理员一站式完成员工接入。",
    'batch-add-modify-members': "通过 Excel 模板批量导入新员工或批量更新已有成员信息——适合新组织上线、校招入职或与 HR 系统同步变更场景。",
    'set-enterprise-basic-info': "在管理后台编辑企业名称、Logo、行业、规模等基础信息——已认证与未认证企业均覆盖。",
    'set-basic-contacts-info': "定制通讯录使用体验：切换组织架构展示样式、选择部门路径显示方式，并配置员工字段对外可见性。",
    'enable-member-invitations': "允许普通员工直接邀请新成员加入——适合企业快速扩张；含管理员开关与员工端邀请流程双视角说明。",
    'manage-departments': "编辑部门元信息（ID、负责人、简介、电话），并管理全员群与部门群的生命周期——创建、解散、转让群主一站式处理。",
    'manage-roles': "配置默认角色（创建人、部门负责人、主管理员），自建角色组并分配成员——基于角色的精细权限管理。",
    'manage-members': "区分工号与职位，逐个编辑员工档案——部门、汇报上级、职位、邮箱、工号、角色，并叠加高管模式与手机号隐藏开关。",
    'set-department-visibility': "隐藏敏感部门或限制其成员的通讯录视野——支持完全隐藏、白名单可见、仅自己 / 仅下级部门可见多种范围。",
    'set-member-field-visibility': "控制成员详情页字段的展示、是否可被本人编辑、是否可被搜索——并支持自建字段与字段顺序调整。",
    'enable-executive-mode': "对普通员工隐藏高管手机号、屏蔽 DING 与商务电话——10 种屏蔽方式叠加按部门白名单配置，保护高管隐私。",
    'require-friend-verification': "为陌生人添加好友请求加一道手动确认——保护个人隐私，屏蔽组织外的好友邀请骚扰。",
    'transfer-enterprise-creator': "通过验证码把企业创建人（超级管理员）身份转移给另一位成员——创建人注销账号或退出企业前必须先转让。",
}

# 15 篇 → 3 group（对齐 en contacts/ 的 3-group 划分,按 docs.json en Contacts tab 顺序排列）
# 三元组: (slug, source_basename, expected_title)
# - slug 全部复用 en contacts/ 的 kebab-case 命名做三语 URL 镜像
# - source_basename 是 ~/Downloads/2026-06-18_DingTalk_Contacts_zh/ 下的实际文件名
# - expected_title 用钉钉源 H1 字面值(含中文标点 / 全角问号)
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('开始使用', [
        ('quickly-enable-organization',
         '快速启用钉钉组织.adoc.md',
         '快速启用钉钉组织'),
        ('create-departments',
         '如何创建部门？.adoc.md',
         '如何创建部门？'),
        ('add-organization-members',
         '如何添加组织成员.adoc.md',
         '如何添加组织成员'),
        ('batch-add-modify-members',
         '如何批量添加成员或修改成员信息.adoc.md',
         '如何批量添加成员或修改成员信息'),
        ('set-enterprise-basic-info',
         '如何设置企业基础信息.adoc.md',
         '如何设置企业基础信息'),
    ]),
    ('成员与部门', [
        ('set-basic-contacts-info',
         '如何设置通讯录基础信息？.adoc.md',
         '如何设置通讯录基础信息？'),
        ('enable-member-invitations',
         '如何开启成员邀请.adoc.md',
         '如何开启成员邀请'),
        ('manage-departments',
         '如何对部门及部门群进行管理.adoc.md',
         '如何对部门及部门群进行管理'),
        ('manage-roles',
         '如何对角色进行管理.adoc.md',
         '如何对角色进行管理'),
        ('manage-members',
         '如何对成员进行管理.adoc.md',
         '如何对成员进行管理'),
    ]),
    ('隐私与账号', [
        ('set-department-visibility',
         '如何设置部门可见性？.adoc.md',
         '如何设置部门可见性？'),
        ('set-member-field-visibility',
         '如何设置成员信息字段可见性.adoc.md',
         '如何设置成员信息字段可见性'),
        ('enable-executive-mode',
         '如何开启高管模式？.adoc.md',
         '如何开启高管模式？'),
        ('require-friend-verification',
         '开启添加我为好友需要验证.adoc.md',
         '开启添加我为好友需要验证'),
        ('transfer-enterprise-creator',
         '企业创建人转移身份.adoc.md',
         '企业创建人转移身份'),
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
    """剥 H1 后紧跟的「[企业通讯录](url) > ... > 当前页面」面包屑段（兜底，contacts 源 0 命中）。"""
    return LEADING_BREADCRUMB_RE.sub('', body, count=1)


def strip_leading_hr(body: str) -> str:
    """剥正文前的孤立 hr `---`（来自钉钉源「H1 + hr + 正文」结构）。"""
    return LEADING_HR_RE.sub('', body, count=1)


def strip_admonition_markers(body: str) -> str:
    return ADMONITION_MARKER_RE.sub('', body)


def strip_trailing_back_to(body: str) -> str:
    """剥 body 末尾钉钉文档自动加的「返回「[xxx](url)」」段（兜底，contacts 源 0 命中）。"""
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
        'tab': '通讯录',
        'groups': [
            {
                'group': group_name,
                'pages': [f'zh/contacts/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Contacts (DingTalk Contacts) ZH markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-06-18_DingTalk_Contacts_zh/)')
    ap.add_argument('--dry-run', action='store_true', help='不写文件，只打印总结')
    args = ap.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        print(f'❌ 源目录不存在: {source_dir}', file=sys.stderr)
        return 1

    print(f'源: {source_dir}')
    print(f'目标: {CONTACTS_DIR}')
    print(f'dry-run: {args.dry_run}')
    print('=' * 70)

    if not args.dry_run:
        CONTACTS_DIR.mkdir(parents=True, exist_ok=True)
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
                target = CONTACTS_DIR / f'{slug}.mdx'
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
            '# Contacts ZH Import Report\n',
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
        print(f'  mdx:               {CONTACTS_DIR}/*.mdx ({len(report_rows)} 个)')
        print(f'  nav-fragment.json: {OUTPUT_DIR}/nav-fragment.json')
        print(f'  slug-map.json:     {OUTPUT_DIR}/slug-map.json')
        print(f'  report.md:         {OUTPUT_DIR}/report.md')

    if missing or total_residual_nbsp > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
