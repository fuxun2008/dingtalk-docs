#!/usr/bin/env python3
"""
MDX 质量审计：扫所有 mdx，检出多类问题并按需修复。

通用模式（全仓）：
A. `++text++` 下划线语法（Mintlify 不支持）→ 剥 `++`，保留内层；若内层是 `**…**` 且内侧紧贴空格，挤出来
B. `** text**` 粗体空白破坏（仅 LEADING-space 安全检测；TRAILING-space 会跟相邻粗体打架）→ 修
C. `[label](https:xxx)` 形态废 URL（协议后跟纯字母≤8 字符，无 `//`）→ 去链留文案
D. `[https://...full-url...](url)` label 含完整 URL → 仅报告，人审
E. 空 `<Note>` 块（`<Note>---</Note>` / `<Note></Note>` / 跨行空 Note）→ 整段删除

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


def scan_file(path: Path) -> tuple[list[Issue], str | None]:
    """返回 (issues, 修复后内容 or None)。"""
    rel = str(path.relative_to(REPO_ROOT))
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], None

    issues: list[Issue] = []

    # A: underline
    for m in RE_UNDERLINE.finditer(src):
        before = m.group(0)
        after = normalize_underline_inner(m.group(1))
        if before == after:
            continue
        issues.append(Issue(
            file=rel, line=find_line(src, m.start()), pattern="underline",
            before=before, after=after,
            context=src[max(0, m.start()-30):m.end()+30].replace("\n", "\\n"),
        ))

    # B: bold whitespace — per-line 配对法。先模拟剥 ++ 让破碎粗体浮出来。
    after_underline = fix_underline(src)
    for line_idx, line in enumerate(after_underline.split("\n"), start=1):
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

    # 修复（按 fix 顺序：A → B → C → E → F → G；D 不动）
    fixed = src
    fixed = fix_underline(fixed)
    fixed = fix_bold_whitespace(fixed)
    fixed = fix_bad_url_placeholder(fixed)
    fixed = fix_empty_note(fixed)
    if is_release_notes(rel):
        fixed = fix_strip_note_tags(fixed)
    if is_release_notes_index(rel):
        fixed = fix_four_space_indent(fixed)

    has_changes = fixed != src and any(i.pattern != "url_as_label" for i in issues)
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
        if lang == "en" and first in ("zh", "ja"):
            continue
        if lang == "zh" and first != "zh":
            continue
        if lang == "ja" and first != "ja":
            continue

        if root:
            # 命中条件：路径段含 root，或紧跟 lang 前缀后的段是 root
            if first in ("zh", "ja"):
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
    p.add_argument("--lang", default="all", choices=["all", "en", "zh", "ja"])
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

        actionable = [i for i in issues if i.pattern != "url_as_label"]
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
