"""
convert_admonitions.py

将 zh/docs/**/*.mdx 中 markdown-it / Docusaurus 风格的 `:::xxx` ... `:::`
高亮块转为 Mintlify JSX 组件 (<Note>/<Tip>/<Info>/<Warning>/<Check>).

类型映射:
  :::            -> <Note>      # 裸 ::: 默认 = 提示
  :::tip / tips  -> <Tip>
  :::info        -> <Info>
  :::warning     -> <Warning>
  :::danger      -> <Warning>   # Mintlify 无 Danger，用 Warning 最接近
  :::success     -> <Check>

算法（线性扫描，栈式配对）:
  - 跳过代码块 (``` 之间)
  - 行 = `^\s*:::([a-zA-Z]*)\s*$` 时:
      - 若 group(1) 非空，或栈为空: 开块，类型入栈
      - 否则: 闭块，类型出栈
  - 闭标签从栈弹出的类型决定 (与对应开标签匹配)

边界:
  - 嵌套理论支持（栈），实测 zh/docs 全无嵌套
  - 内部含 markdown 标题: 保留 (Mintlify <Note> 内部可含 ##)

用法:
  python3 scripts/lint/convert_admonitions.py             # dry-run 统计
  python3 scripts/lint/convert_admonitions.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "zh" / "docs"

COL = re.compile(r"^(\s*):::([a-zA-Z]*)\s*$")

TYPE_MAP = {
    "":         "Note",
    "tip":      "Tip",
    "tips":     "Tip",
    "info":     "Info",
    "warning":  "Warning",
    "danger":   "Warning",
    "success":  "Check",
    "note":     "Note",
}


def process(path: Path, apply: bool) -> tuple[int, int, list[str]]:
    """返回 (opened, closed, unmapped_types)。"""
    text = path.read_text(encoding="utf-8")
    fm_m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    body_start = fm_m.end() if fm_m else 0
    head = text[:body_start]
    body = text[body_start:]

    lines = body.split("\n")
    new_lines = list(lines)
    in_code = False
    stack: list[str] = []  # 存 component name, e.g. ["Note", "Warning"]
    opened = closed = 0
    unmapped: list[str] = []

    for i, l in enumerate(lines):
        if l.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = COL.match(l)
        if not m:
            continue
        indent = m.group(1)
        kind = m.group(2).lower()

        is_open = bool(kind) or not stack
        if is_open:
            comp = TYPE_MAP.get(kind)
            if comp is None:
                unmapped.append(kind)
                continue
            stack.append(comp)
            new_lines[i] = f"{indent}<{comp}>"
            opened += 1
        else:
            comp = stack.pop()
            new_lines[i] = f"{indent}</{comp}>"
            closed += 1

    if (opened or closed) and apply:
        path.write_text(head + "\n".join(new_lines), encoding="utf-8")

    return opened, closed, unmapped


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    files = 0
    sum_open = sum_close = 0
    all_unmapped: Counter = Counter()
    leftover_files: list[Path] = []
    for p in sorted(ROOT.rglob("*.mdx")):
        o, c, um = process(p, args.apply)
        if o or c:
            files += 1
            sum_open += o
            sum_close += c
            if o != c:
                leftover_files.append(p.relative_to(ROOT.parent.parent))
            print(f"  {p.relative_to(ROOT.parent.parent)}  open={o} close={c}")
        for k in um:
            all_unmapped[k] += 1
    print()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] {files} files  /  opened={sum_open}  closed={sum_close}")
    if all_unmapped:
        print(f"  unmapped types: {dict(all_unmapped)}")
    if leftover_files:
        print(f"  asymmetric files (open != close): {len(leftover_files)}")
        for f in leftover_files: print(f"    {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
