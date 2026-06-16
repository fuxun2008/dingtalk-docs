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
# 钉钉 .com 域名 → .io 国际版品牌对齐（覆盖：oa.dingtalk.com / docs.dingtalk.com 等管理后台 / 文档外链；
# 邮箱地址后缀 @dingtalk.com → @dingtalk.io 同步生效；适用 markdown link target + 裸字面）
# 裸域名（无 https://）会补协议头，避免 mintlify 误判为本地相对路径死链
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
# 每条 ≤ 200 chars，覆盖该页主要 H2 章节范围。与 en mail/ 同篇 description 语义镜像；
# 术语遵循 scripts/glossary/zh-en.json 反向中文原词
# （钉钉企业邮箱 / 邮件 / 联系人 / 标签 / 群发 / 自动转发 / 自动回复 / 黑白名单 等）。
DESCRIPTION_OVERRIDES: dict[str, str] = {
    'dingtalk-enterprise-mail': "钉钉企业邮箱是基于钉钉打造的原生邮件服务，不限容量、高吞吐多副本冗余，覆盖管理员工具与用户协作的完整功能矩阵。",
    'customer-story-xinfengwei': "客户案例：作为钉钉首位客户，鑫蜂维如何借助钉钉邮箱在移动端处理邮件，加速组织数字化转型与日常工作响应。",
    'what-is-dingtalk-mail': "钉钉邮箱聚焦高效、安全的商务邮件沟通，包含钉钉个人邮箱、钉钉企业邮箱以及三方邮箱客户端三种形态。",
    'send-an-email': "在手机端钉钉「更多 > 邮箱」或电脑端钉钉左侧菜单「邮箱 > + 撰写」中撰写并发送邮件，让邮件像聊天一样简单。",
    'move-or-delete-emails': "在手机端长按邮件或在电脑端选中邮件，将邮件移动到其他文件夹或删除，保持收件箱整洁。",
    'reply-to-or-forward-emails': "在手机端或电脑端打开邮件后选择「回复」或「转发」，快速对邮件作出回应或将邮件转给其他收件人。",
    'download-an-email': "在钉钉电脑端打开邮件后下载到本地，便于离线阅读或归档备份。",
    'quickly-discuss-an-email': "在手机端钉钉邮箱中把邮件转发到群聊或邮件参与人，即时在钉钉中围绕邮件展开讨论。",
    'set-up-automatic-email-replies': "在电脑端钉钉邮箱的「休假回复设置」中开启自动回复，自定义回复内容并设定生效日期，休假期间自动响应来信。",
    'add-labels-to-emails': "在电脑端钉钉邮箱中自定义标签，按项目、客户、优先级等维度对邮件分类，方便后续筛选与查找。",
    'forward-an-email-to-chat-with-one-click': "通过「转发到聊天」一键把完整邮件发送到钉钉单聊或群聊，无需截图即可保留完整邮件内容。",
    'set-up-new-email-notifications': "通过手机系统设置和钉钉邮箱应用内设置配置新邮件提醒，包括声音、推送和按账号开关，避免遗漏重要邮件。",
    'add-contacts': "在电脑端钉钉邮箱的「邮件联系人」中添加常用联系人，撰写邮件时即可快速选择收件人。",
    'create-a-contact-group': "在电脑端钉钉邮箱的「邮件联系人」中创建联系人组，把多个联系人按团队、项目或关系分组管理，发信时一次选择全员。",
    'import-or-export-contacts': "将 CSV 或 vCard 格式的联系人导入到「邮件联系人」，或导出现有联系人作备份与迁移到其他邮件客户端。",
    'set-up-automatic-email-forwarding': "在电脑端钉钉邮箱的「邮件设置 > 自动转发」中添加转发规则，将符合条件的来信自动转发到指定邮箱。",
    'set-up-mail-allowlist-and-blocklist': "把发件人或域名加入白名单可绕过垃圾邮件文件夹，加入黑名单则直接进垃圾邮件，每项最多支持 500 条。",
    'receive-emails-from-other-mailboxes': "在钉钉邮箱中绑定其他邮箱账号，无需逐个登录即可在统一钉钉收件箱中代收与回复多个邮箱的邮件。",
    'disable-group-members-from-sending-emails-to-a-group': "在群设置中开启或关闭「群邮件组」，控制是否允许群成员向群邮箱地址发送邮件，避免群邮件被滥用。",
    'activate-alibaba-enterprise-mail': "通过钉钉管理后台开通阿里企业邮箱——基于飞天云提供 7×24 高稳定服务，多层安全防护，日程同步与海内外专属通道。",
    'link-an-existing-alibaba-cloud-mailbox': "主管理员或创建者可通过钉钉管理后台或手机端钉钉，把已有的阿里云企业邮箱域名绑定到钉钉邮箱使用。",
    'dingtalk-mail-faq': "钉钉邮箱常见问题——通用设置项、单封邮件收件人上限、是否有 Web 版、存储容量、三方客户端登录限制、企业邮箱差异等。",
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
        # 'create-a-contact-group' 钉钉中文 hub 无对应源（en mail/ 22 篇 vs zh hub 21 leaf 唯一缺位）
        # ZH 版手写 zh/mail/create-a-contact-group.mdx（参考 en 母版翻译，远程图复用 alicdn URL）
        # 不走脚本，不在本 GROUPS 表里；docs.json zh 邮箱 tab「联系人」group 已直接注册
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


def fix_dingtalk_com_to_io(body: str) -> str:
    """统一处理 dingtalk.com → dingtalk.io（国际版品牌对齐）：
    1. markdown 裸域名链接 `(oa.dingtalk.com...)` → `(https://oa.dingtalk.io...)`（补协议头 + 改域名）
    2. 其余字面 `dingtalk.com` → `dingtalk.io`（含邮箱后缀 @dingtalk.com）
    顺序锁死：先做 (1)（已含 .com → .io 改写），再 (2) 兜底剩余字面。
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
