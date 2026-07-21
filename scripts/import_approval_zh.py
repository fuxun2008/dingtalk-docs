#!/usr/bin/env python3
"""import_approval_zh.py — 把 ~/Downloads/2026-07-20_DingTalk_approval/ 保留范围 → zh/approval/<slug>.mdx。

范围（第一期）：仅核心基础版 36 篇（排除增值能力/旧版操作手册/客户案例）。TOC 纯目录页不入仓。
产品名 OA审批 → 审批。复用考勤（attendance）整套清洗流水线。
处理（含考勤 2026-07-20 QA 走查 8 类修复）：
  - 剥促销块「预约钉钉服务专家」+「返回「X」目录页」尾链（含无链接形态）+ 已失链的「点击此处」括号句
  - `\\>` 反转义 + CJK 粗体边界修复（防 ** 外露）
  - 图片/表格/答句 dedent 独占一行；图片包 <Frame caption>
  - `## 问：` FAQ → <AccordionGroup>/<Accordion>；长句步骤标题 → <Steps>/<Step>
  - :::→<Note> 组件化；内链标题匹配转换/外链转纯文字；标题层级栈规整
  - frontmatter 标题简化（SHORT_TITLES）；FAQ 页 description 由问题列表生成

用法:
    python3 scripts/import_approval_zh.py --dry-run   # 看 skip/import 清单
    python3 scripts/import_approval_zh.py             # 正式写入

产物:
  - zh/approval/<slug>.mdx
  - scripts/output/approval_zh/{nav-fragment.json, slug-map.json, import-report.md}
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import sys
import unicodedata
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
from import_archive import escape_mdx, parse_frontmatter_data, yaml_escape  # noqa: E402

DEFAULT_SOURCE = Path.home() / 'Downloads' / '2026-07-20_DingTalk_approval'
ATT_DIR = REPO_ROOT / 'zh' / 'approval'
OUTPUT_DIR = REPO_ROOT / 'scripts' / 'output' / 'approval_zh'

INVISIBLE_CHARS_RE = re.compile(r'[\xa0​‌‍⁠﻿⁡⁢⁣‬]')
PROMO_BLOCK_RE = re.compile(r'^:::\s*\n(?:[^\n]*\n)*?[^\n]*预约钉钉服务专家[^\n]*\n(?:[^\n]*\n)*?:::[ \t]*\n?',
                            re.MULTILINE)
# 尾链两种形态：带 markdown 链接 / 纯文本「返回「 **X** 」目录页」（可带 ▍ 前缀与前置 --- 分割线）
TRAILING_BACK_LINK_RE = re.compile(
    r'\n+(?:---\s*\n+)?(?:[▍▌▲◆])?[\xa0﻿​‌‍⁠]*'
    r'返回[「『]?\s*\[(?:\*\*)?[^\]]+(?:\*\*)?\]\([^)]+\)\s*[」『』]?'
    r'[\s*_`~、，。\xa0﻿​‌‍⁠]*\Z')
TRAILING_BACK_TEXT_RE = re.compile(
    r'\n+(?:---\s*\n+)?[▍▌▲◆]?\s*返回「[^\n」]{1,40}」\s*(?:目录页?)?\s*\Z')
CLICK_HERE_PAREN_RE = re.compile(r'[（(][^（）()\n]{0,40}点击此处[^（）()\n]{0,40}[）)]')
DINGTALK_DOC_LINK_HOST_RE = re.compile(r'https?://[a-z]+\.dingtalk\.com/i/(?:p/[^/]+/docs|nodes)/')
MD_LINK_RE = re.compile(r'\[([^\]\n]+)\]\((<)?([^)\s]+)(?:\s+"[^"]*")?(>)?\)')
EXTERNAL_LINK_HOST_RE = re.compile(
    r'^(?:dingtalk://|https?://(?:[a-z0-9-]+\.)*(?:dingtalk\.com|dingtalk\.io|aliyun|taobao|alibaba|page\.dingtalk))', re.I)
ADMONITION_MAP = {'': 'Note', 'note': 'Note', 'tip': 'Tip', 'info': 'Info',
                  'warning': 'Warning', 'caution': 'Warning', 'check': 'Check', 'danger': 'Warning'}
LEADING_H1_RE = re.compile(r'\A#\s+(.+?)\n')
MD_INLINE_IMAGE_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)')
MD_INLINE_LINK_RE = re.compile(r'\[([^\]]+)\]\([^)]+\)')
MD_EMPHASIS_CHARS_RE = re.compile(r'[*_`~]')
MD_LIST_PREFIX_RE = re.compile(r'^\s*(?:\d+[.)]|[-*+])\s+')
IMG_LINE_RE = re.compile(r'^\s*(!\[[^\]]*\]\([^)]+\))\s*$')
IMG_PARSE_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s"]+)(?:\s+"([^"]*)")?\)')
CAPTION_LINE_RE = re.compile(r'^\s*[（(]([^（）()\n]{2,60})[)）]\s*$')
Q_HEADING_RE = re.compile(r'^(#{2,6})\s*(?:\d+[.、)]?\s*)?(?:\*\*)?\s*问[:：]\s*(.+?)(?:\*\*)?\s*$')
HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')

# ---- 手工维护、脚本不覆盖（源结构畸形/需人工重构）----
MANUAL_KEEP: set[str] = set()

# ---- frontmatter 标题简化（QA 走查：标题不要太长和冗余）----
SHORT_TITLES: dict[str, str] = {
    'quick-start': '快速入门',
    'operation-interface': '操作界面',
    'initiator-guide': '发起人手册',
    'operator-guide': '操作人手册',
    'data-manager-guide': '数据管理人手册',
    'admin-guide-overview': '管理员手册概览',
    'admin-controls': '审批控件',
    'controls-detail': '明细控件',
    'controls-option-link': '选项关联',
    'admin-process-design': '流程设计',
    'set-role-approval': '角色人员审批',
    'set-direct-manager-approval': '直属主管审批',
    'set-dept-manager-approval': '部门主管审批',
    'set-form-contact-approval': '表单内联系人审批',
    'set-node-permission': '节点操作权限',
    'set-conditional-approval': '分条件审批',
    'conditional-branch-controls': '条件分支控件',
    'conditional-troubleshooting': '分条件审批排查',
    'conditional-special-case': '分管领导审批设置',
    'admin-advanced-settings': '高级设置',
    'admin-manage-form-data': '管理表单数据',
    'admin-agent-settings': '代理人设置',
    'ai-capabilities-overview': 'AI 能力概览',
    'ai-fill-form': 'AI 填单',
    'ai-controls': 'AI 控件',
    'cross-org-overview': '跨组织审批概览',
    'cross-org-quick-start': '跨组织快速入门',
    'cross-org-supplier-order': '组织外供应商确认订单',
    'cross-org-partner-contract': '组织外伙伴合同审批',
    'cross-org-admin-guide': '跨组织管理员手册',
    'cross-org-employee-guide': '跨组织员工手册',
    'open-solution-overview': '流程中心开放方案',
    'open-third-party-process': '三方流程页面对接',
    'open-dingtalk-process': '钉钉流程页面对接',
    'open-advanced-openapi': '专享 OpenAPI 说明',
}
TITLE_OVERRIDES: dict[str, str] = {}

# ================= 结构表 =================
_ADM = 'OA审批管理员手册.adoc/'
_AI = 'OA审批AI能力.adoc/'
_CROSS = '跨组织审批.adoc/'
_OPEN = 'OA审批流程中心开放方案.adoc/'
STRUCTURE: list[tuple[str, list, list]] = [
    ('快速上手', [
        ('quick-start', 'OA审批快速入门手册.adoc.md', None),
        ('operation-interface', 'OA审批操作界面.adoc.md', None),
    ], []),
    ('角色手册', [
        ('initiator-guide', 'OA审批发起人手册.adoc.md', None),
        ('operator-guide', 'OA审批操作人手册.adoc.md', None),
        ('data-manager-guide', 'OA审批数据管理人手册.adoc.md', None),
    ], []),
    ('管理员手册', [
        ('admin-guide-overview', 'OA审批管理员手册.adoc.md', None),
        ('admin-advanced-settings', _ADM + '管理员进行高级设置.adoc.md', None),
        ('admin-manage-form-data', _ADM + '管理员管理表单数据.adoc.md', None),
        ('admin-agent-settings', _ADM + '管理员代理人设置.adoc.md', None),
    ], [
        ('审批控件', [
            ('admin-controls', _ADM + '审批控件.adoc.md', None),
            ('controls-detail', _ADM + '审批控件.adoc - 如何使用明细控件.adoc.md', None),
            ('controls-option-link', _ADM + '审批控件.adoc - 如何设置选项关联.adoc.md', None),
        ]),
        ('流程设计', [
            ('admin-process-design', _ADM + '管理员进行流程设计.adoc.md', None),
            ('set-role-approval', _ADM + '管理员进行流程设计.adoc - 如何设置角色人员审批.adoc.md', None),
            ('set-direct-manager-approval', _ADM + '管理员进行流程设计.adoc - 如何设置直属主管审批.adoc.md', None),
            ('set-dept-manager-approval', _ADM + '管理员进行流程设计.adoc - 如何设置部门主管审批.adoc.md', None),
            ('set-form-contact-approval', _ADM + '管理员进行流程设计.adoc - 如何设置表单内联系人审批.adoc.md', None),
            ('set-node-permission', _ADM + '管理员进行流程设计.adoc - 如何设置节点操作权限.adoc.md', None),
            ('set-conditional-approval', _ADM + '管理员进行流程设计.adoc - 如何设置分条件审批.adoc.md', None),
            ('conditional-branch-controls', _ADM + '管理员进行流程设计.adoc - 如何设置分条件审批.adoc - 支持设置条件分支的控件.adoc.md', None),
            ('conditional-troubleshooting', _ADM + '管理员进行流程设计.adoc - 如何设置分条件审批.adoc - 分条件审批异常问题排查.adoc.md', None),
            ('conditional-special-case', _ADM + '管理员进行流程设计.adoc - 如何设置分条件审批.adoc - 当分管领导在总经办时如何设置审批.adoc.md', None),
        ]),
    ]),
    ('进阶能力', [
        ('ai-capabilities-overview', 'OA审批AI能力.adoc.md', None),
    ], [
        ('AI 能力', [
            ('ai-fill-form', _AI + 'OA审批AI填单：AI帮你填单，3秒发起审批.adoc.md', None),
            ('ai-controls', _AI + 'OA审批AI控件：AI帮你看审批单，决策快人一步.adoc.md', None),
        ]),
        ('跨组织审批', [
            ('cross-org-overview', '跨组织审批.adoc.md', None),
            ('cross-org-quick-start', _CROSS + '跨组织审批快速入门.adoc.md', None),
            ('cross-org-supplier-order', _CROSS + '跨组织审批快速入门.adoc - 如何由组织外供应商确认采购订单？.adoc.md', None),
            ('cross-org-partner-contract', _CROSS + '跨组织审批快速入门.adoc - 如何让组织外合作伙伴参与合同审批？.adoc.md', None),
            ('cross-org-admin-guide', _CROSS + '跨组织审批管理员操作手册.adoc.md', None),
            ('cross-org-employee-guide', _CROSS + '跨组织审批员工操作手册.adoc.md', None),
        ]),
        ('开放方案', [
            ('open-solution-overview', 'OA审批流程中心开放方案.adoc.md', None),
            ('open-third-party-process', _OPEN + '使用三方流程和页面对接.adoc.md', None),
            ('open-dingtalk-process', _OPEN + '使用钉钉OA审批流程和页面对接.adoc.md', None),
            ('open-advanced-openapi', _OPEN + '关于智能OA（原OA审批高级版）专享OpenAPI的说明.adoc.md', None),
        ]),
    ]),
]


def iter_pages():
    for group, direct, subgroups in STRUCTURE:
        for slug, src, tov in direct:
            yield slug, src, tov, group, None
        for subname, pages in subgroups:
            for slug, src, tov in pages:
                yield slug, src, tov, group, subname


def norm_title(s: str) -> str:
    return re.sub(r'[\s\|/\-—·•、，,。？?：:（）()【】\[\]「」【】"\'’*_~`+]+', '', s).lower()


def clean_invisible(text: str) -> str:
    return INVISIBLE_CHARS_RE.sub(lambda m: ' ' if m.group(0) == '\xa0' else '', text)


def strip_promo(body: str) -> str:
    return PROMO_BLOCK_RE.sub('', body)


BACK_LINE_RE = re.compile(r'^[▍▌▲◆]?\s*返回\s*[「『\[].*[」』\]]\s*(?:目录页?)?\s*$')


def strip_trailing_back_to(body: str) -> str:
    """行级删除「返回「X」目录页」（任何位置），并连带清掉其紧邻的前置孤立 --- 分割线。"""
    body = TRAILING_BACK_LINK_RE.sub('', body)
    lines = body.split('\n')
    keep: list[bool] = [True] * len(lines)
    for i, l in enumerate(lines):
        if BACK_LINE_RE.match(l.strip()) and '返回' in l:
            keep[i] = False
            # 向前清掉紧邻的 --- 与空行
            j = i - 1
            while j >= 0 and not lines[j].strip():
                keep[j] = False
                j -= 1
            if j >= 0 and lines[j].strip() == '---':
                keep[j] = False
    return '\n'.join(l for i, l in enumerate(lines) if keep[i])


def unescape_gt(body: str) -> str:
    """`\\>` → `>`（钉钉 export 转义残留；粘连粗体时破坏渲染）。"""
    out, fence = [], False
    for l in body.split('\n'):
        if l.lstrip().startswith('```'):
            fence = not fence
        out.append(l if fence else l.replace('\\>', '>'))
    return '\n'.join(out)


def _is_punct(ch: str) -> bool:
    return bool(ch) and unicodedata.category(ch).startswith('P')


EMOJI_RE = re.compile(r'([\U0001F000-\U0001FAFF☀-➿⬀-⯿←-⇿]️?)')
BRACKET_TAG_MAP = {'警告': 'Warning', '注意': 'Warning', '危险': 'Warning',
                   '提示': 'Tip', '小贴士': 'Tip', '技巧': 'Tip',
                   '信息': 'Info', '说明': 'Note', '注': 'Note'}


def bracket_tags_to_admonition(body: str) -> str:
    """行首 `[警告]xxx` 伪表情标签 → <Warning>/<Tip>/<Info>/<Note> 组件。"""
    out = []
    for l in body.split('\n'):
        m = re.match(r'^\s*\[(警告|注意|危险|提示|小贴士|技巧|信息|说明|注)\]\s*(.*)$', l)
        if m and m.group(2).strip():
            typ = BRACKET_TAG_MAP[m.group(1)]
            out += [f'<{typ}>', m.group(2).strip(), f'</{typ}>']
        else:
            out.append(l)
    return '\n'.join(out)


def space_after_emoji(body: str) -> str:
    """emoji 紧贴中文/字母时补空格（如 ⚠️操作须知 → ⚠️ 操作须知）。"""
    def repl(m: re.Match) -> str:
        end = m.end()
        nxt = body[end] if end < len(body) else ''
        if nxt and (nxt.isalnum() or '一' <= nxt <= '鿿'):
            return m.group(1) + ' '
        return m.group(1)
    return EMOJI_RE.sub(repl, body)


def strip_table_cell_headings(body: str) -> str:
    """表格单元格内裸 `####` 标题符（钉钉 export 残留）→ 删除。"""
    out = []
    for l in body.split('\n'):
        if l.lstrip().startswith('|') and '#' in l:
            l = re.sub(r'#{2,6}\s*', '', l)
        out.append(l)
    return '\n'.join(out)


def normalize_bold(body: str) -> str:
    """CJK/数字/标点紧贴导致 `**` 不渲染 → 规范化：
    1) 解包只含箭头/标点/空白的伪粗体（如 `**>**` → ` > `）；
    2) 平衡粗体外侧贴非空白 → 补空格，确保 flanking 成立。"""
    out, fence = [], False
    for line in body.split('\n'):
        if line.lstrip().startswith('```'):
            fence = not fence
            out.append(line)
            continue
        if fence or '**' not in line:
            out.append(line)
            continue
        line = re.sub(r'\*\*([\s>》〉、，,。.:：;；·\-—>]*)\*\*', r'\1', line)
        poss = [m.start() for m in re.finditer(r'\*\*', line)]
        if len(poss) % 2:
            out.append(line)
            continue
        ins: list[tuple[int, str]] = []
        for idx, p in enumerate(poss):
            prev = line[p - 1] if p > 0 else ''
            nxt = line[p + 2] if p + 2 < len(line) else ''
            if idx % 2 == 0:   # opener
                if prev and prev not in ' \t([（【' and not prev.isspace():
                    ins.append((p, ' '))
            else:              # closer
                if nxt and nxt not in ' \t)]）】' and not nxt.isspace() and not _is_punct(nxt):
                    ins.append((p + 2, ' '))
        for pos, txt in sorted(ins, reverse=True):
            line = line[:pos] + txt + line[pos:]
        out.append(line)
    return '\n'.join(out)


def dedent_blocks(body: str) -> str:
    """图片/表格行完全去缩进独占一行；≥5 空格文本（FAQ 答句等）去缩进防代码块；纯空白行清空。"""
    out, fence = [], False
    for l in body.split('\n'):
        if l.lstrip().startswith('```'):
            fence = not fence
            out.append(l)
            continue
        if fence:
            out.append(l)
            continue
        if not l.strip():
            out.append('')
            continue
        s = l.lstrip()
        if IMG_LINE_RE.match(l) or s.startswith('|'):
            out.append(s)
        elif re.match(r'^ {5,}\S', l) and not re.match(r'^[*+\-]|\d+[.)]', s):
            out.append(s)
        else:
            out.append(l)
    return '\n'.join(out)


def convert_links(body: str, title2slug: dict[str, str]) -> tuple[str, int, int]:
    n_int = n_plain = 0

    def repl(m: re.Match) -> str:
        nonlocal n_int, n_plain
        text, url = m.group(1), m.group(3)
        key = norm_title(text)
        is_doc = bool(DINGTALK_DOC_LINK_HOST_RE.match(url))
        if is_doc and key in title2slug:
            n_int += 1
            return f'[{text}](/zh/approval/{title2slug[key]})'
        if is_doc or EXTERNAL_LINK_HOST_RE.match(url):
            n_plain += 1
            return text
        return m.group(0)

    images = []
    tmp = MD_INLINE_IMAGE_RE.sub(lambda m: (images.append(m.group(0)) or f'\x00IMG{len(images)-1}\x00'), body)
    tmp = MD_LINK_RE.sub(repl, tmp)
    for i, img in enumerate(images):
        tmp = tmp.replace(f'\x00IMG{i}\x00', img)
    return tmp, n_int, n_plain


def convert_admonitions(body: str) -> str:
    result, content = [], []
    in_block, open_type = False, None
    for l in body.split('\n'):
        m = re.match(r'^:::([a-zA-Z]*)\s*$', l)
        if m:
            if not in_block:
                in_block, open_type, content = True, ADMONITION_MAP.get(m.group(1).lower(), 'Note'), []
            else:
                inner = '\n'.join(content).strip('\n')
                stripped = inner.strip()
                if stripped:
                    if re.match(r'^#{1,6}\s', stripped) and '\n' not in stripped:
                        result.append(stripped)
                    else:
                        result.append(f'<{open_type}>\n{inner}\n</{open_type}>')
                in_block, open_type, content = False, None, []
        elif in_block:
            content.append(l)
        else:
            result.append(l)
    if in_block and '\n'.join(content).strip():
        result.append(f'<Note>\n{chr(10).join(content).strip(chr(10))}\n</Note>')
    return '\n'.join(result)


def fix_inline_marks(body: str) -> str:
    body = re.sub(r'\+\+([^+\n]+)\+\+', r'\1', body)
    body = body.replace('****', '')
    body = re.sub(r'\[优先级[:：]?\s*\d+\]\s*', '', body)
    body = re.sub(r'\[(?:星星转动|星星|灯泡|笔记本|对钩|铅笔|放大镜|齿轮|火箭|礼物|旗帜|进度|本子)\]\s*', '', body)
    body = CLICK_HERE_PAREN_RE.sub('', body)
    # 「可点击此处…咨询/购买/查看」推销子句（高级版/旗舰版国际版不售卖）：整句/子句删
    out = []
    for l in body.split('\n'):
        # <N> 截图圈注标记（行首 / 行中 / 粗体内）→ 「N. 」或「N)」
        m = re.match(r'^(\s*)<(\d+)>\s*(.+)$', l)
        if m:
            l = f'{m.group(1)}{m.group(2)}. {m.group(3)}'
        l = re.sub(r'(\*\*)<(\d+)>', r'\1\2. ', l)      # 粗体内开头
        l = re.sub(r'(?<=[;；:：] )<(\d+)>', r'\1. ', l)  # 句中接续
        l = re.sub(r'<(\d+)>', r'\1. ', l)               # 兜底
        if '点击此处' in l:
            # 按中文逗号/句号切分，丢弃含推销关键词的子句
            parts = re.split(r'(?<=[，。；])', l)
            kept = [p for p in parts if not re.search(r'点击此处|提交表单|进一步了解|升级(?:钉钉)?专业版|可升级专业版', p)]
            l2 = ''.join(kept).strip()
            l2 = re.sub(r'[，、；]\s*$', '。', l2)
            if l2.count('**') % 2:          # 子句删除后粗体破碎 → 剥平该行 **
                l2 = l2.replace('**', '')
            if l2.strip('*# 　-'):
                out.append(l2)
        else:
            out.append(l)
    return '\n'.join(out)


def _attr_escape(s: str) -> str:
    return s.replace('"', '”').strip()


# ---- 图片宽高（判定横竖图，缓存到 image-dims.json）----
IMAGE_DIMS_CACHE = OUTPUT_DIR / 'image-dims.json'
_IMG_DIMS: dict[str, list[int]] = {}
_DIMS_LOADED = [False]


def _fetch_dim(url: str):
    try:
        r = urllib.request.urlopen(url.split('?')[0] + '?x-oss-process=image/info', timeout=12)
        d = json.load(r)
        return [int(d['ImageWidth']['value']), int(d['ImageHeight']['value'])]
    except Exception:
        return None


def prefetch_dims(urls: list[str]) -> None:
    global _IMG_DIMS
    if not _DIMS_LOADED[0]:
        if IMAGE_DIMS_CACHE.exists():
            _IMG_DIMS = json.loads(IMAGE_DIMS_CACHE.read_text(encoding='utf-8'))
        _DIMS_LOADED[0] = True
    todo = [u for u in dict.fromkeys(urls) if u not in _IMG_DIMS]
    if not todo:
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for u, res in zip(todo, ex.map(_fetch_dim, todo)):
            if res:
                _IMG_DIMS[u] = res
    IMAGE_DIMS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    IMAGE_DIMS_CACHE.write_text(json.dumps(_IMG_DIMS, ensure_ascii=False), encoding='utf-8')


def is_portrait(url: str) -> bool:
    """竖图（手机截图，h>w）返回 True；未知 → False（当横图，独占一行更安全）。"""
    d = _IMG_DIMS.get(url)
    return bool(d) and d[1] > d[0]


def faq_to_accordion(body: str) -> tuple[str, list[str]]:
    """`## 问：xxx` 标题簇 → <AccordionGroup>/<Accordion>。返回 (body, questions)。"""
    lines = body.split('\n')
    questions: list[str] = []
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        m = Q_HEADING_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        # 收集连续的问答簇（同级问标题）
        level = len(m.group(1))
        items: list[tuple[str, list[str]]] = []
        while i < n:
            m = Q_HEADING_RE.match(lines[i])
            if not (m and len(m.group(1)) == level):
                break
            q = MD_EMPHASIS_CHARS_RE.sub('', m.group(2)).strip()
            i += 1
            content: list[str] = []
            while i < n and not HEADING_RE.match(lines[i]):
                if lines[i].strip() != '---':
                    content.append(lines[i])
                i += 1
            # 答案首行剥「答：」前缀
            for j, cl in enumerate(content):
                if cl.strip():
                    content[j] = re.sub(r'^\s*答[:：]\s*', '', cl)
                    break
            items.append((q, content))
        questions.extend(q for q, _ in items)
        out.append('<AccordionGroup>')
        for q, content in items:
            out.append(f'  <Accordion title="{_attr_escape(q)}">')
            out.append('')
            out.extend(l for l in content)
            out.append('')
            out.append('  </Accordion>')
        out.append('</AccordionGroup>')
    return '\n'.join(out), questions


def _is_sentence_heading(level: int, text: str) -> bool:
    if level < 3:
        return False
    t = text.strip()
    return len(t) > 20 or (' > ' in t and len(t) > 12) or t.endswith('。') or re.search(r'如下[:：]?$', t) is not None


def steps_transform(body: str) -> str:
    """连续 ≥2 个同级「长句标题」（多为编号操作步骤）→ <Steps>/<Step>；孤立 1 个 → 降为普通段落。"""
    lines = body.split('\n')
    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        m = HEADING_RE.match(lines[i])
        if not (m and _is_sentence_heading(len(m.group(1)), m.group(2))):
            out.append(lines[i])
            i += 1
            continue
        level = len(m.group(1))
        run: list[tuple[str, list[str]]] = []
        while i < n:
            m = HEADING_RE.match(lines[i])
            if not (m and len(m.group(1)) == level and _is_sentence_heading(level, m.group(2))):
                break
            sent = re.sub(r'^\d+(?:\.\d+)*\s*[\.、]?\s*', '', m.group(2).strip())
            i += 1
            content: list[str] = []
            while i < n and not HEADING_RE.match(lines[i]):
                content.append(lines[i])
                i += 1
            run.append((sent, content))
        if len(run) >= 2:
            out.append('<Steps>')
            for sent, content in run:
                out.append('  <Step>')
                out.append('')
                out.append(f'{sent}')
                out.extend(content)
                out.append('')
                out.append('  </Step>')
            out.append('</Steps>')
        else:
            sent, content = run[0]
            out.append(f'**{MD_EMPHASIS_CHARS_RE.sub("", sent)}**')
            out.append('')
            out.extend(content)
    return '\n'.join(out)


def wrap_images(body: str) -> str:
    """图片包裹（在 escape_mdx 之后运行，保护 JSX 花括号）：
    - 横图（PC 截图，w≥h）/ 单张 → <Frame> 独占一行
    - 连续 ≥2 张竖图（手机截图，h>w）→ flex 行并排（遵循项目移动端图片规则）"""
    lines = body.split('\n')
    # 预取本文所有图宽高
    urls = [IMG_PARSE_RE.match(m.group(1).strip()).group(2)
            for l in lines if (m := IMG_LINE_RE.match(l)) and IMG_PARSE_RE.match(m.group(1).strip())]
    prefetch_dims(urls)

    def frame(alt, url, cap):
        cap_attr = f' caption="{_attr_escape(cap)}"' if cap else ''
        return ['', f'<Frame{cap_attr}>', f'![{alt}]({url})', '</Frame>', '']

    def flex(items):
        w = '48%' if len(items) <= 2 else '31%'
        o = ['', "<div style={{display:'flex', flexWrap:'wrap', gap:'16px', justifyContent:'center', margin:'16px 0'}}>"]
        for alt, url, cap in items:
            a = _attr_escape(cap or alt)
            o.append("  <img src=\"%s\" alt=\"%s\" style={{width:'%s', minWidth:'220px', borderRadius:'8px', boxShadow:'0 2px 12px rgba(0,0,0,0.08)', margin:0}} />" % (url, a, w))
        o += ['</div>', '']
        return o

    out: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        if not IMG_LINE_RE.match(lines[i]):
            out.append(lines[i])
            i += 1
            continue
        run: list[tuple[str, str, str]] = []
        while i < n:
            im = IMG_LINE_RE.match(lines[i])
            if not im:
                break
            p = IMG_PARSE_RE.match(im.group(1).strip())
            if not p:
                break
            alt, url, title = p.group(1) or 'image', p.group(2), (p.group(3) or '').strip()
            i += 1
            j = i
            while j < n and not lines[j].strip():
                j += 1
            cap = ''
            if j < n:
                cm = CAPTION_LINE_RE.match(lines[j])
                if cm:
                    cap = cm.group(1).strip()
                    i = j + 1
            if not cap and title:
                cap = re.sub(r'^[（(]|[)）]$', '', title).strip()
            run.append((alt, url, cap))
            while i < n and not lines[i].strip():
                i += 1
        # 按方向切分：连续竖图聚成 flex，横图各自 Frame
        buf: list[tuple[str, str, str]] = []
        for item in run:
            if is_portrait(item[1]):
                buf.append(item)
            else:
                if len(buf) >= 2:
                    out += flex(buf)
                elif buf:
                    out += frame(*buf[0])
                buf = []
                out += frame(*item)
        if len(buf) >= 2:
            out += flex(buf)
        elif buf:
            out += frame(*buf[0])
    return '\n'.join(out)


def normalize_heading_stack(body: str) -> str:
    """栈深度重映射：顶层 → ##，消跳级、兄弟同级；标题尾冒号剥除。"""
    stack: list[int] = []
    out, fence = [], False
    for l in body.split('\n'):
        if l.lstrip().startswith('```'):
            fence = not fence
            out.append(l)
            continue
        m = HEADING_RE.match(l)
        if fence or not m:
            out.append(l)
            continue
        L = len(m.group(1))
        while stack and stack[-1] >= L:
            stack.pop()
        stack.append(L)
        text = re.sub(r'[:：]\s*$', '', m.group(2).strip())
        out.append('#' * (len(stack) + 1) + ' ' + text)
    return '\n'.join(out)


