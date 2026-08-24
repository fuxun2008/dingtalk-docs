#!/usr/bin/env python3
"""
MDX 质量审计：扫所有 mdx，检出多类问题并按需修复。

通用模式（全仓）：
A. `++text++` 下划线语法（Mintlify 不支持）→ 剥 `++`，保留内层；若内层是 `**…**` 且内侧紧贴空格，挤出来
B. `** text**` 粗体空白破坏（仅 LEADING-space 安全检测；TRAILING-space 会跟相邻粗体打架）→ 修
C. `[label](https:xxx)` 形态废 URL（协议后跟纯字母≤8 字符，无 `//`）→ 去链留文案
D. `[https://...full-url...](url)` label 含完整 URL → 仅报告，人审
E. 空 `<Note>` 块（`<Note>---</Note>` / `<Note></Note>` / 跨行空 Note）→ 整段删除
H. `**X****Y**` 破碎嵌套粗体（恰好 4 连星）→ 合并为单段 `**XY**`（auto-fix）
I. 同段内 ≥4 段独立 `**bold**` 行 → 建议 `<CardGroup>`（仅报告，人审）
J. 连续 ≥2 张移动端截图（按 alt 文件名 lQDPKH/IMG_ 前缀或 URL crop 高瘦比例 h/w≥1.5）→ 建议 flex 容器（仅报告）
K. `[xxx.mp4](alidocs.dingtalk.*/...)` 钉钉附件 mp4 链接 → 建议 `<video>` 标签（仅报告）
L. CJK 字符紧贴粗体（`[CJK]**X**` 或 `**X**[CJK]`）→ 加空格分隔，否则 mdx 解析失败 ** 字符外露（auto-fix）
M. CJK 标点紧贴粗体（仅 `「」，：。（）` 等全角标点，无 CJK 字符）→ 仅报告，部分 mdx 解析器会失败
N. 图下方短文本（≤12 字符，紧邻 image / `</div>` 行）→ 建议包装为居中图说 div（仅报告，启发式）

定向模式（仅 release-notes/）：钉钉编辑器导出 mdx 时把 `<Note>` 拆碎，icon/标题被强制分行
F. `release-notes/` 下 `<Note>` 与 `</Note>` 标签行整段剥离（保留内部 markdown）
G. `release-notes/index.mdx` 4 空格缩进续行修正（钉钉编辑器把日期小标题缩进成上一段续行）

CLI:
  python3 scripts/audit_mdx_quality.py                   # dry-run，全部 mdx
  python3 scripts/audit_mdx_quality.py --root docs       # 只扫 docs 产品
  python3 scripts/audit_mdx_quality.py --lang en         # 只扫英文
  python3 scripts/audit_mdx_quality.py --apply           # 实际写盘
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "audit_mdx"

EXCLUDE_DIRS = {"node_modules", ".next", ".mintlify", "scripts", ".claude", ".git"}


# ---------------------------------------------------------------------------
# 检测 / 修复
# ---------------------------------------------------------------------------

# A: ++text++ —— 非贪婪、跨行；inner 不能含 ++（防贪婪吃掉相邻段）
RE_UNDERLINE = re.compile(r'\+\+((?:(?!\+\+).)+?)\+\+', re.S)

# B: 破碎粗体（inner 含 leading/trailing 空白）。
#    用 per-line + 配对计数法，避开"相邻独立粗体之间的空隙"这种结构性误报。
#    单 lookbehind 无法区分 `**` 是 opener 还是 closer——`[** X**]` 起手 `**` 前是 `[`
#    会被 `(?<!\S)` 误拦；`**Note:** clicking **New**` 中间空隙又会被 `(?<!\w)` 误命中。
#    单行内按出现顺序两两配对 `**`，inner 含前后空白即报。代价：跨行的破碎粗体（原本
#    渲染就崩的废 marker）漏报——可接受，修不修都不影响视觉。
RE_BOLD_PAIR = re.compile(r'\*\*')

# C: [label](https:xxx) —— scheme 后跟字母数字（无 `//`），≤12 字符，非真实 URL
RE_BAD_URL_PLACEHOLDER = re.compile(r'\[([^\]]*)\]\((https?:[a-zA-Z0-9_]{1,12})\)')

# D: label 含完整 URL（仅报告，不修）—— label 长度 ≥ 20 且以 https?:// 开头
RE_URL_AS_LABEL = re.compile(r'\[(https?://[^\]]{20,})\]\(([^)]+)\)')

# E: 空 Note 块。跨行匹配 `<Note>` 后只含空白/水平分隔线/空 li 的 `</Note>`。
#    覆盖 3 种钉钉编辑器导出残骸：
#      <Note></Note>            （单行空）
#      <Note>\n</Note>          （仅换行）
#      <Note>\n---\n</Note>     （仅水平分隔线）
#    匹配时把前置换行一起吃掉,避免修复后留空行堆叠。
RE_EMPTY_NOTE = re.compile(r'\n?<Note>\s*(?:-{3,}\s*)?</Note>\n?', re.S)

# F: release-notes 专项 —— 整行 `<Note>` / `</Note>` 标签独占一行,直接剥（保留内层 markdown）。
#    钉钉编辑器把每条 release item 错误地用 `<Note>` 包成碎片,导致 icon 在外、title 在内。
#    剥后变成普通段落 + `---` 分隔,语义不变,视觉连贯。
RE_NOTE_OPEN_LINE = re.compile(r'^[ \t]*<Note>[ \t]*\r?\n', re.M)
RE_NOTE_CLOSE_LINE = re.compile(r'^[ \t]*</Note>[ \t]*\r?\n', re.M)

# G: release-notes/index.mdx 专项 —— 4 空格缩进续行修正。
#    钉钉编辑器把日期小标题 `    **2024.06 ...**` 缩进成上一个列表项续行,
#    解析器吃掉了它的章节地位。任意以 4 个空格开头的非空行,统一夺为 0 缩进。
RE_FOUR_SPACE_INDENT = re.compile(r'^    (?!\s)', re.M)

# H: 破碎嵌套粗体 `**X****Y**` → `**XY**`。
#    钉钉编辑器粗体内嵌套粗体导出残骸——`****`（恰好 4 个连续 `*`）在 `**…**` 内部
#    把单段加粗截成 `**A** **B**` 三段紧挨。删掉 4 连星即合并。
#    `(?<!\*)` / `(?!\*)` 锚定恰好 4 连，避开 `***italic-bold***` / `*****bold-italic*****`。
RE_NESTED_BOLD = re.compile(r'(?<!\*)\*{4}(?!\*)')

# I: 同段内 ≥4 段独立 `**bold**` 段落 → 建议 CardGroup（仅报告）。
#    启发式：H1-H4 section 内统计 RE_BOLD_PARA_LINE 命中数，≥4 即报。
RE_BOLD_PARA_LINE = re.compile(r'^\*\*[^*\n]+\*\*\s*$')

# J: 连续 ≥2 张移动端截图 → 建议 flex 容器（仅报告）。
#    移动端启发式：alt 文件名 `lQDPKH` / `IMG_\d+` 前缀，OR url crop 比例高瘦（h/w≥1.5），
#    OR 文件名内嵌尺寸 `_1179_2556` 这类。
RE_IMG_INLINE = re.compile(r'!\[([^\]]*)\]\((https?://[^)\s]+)\)')

# K: 钉钉附件链接当 mp4 视频 → 建议 video 标签（仅报告）。
#    label 含 `.mp4`，url 是 alidocs.dingtalk.*。
RE_DINGTALK_MP4_LINK = re.compile(
    r'\[([^\]]*\.mp4[^\]]*)\]\((https?://alidocs\.dingtalk\.[^)]+)\)',
    re.I,
)

# L/M: CJK 边界粗体破碎。CommonMark 规定 ** 作为 opener/closer 的判定依赖左右"flank"，
#    CJK 字符（U+4E00-U+9FFF / U+3400-U+4DBF 等基本+扩展A）在 remark/mdx 中被视为
#    "non-punctuation, non-whitespace"，紧贴时 ** 既不算 opener 也不算 closer → 渲染失败 `**` 字符外露。
#    CJK 全角标点（「」，。：（）等 U+3000-U+303F / U+FF00-U+FFEF）按规范是 punctuation，bold 可识别，
#    但实测部分版本 mintlify/remark 行为不稳 → 列 MED 仅报告。
RE_CJK_CHAR = re.compile(r'[一-鿿㐀-䶿]')
RE_CJK_PUNCT = re.compile(r'[　-〿＀-￯]')

# L 自动修：opener `**` 前紧贴 CJK 字符 → 加空格分隔；closer `**` 后紧贴 CJK 字符 → 加空格。
RE_BOLD_CJK_CHAR_LEFT = re.compile(r'([一-鿿㐀-䶿])(\*\*[^*\n]+?\*\*)')
RE_BOLD_CJK_CHAR_RIGHT = re.compile(r'(\*\*[^*\n]+?\*\*)([一-鿿㐀-䶿])')

# M 仅报告：opener `**` 前 / closer `**` 后是 CJK 标点，且另一侧不是 CJK 字符。
#    扫描层用 classify_bold_flank() 精判，避免 L 已修过的也算 M。

# N: 图下方短文本（≤12 字符，紧邻 image / `</div>` 行）→ 建议居中图说 div（仅报告）。
#    启发式 pattern: image-line → blank → short-text-line（非 heading / 非 list / 非 image / 非 JSX）。
RE_IMAGE_LINE_LIKE = re.compile(r'^\s*(?:!\[|<img\b|</div>)')


def find_broken_bold_pairs(line: str) -> list[tuple[int, int, str]]:
    """单行扫破碎粗体。返回 [(start, end, inner)]，其中 inner 是 ** … ** 之间的原文。
    仅当 ** 数为偶数（行内完美配对）才扫，按出现顺序两两配对。inner 必须含前/后空白。
    """
    positions = [m.start() for m in RE_BOLD_PAIR.finditer(line)]
    if not positions or len(positions) % 2:
        return []
    out: list[tuple[int, int, str]] = []
    for i in range(0, len(positions), 2):
        start, end = positions[i], positions[i + 1]
        inner = line[start + 2 : end]
        if not inner or inner == inner.strip():
            continue
        out.append((start, end + 2, inner))
    return out


def fix_bold_whitespace(s: str) -> str:
    """逐行修复破碎粗体；不动行内 ** 配对失衡的行。"""
    lines = s.split("\n")
    for idx, line in enumerate(lines):
        hits = find_broken_bold_pairs(line)
        if not hits:
            continue
        # 从后往前替换，保持前置位置不变
        for start, end, inner in reversed(hits):
            stripped = inner.strip()
            replacement = f"**{stripped}**" if stripped else ""
            line = line[:start] + replacement + line[end:]
        lines[idx] = line
    return "\n".join(lines)


def normalize_underline_inner(inner: str) -> str:
    """剥 ++ 时同步净化内层 **…** 的紧贴空格。
    复用 per-line 配对法（inner 一般是单段文本，行内 ** 配对完整）。"""
    return fix_bold_whitespace(inner)


def fix_underline(s: str) -> str:
    """剥 ++text++，保留内层；嵌套 ++ 由非贪婪 + 否定前瞻防止跨匹配。"""
    return RE_UNDERLINE.sub(lambda m: normalize_underline_inner(m.group(1)), s)


def fix_bad_url_placeholder(s: str) -> str:
    """[label](https:xxx) → label；label 为空时返回空串（让后续段落自然收尾）。"""
    return RE_BAD_URL_PLACEHOLDER.sub(lambda m: m.group(1), s)


def fix_empty_note(s: str) -> str:
    """删除空 Note 块（含纯 `---` 的）。"""
    return RE_EMPTY_NOTE.sub("\n", s)


def fix_strip_note_tags(s: str) -> str:
    """剥 `<Note>` / `</Note>` 整行标签（仅 release-notes 用）。"""
    s = RE_NOTE_OPEN_LINE.sub("", s)
    s = RE_NOTE_CLOSE_LINE.sub("", s)
    return s


def fix_four_space_indent(s: str) -> str:
    """4 空格缩进行 → 0 缩进（仅 release-notes/index.mdx 用）。"""
    return RE_FOUR_SPACE_INDENT.sub("", s)


def fix_nested_bold(s: str) -> str:
    """4 连星 `****` 删除——合并 `**A****B**` 为 `**AB**`。"""
    return RE_NESTED_BOLD.sub("", s)


def is_mobile_screenshot(alt: str, url: str) -> bool:
    """启发式判定一张图是否移动端截图。"""
    alt = alt or ""
    if re.match(r'(?:lQDPKH|IMG_\d+)', alt, re.I):
        return True
    # alt 文件名内嵌尺寸：_1179_2556 / _1320_2862 等高瘦
    name_match = re.search(r'_(\d{3,4})_(\d{3,4})\.(?:png|jpg|jpeg)', alt, re.I)
    if name_match:
        w, h = int(name_match.group(1)), int(name_match.group(2))
        if w > 0 and h > w * 1.5:
            return True
    # URL crop 参数：w_1320,h_2862 之类
    crop_match = re.search(r'w_(\d+),h_(\d+)', url)
    if crop_match:
        w, h = int(crop_match.group(1)), int(crop_match.group(2))
        if w > 0 and h > w * 1.5:
            return True
    return False


def find_mobile_screenshot_groups(text: str) -> list[tuple[int, int]]:
    """[(开始行号 1-based, 连续移动端截图张数)]。
    "连续" 指相邻图行之间最多隔一个空白行，且不被非空非图行打断。
    一行内多张图同样计入。
    """
    lines = text.split("\n")
    groups: list[tuple[int, int]] = []
    n = len(lines)
    i = 0
    while i < n:
        imgs = RE_IMG_INLINE.findall(lines[i])
        if not imgs:
            i += 1
            continue
        mobile = [(a, u) for a, u in imgs if is_mobile_screenshot(a, u)]
        if not mobile or len(mobile) != len(imgs):
            i += 1
            continue
        run_start = i + 1
        run_count = len(mobile)
        j = i + 1
        while j < n:
            line_j = lines[j]
            if line_j.strip() == "":
                # 跳到下一非空行
                k = j + 1
                while k < n and lines[k].strip() == "":
                    k += 1
                if k >= n:
                    break
                imgs_k = RE_IMG_INLINE.findall(lines[k])
                if not imgs_k:
                    break
                mobile_k = [(a, u) for a, u in imgs_k if is_mobile_screenshot(a, u)]
                if not mobile_k or len(mobile_k) != len(imgs_k):
                    break
                run_count += len(mobile_k)
                j = k + 1
                continue
            imgs_j = RE_IMG_INLINE.findall(line_j)
            if not imgs_j:
                break
            mobile_j = [(a, u) for a, u in imgs_j if is_mobile_screenshot(a, u)]
            if not mobile_j or len(mobile_j) != len(imgs_j):
                break
            run_count += len(mobile_j)
            j += 1
        if run_count >= 2:
            groups.append((run_start, run_count))
        i = max(j, i + 1)
    return groups


def fix_bold_cjk_boundary(s: str) -> str:
    """L: 粗体两侧紧贴 CJK 字符 → 自动插空格。
    用配对扫描法（按行内 ** 出现顺序两两配对）避开 `** A ** ** B **` 这种相邻
    粗体被贪婪 regex 当成单个粗体的误判。表格行（`|`-leading）整行跳过。
    """
    lines = s.split("\n")
    cjk_re = re.compile(r"[一-鿿㐀-䶿]")
    for idx, line in enumerate(lines):
        if line.lstrip().startswith("|"):
            continue
        positions = [m.start() for m in re.finditer(r"\*\*", line)]
        if len(positions) < 2 or len(positions) % 2:
            continue
        # 收集 insert 点（不立即改，避免位置漂移）
        edits: list[int] = []
        for i in range(0, len(positions), 2):
            start = positions[i]
            end = positions[i + 1] + 2  # closer 之后一格
            inner = line[start + 2 : end - 2]
            if not inner or inner.strip() != inner:
                continue  # 内层带空白，留给 B 处理
            left = line[start - 1] if start > 0 else ""
            right = line[end] if end < len(line) else ""
            if left and cjk_re.match(left):
                edits.append(start)
            if right and cjk_re.match(right):
                edits.append(end)
        if not edits:
            continue
        new_line = line
        for pos in sorted(set(edits), reverse=True):
            new_line = new_line[:pos] + " " + new_line[pos:]
        lines[idx] = new_line
    return "\n".join(lines)


def classify_bold_flank(ch: str) -> str:
    """单字符分类：'space' / 'cjk_char' / 'cjk_punct' / 'ascii' / 'other'。"""
    if not ch or ch in " \t":
        return "space"
    if RE_CJK_CHAR.match(ch):
        return "cjk_char"
    if RE_CJK_PUNCT.match(ch):
        return "cjk_punct"
    if re.match(r"[A-Za-z0-9]", ch):
        return "ascii"
    return "other"


def find_cjk_punct_bold_issues(text: str) -> list[tuple[int, str, str]]:
    """M: 粗体紧贴 CJK 标点（但两侧都不是 CJK 字符——L 已自动修过的不重复报）。
    返回 [(行号 1-based, 粗体片段, 'L=...,R=...')]。
    """
    out = []
    for ln, line in enumerate(text.split("\n"), start=1):
        if line.lstrip().startswith("|"):
            continue
        for m in re.finditer(r"\*\*([^*\n]+?)\*\*", line):
            left = line[m.start() - 1] if m.start() > 0 else ""
            right = line[m.end()] if m.end() < len(line) else ""
            lc = classify_bold_flank(left)
            rc = classify_bold_flank(right)
            if lc == "cjk_char" or rc == "cjk_char":
                continue  # L 范围
            if lc == "cjk_punct" or rc == "cjk_punct":
                out.append((ln, m.group(0), f"L={lc},R={rc}"))
    return out


def find_caption_candidates(text: str) -> list[tuple[int, str]]:
    """N: 图下方短文本（≤12 字符，前一行空，前前行是 image / `</div>`）。
    返回 [(行号 1-based, 文本)]。
    """
    lines = text.split("\n")
    out = []
    for i in range(2, len(lines)):
        line = lines[i].strip()
        if not line or len(line) > 12:
            continue
        if line.startswith(("#", "-", "*", "!", "<", "|", ">", "`", "[")):
            continue
        if lines[i - 1].strip() != "":
            continue
        upup = lines[i - 2]
        if not RE_IMAGE_LINE_LIKE.match(upup):
            continue
        out.append((i + 1, line))
    return out


def find_card_candidate_sections(text: str) -> list[tuple[int, str, int]]:
    """[(标题行号 1-based, section 标题, bold 段落数)]，bold 段落 ≥4 才返回。"""
    lines = text.split("\n")
    sections: list[tuple[int, str, int, int]] = []  # (heading_line_1based, title, start_idx, end_idx)
    current_h: tuple[int, str, int] | None = None
    for i, line in enumerate(lines):
        if re.match(r'^#{1,4}\s', line):
            if current_h is not None:
                sections.append((current_h[0], current_h[1], current_h[2], i))
            current_h = (i + 1, line.lstrip("#").strip(), i + 1)
    if current_h is not None:
        sections.append((current_h[0], current_h[1], current_h[2], len(lines)))

    out: list[tuple[int, str, int]] = []
    for h_line, h_text, start, end in sections:
        count = sum(1 for j in range(start, end) if RE_BOLD_PARA_LINE.match(lines[j]))
        if count >= 4:
            out.append((h_line, h_text, count))
    return out


def is_release_notes(rel_path: str) -> bool:
    """`docs/release-notes/`、`zh/docs/release-notes/`、`ja/docs/release-notes/` 全覆盖。"""
    parts = Path(rel_path).parts
    if "release-notes" not in parts:
        return False
    # 必须出现在 docs/ 下,避免误命中其他目录的同名
    return "docs" in parts


def is_release_notes_index(rel_path: str) -> bool:
    p = Path(rel_path)
    return is_release_notes(rel_path) and p.name == "index.mdx"


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    file: str
    line: int
    pattern: str            # underline / bold_whitespace / bad_url_placeholder / url_as_label
    before: str
    after: str              # proposed fix；url_as_label 留空
    context: str            # 行内片段，前后各 30 char

    def to_dict(self) -> dict:
        return asdict(self)


def find_line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


RE_FENCE_OPEN = re.compile(r'(`{3,}|~{3,})')
RE_FENCE_CLOSE = re.compile(r'(`{3,}|~{3,})[ \t]*$')
RE_INLINE_CODE = re.compile(r'`[^`\n]+`')


def code_spans(text: str) -> list[tuple[int, int]]:
    """返回代码区间 [start, end) —— 围栏块（``` / ~~~）+ 行内 code。

    Markdown 的格式标记（++ 下划线 / ** 粗体）在代码里不生效，是字面量。
    实测 A 类 12/12、H 类 84/90 命中都落在代码区内（URL 编码串、JSON 示例、
    Java 代码片段），照修会破坏示例代码，故检测与修复两侧都必须跳过。
    """
    spans: list[tuple[int, int]] = []
    pos = 0
    fence: tuple[str, int] | None = None
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if fence is None:
            m = RE_FENCE_OPEN.match(stripped)
            if m:
                fence = (m.group(1)[0], pos)
        else:
            ch, start = fence
            m = RE_FENCE_CLOSE.match(stripped)
            if m and m.group(1)[0] == ch:
                spans.append((start, pos + len(line)))
                fence = None
        pos += len(line)
    if fence is not None:           # 未闭合围栏 → 延伸到文末
        spans.append((fence[1], len(text)))
    for m in RE_INLINE_CODE.finditer(text):
        if not any(s <= m.start() < e for s, e in spans):
            spans.append((m.start(), m.end()))
    return sorted(spans)


def in_code(pos: int, spans: list[tuple[int, int]]) -> bool:
    return any(s <= pos < e for s, e in spans)


def apply_outside_code(text: str, fn) -> str:
    """只对非代码片段套用 fn，代码区间（含行内 code）原样保留。

    会在行内 code 处把行切断，**仅适用于无行语义的纯正则修复**（A / H）。
    行敏感的修复（B 配对法、L 表格行跳过）必须改用 apply_outside_fenced_lines，
    否则切片后片段不再以 `|` 开头，表格行跳过规则失效会造出误修。
    """
    spans = code_spans(text)
    if not spans:
        return fn(text)
    out: list[str] = []
    prev = 0
    for s, e in spans:
        if s > prev:
            out.append(fn(text[prev:s]))
        out.append(text[s:e])
        prev = e
    if prev < len(text):
        out.append(fn(text[prev:]))
    return "".join(out)


def apply_outside_fenced_lines(text: str, fn) -> str:
    """按整行跳过围栏代码块，其余行成块套用 fn —— 保留行首，行语义不受影响。"""
    lines = text.split("\n")
    out: list[str] = []
    buf: list[str] = []
    in_fence = False
    fence_ch = ""

    def flush() -> None:
        if buf:
            out.append(fn("\n".join(buf)))
            buf.clear()

    for line in lines:
        stripped = line.lstrip()
        m = RE_FENCE_OPEN.match(stripped)
        if m and not in_fence:
            flush()
            in_fence, fence_ch = True, m.group(1)[0]
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            if m and m.group(1)[0] == fence_ch and RE_FENCE_CLOSE.match(stripped):
                in_fence = False
            continue
        buf.append(line)
    flush()
    return "\n".join(out)


def scan_file(path: Path) -> tuple[list[Issue], str | None]:
    """返回 (issues, 修复后内容 or None)。"""
    rel = str(path.relative_to(REPO_ROOT))
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], None

    issues: list[Issue] = []
    spans = code_spans(src)

    # A: underline
    for m in RE_UNDERLINE.finditer(src):
        if in_code(m.start(), spans):
            continue
        before = m.group(0)
        after = normalize_underline_inner(m.group(1))
        if before == after:
            continue
        issues.append(Issue(
            file=rel, line=find_line(src, m.start()), pattern="underline",
            before=before, after=after,
            context=src[max(0, m.start()-30):m.end()+30].replace("\n", "\\n"),
        ))

    # H: 破碎嵌套粗体 ****（auto-fix，剥 4 连星）
    for m in RE_NESTED_BOLD.finditer(src):
        if in_code(m.start(), spans):
            continue
        ctx_start = max(0, m.start() - 30)
        ctx_end = min(len(src), m.end() + 30)
        issues.append(Issue(
            file=rel, line=find_line(src, m.start()), pattern="nested_bold",
            before="****", after="（删除）",
            context=src[ctx_start:ctx_end].replace("\n", "\\n"),
        ))

    # B: bold whitespace — per-line 配对法。先模拟剥 ++ 让破碎粗体浮出来。
    after_underline = apply_outside_code(src, fix_underline)
    in_fence = False
    fence_ch = ""
    for line_idx, line in enumerate(after_underline.split("\n"), start=1):
        stripped_line = line.lstrip()
        m_fence = RE_FENCE_OPEN.match(stripped_line)
        if m_fence:
            if not in_fence:
                in_fence, fence_ch = True, m_fence.group(1)[0]
                continue
            if m_fence.group(1)[0] == fence_ch and RE_FENCE_CLOSE.match(stripped_line):
                in_fence = False
                continue
        if in_fence:
            continue
        for start, end, inner in find_broken_bold_pairs(line):
            stripped = inner.strip()
            before = line[start:end]
            after = f"**{stripped}**" if stripped else ""
            ctx_start = max(0, start - 30)
            ctx_end = min(len(line), end + 30)
            issues.append(Issue(
                file=rel, line=line_idx, pattern="bold_whitespace",
                before=before, after=after,
                context=line[ctx_start:ctx_end],
            ))

    # C: 废 URL 占位
    for m in RE_BAD_URL_PLACEHOLDER.finditer(src):
        before = m.group(0)
        after = m.group(1)
        issues.append(Issue(
            file=rel, line=find_line(src, m.start()), pattern="bad_url_placeholder",
            before=before, after=after,
            context=src[max(0, m.start()-30):m.end()+30].replace("\n", "\\n"),
        ))

    # D: URL-as-label（仅报告）
    for m in RE_URL_AS_LABEL.finditer(src):
        before = m.group(0)
        issues.append(Issue(
            file=rel, line=find_line(src, m.start()), pattern="url_as_label",
            before=before[:120] + ("…" if len(before) > 120 else ""),
            after="",  # 人审
            context=src[max(0, m.start()-30):min(len(src), m.end()+30)].replace("\n", "\\n"),
        ))

    # E: 空 Note 块（全仓）
    for m in RE_EMPTY_NOTE.finditer(src):
        before = m.group(0).strip("\n")
        issues.append(Issue(
            file=rel, line=find_line(src, m.start()), pattern="empty_note",
            before=before.replace("\n", "\\n"),
            after="（整段删除）",
            context=src[max(0, m.start()-30):min(len(src), m.end()+30)].replace("\n", "\\n"),
        ))

    # F: Note 标签剥除（仅 release-notes/）
    if is_release_notes(rel):
        for m in RE_NOTE_OPEN_LINE.finditer(src):
            issues.append(Issue(
                file=rel, line=find_line(src, m.start()), pattern="strip_note_open",
                before="<Note>", after="（整行删除）",
                context=src[max(0, m.start()-30):min(len(src), m.end()+30)].replace("\n", "\\n"),
            ))
        for m in RE_NOTE_CLOSE_LINE.finditer(src):
            issues.append(Issue(
                file=rel, line=find_line(src, m.start()), pattern="strip_note_close",
                before="</Note>", after="（整行删除）",
                context=src[max(0, m.start()-30):min(len(src), m.end()+30)].replace("\n", "\\n"),
            ))

    # G: 4 空格缩进矫正（仅 release-notes/index.mdx）
    if is_release_notes_index(rel):
        for m in RE_FOUR_SPACE_INDENT.finditer(src):
            line_no = find_line(src, m.start())
            # 取该行内容做 context
            line_text = src.splitlines()[line_no - 1] if line_no - 1 < len(src.splitlines()) else ""
            issues.append(Issue(
                file=rel, line=line_no, pattern="four_space_indent",
                before=f"    {line_text[4:][:50]}", after=line_text[4:][:50],
                context=line_text[:80],
            ))

    # I: CardGroup 候选段（同段内 ≥4 段 bold 行，仅报告）
    for h_line, h_text, n_bolds in find_card_candidate_sections(src):
        issues.append(Issue(
            file=rel, line=h_line, pattern="card_candidate",
            before=f"section: {h_text[:60]}",
            after=f"建议改 <CardGroup>（{n_bolds} 段 bold 标题）",
            context=h_text[:120],
        ))

    # J: 连续 ≥2 张移动端截图（仅报告）
    for start_line, count in find_mobile_screenshot_groups(src):
        issues.append(Issue(
            file=rel, line=start_line, pattern="mobile_screenshot_group",
            before=f"{count} 张移动端截图连续",
            after="建议用 flex 容器（参考 zh/ai-minutes/start-ai-minutes 范式）",
            context="",
        ))

    # K: 钉钉附件 mp4 链接（仅报告）
    for m in RE_DINGTALK_MP4_LINK.finditer(src):
        before = m.group(0)
        issues.append(Issue(
            file=rel, line=find_line(src, m.start()), pattern="dingtalk_mp4_link",
            before=before[:120] + ("…" if len(before) > 120 else ""),
            after="建议改 <video> 标签（外联 mp4 直链）",
            context=src[max(0, m.start()-30):min(len(src), m.end()+30)].replace("\n", "\\n"),
        ))

    # L: CJK 字符紧贴粗体（auto-fix，加空格）—— 用 fix 前后 diff 反推 issue
    # 必须与修复路径同样跳过代码区，否则会报出永远不会被修的 issue。
    pre_l = src
    post_l = apply_outside_fenced_lines(src, fix_bold_cjk_boundary)
    if pre_l != post_l:
        # 逐行比对，定位变更行
        pre_lines = pre_l.split("\n")
        post_lines = post_l.split("\n")
        for line_idx, (b, a) in enumerate(zip(pre_lines, post_lines), start=1):
            if b != a:
                issues.append(Issue(
                    file=rel, line=line_idx, pattern="bold_cjk_char",
                    before=b.strip()[:100],
                    after=a.strip()[:100],
                    context=b.strip()[:100],
                ))

    # M: CJK 标点紧贴粗体（仅报告，跳过 L 已修的）
    for ln, bold, flank in find_cjk_punct_bold_issues(post_l):
        issues.append(Issue(
            file=rel, line=ln, pattern="bold_cjk_punct",
            before=bold, after=f"建议加空格分隔（{flank}）",
            context="",
        ))

    # N: 图下方短文本图说候选（仅报告）
    for ln, text in find_caption_candidates(post_l):
        issues.append(Issue(
            file=rel, line=ln, pattern="caption_candidate",
            before=text, after="建议包装居中图说 div（参考 zh/ai-minutes/start-ai-minutes:42-50）",
            context="",
        ))

    # 修复（按 fix 顺序：A → H → L → B → C → E → F → G；D/I/J/K/M/N 不动）
    # A/H/L/B 是 markdown 格式标记修复，在代码区内是字面量，必须跳过（见 code_spans）。
    fixed = src
    fixed = apply_outside_code(fixed, fix_underline)
    fixed = apply_outside_code(fixed, fix_nested_bold)
    fixed = apply_outside_fenced_lines(fixed, fix_bold_cjk_boundary)
    fixed = apply_outside_fenced_lines(fixed, fix_bold_whitespace)
    fixed = fix_bad_url_placeholder(fixed)
    fixed = fix_empty_note(fixed)
    if is_release_notes(rel):
        fixed = fix_strip_note_tags(fixed)
    if is_release_notes_index(rel):
        fixed = fix_four_space_indent(fixed)

    report_only_patterns = {
        "url_as_label", "card_candidate", "mobile_screenshot_group",
        "dingtalk_mp4_link", "bold_cjk_punct", "caption_candidate",
    }
    has_changes = fixed != src and any(i.pattern not in report_only_patterns for i in issues)
    return issues, (fixed if has_changes else None)


def discover_files(root: str | None, lang: str) -> list[Path]:
    """收集待扫 mdx；按 --root / --lang 过滤。"""
    files: list[Path] = []
    for p in REPO_ROOT.rglob("*.mdx"):
        rel = p.relative_to(REPO_ROOT)
        parts = rel.parts
        if any(part in EXCLUDE_DIRS for part in parts):
            continue

        first = parts[0]
        if lang == "en" and first in ("zh", "ja", "id", "ms"):
            continue
        if lang == "zh" and first != "zh":
            continue
        if lang == "ja" and first != "ja":
            continue
        if lang == "id" and first != "id":
            continue
        if lang == "ms" and first != "ms":
            continue

        if root:
            # 命中条件：路径段含 root，或紧跟 lang 前缀后的段是 root
            if first in ("zh", "ja", "id", "ms"):
                if len(parts) < 2 or parts[1] != root:
                    continue
            else:
                if first != root:
                    continue

        files.append(p)
    files.sort()
    return files


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

PATTERN_LABEL = {
    "underline": "A. `++text++` 下划线（剥 ++）",
    "bold_whitespace": "B. `** text**` 粗体空白（修空格）",
    "bad_url_placeholder": "C. `[label](https:xxx)` 废 URL（去链留文）",
    "url_as_label": "D. label 含完整 URL（仅报告，人审）",
    "empty_note": "E. 空 `<Note>` 块（整段删）",
    "strip_note_open": "F1. release-notes `<Note>` 标签行（剥）",
    "strip_note_close": "F2. release-notes `</Note>` 标签行（剥）",
    "four_space_indent": "G. release-notes/index 4 空格缩进（夺为 0）",
    "nested_bold": "H. `**X****Y**` 破碎嵌套粗体（剥 4 连星）",
    "card_candidate": "I. 同段 ≥4 段 bold 段落（建议 CardGroup，人审）",
    "mobile_screenshot_group": "J. 连续 ≥2 张移动端截图（建议 flex 容器，人审）",
    "dingtalk_mp4_link": "K. 钉钉附件 .mp4 链接（建议 <video> 标签，人审）",
    "bold_cjk_char": "L. CJK 字符紧贴粗体（加空格分隔，auto-fix）",
    "bold_cjk_punct": "M. CJK 标点紧贴粗体（仅报告，人审）",
    "caption_candidate": "N. 图下方短文本（建议居中图说 div，人审）",
}


def write_reports(issues: list[Issue], applied: dict[str, int], scanned: int, mode: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    by_pattern: dict[str, list[Issue]] = {}
    for i in issues:
        by_pattern.setdefault(i.pattern, []).append(i)
    by_file: dict[str, int] = {}
    for i in issues:
        by_file[i.file] = by_file.get(i.file, 0) + 1

    summary = {
        "mode": mode,
        "scanned_files": scanned,
        "total_issues": len(issues),
        "by_pattern": {k: len(v) for k, v in by_pattern.items()},
        "files_with_issues": len(by_file),
        "files_applied": len(applied),
        "applied_changes_per_file": applied,
    }

    (OUTPUT_DIR / "syntax-report.json").write_text(
        json.dumps({"summary": summary, "issues": [i.to_dict() for i in issues]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md = [
        "# MDX 质量审计报告",
        "",
        f"- 模式：**{mode}**",
        f"- 扫描文件数：{scanned}",
        f"- 命中文件数：{len(by_file)}",
        f"- 命中总数：{len(issues)}",
    ]
    if mode == "apply":
        md.append(f"- 已修改文件数：{len(applied)}")
    md.append("")
    md.append("## 按模式统计")
    md.append("")
    md.append("| 模式 | 命中数 |")
    md.append("|---|---|")
    for key, label in PATTERN_LABEL.items():
        md.append(f"| {label} | {len(by_pattern.get(key, []))} |")
    md.append("")

    md.append("## Top 10 命中文件")
    md.append("")
    top = sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:10]
    for f, n in top:
        md.append(f"- `{f}` — {n}")
    md.append("")

    for key, label in PATTERN_LABEL.items():
        items = by_pattern.get(key, [])
        if not items:
            continue
        md.append(f"## {label}（前 30 例）")
        md.append("")
        md.append("| 文件 | 行 | 命中 | 修复后 |")
        md.append("|---|---|---|---|")
        for i in items[:30]:
            before = i.before.replace("|", "\\|").replace("\n", " ")
            after = (i.after or "（人审）").replace("|", "\\|").replace("\n", " ")
            md.append(f"| `{i.file}` | {i.line} | `{before}` | `{after}` |")
        if len(items) > 30:
            md.append(f"\n_（共 {len(items)} 例，余见 syntax-report.json）_")
        md.append("")

    (OUTPUT_DIR / "syntax-report.md").write_text("\n".join(md), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MDX 质量审计：++/  /废 URL 检测与修复")
    p.add_argument("--root", default=None, help="限定单产品根，如 docs / aitable")
    p.add_argument("--lang", default="all", choices=["all", "en", "zh", "ja", "id", "ms"])
    p.add_argument("--apply", action="store_true", help="实际写盘修复（默认 dry-run）")
    p.add_argument("--limit", type=int, default=0, help="只扫前 N 个文件")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    files = discover_files(args.root, args.lang)
    if args.limit:
        files = files[: args.limit]

    mode = "apply" if args.apply else "dry-run"
    print(f"[info] 模式={mode} root={args.root or 'all'} lang={args.lang} 文件数={len(files)}")

    all_issues: list[Issue] = []
    applied: dict[str, int] = {}

    for path in files:
        issues, fixed = scan_file(path)
        all_issues.extend(issues)

        actionable = [
            i for i in issues
            if i.pattern not in {
                "url_as_label", "card_candidate", "mobile_screenshot_group",
                "dingtalk_mp4_link", "bold_cjk_punct", "caption_candidate",
            }
        ]
        if args.apply and fixed is not None and actionable:
            path.write_text(fixed, encoding="utf-8")
            applied[str(path.relative_to(REPO_ROOT))] = len(actionable)

    write_reports(all_issues, applied, len(files), mode)

    print(f"[done] 命中 {len(all_issues)} 处 / {len({i.file for i in all_issues})} 文件")
    if args.apply:
        print(f"[done] 已修改 {len(applied)} 文件")
    print(f"[done] 报告：{OUTPUT_DIR / 'syntax-report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
