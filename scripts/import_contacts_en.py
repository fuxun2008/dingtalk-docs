#!/usr/bin/env python3
"""import_contacts_en.py — 把 ~/Downloads/<date>_DingTalk_Contacts/*.adoc.md → contacts/<slug>.mdx。

仿 import_drive_en.py（三元组 GROUPS）+ import_mail_en.py（剥编号 H1）。差异：

源每篇头部固定 5 行：
  line 1: `# NN - <Title>`     (编号 H1 噪声，先剥)
  line 2: 空
  line 3: `# <Title>`           (真 H1，留给 parse_frontmatter_data 抽)
  line 4: 空
  line 5: `Enterprise Contacts > <Title>`  (面包屑噪声，剥)

源尾部三种形态：
  a) 6 篇裸 `---` 收尾                   → TRAILING_HR_RE
  b) 9 篇直接以正文/图片收尾，无 hr        → 不需处理
  c) 10 号特殊：`---\\n\\nReturn to [Enterprise Contacts](alidocs)... catalog page.\\n\\n---\\n\\nOriginal title: <中文>\\n\\nSource: https://alidocs...`
     → TRAILING_RETURN_TO_RE + TRAILING_ORIGINAL_TITLE_RE 串联剥

15 篇 → 3 group（按编号 01-15 顺序排列，5+5+5 平均分）：
  Getting Started (01-05) / Members & Departments (06-10) / Privacy & Account (11-15)

用法:
    python3 scripts/import_contacts_en.py              # 默认源 ~/Downloads/2026-06-15_DingTalk_Contacts
    python3 scripts/import_contacts_en.py --source <path>
    python3 scripts/import_contacts_en.py --dry-run

产物：
  - contacts/<slug>.mdx × 15
  - scripts/output/contacts_en/{nav-fragment.json, slug-map.json, report.md}
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

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-15_DingTalk_Contacts'
CONTACTS_DIR = REPO_ROOT / 'contacts'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'contacts_en'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
# 行首 `# 01 - <Title>` 编号 H1（剥完后 line 1 暴露真 H1，由 parse_frontmatter_data 自动抽）
LEADING_NUMBERED_H1_RE = re.compile(r'\A\s*#\s+\d+\s*-\s*[^\n]+\n+')
# 剥真 H1 后 body line 1 是 `Enterprise Contacts > <Title>` 面包屑
LEADING_BREADCRUMB_RE = re.compile(r'\AEnterprise Contacts\s*>\s*[^\n]+\n+')
# 10 号特有「Return to the [Enterprise Contacts](alidocs) catalog page.」段
# 用 `[^\n\[]*` 应对 "Return to" 后任意中间词（the / 空 / 其他冠词）
TRAILING_RETURN_TO_RE = re.compile(
    r'\n+---\s*\n+Return to [^\n\[]*\[[^\]]+\]\(https://alidocs\.dingtalk\.com[^)]+\)[^\n]*\.\s*\n*'
)
# 10 号特有「Original title: <中文>\n\nSource: https://alidocs...」段
TRAILING_ORIGINAL_TITLE_RE = re.compile(
    r'\n+---\s*\n+Original title:[^\n]+\s*\n+Source:\s*https://alidocs\.dingtalk\.com[^\n]+\s*\n*'
)
# body 末尾裸 `---` 分隔线（钉钉文档导出常见尾巴）
TRAILING_HR_RE = re.compile(r'\n+---\s*\Z')

MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')

# `](oa.dingtalk.com...)` / `](https://oa.dingtalk.com...)` / `](http://oa.dingtalk.com...)` 一律改为
# `](https://oa.dingtalk.io...)`。对齐 commit 64dae6d 的 EXTERNAL_URL_REWRITES 先例（钉钉国际版 OA 域名是 .io）。
# 同时解决 mintlify 把无 scheme 链接当相对路径致死链的问题（裸域名）。
OA_DINGTALK_LINK_RE = re.compile(r'\]\(\s*(?:https?://)?oa\.dingtalk\.com([^)]*)\)')

# 表格行（以 | 开头）单元格内的 `####` 前缀 — 钉钉文档导出常见瑕疵
# set-department-visibility 5 处命中：把 markdown H4 误导出在表格 cell 里，mintlify 渲染表格时这种语法无意义
TABLE_CELL_H4_PREFIX_RE = re.compile(r'(\|\s*)####\s+')

# manage-members 表格里源文档残留的中文（表头 + 单元格数据）
# 钉钉国际版源文档自身瑕疵（中英混合），手术级翻译
TABLE_CN_TO_EN: dict[str, str] = {
    '名称': 'Name',
    '含义': 'Meaning',
    '截图': 'Screenshot',
    '开放程度': 'Visibility',
    'OA 后台可见': 'Visible in Admin Console',
    '员工可见': 'Visible to Employees',
}

# frontmatter description 手写覆盖：让 mintlify 副标题是「全页 AI 总结」而非 body 首段截断。
# 长度 < 200 chars（mintlify 副标题不截断的实用上限），覆盖各页主要 H2 章节范围。仿 import_meetings_en.py 风格。
DESCRIPTION_OVERRIDES: dict[str, str] = {
    'quickly-enable-organization': "An end-to-end onboarding flow for new admins to launch a DingTalk organization—create the company, build the department tree, and add members in one streamlined path.",
    'create-departments': "Add a single department or build a multi-level hierarchy from the Admin Console—rename, reorder, or nest departments to mirror your real-world org chart.",
    'add-organization-members': "Invite or directly add employees on desktop and assign them to the right departments—covers per-member entry, invitation links, and batch flows for the admin.",
    'batch-add-modify-members': "Bulk-import or bulk-update employees via an Excel template—ideal for onboarding a new org, campus recruiting, or syncing changes from an HR system.",
    'set-enterprise-basic-info': "Edit organization name, logo, industry, scale, and other profile fields from the Admin Console—covers both certified and uncertified enterprises.",
    'set-basic-contacts-info': "Tailor the Contacts experience: switch organization-structure layout, choose department path display, and configure which employee fields are exposed.",
    'enable-member-invitations': "Let ordinary employees invite new members directly—useful for fast org expansion; covers the admin toggle and the invitation flow employees see.",
    'manage-departments': "Edit department metadata (ID, leaders, intro, phone), and run the lifecycle of all-employee and per-department group chats—create, delete, set or transfer the owner.",
    'manage-roles': "Configure default roles (owner, department leader, primary admin), build custom role groups, assign members, and manage role-based permissions for refined collaboration.",
    'manage-members': "Distinguish Emp ID from jobtitle, and edit each employee's profile—department, supervisor, position, email, employee ID, role, plus Executive Mode and number-hiding switches.",
    'set-department-visibility': "Hide sensitive departments or restrict their members' view of Contacts—choose hide-from-all, allow-specified-viewers, or self-only / sub-department-only access scopes.",
    'set-member-field-visibility': "Control which profile fields appear on member detail pages, are editable by the user, or are searchable—plus add custom fields and reorder the field list.",
    'enable-executive-mode': "Hide an executive's mobile number from ordinary employees and block DING messages or business calls to them—10 blocking methods and a per-department allowlist.",
    'require-friend-verification': "Require manual confirmation before any stranger can add you as a DingTalk friend—improves privacy and blocks unsolicited add-friend requests from outside the org.",
    'transfer-enterprise-creator': "Pass enterprise creator (super-admin) identity to another member with verification codes—required before the original creator cancels their account or leaves the org.",
}

# 15 篇 → 3 group，按编号 01-15 顺序排列（用户要求"按标题序号排序"）
# 三元组: (slug, source_basename, expected_title)
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('Getting Started', [
        ('quickly-enable-organization',
         '01 - Quickly Enable a DingTalk Organization.adoc.md',
         'Quickly Enable a DingTalk Organization'),
        ('create-departments',
         '02 - Create Departments.adoc.md',
         'Create Departments'),
        ('add-organization-members',
         '03 - Add Organization Members.adoc.md',
         'Add Organization Members'),
        ('batch-add-modify-members',
         '04 - Batch Add Members or Modify Member Information.adoc.md',
         'Batch Add Members or Modify Member Information'),
        ('set-enterprise-basic-info',
         '05 - Set Enterprise Basic Information.adoc.md',
         'Set Enterprise Basic Information'),
    ]),
    ('Members & Departments', [
        ('set-basic-contacts-info',
         '06 - Set Basic Contacts Information.adoc.md',
         'Set Basic Contacts Information'),
        ('enable-member-invitations',
         '07 - Enable Member Invitations.adoc.md',
         'Enable Member Invitations'),
        ('manage-departments',
         '08 - Manage Departments and Department Groups.adoc.md',
         'Manage Departments and Department Groups'),
        ('manage-roles',
         '09 - Manage Roles.adoc.md',
         'Manage Roles'),
        ('manage-members',
         '10 - Manage Members.adoc.md',
         'Manage Members'),
    ]),
    ('Privacy & Account', [
        ('set-department-visibility',
         '11 - Set Department Visibility.adoc.md',
         'Set Department Visibility'),
        ('set-member-field-visibility',
         '12 - Set Member Information Field Visibility.adoc.md',
         'Set Member Information Field Visibility'),
        ('enable-executive-mode',
         '13 - Enable Executive Mode.adoc.md',
         'Enable Executive Mode'),
        ('require-friend-verification',
         '14 - Require Verification When Adding Me as a Friend.adoc.md',
         'Require Verification When Adding Me as a Friend'),
        ('transfer-enterprise-creator',
         '15 - Transfer Enterprise Creator Identity.adoc.md',
         'Transfer Enterprise Creator Identity'),
    ]),
]


def clean_invisible(text: str) -> str:
    def repl(m: re.Match) -> str:
        return ' ' if m.group(0) == '\xa0' else ''
    return INVISIBLE_CHARS_RE.sub(repl, text)


def strip_leading_numbered_h1(text: str) -> str:
    return LEADING_NUMBERED_H1_RE.sub('', text, count=1)


def strip_leading_breadcrumb(text: str) -> str:
    return LEADING_BREADCRUMB_RE.sub('', text, count=1)


def strip_trailing_trailers(text: str) -> str:
    """串联剥三种尾巴（剥序：从末尾向前，避免吃光相邻段之间的换行）：
    1. Original title/Source 段（10 号特有，最末）
    2. Return to catalog 段（10 号特有，中间）
    3. 裸 `---` 横线（6 篇通用尾巴 + 上两段剥完后可能暴露的孤立 hr）
    """
    text = TRAILING_ORIGINAL_TITLE_RE.sub('', text)
    text = TRAILING_RETURN_TO_RE.sub('', text)
    text = TRAILING_HR_RE.sub('', text)
    return text


def normalize_bare_dingtalk_links(text: str) -> str:
    """OA 域名统一：`](*oa.dingtalk.com*)` → `](https://oa.dingtalk.io*)`。
    一次处理两件事：(a) 补 https:// 前缀（mintlify 当相对路径致死链） (b) .com → .io（国际版品牌域名）。
    """
    return OA_DINGTALK_LINK_RE.sub(r'](https://oa.dingtalk.io\1)', text)


def strip_table_cell_headings(text: str) -> str:
    """剥表格行（以 | 开头）单元格内的 `####` heading 前缀。
    钉钉文档导出常见瑕疵：把 H4 误嵌在表格 cell 里，mintlify 渲染不出预期视觉。
    """
    lines = text.split('\n')
    for i, line in enumerate(lines):
        if line.lstrip().startswith('|'):
            lines[i] = TABLE_CELL_H4_PREFIX_RE.sub(r'\1', line)
    return '\n'.join(lines)


def translate_table_cn(text: str) -> str:
    """翻译 manage-members 表格里源残留的中文词条（钉钉国际版源自身瑕疵）。"""
    for zh, en in TABLE_CN_TO_EN.items():
        text = text.replace(zh, en)
    return text


# 钉钉文档外链 → 纯文本映射（本仓无对应内链文档，按 user 决策去链留文）
# transfer-enterprise-creator 唯一外链 dissolve enterprise（mM3zoYAw...）：本仓 contacts 不收录解散企业指南
EXTERNAL_LINK_TO_PLAIN: dict[str, str] = {
    'https://alidocs.dingtalk.com/i/p/Y7kmbokZp3pgGLq2/docs/mM3zoYAw1Rr8DOzxz962JnZ07y9NpXxD': 'dissolve the enterprise',
}


def delinkify_external_links(text: str) -> str:
    """匹配 [label](url_prefix...) → 纯文本 label_text；忽略 query / fragment 差异。"""
    for url_prefix, label_text in EXTERNAL_LINK_TO_PLAIN.items():
        pattern = re.compile(r'\[[^\]]+\]\(' + re.escape(url_prefix) + r'[^)]*\)')
        text = pattern.sub(label_text, text)
    return text


def extract_clean_description(body: str, fallback: str) -> str:
    text = MD_INLINE_IMAGE_RE.sub(' ', body)
    for raw_line in text.splitlines():
        s = raw_line.strip()
        if not s or s.startswith('#') or s.startswith('!['):
            continue
        # 跳过 markdown 表格行（首尾都是 | 的行：表头 / 分隔 / 数据行）
        # manage-members 第一段就是表格，会让 description 抽到中文表头
        if s.startswith('|') and s.endswith('|'):
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
    after_numbered = strip_leading_numbered_h1(cleaned)

    parsed_title, _orig_desc, body = parse_frontmatter_data(after_numbered, source.stem)
    body = strip_leading_breadcrumb(body)
    body = strip_trailing_trailers(body)
    body = normalize_bare_dingtalk_links(body)
    body = strip_table_cell_headings(body)
    body = translate_table_cn(body)
    body = delinkify_external_links(body)

    title = parsed_title or expected_title
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
        'title_mismatch': title != expected_title,
        'description': description,
        'mdx': mdx,
        'source': str(source),
        'nbsp_before': nbsp_count,
        'nbsp_after': residual_nbsp,
        'mdx_size': len(mdx),
    }


def build_nav_fragment() -> dict:
    return {
        'tab': 'Contacts',
        'groups': [
            {
                'group': group_name,
                'pages': [f'contacts/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Contacts EN markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-06-15_DingTalk_Contacts/)')
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
        CONTACTS_DIR.mkdir(exist_ok=True)
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
                print(f'  {slug:<32} ❌ 未找到源 (期望 {source_basename})')
                continue
            try:
                info = process_one(src, slug, expected_title)
            except Exception as e:
                print(f'  {slug:<32} ❌ {type(e).__name__}: {e}')
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
            print(f'  {slug:<32} {marker} {info["mdx_size"]} bytes (NBSP={info["nbsp_before"]})')

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
            '# Contacts EN Import Report\n',
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
