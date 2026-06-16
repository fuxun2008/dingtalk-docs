#!/usr/bin/env python3
"""import_mail_zh.py — 把 ~/Downloads/<date>_DingTalk_Mail_zh/*.adoc.md → zh/mail/<slug>.mdx。

仿 import_messages_zh.py，差异：
- 输出到 zh/mail/（与现有 en mail/ 共享 slug 命名做三语 URL 镜像）
- tab 名 '邮箱'，6 group 对齐 en mail/ 6-group 划分的中文翻译
- 21 个 slug 与 en mail/ 22 篇中的 21 篇一一对应；en `create-a-contact-group` 暂无 ZH 源（钉钉中文 hub 21 leaf）
- TRAILING_BACK_TO_RE 扩展支持 notes.dingtalk.com 域名 + ▍ 前缀 + 「目录页」后缀（区别于 messages 的 alidocs 域名版）

用法:
    python3 scripts/import_mail_zh.py                    # 默认源 ~/Downloads/2026-06-16_DingTalk_Mail_zh
    python3 scripts/import_mail_zh.py --source <path>    # 自定义源
    python3 scripts/import_mail_zh.py --dry-run          # 只打印总结

产物:
  - zh/mail/<slug>.mdx × 21
  - scripts/output/mail_zh/{nav-fragment.json, slug-map.json, report.md}
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

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-16_DingTalk_Mail_zh'
MAIL_DIR = REPO_ROOT / 'zh' / 'mail'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'mail_zh'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
LEADING_H1_RE = re.compile(r'\A# (.+?)\n')
ADMONITION_MARKER_RE = re.compile(r'^:::\s*$', re.MULTILINE)
# body 末尾钉钉文档自动加的「返回「[**<Group>**](url)」目录页」段
# 邮箱版差异（vs messages 版）：
#   1. 域名是 notes.dingtalk.com（不是 alidocs.dingtalk.com）
#   2. 「返回」前可能有 widget marker ▍ + BOM/零宽
#   3. 「目录」后跟「页」字
#   4. 「」内有空格容差
TRAILING_BACK_TO_RE = re.compile(
    r'\n+---\s*\n+(?:[▍▌▲◆])?[\xa0﻿​‌‍⁠]*'
    r'返回[「『]?\s*\[\*\*[^\]]+\*\*\]\([^)]+\)\s*[」』]?\s*目录(?:页)?\s*\Z'
)
# 钉钉文档外链 → 仓库内链映射（按 dentry UUID 匹配）
# 邮箱 21 篇属于平铺 hub，相互无内链引用，map 暂留空
ALIDOCS_INTERNAL_LINK_MAP: dict[str, str] = {}
ALIDOCS_LINK_RE = re.compile(
    r'\(https://alidocs\.dingtalk\.com/i/(?:nodes|p/[^/]+/docs)/([A-Za-z0-9_]+)(?:\?[^)]*)?\)'
)
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')
MD_LIST_PREFIX_RE = re.compile(r'^\s*(?:\d+[.)]|[-*+])\s+')

# overview slug title 强制覆盖（避免与所在 group 同名等场景）
TITLE_OVERRIDES: dict[str, str] = {}

# frontmatter description 手写覆盖：让 mintlify 副标题是「全页 AI 总结」而非 body 首段重复
# 每条 ≤ 200 chars，覆盖该页主要 H2 章节范围。与 en mail/ 同篇 description 语义镜像；
# 术语遵循 scripts/glossary/zh-en.json 反向中文原词
# （钉钉企业邮箱 / 邮件 / 联系人 / 标签 / 群发 / 自动转发 / 自动回复 / 黑白名单 等）。
DESCRIPTION_OVERRIDES: dict[str, str] = {
    'dingtalk-enterprise-mail': "钉钉企业邮箱产品介绍：海量吞吐、多副本冗余存储的企业级邮件服务，覆盖管理侧域名管理、邮件组、安全审计与用户侧会话模式、附件管理等完整功能矩阵。",
    'customer-story-xinfengwei': "客户案例：鑫蜂维如何借助钉钉企业邮箱打通组织协同与邮件沟通，提升日常办公与客户响应效率。",
    'what-is-dingtalk-mail': "钉钉邮箱是钉钉为每位用户免费提供的邮件入口，并可在组织内开通钉钉企业邮箱，与聊天、文档等钉钉应用深度协同。",
    'send-an-email': "在手机端钉钉「更多 - 邮箱」或电脑端钉钉左侧菜单「邮箱」中点击「+」号撰写并发送邮件，享受与聊天一样简单的邮件体验。",
    'move-or-delete-emails': "在手机端长按或电脑端右键邮件，将邮件移动到指定文件夹或删除，对收件箱进行有效整理。",
    'reply-to-or-forward-emails': "在邮件详情页点击「回复」「回复全部」或「转发」，可以快速对邮件进行回应或将内容转给其他收件人。",
    'download-an-email': "在邮件详情页通过更多操作，将邮件以 .eml 格式下载到本地保存，便于归档或线下查看。",
    'quickly-discuss-an-email': "在邮件详情页点击「快速讨论」，把邮件相关人一键拉到钉钉群中沟通，邮件场景无缝衔接到即时通讯。",
    'set-up-automatic-email-replies': "在邮箱设置中开启自动回复，可针对休假、出差等场景预设回复内容，并设定生效时段。",
    'add-labels-to-emails': "为邮件添加自定义标签，按项目、客户、优先级等维度对邮件进行分类管理，方便后续筛选与查找。",
    'forward-an-email-to-chat-with-one-click': "通过邮件详情页的「转发到聊天」操作，把邮件内容一键发送给钉钉单聊或群聊，邮件与即时通讯协同。",
    'set-up-new-email-notifications': "在邮箱设置中开启或调整新邮件提醒方式，包括手机端推送、电脑端弹窗、声音提示等，避免遗漏重要邮件。",
    'add-contacts': "在邮箱通讯录中添加常用联系人，并可为联系人设置备注、分组，方便后续撰写邮件时快速选择收件人。",
    'import-or-export-contacts': "通过通讯录的导入导出功能，可批量导入 CSV / vCard 格式联系人，或把现有联系人导出备份。",
    'set-up-automatic-email-forwarding': "在邮箱设置中开启自动转发规则，将符合条件的来信自动转发到指定邮箱，便于多邮箱集中管理。",
    'set-up-mail-allowlist-and-blocklist': "通过邮箱黑白名单设置，把指定发件人加入白名单确保来信不被拦截，或加入黑名单屏蔽骚扰邮件。",
    'receive-emails-from-other-mailboxes': "在钉钉邮箱中绑定其他第三方邮箱账号，集中代收来自不同邮箱的邮件，统一在钉钉中查看与回复。",
    'disable-group-members-from-sending-emails-to-a-group': "在群邮箱设置中关闭群成员发送权限，仅允许群主或管理员向群邮箱地址发信，避免群邮件被滥用。",
    'activate-alibaba-enterprise-mail': "管理员通过钉钉管理后台开通阿里企业邮箱服务，按席位购买并完成域名验证，即可为组织成员分发企业邮箱账号。",
    'link-an-existing-alibaba-cloud-mailbox': "把已有的阿里云企业邮箱账号绑定到钉钉，无需迁移即可在钉钉邮箱中收发原邮箱的邮件。",
    'dingtalk-mail-faq': "关于钉钉邮箱的常见问题——包括邮箱开通、账号绑定、收发限制、附件大小、企业邮箱购买与续费等场景的解答。",
}

# 21 篇 → 6 group（对齐 en mail/ 的 6-group 划分，按 docs.json en Mail tab 顺序排列）
# 三元组: (slug, source_basename, expected_title)
# - slug 全部复用 en mail/ 的 kebab-case 命名做三语 URL 镜像
# - source_basename 是 ~/Downloads/2026-06-16_DingTalk_Mail_zh/ 下的实际文件名（含「/」→「_」替换）
# - expected_title 用钉钉源 H1 字面值（含「/」斜杠和全角问号「？」）
# - en `create-a-contact-group` 暂无 ZH 源，不在本表（注册 docs.json 时也同步只 2 篇）
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('开始使用', [
        ('dingtalk-enterprise-mail',
         '钉钉企业邮箱.adoc.md',
         '钉钉企业邮箱'),
        ('customer-story-xinfengwei',
         '客户案例-鑫蜂维.adoc.md',
         '客户案例-鑫蜂维'),
        ('what-is-dingtalk-mail',
         '什么是钉钉邮箱？.adoc.md',
         '什么是钉钉邮箱？'),
    ]),
    ('基础功能', [
        ('send-an-email',
         '如何发送邮件？.adoc.md',
         '如何发送邮件？'),
        ('move-or-delete-emails',
         '如何移动_删除邮件？.adoc.md',
         '如何移动/删除邮件？'),
        ('reply-to-or-forward-emails',
         '如何回复_转发邮件？.adoc.md',
         '如何回复/转发邮件？'),
        ('download-an-email',
         '如何下载邮件？.adoc.md',
         '如何下载邮件？'),
        ('quickly-discuss-an-email',
         '如何快速讨论邮件？.adoc.md',
         '如何快速讨论邮件？'),
    ]),
    ('设置', [
        ('set-up-automatic-email-replies',
         '如何设置邮件自动回复？.adoc.md',
         '如何设置邮件自动回复？'),
        ('add-labels-to-emails',
         '如何给邮件添加标签？.adoc.md',
         '如何给邮件添加标签？'),
        ('forward-an-email-to-chat-with-one-click',
         '如何将邮件一键转发至聊天？.adoc.md',
         '如何将邮件一键转发至聊天？'),
        ('set-up-new-email-notifications',
         '如何设置新到邮件提醒？.adoc.md',
         '如何设置新到邮件提醒？'),
    ]),
    ('联系人', [
        ('add-contacts',
         '如何添加联系人？.adoc.md',
         '如何添加联系人？'),
        # 'create-a-contact-group' 暂无 ZH 源（en mail/ 22 篇 vs zh hub 21 leaf 唯一缺位）
        ('import-or-export-contacts',
         '通讯录如何导入_导出？.adoc.md',
         '通讯录如何导入/导出？'),
    ]),
    ('高级功能', [
        ('set-up-automatic-email-forwarding',
         '如何设置邮件自动转发？.adoc.md',
         '如何设置邮件自动转发？'),
        ('set-up-mail-allowlist-and-blocklist',
         '如何设置邮箱的黑白名单？.adoc.md',
         '如何设置邮箱的黑白名单？'),
        ('receive-emails-from-other-mailboxes',
         '如何代收其他邮箱的邮件？.adoc.md',
         '如何代收其他邮箱的邮件？'),
        ('disable-group-members-from-sending-emails-to-a-group',
         '如何禁止群成员向群内发送邮件？.adoc.md',
         '如何禁止群成员向群内发送邮件？'),
    ]),
    ('企业邮箱与常见问题', [
        ('activate-alibaba-enterprise-mail',
         '如何开通阿里企业邮箱？.adoc.md',
         '如何开通阿里企业邮箱？'),
        ('link-an-existing-alibaba-cloud-mailbox',
         '如何绑定已有阿里云邮箱？.adoc.md',
         '如何绑定已有阿里云邮箱？'),
        ('dingtalk-mail-faq',
         '钉钉邮箱常见问题.adoc.md',
         '钉钉邮箱常见问题'),
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
        'tab': '邮箱',
        'groups': [
            {
                'group': group_name,
                'pages': [f'zh/mail/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Mail (DingTalk Email) ZH markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-06-16_DingTalk_Mail_zh/)')
    ap.add_argument('--dry-run', action='store_true', help='不写文件，只打印总结')
    args = ap.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        print(f'❌ 源目录不存在: {source_dir}', file=sys.stderr)
        return 1

    print(f'源: {source_dir}')
    print(f'目标: {MAIL_DIR}')
    print(f'dry-run: {args.dry_run}')
    print('=' * 70)

    if not args.dry_run:
        MAIL_DIR.mkdir(parents=True, exist_ok=True)
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
                target = MAIL_DIR / f'{slug}.mdx'
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
            '# Mail ZH Import Report\n',
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
        print(f'  mdx:               {MAIL_DIR}/*.mdx ({len(report_rows)} 个)')
        print(f'  nav-fragment.json: {OUTPUT_DIR}/nav-fragment.json')
        print(f'  slug-map.json:     {OUTPUT_DIR}/slug-map.json')
        print(f'  report.md:         {OUTPUT_DIR}/report.md')

    if missing or total_residual_nbsp > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
