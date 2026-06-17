#!/usr/bin/env python3
"""import_calendar_zh.py — 把 ~/Downloads/<date>_DingTalk_Calendar_zh/*.adoc.md → zh/calendar/<slug>.mdx。

仿 import_mail_zh.py，差异：
- 输出到 zh/calendar/（与现有 en calendar/ 共享 slug 命名做三语 URL 镜像）
- tab 名 '日历'，5 group 对齐 en calendar/ 5-group 划分的中文翻译
- 18 个 slug 与 en calendar/ 18 篇一一对应（钉钉中文 hub 18 leaf 全匹配）
- TRAILING_BACK_TO_RE 复用 mail 版（notes.dingtalk.com 域名 + ▍ 前缀 + 「目录页」后缀）

用法:
    python3 scripts/import_calendar_zh.py                    # 默认源 ~/Downloads/2026-06-17_DingTalk_Calendar_zh
    python3 scripts/import_calendar_zh.py --source <path>    # 自定义源
    python3 scripts/import_calendar_zh.py --dry-run          # 只打印总结

产物:
  - zh/calendar/<slug>.mdx × 18
  - scripts/output/calendar_zh/{nav-fragment.json, slug-map.json, report.md}
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

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-17_DingTalk_Calendar_zh'
CAL_DIR = REPO_ROOT / 'zh' / 'calendar'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'calendar_zh'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
LEADING_H1_RE = re.compile(r'\A# (.+?)\n')
ADMONITION_MARKER_RE = re.compile(r'^:::\s*$', re.MULTILINE)
# body 末尾钉钉文档自动加的「返回「[**<Group>**](url)」目录页」段
# 日历版差异（同 mail 版，区别于 messages 的 alidocs 域名版）：
#   1. 域名是 notes.dingtalk.com（不是 alidocs.dingtalk.com）
#   2. 「返回」前可能有 widget marker ▍ + BOM/零宽
#   3. 「目录」后跟「页」字
#   4. 「」内有空格容差
TRAILING_BACK_TO_RE = re.compile(
    r'\n+---\s*\n+(?:[▍▌▲◆])?[\xa0﻿​‌‍⁠]*'
    r'返回[「『]?\s*\[\*\*[^\]]+\*\*\]\([^)]+\)\s*[」』]?\s*目录(?:页)?\s*\Z'
)
# 钉钉文档外链 → 仓库内链映射（按 dentry UUID 匹配）
# 日历 18 篇属于平铺 hub，相互无内链引用，map 暂留空
ALIDOCS_INTERNAL_LINK_MAP: dict[str, str] = {}
ALIDOCS_LINK_RE = re.compile(
    r'\(https://alidocs\.dingtalk\.com/i/(?:nodes|p/[^/]+/docs)/([A-Za-z0-9_]+)(?:\?[^)]*)?\)'
)
# 钉钉 .com 域名 → .io 国际版品牌对齐（保险管道，仿 mail_zh）
# 18 篇 grep 后实测正文无 dingtalk.com 命中（仅 trailing 段被 TRAILING_BACK_TO_RE 剥掉），
# 保留 fix_dingtalk_com_to_io 作未来重跑保险
BARE_DINGTALK_LINK_RE = re.compile(
    r'\((?P<sub>[A-Za-z0-9-]+)\.dingtalk\.com(?P<path>[^)]*)\)'
)
DINGTALK_COM_RE = re.compile(r'\bdingtalk\.com\b')

MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')
MD_LIST_PREFIX_RE = re.compile(r'^\s*(?:\d+[.)]|[-*+])\s+')

# overview slug title 强制覆盖（避免与所在 group 同名等场景）
TITLE_OVERRIDES: dict[str, str] = {}

# frontmatter description 手写覆盖：让 mintlify 副标题是「全页 AI 总结」而非 body 首段重复
# 每条 ≤ 200 chars，覆盖该页主要 H2 章节范围。与 en calendar/ 同篇 description 语义镜像；
# 术语遵循 scripts/glossary/zh-en.json 反向中文原词（日历 / 日程 / 订阅 / 提醒 / 视频会议 /
# 钉钉企业邮箱 / 共享日历 / 重复日程 / 员工关怀 等）。
DESCRIPTION_OVERRIDES: dict[str, str] = {
    'what-is-calendar': "钉钉日历是连接聊天、邮件、待办的时间管理利器，提供日程会议精确通知、自动生成会议群以及“日/周/月/3日”视图。",
    'where-can-i-find-calendar': "移动端钉钉底部菜单第 2 个图标，或电脑端钉钉左侧导航点击「日历」即可进入，开始管理你的日程。",
    'what-is-on-calendar-home': "日历首页功能巡览——新建日程、显示/隐藏我的日历、打开日历设置、切换列表/日/周/月四种视图、查看会议纪要并搜索日程。",
    'set-calendar-views': "一键切换列表、日、周、月以及移动端多种视图，自定义每周的起始日，开启第二时区方便跨境协作。",
    'set-default-event-duration': "在「日历设置 > 视图」中为新建日程设置默认时长，常用时长自动套用——适合人事、招聘、培训、例会等场景。",
    'change-calendar-colors': "更换订阅日历的显示颜色——移动端或电脑端打开「我的日历」，点击日历名旁的「…」选择更换颜色。",
    'search-events': "在移动端或电脑端钉钉日历点击搜索图标，输入日程或会议关键词，快速定位到对应日程。",
    'create-an-event': "移动端或电脑端两种新建日程方式——点击「+」按钮或直接点击/拖拽日历日期，设置标题、时间、参与人、地点、视频会议、议程、附件与提醒。",
    'export-calendar-events': "创建者在电脑端「日历 > 我的」点击「…」选择「导出」，设置时间段后导出为 AI 表格、在线表格或下载到本地。",
    'sync-mobile-events': "在「日历设置」开启移动端日程同步与提醒，把钉钉企业邮箱、手机自带日程和日志合并显示到日历中。",
    'share-my-calendar': "把日历共享给同事查看你的忙闲——在移动端或电脑端「日历设置」中选择只读或授予新建/编辑权限。",
    'internal-organization-event-management': "把日程标记为组织内部，参与人限定本企业，离职员工自动退出、外部参与人会被标记，分享范围保持在组织内。",
    'snooze-an-event-reminder': "收到日程提醒时点击「稍后」推迟提醒——适合背靠背会议或专注工作时段，提醒会在合适时机再次弹出。",
    'optional-attendance-in-event-reminders': "创建日程时把参与人标记为「可选参加」，被邀请人会在提醒卡片看到该标识，可根据日程冲突自行决定是否参加。",
    'create-dingtalk-mail-events-in-calendar': "钉钉企业邮箱用户可在日历中收发邮件日程——在移动端或电脑端创建日程时添加邮件联系人，让双方日历保持同步。",
    'sync-employee-care-events-to-calendar': "在「日历设置 > 同步」开启员工关怀同步，把工作周年与生日自动同步到日历，并提前 3 天提醒，可选 AI 自动生成祝福语。",
    'delete-an-event': "不再需要的日程支持取消或删除——组织者可在电脑端或移动端取消未来的多人日程，参与人也可仅从自己日历中删除。",
    'set-a-repeating-event': "在新建日程表单点击「不重复」，选择每天、每周、每月或自定义周期，让日程在未来按周期自动重复，无需逐次创建。",
}

# 18 篇 → 5 group（对齐 en calendar/ 的 5-group 划分，按 docs.json en Calendar tab 顺序排列）
# 三元组: (slug, source_basename, expected_title)
# - slug 全部复用 en calendar/ 的 kebab-case 命名做三语 URL 镜像
# - source_basename 是 ~/Downloads/2026-06-17_DingTalk_Calendar_zh/ 下的实际文件名
# - expected_title 用钉钉源 H1 字面值（含「？」全角问号 + 中文标点）
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('开始使用', [
        ('what-is-calendar',
         '什么是日历？.adoc.md',
         '什么是日历？'),
        ('where-can-i-find-calendar',
         '日历产品入口在哪.adoc.md',
         '日历产品入口在哪'),
        ('what-is-on-calendar-home',
         '日历首页都有什么.adoc.md',
         '日历首页都有什么'),
    ]),
    ('自定义日历', [
        ('set-calendar-views',
         '如何设置日历视图.adoc.md',
         '如何设置日历视图'),
        ('set-default-event-duration',
         '日历如何设置默认时长.adoc.md',
         '日历如何设置默认时长'),
        ('change-calendar-colors',
         '如何给日历换新“颜”.adoc.md',
         '如何给日历换新“颜”'),
        ('search-events',
         '如何搜索日程？.adoc.md',
         '如何搜索日程？'),
    ]),
    ('创建与共享日程', [
        ('create-an-event',
         '如何新建日程？.adoc.md',
         '如何新建日程？'),
        ('export-calendar-events',
         '日程在哪里导出.adoc.md',
         '日程在哪里导出'),
        ('sync-mobile-events',
         '如何同步手机日程？.adoc.md',
         '如何同步手机日程？'),
        ('share-my-calendar',
         '如何共享我的日历？.adoc.md',
         '如何共享我的日历？'),
        ('internal-organization-event-management',
         '组织内部日程管理说明.adoc.md',
         '组织内部日程管理说明'),
    ]),
    ('提醒', [
        ('snooze-an-event-reminder',
         '接收日程时如何设置稍后提醒？.adoc.md',
         '接收日程时如何设置稍后提醒？'),
        ('optional-attendance-in-event-reminders',
         '日程提醒新增「可选参加」提示.adoc.md',
         '日程提醒新增「可选参加」提示'),
    ]),
    ('同步与管理', [
        ('create-dingtalk-mail-events-in-calendar',
         '在钉钉日历中创建钉钉企业邮箱日程.adoc.md',
         '在钉钉日历中创建钉钉企业邮箱日程'),
        ('sync-employee-care-events-to-calendar',
         '将员工关怀同步到日历.adoc.md',
         '将员工关怀同步到日历'),
        ('delete-an-event',
         '日程如何删除.adoc.md',
         '日程如何删除'),
        ('set-a-repeating-event',
         '如何设置重复日程.adoc.md',
         '如何设置重复日程'),
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


def strip_admonition_markers(body: str) -> str:
    return ADMONITION_MARKER_RE.sub('', body)


def strip_trailing_back_to(body: str) -> str:
    """剥 body 末尾钉钉文档自动加的「返回「[**<Group>**](url)」目录页」段（含前置 --- 横线 + 可选 ▍ 前缀）。"""
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
        'tab': '日历',
        'groups': [
            {
                'group': group_name,
                'pages': [f'zh/calendar/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Calendar (DingTalk Calendar) ZH markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-06-17_DingTalk_Calendar_zh/)')
    ap.add_argument('--dry-run', action='store_true', help='不写文件，只打印总结')
    args = ap.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        print(f'❌ 源目录不存在: {source_dir}', file=sys.stderr)
        return 1

    print(f'源: {source_dir}')
    print(f'目标: {CAL_DIR}')
    print(f'dry-run: {args.dry_run}')
    print('=' * 70)

    if not args.dry_run:
        CAL_DIR.mkdir(parents=True, exist_ok=True)
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
                target = CAL_DIR / f'{slug}.mdx'
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
            '# Calendar ZH Import Report\n',
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
        print(f'  mdx:               {CAL_DIR}/*.mdx ({len(report_rows)} 个)')
        print(f'  nav-fragment.json: {OUTPUT_DIR}/nav-fragment.json')
        print(f'  slug-map.json:     {OUTPUT_DIR}/slug-map.json')
        print(f'  report.md:         {OUTPUT_DIR}/report.md')

    if missing or total_residual_nbsp > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
