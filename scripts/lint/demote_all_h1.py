"""
demote_all_h1.py

将 zh/docs/**/*.mdx 中正文（frontmatter 之后）的所有 H1 (`# ...`) 统一降级为 H2 (`## ...`)。

为什么:
- Mintlify 自动用 frontmatter.title 作为页面唯一 H1
- en/ja 镜像 0 处正文 H1，证明规范本就如此
- zh 大量文件把"操作说明" / "了解 xxx" / 章节标题写成了 H1，导致：
  - SEO 重复 H1
  - 标题层级跳跃（H1 直接到 H3）

代码块内的 `# ...` (Python/Shell 注释) 不处理。

用法:
  python3 scripts/lint/demote_all_h1.py             # 报告
  python3 scripts/lint/demote_all_h1.py --apply     # 应用
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "zh" / "docs"


def process(path: Path, apply: bool) -> int:
    text = path.read_text(encoding="utf-8")
    fm_m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    body_start = fm_m.end() if fm_m else 0
    head = text[:body_start]
    body = text[body_start:]

    lines = body.split("\n")
    in_code = False
    changed = 0
    for i, l in enumerate(lines):
        if l.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if re.match(r"^# .+", l):
            lines[i] = "#" + l   # `# x` → `## x`
            changed += 1
    if changed and apply:
        path.write_text(head + "\n".join(lines), encoding="utf-8")
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
            print(f"  {p.relative_to(ROOT.parent.parent)}  ({n} H1)")
    print()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] {files} files, {total} H1 demoted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
