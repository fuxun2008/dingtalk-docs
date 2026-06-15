#!/usr/bin/env python3
"""import_calendar_en.py — 把 ~/Downloads/<date>_DingTalk_Calendar/*.adoc.md → calendar/<slug>.mdx。

仿 import_drive_en.py（文件名形态 C：Title Case + 空格/标点），差异：
- Calendar hub 不是子集 wiki → 无 `Back to <hub>` 尾段（不需 TRAILING_BACK_TO_RE）
- 源无 line-3 `---` 分隔线噪声（不需 LEADING_HR_RE）
- 4 篇有 body 内多余 H1（line 3/5 等）应降级为 H2（DEMOTE_BODY_H1_RE）
  - Set Calendar Views（4 H1）/ Create DingTalk Enterprise Mail Events（3 H1）
  - Where Can I Find Calendar（2 H1）/ Sync Employee Care Events to Calendar（2 H1）
- 2 篇有字面 `\\[Image placeholder\\]` 占位符（What Is Calendar / Create DingTalk Mail Events）→ IMAGE_PLACEHOLDER_RE 剥掉
- Delete an Event 一篇有 `Original title: <中文>\\n\\nSource: <alidocs>` 尾段
  → 复用 contacts 的 TRAILING_ORIGINAL_TITLE_RE + TRAILING_HR_RE 串联剥
- 18 篇 / 5 group（全按源 hub 折叠顺序，用户强调"注意文档顺序"）：
  Getting Started(3) + Customize Calendar(4) + Create and Share Events(5)
  + Reminders(2) + Sync and Manage(4)

用法:
    python3 scripts/import_calendar_en.py                    # 默认源 ~/Downloads/2026-06-15_DingTalk_Calendar
    python3 scripts/import_calendar_en.py --source <path>    # 自定义源
    python3 scripts/import_calendar_en.py --dry-run          # 只打印总结

产物:
  - calendar/<slug>.mdx × 18
  - scripts/output/calendar_en/{nav-fragment.json, slug-map.json, report.md}
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

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-15_DingTalk_Calendar'
CALENDAR_DIR = REPO_ROOT / 'calendar'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'calendar_en'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')

# body 内多余 H1（line 3/5 等位置的二次 H1）降级为 H2
# parse_frontmatter_data 已剥过 line-1 H1，剩下的 `^# ` 都是 body 内噪声 → 全降为 `## `
DEMOTE_BODY_H1_RE = re.compile(r'^# ', re.MULTILINE)

# 字面占位符 `\[Image placeholder\]`（钉钉文档作者忘删的占位文字）
# 整行剥掉，前后空行自然合并
IMAGE_PLACEHOLDER_RE = re.compile(r'^\\?\[Image placeholder\\?\]\s*$\n?', re.MULTILINE)

# 粗体内仅含标点 / 空白（如 `**,**`、`** **`）—— 钉钉文档导出常见瑕疵
# 把 `**X**` 中 X 仅由 ASCII/CJK 标点 + 空白构成的 bold 拆掉，保留裸标点
# where-can-i-find-calendar.mdx:12 命中 1 处（`bottom menu**,**  tap`）
BOLD_PUNCT_RE = re.compile(r'\*\*([\s\.,，。;；:：!！\?？、]+?)\*\*')

# 尾段「Original title: <中文>\n\nSource: https://alidocs...」段（Delete an Event 一篇有）
# 含前置 --- 分隔线
TRAILING_ORIGINAL_TITLE_RE = re.compile(
    r'\n+---\s*\n+Original title:[^\n]+\s*\n+Source:\s*https://alidocs\.dingtalk\.com[^\n]+\s*\n*\Z'
)
# body 末尾裸 `---` 分隔线兜底（钉钉文档导出常见尾巴）
TRAILING_HR_RE = re.compile(r'\n+---\s*\Z')

MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')

# frontmatter description 手写覆盖：让 mintlify 副标题是「全页 AI 总结」而非 body 首段 160 字符截断。
# 长度 < 200 chars（mintlify 副标题不截断的实用上限），每条覆盖该页所有主要 H2 章节。仿 ai-minutes / contacts 风格。
DESCRIPTION_OVERRIDES: dict[str, str] = {
    'what-is-calendar': "DingTalk Calendar is a time-management tool linked to chats, mail, and To Do—covers precise event notifications, auto meeting-group creation, and day/week/month/three-day views.",
    'where-can-i-find-calendar': "Quick access guide for DingTalk Calendar—tap the second icon in the mobile bottom menu, or click Calendar in the left navigation on desktop to start managing schedules.",
    'what-is-on-calendar-home': "A tour of Calendar Home: create new events, toggle My Calendar visibility, open Calendar Settings, switch list/day/week/month/3-day views, view meeting minutes, and search events.",
    'set-calendar-views': "Switch between list, day, week, month, and mobile three-day views with one click; customize the first day of the week; enable a secondary time zone for cross-border collaboration.",
    'set-default-event-duration': "Set a default duration for new events under Calendar Settings → View so common lengths apply automatically—useful for HR, recruiting, training, and recurring meeting workflows.",
    'change-calendar-colors': "Update the display color of a subscribed calendar on desktop or mobile—open My Calendars, tap the … icon next to a calendar, choose Change color, and pick the color you want.",
    'search-events': "Find events fast on mobile and desktop—tap or click the search icon in DingTalk Calendar, type event or meeting keywords, and jump straight to the matching schedule entry.",
    'create-an-event': "Two ways to add events on mobile or desktop—tap +, or click a date or drag on day/week view—then set title, time, participants, location, video meeting, agenda, attachments, and reminders.",
    'export-calendar-events': "Export events as the creator on desktop—go to Calendar > My, click …, choose Export, pick a time range, and send events to AI Sheet, an online sheet, or a local download.",
    'sync-mobile-events': "Combine events from DingTalk Mail, your phone, and Logs into one Calendar view—enable mobile-event sync and reminders in Calendar Settings so important schedules stay visible.",
    'share-my-calendar': "Share your calendar with teammates so they see your availability—choose view-only or grant create / edit rights from Calendar Settings on mobile or desktop to avoid interruptions.",
    'internal-organization-event-management': "Mark events as internal-organization-only so participants are scoped to your company; leavers exit automatically, external guests are flagged, and sharing stays inside the org.",
    'snooze-an-event-reminder': "When a reminder pops up at a busy moment, tap Later to postpone it—useful for back-to-back meetings or focused work so reminders return when you can actually act on them.",
    'optional-attendance-in-event-reminders': "Organizers can flag participants as Optional when creating an event; invitees see the Optional tag in the reminder card and can decide whether to attend without schedule conflicts.",
    'create-dingtalk-mail-events-in-calendar': "For DingTalk Enterprise Mail users—send and receive mail-calendar events directly in Calendar; add Mail contacts when creating events on mobile or desktop to stay in sync.",
    'sync-employee-care-events-to-calendar': "Auto-sync work anniversaries and birthdays into Calendar with a three-day-ahead reminder and optional AI-generated greetings—enable it under Calendar Settings → Sync.",
    'delete-an-event': "Cancel or remove events you no longer need—organizers can cancel future multi-participant events from desktop or mobile, while participants can delete events from their own calendar.",
    'set-a-repeating-event': "Create one event that recurs over weeks—open the new-event form, tap Does not repeat, and pick daily, weekly, monthly, or a custom cycle so future schedules are filled in automatically.",
}

# 18 篇 → 5 group（全按源 hub 折叠菜单顺序，用户明确"注意文档顺序"）
# 三元组: (slug, source_basename, expected_title)
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('Getting Started', [
        ('what-is-calendar',
         'What Is Calendar_.adoc.md',
         'What Is Calendar?'),
        ('where-can-i-find-calendar',
         'Where Can I Find Calendar_.adoc.md',
         'Where Can I Find Calendar?'),
        ('what-is-on-calendar-home',
         'What Is on Calendar Home_.adoc.md',
         'What Is on Calendar Home?'),
    ]),
    ('Customize Calendar', [
        ('set-calendar-views',
         'Set Calendar Views.adoc.md',
         'Set Calendar Views'),
        ('set-default-event-duration',
         'Set the Default Event Duration.adoc.md',
         'Set the Default Event Duration'),
        ('change-calendar-colors',
         'Change Calendar Colors.adoc.md',
         'Change Calendar Colors'),
        ('search-events',
         'Search Events.adoc.md',
         'Search Events'),
    ]),
    ('Create and Share Events', [
        ('create-an-event',
         'Create an Event.adoc.md',
         'Create an Event'),
        ('export-calendar-events',
         'Export Calendar Events.adoc.md',
         'Export Calendar Events'),
        ('sync-mobile-events',
         'Sync Mobile Events.adoc.md',
         'Sync Mobile Events'),
        ('share-my-calendar',
         'Share My Calendar.adoc.md',
         'Share My Calendar'),
        ('internal-organization-event-management',
         'Internal Organization Event Management.adoc.md',
         'Internal Organization Event Management'),
    ]),
    ('Reminders', [
        ('snooze-an-event-reminder',
         'Snooze an Event Reminder.adoc.md',
         'Snooze an Event Reminder'),
        ('optional-attendance-in-event-reminders',
         'Optional Attendance in Event Reminders.adoc.md',
         'Optional Attendance in Event Reminders'),
    ]),
    ('Sync and Manage', [
        ('create-dingtalk-mail-events-in-calendar',
         'Create DingTalk Enterprise Mail Events in Calendar.adoc.md',
         'Create DingTalk Enterprise Mail Events in Calendar'),
        ('sync-employee-care-events-to-calendar',
         'Sync Employee Care Events to Calendar.adoc.md',
         'Sync Employee Care Events to Calendar'),
        ('delete-an-event',
         'Delete an Event.adoc.md',
         'Delete an Event'),
        ('set-a-repeating-event',
         'Set a Repeating Event.adoc.md',
         'Set a Repeating Event'),
    ]),
]


def clean_invisible(text: str) -> str:
    def repl(m: re.Match) -> str:
        return ' ' if m.group(0) == '\xa0' else ''
    return INVISIBLE_CHARS_RE.sub(repl, text)


def demote_body_h1(text: str) -> str:
    """parse_frontmatter_data 剥过 line-1 H1 后，body 内剩余 `^# ` 全降级为 `## `。
    Calendar 源 4 篇有 body 内多余 H1（应是 section heading 即 H2）。"""
    return DEMOTE_BODY_H1_RE.sub('## ', text)


def strip_image_placeholders(text: str) -> str:
    """剥字面占位符 `\\[Image placeholder\\]`（钉钉文档作者忘删的占位文字）。
    What Is Calendar / Create DingTalk Mail Events 两篇命中。"""
    return IMAGE_PLACEHOLDER_RE.sub('', text)


def fix_bold_punct(text: str) -> str:
    """把 bold 包裹的纯标点（含中英文逗号/句号/分号/冒号/叹号/问号/顿号、以及空白）剥成裸标点。
    钉钉文档导出常见瑕疵：作者误把标点也加粗，mintlify 渲染异常。
    where-can-i-find-calendar.mdx 命中 1 处（`bottom menu**,**  tap` → `bottom menu,  tap`）。"""
    return BOLD_PUNCT_RE.sub(r'\1', text)


def strip_trailing_trailers(text: str) -> str:
    """剥末尾「Original title: <中文>\\n\\nSource: <alidocs>」+ 裸 `---` 兜底。
    顺序：先 Original-title 段（含前置 ---），再裸 ---（兜底未匹配的）。"""
    text = TRAILING_ORIGINAL_TITLE_RE.sub('', text)
    text = TRAILING_HR_RE.sub('', text)
    return text


def extract_clean_description(body: str, fallback: str) -> str:
    text = MD_INLINE_IMAGE_RE.sub(' ', body)
    for raw_line in text.splitlines():
        s = raw_line.strip()
        if not s or s.startswith('#') or s.startswith('!['):
            continue
        # 跳过 markdown 表格行（首尾都是 |）
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
    parsed_title, _orig_desc, body = parse_frontmatter_data(cleaned, source.stem)
    body = demote_body_h1(body)
    body = strip_image_placeholders(body)
    body = fix_bold_punct(body)
    body = strip_trailing_trailers(body)

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
        'tab': 'Calendar',
        'groups': [
            {
                'group': group_name,
                'pages': [f'calendar/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Calendar EN markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-06-15_DingTalk_Calendar/)')
    ap.add_argument('--dry-run', action='store_true', help='不写文件，只打印总结')
    args = ap.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        print(f'❌ 源目录不存在: {source_dir}', file=sys.stderr)
        return 1

    print(f'源: {source_dir}')
    print(f'目标: {CALENDAR_DIR}')
    print(f'dry-run: {args.dry_run}')
    print('=' * 70)

    if not args.dry_run:
        CALENDAR_DIR.mkdir(exist_ok=True)
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
                print(f'  {slug:<48} ❌ 未找到源 (期望 {source_basename})')
                continue
            try:
                info = process_one(src, slug, expected_title)
            except Exception as e:
                print(f'  {slug:<48} ❌ {type(e).__name__}: {e}')
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
            print(f'  {slug:<48} {marker} {info["mdx_size"]} bytes (NBSP={info["nbsp_before"]})')

            if not args.dry_run:
                target = CALENDAR_DIR / f'{slug}.mdx'
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
            '# Calendar EN Import Report\n',
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
        print(f'  mdx:               {CALENDAR_DIR}/*.mdx ({len(report_rows)} 个)')
        print(f'  nav-fragment.json: {OUTPUT_DIR}/nav-fragment.json')
        print(f'  slug-map.json:     {OUTPUT_DIR}/slug-map.json')
        print(f'  report.md:         {OUTPUT_DIR}/report.md')

    if missing or total_residual_nbsp > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
