#!/usr/bin/env python3
"""import_oa_zh.py — 把 ~/Downloads/<date>_DingTalk_OA_zh/*.adoc.md → zh/oa/<slug>.mdx。

仿 import_oa_en.py，差异：
- 输出到 zh/oa/（与 en oa/ 共享 slug 命名做三语 URL 镜像）
- tab 名「管理后台」，6 group 对齐 en oa/ 分组的中文名
- 19 个 slug 与 en oa/ 一一对应
- 管理后台 zh 源同样干净：无面包屑、无 "返回母文档" 尾段、无 line-3 `---`
  → 与 en 一样不需要任何 leading/trailing 正则；正文里 open.dingtalk.com / alidocs.dingtalk.com
    是指向外部真实资源的链接，不做 .com→.io 改写（open 平台无 .io 版，改写会误伤）

用法:
    python3 scripts/import_oa_zh.py                    # 默认源 ~/Downloads/2026-07-29_DingTalk_OA_zh
    python3 scripts/import_oa_zh.py --source <path>    # 自定义源
    python3 scripts/import_oa_zh.py --dry-run          # 只打印总结

产物:
  - zh/oa/<slug>.mdx × 19
  - scripts/output/oa_zh/{nav-fragment.json, slug-map.json, report.md}
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

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-07-29_DingTalk_OA_zh'
OA_DIR = REPO_ROOT / 'zh' / 'oa'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'oa_zh'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')

TITLE_OVERRIDES: dict[str, str] = {}

# 19 篇 → 6 group。三元组 (slug, source_basename, expected_title)
# slug 与 import_oa_en.py 完全一致（三语 URL 镜像）；source_basename / group 名 / title 用中文
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('快速入门', [
        ('how-to-log-in-to-admin-console',
         '快速入门/如何登录管理后台.adoc.md',
         '如何登录管理后台'),
    ]),
    ('组织与人员', [
        ('partner-organizations',
         '组织与人员/协作组织.adoc.md',
         '协作组织'),
    ]),
    ('企业配置', [
        ('sso',
         '企业配置/SSO单点登录设置.adoc.md',
         'SSO单点登录设置'),
        ('create-package',
         '企业配置/创建打包.adoc.md',
         '创建打包'),
        ('packaging-material-management',
         '企业配置/打包素材管理.adoc.md',
         '打包素材管理'),
        ('fcm-push-notification-setup',
         '企业配置/申请开通FCM推送引导.adoc.md',
         '申请开通FCM推送引导'),
        ('organization-code-login',
         '企业配置/组织代码登录.adoc.md',
         '组织代码登录'),
    ]),
    ('安全与权限', [
        ('set-up-primary-admins',
         '安全与权限/设置主管理员.adoc.md',
         '设置主管理员'),
        ('trusted-devices',
         '安全与权限/安全准入平台.adoc - 可信设备.adoc.md',
         '可信设备'),
        ('global-visible-watermark',
         '安全与权限/数据防泄平台.adoc - 全局明水印.adoc.md',
         '全局明水印'),
        ('in-app-file-control',
         '安全与权限/数据防泄平台.adoc - 钉内文件管控.adoc.md',
         '钉内文件管控'),
        ('online-document-control',
         '安全与权限/数据防泄平台.adoc - 在线文档管控.adoc.md',
         '在线文档管控'),
    ]),
    ('应用管理', [
        ('ai-minutes-equity-allocation',
         '应用管理/AI听记 - 权益分配.adoc.md',
         '权益分配'),
        ('video-meetings-allocate-equity',
         '应用管理/音视频会议 - 如何分配权益和查看用量.adoc.md',
         '如何分配权益和查看用量'),
        ('video-meetings-custom-hotwords',
         '应用管理/音视频会议 - 字幕和AI听记转写支持自定义热词.adoc.md',
         '字幕和AI听记转写支持自定义热词'),
    ]),
    ('费用与订阅', [
        ('order-center',
         '费用与订阅/订单中心.adoc.md',
         '订单中心'),
        ('payment-information',
         '费用与订阅/支付信息.adoc.md',
         '支付信息'),
        ('purchase-or-upgrade',
         '费用与订阅/购买或升级.adoc.md',
         '购买或升级'),
        ('subscriptions',
         '费用与订阅/订阅管理.adoc.md',
         '订阅管理'),
    ]),
]


def clean_invisible(text: str) -> str:
    def repl(m: re.Match) -> str:
        return ' ' if m.group(0) == '\xa0' else ''
    return INVISIBLE_CHARS_RE.sub(repl, text)


def extract_clean_description(body: str, fallback: str) -> str:
    text = MD_INLINE_IMAGE_RE.sub(' ', body)
    for raw_line in text.splitlines():
        s = raw_line.strip()
        if not s or s.startswith('#') or s.startswith('!['):
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

    title = TITLE_OVERRIDES.get(expected_slug) or parsed_title or expected_title
    description = extract_clean_description(body, fallback=title)

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
        'tab': '管理后台',
        'groups': [
            {
                'group': group_name,
                'pages': [f'zh/oa/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='OA (管理后台) ZH markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-07-29_DingTalk_OA_zh/)')
    ap.add_argument('--dry-run', action='store_true', help='不写文件，只打印总结')
    args = ap.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        print(f'❌ 源目录不存在: {source_dir}', file=sys.stderr)
        return 1

    print(f'源: {source_dir}')
    print(f'目标: {OA_DIR}')
    print(f'dry-run: {args.dry_run}')
    print('=' * 70)

    if not args.dry_run:
        OA_DIR.mkdir(parents=True, exist_ok=True)
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
                print(f'  {slug:<42} ❌ 未找到源 (期望 {source_basename})')
                continue
            try:
                info = process_one(src, slug, expected_title)
            except Exception as e:
                print(f'  {slug:<42} ❌ {type(e).__name__}: {e}')
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
            print(f'  {slug:<42} {marker} {info["mdx_size"]} bytes (NBSP={info["nbsp_before"]})')

            if not args.dry_run:
                target = OA_DIR / f'{slug}.mdx'
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
            '# OA (管理后台) ZH Import Report\n',
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
        print(f'  mdx:               {OA_DIR}/*.mdx ({len(report_rows)} 个)')
        print(f'  nav-fragment.json: {OUTPUT_DIR}/nav-fragment.json')
        print(f'  slug-map.json:     {OUTPUT_DIR}/slug-map.json')
        print(f'  report.md:         {OUTPUT_DIR}/report.md')

    if missing or total_residual_nbsp > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
