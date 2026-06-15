#!/usr/bin/env python3
"""import_meetings_zh.py — 把 ~/Downloads/<date>_DingTalk_Meetings_ZH/*.adoc.md → zh/meetings/<slug>.mdx。

仿 import_meetings_en.py，差异：
- 输出到 zh/meetings/，tab 名 '音视频'，group 名按 ZH hub 章节结构
- ZH 没有"Original title + Source" 翻译版痕迹（ZH 是原版），删 TRAILING_ORIGINAL_TITLE_RE
- ZH 含大量 `:::` 容器（40/44 命中，钉钉文档 callout 新格式），加 strip_admonition_markers
- ZH body 末尾常有 "▍﻿返回「[**XXX**](alidocs)」目录" 段（42/44 命中，hub 子集型母文档跳转链）→ 加 TRAILING_BACK_TO_RE
- ZH 部分文件 H1 含 ✅ emoji 装饰（4/44 命中 2.12/2.13 子文档），加 strip_emoji_prefix
- 同样剥编号前缀 + dup leading H1 + demote body H1

用法:
    python3 scripts/import_meetings_zh.py
    python3 scripts/import_meetings_zh.py --source <path>
    python3 scripts/import_meetings_zh.py --dry-run

产物:
  - zh/meetings/<slug>.mdx × 44
  - scripts/output/meetings_zh/{nav-fragment.json, slug-map.json, report.md}
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

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-06-15_DingTalk_Meetings_ZH'
MEETINGS_DIR = REPO_ROOT / 'zh' / 'meetings'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'meetings_zh'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿]')
LEADING_H1_RE = re.compile(r'\A# (.+?)\n')
ADMONITION_MARKER_RE = re.compile(r'^:::\s*$', re.MULTILINE)
# body 中"返回「[**XXX**](alidocs)」目录" + 后续"关注我们 + 公众号二维码图"社交媒体推广段
# 钉钉文档源在每个 H2 章节末尾嵌入推广块；从前导 `---` 分隔线开始到下一个 `##` 章节或文件末尾，全部剥掉
# 末尾 + 中段共 35 处命中
SOCIAL_PROMO_RE = re.compile(
    r'\n+---\s*\n+\s*▍?\s*返回[^\n]*目录[^\n]*(?:\n(?!##\s)[^\n]*)*',
    re.MULTILINE,
)
# 部分文件 "[爱心] 关注我们" 推广段无前导 `---` 分隔线（1/44 命中：web-app-permissions），单独处理
SOCIAL_PROMO_HEART_RE = re.compile(
    r'\n+\s*\[爱心\]\s*关注我们[^\n]*(?:\n(?!##\s)[^\n]*)*',
    re.MULTILINE,
)
# H1 编号前缀：`1.1 ` / `2.12 ` / `6.2 ` 等
NUMBERED_PREFIX_RE = re.compile(r'^\d+(?:\.\d+)?\s+')
# body heading 编号前缀：钉钉源 `### 1.1 为什么...` / `## 2.5 ...`，剥编号让 body 与 frontmatter title 一致
BODY_HEADING_NUMBERED_RE = re.compile(r'^(#+)\s+\d+(?:\.\d+)?\s+(.+)$', re.MULTILINE)
# 紧贴粗体不闭合：`**X：**Y` mintlify 不识别紧贴 `：` 的闭合 → 改 `**X**：Y`（冒号移外）
PUNCT_CLOSE_BOLD_RE = re.compile(r'\*\*([^*\n]+?)([:：])\*\*(?=\S)')
# H1 emoji 装饰前缀：钉钉编辑器 ✅⭐🌟🎯💻💼📱📅📌🔔📢 等装饰 emoji，剥后让 title 干净
EMOJI_PREFIX_RE = re.compile(r'^[✅⭐🌟🎯💻💼📱📅📌🔔📢]+\s*')
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')
MD_LIST_PREFIX_RE = re.compile(r'^\s*(?:\d+[.)]|[-*+])\s+')

# slug title 强制覆盖（避免与所在 group 同名）
TITLE_OVERRIDES: dict[str, str] = {}

# alidocs 跨页引用 label 文字 → 本仓内链 slug 映射
# 仅本仓有对应 slug 的 alidocs URL 转内链；其他外链（如「立即咨询」表单、跨产品引用「共享文档」）保留外链
# label 形态包括：带编号 "1.1 ..."/带书名号 "《2.5 ...》"/带 ++装饰 "++X++"/裸 label
# clean_label 去掉 +/《》/* 装饰后做 dict 查询，命中 → 改 /zh/meetings/<slug>
ALIDOCS_LABEL_TO_SLUG: dict[str, str] = {
    '如何发起/预约视频会议？': 'start-or-schedule-meeting',
    '如何发起/预约会议？': 'start-or-schedule-meeting',   # 带 ++ 装饰的简称变体
    '1.1 如何发起/预约视频会议？': 'start-or-schedule-meeting',
    '如何使用等候室功能？': 'waiting-room',
    '如何处理摄像头画面异常的问题': 'camera-abnormal',
    '4.9 如何处理摄像头画面异常的问题': 'camera-abnormal',
    '2.20 如何使用字幕？': 'captions',                     # 源 typo 编号（实际是 2.19）
    '2.4 如何开启共享屏幕？': 'share-screen',
    '2.5 如何录制视频会议？': 'record-meeting',
    '2.8 如何切换视图？': 'switch-views',
    '4.4 如何处理视频会议中的声音异常问题？': 'audio-abnormal',
    # `2.12 如何保障会议安全？` 本仓无单一对应（hub 母文档 dead-end，下含 waiting-room + prevent-unrelated）→ 保留外链让 audit-mdx 判
    # `了解详情` / `立即咨询` / `**如何使用共享文档？**` / `钉钉相关域名和IP列表` 均仓库外，保留外链
}

ALIDOCS_LINK_LABEL_RE = re.compile(
    r'\[([^\]]+?)\]\(https://alidocs\.dingtalk\.com[^)]+\)'
)

# frontmatter description 手写覆盖（< 200 chars，覆盖各页 H2 章节范围）
DESCRIPTION_OVERRIDES: dict[str, str] = {
    'voice-calls': "在钉钉中与联系人免费拨打语音通话：HD 音质、防窃听、噪声抑制，无话费成本，可从聊天或联系人面板一键发起。",
    'meeting-ai': "钉钉会议 AI 实时记录会议字幕和总结，会议结束后自动生成纪要与待办，参会人无需手动记笔记。",
    'start-or-schedule-meeting': "钉钉会议提供「发起会议」与「预约会议」两种方式：临时会议立即开始，预约会议可提前预定时间并设置提醒、共享加入链接。",
    'get-meeting-id': "查看与复制 9 位钉钉会议号：从会中工具栏、会议详情卡片或我的预约列表获取，邀请他人加入时按编号填写。",
    'invite-others': "5 种方式邀请他人参加视频会议：聊天群分享、联系人选择器、会议号链接、外拨电话、会中参与者列表加入。",
    'join-meeting': "4 种方式加入视频会议：点击聊天邀请、输入会议号、打开日历提醒、扫描主持人屏幕上的二维码。",
    'mute': "在会中开启 / 关闭麦克风静音：用工具栏按钮、空格键按住说话、主持人静音/取消静音参与者控制。",
    'camera': "会中开启 / 关闭摄像头、选择使用哪个摄像头、调整分辨率，适配电脑、手机、会议室设备多端。",
    'audio-mode': "将视频会议切到纯音频模式以节省弱网带宽：可电话拨入加入、或仅以语音方式参会而保持摄像头关闭。",
    'share-screen': "会中共享整个屏幕、单个窗口或局部区域，支持注释、共享音频、主讲人在参与者间切换。",
    'record-meeting': "云录制或本地录制视频会议：主持人权限、参会者通知、自动转写、会后回放访问权限说明。",
    'end-meeting': "作为主持人结束会议（对全员关闭）或作为参与者离开会议（其他人继续），含主持权转交。",
    'switch-devices': "会议进行中在电脑、手机、平板间无缝切换设备，音视频不掉线、一键交接。",
    'switch-views': "在演讲者视图、画廊视图、演示视图之间切换，聚焦当前发言人或一次性看全员。",
    'beauty-effects': "视频会议中开启美颜滤镜、美妆效果、磨皮，桌面与移动端均支持，效果强度可调。",
    'virtual-background': "会中设置虚拟背景或模糊效果：内置背景、上传自定义图片、替换静态或视频背景。",
    'clearer-audio': "通过噪声消除、回声抑制、麦克风选择、耳机推荐改善会议音质，让通话最大化清晰。",
    'waiting-room': "用钉钉会议等候室一一审核进入的参会者，筛掉陌生加入者，敏感讨论开始前由主持人控制入场。",
    'prevent-unrelated': "通过会议密码、大厅控制、允许参会人列表、全员加入后锁定会议，阻止无关人员加入。",
    'focus-participant': "把单个参与者视频固定在主视图，对全员可见或仅对自己可见，用于聚焦当前发言人或演讲者。",
    'host-cohost': "分配会议主持人或联席主持人角色，委托管理参与者、静音控制、录制、屏幕共享权限。",
    'rename-in-meeting': "桌面或移动端在会中修改自己的显示名称，主持人也可修改其他参与者名称。",
    'breakout-discussions': "将会议拆分为多个小型分组讨论室进行平行讨论，主持人可控制分配、时长、广播、再合并。",
    'group-photo': "一键拍下全员视频参会的合影，含布局选项、主持人权限、照片保存位置。",
    'chat-emoji': "会中发送聊天消息、表情反应、动态手势互动，含可见性设置、无需取消静音即可反应。",
    'entitlements': "查看当前会议权益：参会人数上限、时长限制、云录制配额、AI 功能、升级扩容入口。",
    'captions': "会中开启实时字幕做语音转文字，含多语言翻译、字号控制、字幕历史记录回看。",
    'track-attendance': "会后生成参会统计报表：加入时间、离开时间、累计时长，可导出 Excel 用于 HR 跟进。",
    'ai-meeting-notes': "会后查看 AI 听记自动生成的会议纪要、待办、总结，可分享、编辑、导出。",
    'cannot-receive-meeting': "排查无法收到视频会议邀请：通知设置、网络状态、 App 版本、勿扰模式检查。",
    'screen-sharing-no-audio': "解决 Mac 和 Windows 共享屏幕时无系统声音的常见问题：权限授予、音频设备选择、驱动安装。",
    'video-abnormal': "诊断会议中视频画面异常：黑屏、卡帧、画面镜像、用错摄像头等，含桌面与移动端逐步修复。",
    'audio-abnormal': "排查会议声音问题：无声、回声、机器人声、音量低、单向音频，含系统音频设置与设备选择。",
    'participants-and-fees': "理解钉钉会议参会人数上限、时长限制、收费结构：免费版、付费版、企业版差异。",
    'higher-definition': "默认分辨率不清晰时如何开启高清视频：带宽要求、高清套餐档位说明。",
    'video-lag': "修复会议中视频画面卡顿：检查网速、关闭高带宽应用、切换音频模式、调整视频质量。",
    'network-check': "在钉钉中跑网络诊断：测带宽、延迟、丢包率、防火墙连通性，重要会议加入前先检查。",
    'camera-abnormal': "修复会议摄像头问题：未检测到、权限被拒、被其他 App 占用、画面倒置或变形。",
    'important-meeting': "准备一场重要会议：会前网络检查、主持人备份、录制方案、参会人加入异常的应急预案。",
    'network-metrics': "看懂会中网络指标（码率、延迟、丢包、抖动），知道哪些数值预示视频、音频、共享屏幕出问题。",
    'purchase-guide': "两种方式购买钉钉会议套餐：从桌面客户端「官网」入口下单、或直接打开钉钉会议购买页，按参会人数和时长档位选择。",
    'usage-guide': "已购套餐的激活与使用：把权益分配到主持人账号、开启高清与云录制、查看用量。",
    'web-app-permissions': "在 Chrome、Edge、Safari、Firefox 中授权钉钉会议网页版访问麦克风、摄像头、屏幕共享，含各浏览器权限弹窗说明。",
    'web-iframe-integration': "通过 iframe 将钉钉会议嵌入网页：必要的 postMessage 事件、允许的 origin、sandbox 属性、从父页面控制会议。",
}

# 44 篇 → 7 group（与 EN 完全对称）
# 三元组: (slug, source_basename, expected_title_after_strip_prefix)
# expected_title 用「剥编号 + 剥 emoji 后」的 H1 字面值
GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ('开始使用', [
        ('voice-calls', '语音通话.adoc.md', '语音通话'),
        ('meeting-ai', '钉钉会议.adoc/会议AI.adoc.md', '会议AI'),
    ]),
    ('发起和加入', [
        ('start-or-schedule-meeting',
         '钉钉会议.adoc/1. 发起和加入.adoc - 1.1 如何发起_预约视频会议？.adoc.md',
         '如何发起/预约视频会议？'),
        ('get-meeting-id',
         '钉钉会议.adoc/1. 发起和加入.adoc - 1.2 如何获取会议号？.adoc.md',
         '如何获取会议号？'),
        ('invite-others',
         '钉钉会议.adoc/1. 发起和加入.adoc - 1.3 如何邀请他人参加视频会议？.adoc.md',
         '如何邀请他人参加视频会议？'),
        ('join-meeting',
         '钉钉会议.adoc/1. 发起和加入.adoc - 1.4 如何加入视频会议？.adoc.md',
         '如何加入视频会议？'),
    ]),
    ('会议过程中', [
        ('mute',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.1 如何开启_关闭静音？.adoc.md',
         '如何开启/关闭静音？'),
        ('camera',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.2 如何开启_关闭摄像头？.adoc.md',
         '如何开启/关闭摄像头？'),
        ('audio-mode',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.3 如何开启语音模式？.adoc.md',
         '如何开启语音模式？'),
        ('share-screen',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.4 如何开启共享屏幕？.adoc.md',
         '如何开启共享屏幕？'),
        ('record-meeting',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.5 如何录制视频会议？.adoc.md',
         '如何录制视频会议？'),
        ('end-meeting',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.6 如何结束视频会议？.adoc.md',
         '如何结束视频会议？'),
        ('switch-devices',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.7 如何实现多端切换？.adoc.md',
         '如何实现多端切换？'),
        ('switch-views',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.8 如何切换视图？.adoc.md',
         '如何切换视图？'),
        ('beauty-effects',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.9 如何开启美颜功能？.adoc.md',
         '如何开启美颜功能？'),
        ('virtual-background',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.10 如何设置虚拟背景？.adoc.md',
         '如何设置虚拟背景？'),
        ('clearer-audio',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.11 如何让会议声音更清晰？.adoc.md',
         '如何让会议声音更清晰？'),
        ('waiting-room',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.12 如何保障会议安全？.adoc - ✅如何使用等候室功能？.adoc.md',
         '如何使用等候室功能？'),
        ('prevent-unrelated',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.12 如何保障会议安全？.adoc - ✅如何防止无关人员进入会议？.adoc.md',
         '如何防止无关人员进入会议？'),
        ('focus-participant',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.13 如何管理参会成员？.adoc - ✅如何设置_取消全员看TA？.adoc.md',
         '如何设置/取消全员看TA？'),
        ('host-cohost',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.13 如何管理参会成员？.adoc - ✅如何设置会议主持人_联席主持人.adoc.md',
         '如何设置会议主持人/联席主持人'),
        ('rename-in-meeting',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.14 会中如何改名？.adoc.md',
         '会中如何改名？'),
        ('breakout-discussions',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.15 如何进行分组讨论？.adoc.md',
         '如何进行分组讨论？'),
        ('group-photo',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.16 如何全员合影？.adoc.md',
         '如何全员合影？'),
        ('chat-emoji',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.17 会中聊天和表情互动.adoc.md',
         '会中聊天和表情互动'),
        ('entitlements',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.18 如何查看当前会议的权益.adoc.md',
         '如何查看当前会议的权益'),
        ('captions',
         '钉钉会议.adoc/2. 会议过程中.adoc - 2.19 如何使用字幕？.adoc.md',
         '如何使用字幕？'),
    ]),
    ('会后回顾', [
        ('track-attendance',
         '钉钉会议.adoc/3. 会后回顾.adoc - 3.1 如何统计参会情况？.adoc.md',
         '如何统计参会情况？'),
        ('ai-meeting-notes',
         '钉钉会议.adoc/3. 会后回顾.adoc - 3.2 如何查看AI听记内容？.adoc.md',
         '如何查看AI听记内容？'),
    ]),
    ('问题排查', [
        ('cannot-receive-meeting',
         '钉钉会议.adoc/4. 问题排查.adoc - 4.1 如何处理无法收到视频会议的问题？.adoc.md',
         '如何处理无法收到视频会议的问题？'),
        ('screen-sharing-no-audio',
         '钉钉会议.adoc/4. 问题排查.adoc - 4.2 如何处理共享屏幕时没有电脑声音的问题？.adoc.md',
         '如何处理共享屏幕时没有电脑声音的问题？'),
        ('video-abnormal',
         '钉钉会议.adoc/4. 问题排查.adoc - 4.3 如何处理视频会议中的画面异常问题？.adoc.md',
         '如何处理视频会议中的画面异常问题？'),
        ('audio-abnormal',
         '钉钉会议.adoc/4. 问题排查.adoc - 4.4 如何处理视频会议中的声音异常问题？.adoc.md',
         '如何处理视频会议中的声音异常问题？'),
        ('participants-and-fees',
         '钉钉会议.adoc/4. 问题排查.adoc - 4.5 视频会议人数_费用问题（链接需修改）.adoc.md',
         '视频会议人数/费用问题（链接需修改）'),
        ('higher-definition',
         '钉钉会议.adoc/4. 问题排查.adoc - 4.6 画面不清晰，是否支持更高清晰度？.adoc.md',
         '画面不清晰，是否支持更高清晰度？'),
        ('video-lag',
         '钉钉会议.adoc/4. 问题排查.adoc - 4.7 视频会议画面卡顿.adoc.md',
         '视频会议画面卡顿'),
        ('network-check',
         '钉钉会议.adoc/4. 问题排查.adoc - 4.8 如何检测网络是否顺畅.adoc.md',
         '如何检测网络是否顺畅'),
        ('camera-abnormal',
         '钉钉会议.adoc/4. 问题排查.adoc - 4.9 如何处理摄像头画面异常的问题.adoc.md',
         '如何处理摄像头画面异常的问题'),
        ('important-meeting',
         '钉钉会议.adoc/4. 问题排查.adoc - 4.10 如何保障一场重要会议？.adoc.md',
         '如何保障一场重要会议？'),
        ('network-metrics',
         '钉钉会议.adoc/4. 问题排查.adoc - 4.11 如何查看和理解网络指标.adoc.md',
         '如何查看和理解网络指标'),
    ]),
    ('购买指南', [
        ('purchase-guide',
         '钉钉会议.adoc/5. 购买指南.adoc - 6.2 购买指引.adoc.md',
         '购买指引'),
        ('usage-guide',
         '钉钉会议.adoc/5. 购买指南.adoc - 6.3 使用指引.adoc.md',
         '使用指引'),
    ]),
    ('网页会议使用指南', [
        ('web-app-permissions',
         '钉钉会议.adoc/6. 网页会议使用指南.adoc - 授权钉钉会议网页端打开麦克风、摄像头和屏幕共享.adoc.md',
         '授权钉钉会议网页端打开麦克风、摄像头和屏幕共享'),
        ('web-iframe-integration',
         '钉钉会议.adoc/6. 网页会议使用指南.adoc - 钉钉会议网页端iframe集成指南.adoc.md',
         '钉钉会议网页端iframe集成指南'),
    ]),
]


def clean_invisible(text: str) -> str:
    def repl(m: re.Match) -> str:
        return ' ' if m.group(0) == '\xa0' else ''
    return INVISIBLE_CHARS_RE.sub(repl, text)


def clean_title(title: str) -> str:
    """剥 H1 装饰前缀：emoji + 编号。保留无前缀 title 原样。"""
    title = EMOJI_PREFIX_RE.sub('', title)
    title = NUMBERED_PREFIX_RE.sub('', title)
    return title.strip()


def strip_dup_leading_h1(body: str, parsed_title: str) -> str:
    """剥 body 开头与 parsed_title 重复的 H1（防御性保留）。"""
    m = LEADING_H1_RE.match(body)
    if m and m.group(1).strip() == parsed_title.strip():
        return body[m.end():].lstrip()
    return body


def strip_admonition_markers(body: str) -> str:
    """剥单独成行的 `:::`（钉钉文档 callout 容器，MDX 不识别；40/44 ZH 命中）。"""
    return ADMONITION_MARKER_RE.sub('', body)


def strip_trailing_back_to(body: str) -> str:
    """剥 body 中"返回「[**XXX**](alidocs)」目录" + 后续社交媒体推广段（35+ 处命中，含中段嵌入式）。"""
    body = SOCIAL_PROMO_RE.sub('', body)
    body = SOCIAL_PROMO_HEART_RE.sub('', body)
    return body


def demote_body_h1(body: str) -> str:
    """把 body 内所有正文 H1 (`# Title`) 降级为 H2 (`## Title`)；跳过代码块内的 `# ...`。"""
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


def strip_numbered_prefix_in_headings(body: str) -> str:
    """剥 body 内所有 heading 的编号前缀 `### 1.1 为什么...` → `### 为什么...`。
    与 frontmatter title 的 clean_title 一致；ZH 7 处命中（video-abnormal 5+ 其他）。"""
    return BODY_HEADING_NUMBERED_RE.sub(r'\1 \2', body)


def fix_punct_close_bold(body: str) -> str:
    """`**X：**Y` 紧贴粗体不闭合 → `**X**：Y`（冒号移外）。
    钉钉源里 `**免话费：**不需要付费` 这种 `：**` 闭合后紧贴正文文字，mintlify 不识别为 bold 闭合，
    渲染成字面 `**X：**`。把冒号挪到 `**` 外面让闭合明确，渲染正常加粗。voice-calls 5+ 处 + 其他多处。"""
    return PUNCT_CLOSE_BOLD_RE.sub(r'**\1**\2', body)


def rewrite_alidocs_internal_links(body: str) -> str:
    """label 文字命中 ALIDOCS_LABEL_TO_SLUG → 改本仓内链 /zh/meetings/<slug>；不命中保留外链。
    label 形态多样（裸 label / 带编号 / 带 ++装饰 / 带书名号 / 带 **粗体**），用 strip 剥装饰后查 dict。
    10 处 ZH alidocs 内链命中（invite-others 2 / beauty-effects 1 / virtual-background 1 / video-abnormal 1 / important-meeting 4 / share-screen 1 / ai-meeting-notes 1）。"""
    def repl(m: re.Match) -> str:
        raw_label = m.group(1)
        clean = raw_label.strip().lstrip('+').rstrip('+').strip('《》').strip('*').strip()
        slug = ALIDOCS_LABEL_TO_SLUG.get(clean)
        if slug:
            return f'[{raw_label}](/zh/meetings/{slug})'
        return m.group(0)
    return ALIDOCS_LINK_LABEL_RE.sub(repl, body)


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
    body = rewrite_alidocs_internal_links(body)
    body = demote_body_h1(body)
    body = strip_numbered_prefix_in_headings(body)
    body = fix_punct_close_bold(body)

    cleaned_title = clean_title(parsed_title)
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
        'tab': '音视频',
        'groups': [
            {
                'group': group_name,
                'pages': [f'zh/meetings/{slug}' for (slug, _src, _title) in items],
            }
            for group_name, items in GROUPS
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='音视频 ZH markdown → mdx 入库')
    ap.add_argument('--source', default=str(DEFAULT_SOURCE),
                    help='源目录 (默认 ~/Downloads/2026-06-15_DingTalk_Meetings_ZH/)')
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
        MEETINGS_DIR.mkdir(parents=True, exist_ok=True)
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
            '# 音视频 ZH Import Report\n',
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
