#!/usr/bin/env python3
"""
钉钉编辑器伪 emoji 标签 → Unicode emoji 替换。

背景：钉钉文档导出 mdx 时把图标占位写成 `[Bulb]` `[Notebook]` 等英文标签，
在 Mintlify 渲染时直接显示文字方括号，破坏阅读体验。本脚本按映射表把已知
占位转成对应 Unicode emoji。

安全保护：
1. 排除 markdown 链接 `[label](url)` —— 后跟 `(`
2. 排除围栏代码块 ``` ``` 内的内容（mermaid 图节点等真语法）
3. 排除行内代码 `…` 内的内容
4. 只替换 EMOJI_MAP 命中的键；未命中的 `[XxxYyy]` 风格标签列入报告人审

CLI:
  python3 scripts/fix_emoji_tags.py                # dry-run，全部 mdx
  python3 scripts/fix_emoji_tags.py --lang en      # 只扫英文
  python3 scripts/fix_emoji_tags.py --apply        # 实际写盘
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "emoji_tags"

EXCLUDE_DIRS = {"node_modules", ".next", ".mintlify", "scripts", ".claude", ".git"}


# ---------------------------------------------------------------------------
# 映射表 —— 仅收高置信度的占位（在仓库内人工 grep 验证过语义）
# 未列入的标签会进入 dry-run 报告人审；不会乱改。
# ---------------------------------------------------------------------------

EMOJI_MAP: dict[str, str] = {
    # 信息提示类
    "Bulb": "💡",
    "Lightbulb": "💡",
    "Light bulb": "💡",
    "Tip": "💡",
    "Notebook": "📓",
    "Guide": "📖",
    "Prompt": "💬",
    "Use case": "💼",

    # 状态 / 反馈类
    "Yeah": "✅",       # "[Yeah] Solution"
    "Dizzy": "😵",      # "[Dizzy] Pain point"
    "Cheers": "🎉",
    "Get started": "🚀",
    "Blocked": "🚫",

    # 装饰 / 引导类
    "Magic wand": "✨",
    "Magic Wand": "✨",
    "Raise hand": "🙋",
    "Raise Hand": "🙋",
    "Sanduo": "👉",      # CTA 指向符（钉钉吉祥物 "三多" 在 doc 里固定用于 "Try X >>"）
    "Broadcast": "📢",
    "Christmas": "🎄",
    "Focus": "🎯",
    "Right arrow": "➡️",
    "Arrow right": "➡️",
    "Settings": "⚙️",
    "Three Dots": "⋯",
    "Laptop": "💻",

    # 第二批扩展（dry-run 人审通过）
    "Pin": "📌",
    "Right Arrow": "➡️",
    "Right": "➡️",
    "Heart": "❤️",
    "Image": "🖼️",
    "Check": "✅",
    "Document": "📄",
    "File": "📄",
    "Inspiration": "💡",
}

# 候选 key 表（按长度降序排，长 key 优先匹配，避免 "Light bulb" 被 "Bulb" 截断）
SORTED_KEYS = sorted(EMOJI_MAP.keys(), key=len, reverse=True)
ALT = "|".join(re.escape(k) for k in SORTED_KEYS)

# 后置否定先行：排除 `[X](` 这种 markdown 链接
RE_KNOWN = re.compile(rf'\[({ALT})\](?!\()')

# 扫所有 Title-Case 候选标签（用于发现未知占位），同样排除 markdown 链接
RE_CANDIDATE = re.compile(r'\[([A-Z][a-zA-Z][a-zA-Z ]+)\](?!\()')

# 围栏代码块（``` ``` 或 ~~~ ~~~）
RE_FENCE = re.compile(r'^(?P<f>```|~~~).*?\n.*?^(?P=f)\s*$', re.M | re.S)
# 行内代码（` ... `）
RE_INLINE_CODE = re.compile(r'`[^`\n]+`')


@dataclass
class Replacement:
    file: str
    line: int
    before: str
    after: str
    key: str

    def to_dict(self) -> dict:
        return asdict(self)


def mask_code_regions(s: str) -> str:
    """把代码块 / 行内代码替换为等长占位（保持行号），避免 regex 在代码里乱命中。"""
    def _mask(m: re.Match) -> str:
        return re.sub(r'[^\n]', "\x00", m.group(0))
    s = RE_FENCE.sub(_mask, s)
    s = RE_INLINE_CODE.sub(_mask, s)
    return s


def find_line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_file(path: Path) -> tuple[list[Replacement], list[str], str | None]:
    """返回 (已知替换列表, 未知候选列表, 修复后内容 or None)。"""
    rel = str(path.relative_to(REPO_ROOT))
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], [], None

    masked = mask_code_regions(src)

    # 已知替换
    repls: list[Replacement] = []
    for m in RE_KNOWN.finditer(masked):
        key = m.group(1)
        repls.append(Replacement(
            file=rel,
            line=find_line(src, m.start()),
            before=m.group(0),
            after=EMOJI_MAP[key],
            key=key,
        ))

    # 未知候选（用于报告，不修改）
    unknown: list[str] = []
    for m in RE_CANDIDATE.finditer(masked):
        key = m.group(1)
        if key not in EMOJI_MAP:
            unknown.append(key)

    if not repls:
        return repls, unknown, None

    # 在原文上 apply（不在 masked 上 —— masked 只用来定位）
    fixed = RE_KNOWN.sub(lambda m: EMOJI_MAP[m.group(1)], mask_code_regions(src))
    # 把 mask 区原文还原
    out_chars = list(fixed)
    for i, c in enumerate(src):
        if i < len(out_chars) and out_chars[i] == "\x00":
            out_chars[i] = c
    # 但 mask + sub 改变了长度，简单做法直接对原文做替换（安全因为 mask 已经把代码区清零，
    # RE_KNOWN 在 masked 命中的位置在原文上 [key] 也存在；用 finditer 收集 (start,end,emoji) 再倒序替换）
    spans = [(m.start(), m.end(), EMOJI_MAP[m.group(1)]) for m in RE_KNOWN.finditer(masked)]
    fixed = src
    for start, end, emoji in reversed(spans):
        fixed = fixed[:start] + emoji + fixed[end:]

    return repls, unknown, fixed


def discover_files(lang: str) -> list[Path]:
    files: list[Path] = []
    for p in REPO_ROOT.rglob("*.mdx"):
        rel = p.relative_to(REPO_ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        first = rel.parts[0] if rel.parts else ""
        flang = first if first in ("zh", "ja") else "en"
        if lang != "all" and flang != lang:
            continue
        files.append(p)
    files.sort()
    return files


def write_reports(
    repls: list[Replacement],
    unknown_counter: Counter,
    applied: dict[str, int],
    scanned: int,
    mode: str,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    by_key = Counter(r.key for r in repls)
    by_file: dict[str, int] = {}
    for r in repls:
        by_file[r.file] = by_file.get(r.file, 0) + 1

    summary = {
        "mode": mode,
        "scanned_files": scanned,
        "total_replacements": len(repls),
        "by_key": dict(by_key.most_common()),
        "files_with_replacements": len(by_file),
        "files_applied": len(applied),
        "applied_per_file": applied,
        "unknown_candidates_top": dict(unknown_counter.most_common(50)),
    }

    (OUTPUT_DIR / "report.json").write_text(
        json.dumps({"summary": summary, "replacements": [r.to_dict() for r in repls]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md = [
        "# 伪 emoji 标签 → Unicode 替换报告",
        "",
        f"- 模式：**{mode}**",
        f"- 扫描文件数：{scanned}",
        f"- 命中文件数：{len(by_file)}",
        f"- 替换总数：{len(repls)}",
    ]
    if mode == "apply":
        md.append(f"- 已修改文件数：{len(applied)}")
    md.append("")

    md.append("## 按 emoji key 统计")
    md.append("")
    md.append("| Key | Emoji | 命中数 |")
    md.append("|---|---|---|")
    for key, n in by_key.most_common():
        md.append(f"| `[{key}]` | {EMOJI_MAP[key]} | {n} |")
    md.append("")

    md.append("## Top 20 命中文件")
    md.append("")
    for f, n in sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:20]:
        md.append(f"- `{f}` — {n}")
    md.append("")

    md.append("## 未知候选标签（人审决定是否扩 EMOJI_MAP）")
    md.append("")
    md.append("| 候选 | 出现次数 |")
    md.append("|---|---|")
    for k, n in unknown_counter.most_common(50):
        md.append(f"| `[{k}]` | {n} |")
    md.append("")

    (OUTPUT_DIR / "report.md").write_text("\n".join(md), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="伪 emoji 标签转 Unicode")
    p.add_argument("--lang", default="all", choices=["all", "en", "zh", "ja"])
    p.add_argument("--apply", action="store_true", help="实际写盘（默认 dry-run）")
    p.add_argument("--limit", type=int, default=0)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    files = discover_files(args.lang)
    if args.limit:
        files = files[: args.limit]

    mode = "apply" if args.apply else "dry-run"
    print(f"[info] 模式={mode} lang={args.lang} 文件数={len(files)}")

    all_repls: list[Replacement] = []
    unknown_counter: Counter = Counter()
    applied: dict[str, int] = {}

    for path in files:
        repls, unknown, fixed = scan_file(path)
        all_repls.extend(repls)
        unknown_counter.update(unknown)

        if args.apply and fixed is not None and repls:
            path.write_text(fixed, encoding="utf-8")
            applied[str(path.relative_to(REPO_ROOT))] = len(repls)

    write_reports(all_repls, unknown_counter, applied, len(files), mode)

    print(f"[done] 替换 {len(all_repls)} 处 / {len({r.file for r in all_repls})} 文件")
    print(f"[done] 未知候选 {len(unknown_counter)} 种（人审决定是否补 EMOJI_MAP）")
    if args.apply:
        print(f"[done] 已修改 {len(applied)} 文件")
    print(f"[done] 报告：{OUTPUT_DIR / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
