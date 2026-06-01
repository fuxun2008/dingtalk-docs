"""
fix_garbage_descriptions.py

清理 zh/docs/**/*.mdx frontmatter 中 description 为垃圾值的情况：
  - description: ":::"
  - description: "|"
  - description: ""

策略：从正文提取首句作为 description（截断 80 字符）；提不到则删除该行。

跳过：
  - frontmatter 中无 description 字段 → 不变
  - description 含有意义内容（≥ 4 字符且不全是标点） → 不变

用法:
  python3 scripts/lint/fix_garbage_descriptions.py             # dry-run
  python3 scripts/lint/fix_garbage_descriptions.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "zh" / "docs"

DESC_RE = re.compile(r'^description:\s*"(.*)"\s*$', re.M)
# 垃圾值：纯标点 / 太短 / 仅 :::
GARBAGE = re.compile(r'^[\s:|\-=#*~_`]*$')


def extract_first_sentence(body: str) -> str:
    """从正文取一个干净的句子作为 description，找不到返回空串。"""
    in_code = False
    in_jsx = 0
    for raw in body.split("\n"):
        l = raw.strip()
        if l.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        # 跳过 frontmatter / 标题 / 图片 / 链接 only / JSX 标签行 / 分隔线 / 列表项 / 表格
        if not l or l.startswith(("#", "!", "<", "|", "-", "*", "[", ":::", "---")):
            continue
        # 跳过单纯链接：[xx](yy)
        if re.match(r"^\[.*\]\(.*\)\s*$", l):
            continue
        # 取 80 字符内首句
        sent = l[:80]
        # 截到句号 / 问号
        m = re.search(r"[。！？!?]", sent)
        if m:
            sent = sent[: m.end()]
        return sent
    return ""


def process(path: Path, apply: bool) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    fm_m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not fm_m:
        return ("NO_FM", "")
    fm = fm_m.group(1)
    desc_m = DESC_RE.search(fm)
    if not desc_m:
        return ("NO_DESC", "")
    cur = desc_m.group(1)
    if not GARBAGE.match(cur) and len(cur) >= 4:
        return ("OK", cur)
    body = text[fm_m.end():]
    new_desc = extract_first_sentence(body)
    # 替换或删除
    if new_desc:
        new_fm = DESC_RE.sub(f'description: "{new_desc}"', fm)
        action = f"REPLACE -> {new_desc!r}"
    else:
        # 删除该行（连带换行）
        new_fm = re.sub(r'^description:.*\n?', '', fm, count=1, flags=re.M)
        action = "DELETE"
    if apply:
        new_text = "---\n" + new_fm + "\n---\n" + text[fm_m.end():]
        # 防止多余空行
        new_text = re.sub(r'\n{3,}', '\n\n', new_text, count=1)
        path.write_text(new_text, encoding="utf-8")
    return (action, cur)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    counts: dict[str, int] = {}
    for p in sorted(ROOT.rglob("*.mdx")):
        action, cur = process(p, args.apply)
        key = action.split(" ")[0]
        counts[key] = counts.get(key, 0) + 1
        if key in ("REPLACE", "DELETE"):
            print(f"  {p.relative_to(ROOT.parent.parent)}  {action}  (was: {cur!r})")
    print()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}]  " + "  ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
