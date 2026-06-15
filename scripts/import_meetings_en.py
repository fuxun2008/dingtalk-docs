#!/usr/bin/env python3
"""import_meetings_en.py — 把 ~/Downloads/<date>_DingTalk_Meetings_EN/*.adoc.md → meetings/<slug>.mdx。

仿 import_ai_minutes_en.py，差异：
- 7 group / 44 篇（产品体量比 mail/im/drive/ai-minutes 都大）
- EN 是钉钉文档翻译版导出，44 文件全部含末尾 "---\\n\\nOriginal title: ...\\n\\nSource: https://alidocs..." 段，需新增 TRAILING_ORIGINAL_TITLE_RE 剥除
- EN NBSP 11308 个（翻译版 export 用 NBSP 替代 ASCII 空格做断字），clean_invisible 已覆盖
- line-1 真 H1（drive 风格），但 6 文件 line-1+3 重复 H1（AI Minutes 风格）→ 保留 strip_dup_leading_h1
- body 中段 24 个 H1 → demote_body_h1
- source H1 形如 `1.1 How to ...` 带编号前缀，需 strip_numbered_prefix 让 frontmatter title 干净
- TITLE_OVERRIDES: 'purchase-guide' → 'How to Purchase'（避免与 group "Purchase Guide" 同名）
- 删 strip_admonition_markers（EN 0 命中）
- 删 TRAILING_BACK_TO_RE / ALIDOCS_INTERNAL_LINK_MAP（EN 内 alidocs 链接全在 Source 行，已被 TRAILING_ORIGINAL_TITLE_RE 一并剥除）

用法:
    python3 scripts/import_meetings_en.py                    # 默认源 ~/Downloads/2026-06-15_DingTalk_Meetings_EN/
    python3 scripts/import_meetings_en.py --source <path>    # 自定义源
    python3 scripts/import_meetings_en.py --dry-run          # 只打印总结

产物:
  - meetings/<slug>.mdx × 44
  - scripts/output/meetings_en/{nav-fragment.json, slug-map.json, report.md}
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

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-15_DingTalk_Meetings_EN'
MEETINGS_DIR = REPO_ROOT / 'meetings'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'meetings_en'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
LEADING_H1_RE = re.compile(r'\A# (.+?)\n')
# 剥钉钉文档翻译版末尾自动加的 "---\n\nOriginal title: <中文原标题>\n\nSource: https://alidocs.dingtalk.com/i/nodes/<uuid>..." 段
# 全 44 EN 文件命中（钉钉翻译版 export 脚本痕迹）
TRAILING_ORIGINAL_TITLE_RE = re.compile(
    r'\n+---\s*\n+Original title:.*?\Z',
    re.DOTALL,
)
# H1 编号前缀：钉钉源 H1 形如 "# 1.1 How to..." / "# 2.12 ..."，剥后让 title 干净
NUMBERED_PREFIX_RE = re.compile(r'^\d+(?:\.\d+)?\s+')
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')
MD_LIST_PREFIX_RE = re.compile(r'^\s*(?:\d+[.)]|[-*+])\s+')

# slug title 强制覆盖（避免与 group 同名）
TITLE_OVERRIDES: dict[str, str] = {
    'purchase-guide': 'How to Purchase',  # 避免与 group "Purchase Guide" 同名
}

# frontmatter description 手写覆盖：让 mintlify 副标题是「全页 AI 总结」而非 body 首段截断。
# 长度 < 200 chars（mintlify 副标题不截断的实用上限），覆盖各页 H2 章节范围。
DESCRIPTION_OVERRIDES: dict[str, str] = {
    'voice-calls': "Make free, secure voice calls to contacts in DingTalk—no phone charges, HD audio with noise suppression, eavesdropping protection, and one-tap dialing from chats or profiles.",
    'meeting-ai': "DingTalk Meeting AI captures live captions and summaries during a meeting and auto-generates minutes and to-dos after the call, so participants never miss key remarks.",
    'start-or-schedule-meeting': "Two ways to launch a DingTalk video meeting: start an instant meeting for ad-hoc discussions, or schedule one in advance with a reminder and shareable join link.",
    'get-meeting-id': "Find or copy the 9-digit DingTalk meeting ID from the in-meeting toolbar, the meeting details card, or your scheduled meeting list—needed when inviting participants by number.",
    'invite-others': "Five ways to invite people to a DingTalk video meeting: chat group share, contact selector, meeting ID link, dial-out, and joining via the in-meeting participant list.",
    'join-meeting': "Join a DingTalk video meeting by tapping a chat invite, dialing the meeting ID, opening a calendar reminder, or scanning the QR code shown on the meeting host's screen.",
    'mute': "Mute and unmute your microphone in a DingTalk meeting using the toolbar button, the spacebar to push-to-talk, or host controls to mute/unmute participants.",
    'camera': "Turn the camera on or off mid-meeting, choose which camera to use, and adjust resolution—covers desktop, mobile, and meeting-room device flows.",
    'audio-mode': "Switch a video meeting to audio-only mode to save bandwidth on weak networks, dial in by phone, or join with audio while the camera stays off.",
    'share-screen': "Share your screen, a specific window, or just a region in a DingTalk meeting—includes annotation, audio sharing, and presenter handoff between participants.",
    'record-meeting': "Record a DingTalk video meeting to the cloud or locally—covers host permissions, participant notifications, automatic transcription, and post-meeting playback access.",
    'end-meeting': "End a DingTalk video meeting as host (closes for all participants) or leave a meeting as participant (others stay)—plus host transfer before leaving.",
    'switch-devices': "Move an in-progress meeting between desktop, mobile, and tablet without dropping the call, with seamless audio/video continuity and one-tap handover.",
    'switch-views': "Toggle between speaker view, gallery view, and presentation view in a DingTalk meeting to focus on the active speaker or see all participants at once.",
    'beauty-effects': "Apply beauty filters, makeup effects, and skin smoothing during a DingTalk video meeting—available on mobile and desktop with intensity controls.",
    'virtual-background': "Set a virtual background or blur effect in a DingTalk video meeting—built-in backgrounds, upload your own image, or replace with a static or video background.",
    'clearer-audio': "Improve meeting audio quality with noise cancellation, echo suppression, microphone selection, and earphone recommendations for the clearest possible call.",
    'waiting-room': "Use the DingTalk meeting waiting room to admit participants one by one, screen unknown joiners, and keep sensitive discussions private until the host is ready.",
    'prevent-unrelated': "Block unrelated people from joining a DingTalk meeting using meeting passwords, lobby controls, allowed-participant lists, and lock-meeting once everyone has joined.",
    'focus-participant': "Pin or unpin a single participant's video to the main stage for everyone, or only on your own view—useful for spotlighting the active speaker or presenter.",
    'host-cohost': "Assign meeting host or co-host roles to delegate participant management, mute controls, recording, and screen sharing permissions across one or more attendees.",
    'rename-in-meeting': "Change your display name during a DingTalk meeting on desktop or mobile—covers self-rename and host-driven rename of other participants.",
    'breakout-discussions': "Split a DingTalk meeting into smaller breakout rooms for parallel discussion, with host controls for room assignment, time limits, broadcasts, and re-merge.",
    'group-photo': "Capture a group photo of all video meeting participants with a single click—includes layout options, host permissions, and where the photo is saved.",
    'chat-emoji': "Send chat messages, emoji reactions, and animated gestures during a DingTalk meeting—covers visibility settings and how to react without unmuting.",
    'entitlements': "Check the current meeting's entitlements: participant cap, time limit, cloud recording quota, AI features, and how to upgrade for more capacity.",
    'captions': "Turn on live captions during a DingTalk meeting for real-time speech-to-text, with multilingual translation, font size controls, and caption history.",
    'track-attendance': "Generate a post-meeting attendance report listing who joined, when they joined and left, and total minutes attended—exportable to Excel for HR follow-up.",
    'ai-meeting-notes': "View AI-generated meeting notes (Meeting AI minutes, to-dos, and summaries) after a DingTalk video meeting, with share, edit, and export options.",
    'cannot-receive-meeting': "Troubleshoot why you cannot receive incoming DingTalk video meeting invites: notification settings, network status, app version, and Do Not Disturb checks.",
    'screen-sharing-no-audio': "Fix the common issue of no system audio during screen sharing on Mac and Windows—covers permission grants, audio device selection, and driver installation.",
    'video-abnormal': "Diagnose video glitches in DingTalk meetings: black screen, freezing frames, mirrored image, or wrong camera—with step-by-step fixes for desktop and mobile.",
    'audio-abnormal': "Resolve audio problems in DingTalk meetings: no sound, echo, robotic voice, low volume, or one-way audio—covers system audio settings and device selection.",
    'participants-and-fees': "Understand DingTalk Meeting participant caps, time limits, and fee structure across the free tier, paid plans, and enterprise editions.",
    'higher-definition': "Enable higher-definition video for DingTalk meetings when the default resolution looks blurry—covers bandwidth requirements and HD plan tiers.",
    'video-lag': "Fix video lag and stuttering in DingTalk meetings: check network speed, close bandwidth-heavy apps, switch to audio mode, and adjust video quality.",
    'network-check': "Run a network diagnostic in DingTalk to test bandwidth, latency, packet loss, and firewall connectivity before joining a critical meeting.",
    'camera-abnormal': "Fix camera problems in DingTalk meetings: not detected, permission denied, in use by another app, or showing an upside-down or distorted image.",
    'important-meeting': "Prepare for an important DingTalk meeting: pre-call network check, host backup plan, recording setup, and contingency for participant join issues.",
    'network-metrics': "Read in-meeting network metrics (bitrate, latency, packet loss, jitter) and understand which numbers indicate trouble for video, audio, or screen sharing.",
    'purchase-guide': "Two ways to purchase DingTalk Meetings plans: through the desktop app's Official Website link, or directly from the DingTalk Meetings purchase page—pick by participant count and duration.",
    'usage-guide': "How to activate and use a purchased DingTalk Meetings plan: assign the entitlement to the host account, enable HD video and cloud recording, and monitor usage.",
    'web-app-permissions': "Authorize the DingTalk Meetings web app to access microphone, camera, and screen sharing in Chrome, Edge, Safari, and Firefox—covers the permission prompts you'll see.",
    'web-iframe-integration': "Embed DingTalk Meetings in a web page via iframe: required postMessage events, allowed origins, sandbox attributes, and how to control the meeting from the parent page.",
}

# 44 篇 → 7 group
# 三元组: (slug, source_basename, expected_title_after_strip_prefix)
# source_basename 相对源根目录
# expected_title 用「剥编号 + 剥 emoji 后」的 H1 字面值
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('Get Started', [
        ('voice-calls', 'Voice Calls.adoc.md', 'Voice Calls'),
        ('meeting-ai', 'DingTalk Meetings/Meeting AI.adoc.md', 'Meeting AI'),
    ]),
    ('Start and Join', [
        ('start-or-schedule-meeting',
         'DingTalk Meetings/1. Start and Join - 1.1 How to Start or Schedule a Video Meeting_.adoc.md',
         'How to Start or Schedule a Video Meeting?'),
        ('get-meeting-id',
         'DingTalk Meetings/1. Start and Join - 1.2 How to Get the Meeting ID_.adoc.md',
         'How to Get the Meeting ID?'),
        ('invite-others',
         'DingTalk Meetings/1. Start and Join - 1.3 How to Invite Others to a Video Meeting_.adoc.md',
         'How to Invite Others to a Video Meeting?'),
        ('join-meeting',
         'DingTalk Meetings/1. Start and Join - 1.4 How to Join a Video Meeting_.adoc.md',
         'How to Join a Video Meeting?'),
    ]),
    ('During a Meeting', [
        ('mute',
         'DingTalk Meetings/2. During a Meeting - 2.1 How to Turn Mute On or Off_.adoc.md',
         'How to Turn Mute On or Off?'),
        ('camera',
         'DingTalk Meetings/2. During a Meeting - 2.2 How to Turn the Camera On or Off_.adoc.md',
         'How to Turn the Camera On or Off?'),
        ('audio-mode',
         'DingTalk Meetings/2. During a Meeting - 2.3 How to Turn On Audio Mode_.adoc.md',
         'How to Turn On Audio Mode?'),
        ('share-screen',
         'DingTalk Meetings/2. During a Meeting - 2.4 How to Share Your Screen_.adoc.md',
         'How to Share Your Screen?'),
        ('record-meeting',
         'DingTalk Meetings/2. During a Meeting - 2.5 How to Record a Video Meeting_.adoc.md',
         'How to Record a Video Meeting?'),
        ('end-meeting',
         'DingTalk Meetings/2. During a Meeting - 2.6 How to End a Video Meeting_.adoc.md',
         'How to End a Video Meeting?'),
        ('switch-devices',
         'DingTalk Meetings/2. During a Meeting - 2.7 How to Switch Between Devices_.adoc.md',
         'How to Switch Between Devices?'),
        ('switch-views',
         'DingTalk Meetings/2. During a Meeting - 2.8 How to Switch Views_.adoc.md',
         'How to Switch Views?'),
        ('beauty-effects',
         'DingTalk Meetings/2. During a Meeting - 2.9 How to Turn On Beauty Effects_.adoc.md',
         'How to Turn On Beauty Effects?'),
        ('virtual-background',
         'DingTalk Meetings/2. During a Meeting - 2.10 How to Set a Virtual Background_.adoc.md',
         'How to Set a Virtual Background?'),
        ('clearer-audio',
         'DingTalk Meetings/2. During a Meeting - 2.11 How to Make Meeting Audio Clearer_.adoc.md',
         'How to Make Meeting Audio Clearer?'),
        ('waiting-room',
         'DingTalk Meetings/2. During a Meeting - 2.12 Meeting Security - How to Use the Waiting Room_.adoc.md',
         'How to Use the Waiting Room?'),
        ('prevent-unrelated',
         'DingTalk Meetings/2. During a Meeting - 2.12 Meeting Security - How to Prevent Unrelated People from Joining a Meeting_.adoc.md',
         'How to Prevent Unrelated People from Joining a Meeting?'),
        ('focus-participant',
         'DingTalk Meetings/2. During a Meeting - 2.13 Manage Participants - How to Set or Cancel Focus on One Participant_.adoc.md',
         'How to Set or Cancel Focus on One Participant?'),
        ('host-cohost',
         'DingTalk Meetings/2. During a Meeting - 2.13 Manage Participants - How to Set a Meeting Host or Co-host.adoc.md',
         'How to Set a Meeting Host or Co-host'),
        ('rename-in-meeting',
         'DingTalk Meetings/2. During a Meeting - 2.14 How to Rename Yourself During a Meeting_.adoc.md',
         'How to Rename Yourself During a Meeting?'),
        ('breakout-discussions',
         'DingTalk Meetings/2. During a Meeting - 2.15 How to Use Breakout Discussions_.adoc.md',
         'How to Use Breakout Discussions?'),
        ('group-photo',
         'DingTalk Meetings/2. During a Meeting - 2.16 How to Take a Group Photo_.adoc.md',
         'How to Take a Group Photo?'),
        ('chat-emoji',
         'DingTalk Meetings/2. During a Meeting - 2.17 In-meeting Chat and Emoji Interaction.adoc.md',
         'In-meeting Chat and Emoji Interaction'),
        ('entitlements',
         'DingTalk Meetings/2. During a Meeting - 2.18 How to View Current Meeting Entitlements.adoc.md',
         'How to View Current Meeting Entitlements'),
        ('captions',
         'DingTalk Meetings/2. During a Meeting - 2.19 How to Use Captions_.adoc.md',
         'How to Use Captions?'),
    ]),
    ('After the Meeting', [
        ('track-attendance',
         'DingTalk Meetings/3. After the Meeting - 3.1 How to Track Attendance_.adoc.md',
         'How to Track Attendance?'),
        ('ai-meeting-notes',
         'DingTalk Meetings/3. After the Meeting - 3.2 How to View AI Meeting Notes_.adoc.md',
         'How to View AI Meeting Notes?'),
    ]),
    ('Troubleshooting', [
        ('cannot-receive-meeting',
         'DingTalk Meetings/4. Troubleshooting - 4.1 What to Do If You Cannot Receive a Video Meeting_.adoc.md',
         'What to Do If You Cannot Receive a Video Meeting?'),
        ('screen-sharing-no-audio',
         'DingTalk Meetings/4. Troubleshooting - 4.2 What If Screen Sharing Has No Computer Audio_.adoc.md',
         'What If Screen Sharing Has No Computer Audio?'),
        ('video-abnormal',
         'DingTalk Meetings/4. Troubleshooting - 4.3 What to Do If Video Is Abnormal During a Meeting_.adoc.md',
         'What to Do If Video Is Abnormal During a Meeting?'),
        ('audio-abnormal',
         'DingTalk Meetings/4. Troubleshooting - 4.4 What to Do If Audio Is Abnormal During a Video Meeting_.adoc.md',
         'What to Do If Audio Is Abnormal During a Video Meeting?'),
        ('participants-and-fees',
         'DingTalk Meetings/4. Troubleshooting - 4.5 Video Meeting Participants and Fees.adoc.md',
         'Video Meeting Participants and Fees'),
        ('higher-definition',
         'DingTalk Meetings/4. Troubleshooting - 4.6 Is Higher Definition Supported If the Video Is Not Clear_.adoc.md',
         'Is Higher Definition Supported If the Video Is Not Clear?'),
        ('video-lag',
         'DingTalk Meetings/4. Troubleshooting - 4.7 Video Meeting Lag.adoc.md',
         'Video Meeting Lag'),
        ('network-check',
         'DingTalk Meetings/4. Troubleshooting - 4.8 How to Check Whether the Network Is Smooth.adoc.md',
         'How to Check Whether the Network Is Smooth'),
        ('camera-abnormal',
         'DingTalk Meetings/4. Troubleshooting - 4.9 What to Do If the Camera Image Is Abnormal.adoc.md',
         'What to Do If the Camera Image Is Abnormal'),
        ('important-meeting',
         'DingTalk Meetings/4. Troubleshooting - 4.10 How to Support an Important Meeting.adoc.md',
         'How to Support an Important Meeting'),
        ('network-metrics',
         'DingTalk Meetings/4. Troubleshooting - 4.11 How to View and Understand Network Metrics.adoc.md',
         'How to View and Understand Network Metrics'),
    ]),
    ('Purchase Guide', [
        ('purchase-guide',
         'DingTalk Meetings/5. Purchase Guide - 5.1 Purchase Guide.adoc.md',
         'Purchase Guide'),
        ('usage-guide',
         'DingTalk Meetings/5. Purchase Guide - 5.2 Usage Guide.adoc.md',
         'Usage Guide'),
    ]),
    ('Web Meeting User Guide', [
        ('web-app-permissions',
         'DingTalk Meetings/6. Web Meeting User Guide - 6.1 Authorize the DingTalk Meetings Web App to Use Microphone, Camera, and Screen Sharing.adoc.md',
         'Authorize the DingTalk Meetings Web App to Use Microphone, Camera, and Screen Sharing'),
        ('web-iframe-integration',
         'DingTalk Meetings/6. Web Meeting User Guide - 6.2 DingTalk Meetings Web iframe Integration Guide.adoc.md',
         'DingTalk Meetings Web iframe Integration Guide'),
    ]),
]


def clean_invisible(text: str) -> str:
    def repl(m: re.Match) -> str:
        return ' ' if m.group(0) == '\xa0' else ''
    return INVISIBLE_CHARS_RE.sub(repl, text)


def strip_numbered_prefix(title: str) -> str:
    """剥 H1 编号前缀 `1.1 ` / `2.12 ` 等，保留无编号 title 原样。"""
    return NUMBERED_PREFIX_RE.sub('', title).strip()


def strip_dup_leading_h1(body: str, parsed_title: str) -> str:
    """剥 body 开头与 parsed_title 重复的 H1（钉钉文档导出常见，6/44 EN 文件命中 line-1+3 同 H1）。"""
    m = LEADING_H1_RE.match(body)
    if m and m.group(1).strip() == parsed_title.strip():
        return body[m.end():].lstrip()
    return body


def strip_trailing_original_title(body: str) -> str:
    """剥 body 末尾钉钉翻译版 export 脚本痕迹（44/44 EN 文件命中）。"""
    return TRAILING_ORIGINAL_TITLE_RE.sub('', body)


def demote_body_h1(body: str) -> str:
    """把 body 内所有正文 H1 (`# Title`) 降级为 H2 (`## Title`)；跳过代码块内的 `# ...`。
    Mintlify 把 frontmatter.title 视为唯一 H1，正文 H1 会导致重复 + 层级跳跃。
    """
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
    cleaned = strip_trailing_original_title(cleaned)  # 必须在 parse_frontmatter_data 之前剥
    parsed_title, _orig_desc, body = parse_frontmatter_data(cleaned, source.stem)
    body = strip_dup_leading_h1(body, parsed_title)
    body = demote_body_h1(body)

    cleaned_title = strip_numbered_prefix(parsed_title)
    title = TITLE_OVERRIDES.get(expected_slug) or cleaned_title or expected_title
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
        'tab': 'Meetings',
        'groups': [
            {
                'group': group_name,
                'pages': [f'meetings/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Meetings EN markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-06-15_DingTalk_Meetings_EN/)')
    ap.add_argument('--dry-run', action='store_true', help='不写文件，只打印总结')
    args = ap.parse_args()

    source_dir = Path(args.source).expanduser().resolve()
    if not source_dir.exists():
        print(f'❌ 源目录不存在: {source_dir}', file=sys.stderr)
        return 1

    print(f'源: {source_dir}')
    print(f'目标: {MEETINGS_DIR}')
    print(f'dry-run: {args.dry_run}')
    print('=' * 70)

    if not args.dry_run:
        MEETINGS_DIR.mkdir(exist_ok=True)
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
                print(f'  {slug:<28} ❌ 未找到源 (期望 {source_basename})')
                continue
            try:
                info = process_one(src, slug, expected_title)
            except Exception as e:
                print(f'  {slug:<28} ❌ {type(e).__name__}: {e}')
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
            print(f'  {slug:<28} {marker} {info["mdx_size"]} bytes (NBSP={info["nbsp_before"]})')

            if not args.dry_run:
                target = MEETINGS_DIR / f'{slug}.mdx'
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
            '# Meetings EN Import Report\n',
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
        print(f'  mdx:               {MEETINGS_DIR}/*.mdx ({len(report_rows)} 个)')
        print(f'  nav-fragment.json: {OUTPUT_DIR}/nav-fragment.json')
        print(f'  slug-map.json:     {OUTPUT_DIR}/slug-map.json')
        print(f'  report.md:         {OUTPUT_DIR}/report.md')

    if missing or total_residual_nbsp > 0:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
