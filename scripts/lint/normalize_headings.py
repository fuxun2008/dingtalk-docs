"""
normalize_headings.py

栈式归一化 zh/docs/**/*.mdx 的标题层级。

规则：
  frontmatter.title 视为 h1（Mintlify 唯一 H1）
  正文从 h2 开始；任何"层级跳跃"(prev+2 及以上) 一律收紧为 prev+1
  代码块内的 # 不处理

算法（线性走一遍，prev_level 起 1）：
  cur = 当前 heading 级
  if cur > prev + 1:  collapse_to = prev + 1; delta = cur - collapse_to;
                      把 cur 及"其后所有级别 ≥ cur"的标题都减 delta
                      （但减后不得 < 2，因为正文最高 h2）

实现简化版：每次遇到跳跃，重写当前行 + 维护一个 prev。
对深层跳跃 (h2→h5) 的连带后续同级标题，统一向上收紧。

用法:
  python3 scripts/lint/normalize_headings.py             # dry-run
  python3 scripts/lint/normalize_headings.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "zh" / "docs"
HEADING = re.compile(r"^(#{2,6})(\s+\S.*)$")


def normalize_file_headings(lines: list[str]) -> tuple[list[str], int]:
    """走一遍，收紧跳跃。返回 (新 lines, 修改数)."""
    in_code = False
    prev = 1  # frontmatter.title = h1
    # 记录每次"原始→目标"的偏移；一旦某父节收紧，后续更深的同级也按比例收紧
    # 简化：用 stack 跟踪 (original_level, normalized_level)
    stack: list[tuple[int, int]] = []  # 不含 root
    changed = 0
    new_lines = list(lines)

    for i, l in enumerate(lines):
        if l.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = HEADING.match(l)
        if not m:
            continue
        orig = len(m.group(1))
        rest = m.group(2)

        # 弹出栈中比 orig 深的层级（关闭子节）
        while stack and stack[-1][0] >= orig:
            stack.pop()

        parent_norm = stack[-1][1] if stack else 1
        # 目标级 = parent_norm + 1（保证不跳跃）
        norm = parent_norm + 1
        # 但若原本就 ≤ parent_norm+1 也保持不变
        if orig <= parent_norm + 1:
            norm = orig
        if norm < 2:
            norm = 2
        if norm > 6:
            norm = 6

        stack.append((orig, norm))

        if norm != orig:
            new_lines[i] = "#" * norm + rest
            changed += 1
        prev = norm

    return new_lines, changed


def process(path: Path, apply: bool) -> int:
    text = path.read_text(encoding="utf-8")
    fm_m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    body_start = fm_m.end() if fm_m else 0
    head = text[:body_start]
    body = text[body_start:]
    lines = body.split("\n")
    new_lines, changed = normalize_file_headings(lines)
    if changed and apply:
        path.write_text(head + "\n".join(new_lines), encoding="utf-8")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    files = 0
    total = 0
    for p in sorted(ROOT.rglob("*.mdx")):
        n = process(p, args.apply)
        if n:
            files += 1
            total += n
            print(f"  {p.relative_to(ROOT.parent.parent)}  ({n} headings normalized)")
    print()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] {files} files, {total} headings normalized")
    return 0


if __name__ == "__main__":
    sys.exit(main())