def demote_body_h1(body: str) -> str:
    lines = body.split('\n')
    in_code = False
    for i, l in enumerate(lines):
        if l.startswith('```'):
            in_code = not in_code
            continue
        if not in_code and re.match(r'^#\s+\S', l):
            lines[i] = '#' + l
    return '\n'.join(lines)


def extract_description(body: str, fallback: str) -> str:
    text = MD_INLINE_IMAGE_RE.sub(' ', body)
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith('#') or s.startswith('![') or s.startswith('<') or s.startswith('</'):
            continue
        if MD_LIST_PREFIX_RE.match(raw) or s.startswith('|') or set(s) <= set('-| :'):
            continue
        s = MD_INLINE_LINK_RE.sub(r'\1', s)
        s = MD_EMPHASIS_CHARS_RE.sub('', s)
        s = re.sub(r'\s+', ' ', s).strip()
        if len(s) >= 8:
            return s[:150]
    return fallback


def faq_description(title: str, questions: list[str]) -> str:
    qs = [q.rstrip('？?') for q in questions[:2]]
    joined = '」「'.join(q[:20] for q in qs)
    return f'解答「{joined}」等{title}高频问题。'[:150]


def process_one(source: Path, slug: str, title_override: str | None, title2slug: dict) -> dict:
    raw = source.read_text(encoding='utf-8')
    nbsp = raw.count('\xa0')
    cleaned = clean_invisible(raw)
    parsed_title, _d, body = parse_frontmatter_data(cleaned, source.stem)
    m = LEADING_H1_RE.match(body)
    if m and m.group(1).strip() == parsed_title.strip():
        body = body[m.end():].lstrip()
    body = strip_promo(body)
    body = strip_trailing_back_to(body)
    body = unescape_gt(body)
    body, n_int, n_plain = convert_links(body, title2slug)
    body = fix_inline_marks(body)
    body = bracket_tags_to_admonition(body)
    body = space_after_emoji(body)
    body = strip_table_cell_headings(body)
    body = dedent_blocks(body)
    body = normalize_bold(body)
    body = demote_body_h1(body)
    body, questions = faq_to_accordion(body)
    body = steps_transform(body)
    body = convert_admonitions(body)
    body = normalize_heading_stack(body)
    body = escape_mdx(body)
    body = wrap_images(body)      # escape 之后：保护 flex <div style={{}}> 花括号
    body = re.sub(r'\n{3,}', '\n\n', body).strip()

    title = title_override or SHORT_TITLES.get(slug) or TITLE_OVERRIDES.get(slug) or parsed_title
    if questions:
        description = faq_description(title, questions)
    else:
        description = extract_description(body, fallback=title)
    mdx = (f'---\ntitle: {yaml_escape(title)}\n'
           f'description: {yaml_escape(description)}\n---\n\n{body}\n')
    return {'slug': slug, 'title': title, 'mdx': mdx, 'nbsp': nbsp,
            'residual_nbsp': mdx.count('\xa0'), 'size': len(mdx),
            'n_internal': n_int, 'n_plain': n_plain, 'n_questions': len(questions)}


def build_nav_fragment() -> dict:
    def page_ref(slug):
        return f'zh/approval/{slug}'
    groups = []
    for group, direct, subgroups in STRUCTURE:
        pages = [page_ref(s) for s, _, _ in direct]
        for subname, subpages in subgroups:
            pages.append({'group': subname, 'pages': [page_ref(s) for s, _, _ in subpages]})
        groups.append({'group': group, 'pages': pages})
    return {'tab': '审批', 'groups': groups}


def load_existing_titles() -> dict[str, str]:
    out = {}
    for f in ATT_DIR.glob('*.mdx'):
        m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', f.read_text(encoding='utf-8'), re.M)
        if m:
            out[norm_title(m.group(1))] = f.stem
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default=str(DEFAULT_SOURCE))
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    src_dir = Path(args.source).expanduser().resolve()
    if not src_dir.exists():
        print(f'❌ 源目录不存在: {src_dir}', file=sys.stderr)
        return 1

    title2slug = load_existing_titles()
    for slug, src, tov, _g, _s in iter_pages():
        if src is None:
            continue
        p = src_dir / src
        h1 = ''
        if p.exists():
            for ln in p.read_text(encoding='utf-8').splitlines():
                if ln.startswith('# '):
                    h1 = ln[2:].strip()
                    break
        for key in {h1, tov or '', SHORT_TITLES.get(slug, '')}:
            if key:
                title2slug[norm_title(key)] = slug

    print(f'源: {src_dir}\n目标: {ATT_DIR}\ndry-run: {args.dry_run}\n' + '=' * 60)
    if not args.dry_run:
        ATT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rows, missing, manual, collisions = [], [], [], []
    managed = {slug for slug, _s, _t, _g, _sub in iter_pages()}
    existing_slugs = {f.stem for f in ATT_DIR.glob('*.mdx')} - managed  # 仅原始19篇算冲突

    tot_int = tot_plain = tot_nbsp = 0
    for slug, src, tov, group, sub in iter_pages():
        loc = f'{group}/{sub}' if sub else group
        if src is None or slug in MANUAL_KEEP:
            manual.append(slug)
            print(f'  {slug:<34} ⏭  手工页（{loc}）')
            continue
        if slug in existing_slugs:
            collisions.append(slug)
            print(f'  {slug:<34} ⚠️  与原始19篇 slug 冲突！')
            continue
        p = src_dir / src
        if not p.exists():
            missing.append((slug, src))
            print(f'  {slug:<34} ❌ 源缺失: {src}')
            continue
        info = process_one(p, slug, tov, title2slug)
        tot_int += info['n_internal']
        tot_plain += info['n_plain']
        tot_nbsp += info['nbsp']
        rows.append({**info, 'group': group, 'sub': sub})
        qa = f' FAQ{info["n_questions"]}' if info['n_questions'] else ''
        print(f'  {slug:<34} ✓ {info["size"]:>5}B  内链{info["n_internal"]} 转文{info["n_plain"]}{qa}  ({loc})')
        if not args.dry_run:
            (ATT_DIR / f'{slug}.mdx').write_text(info['mdx'], encoding='utf-8')

    print('=' * 60)
    print(f'导入 {len(rows)} / 缺失 {len(missing)} / 手工 {len(manual)} / slug冲突 {len(collisions)}')
    print(f'内链 {tot_int} / 外链转文 {tot_plain} / NBSP {tot_nbsp}')
    residual = sum(1 for r in rows if r['residual_nbsp'] > 0)
    if residual:
        print(f'⚠️ 残留 NBSP 文件 {residual}')

    if not args.dry_run:
        (OUTPUT_DIR / 'nav-fragment.json').write_text(
            json.dumps(build_nav_fragment(), indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        (OUTPUT_DIR / 'slug-map.json').write_text(
            json.dumps({r['slug']: {'title': r['title'], 'group': r['group'], 'sub': r['sub']} for r in rows},
                       indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        lines = ['# Attendance ZH Import Report\n',
                 f'- 导入 {len(rows)} / 手工 {len(manual)} / 缺失 {len(missing)}',
                 f'- 内链 {tot_int} / 外链转文 {tot_plain} / NBSP {tot_nbsp}\n',
                 '| group | sub | slug | title | size | FAQ |',
                 '|---|---|---|---|---|---|']
        for r in rows:
            lines.append(f'| {r["group"]} | {r["sub"] or ""} | `{r["slug"]}` | {r["title"]} | {r["size"]} | {r["n_questions"] or ""} |')
        (OUTPUT_DIR / 'import-report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
        print(f'产物: {OUTPUT_DIR}/(nav-fragment.json, slug-map.json, import-report.md)')

    return 1 if (missing or collisions or residual) else 0


if __name__ == '__main__':
    sys.exit(main())
