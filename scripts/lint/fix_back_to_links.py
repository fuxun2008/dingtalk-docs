"""
fix_back_to_links.py

清理 zh/docs/**/*.mdx 中钉钉编辑器导出的引用块返回链接残骸：
  ▍返回「[X](href) 」目录页
  ▍返回「 **X** 」目录页
  ▍返回「 [**X**](href) 」目录页同办公平台出品 ——
  ...
统一为：
  **返回[X](href)目录页**       （X 是链接时）
  **返回 X 目录页**             （X 是纯文本/纯粗体时）

对齐英文 commit 5075cf3 的 `**Back to [X](href)**` 风格。

ja 模式（语序不同：动词在末尾）：
  ▍「 **X** 」目次ページに戻る
  ▍「 [**X**](href) 」目次ページへ戻る
  ▍「 X 」の目次ページに戻る
  → **[X](href)目次ページに戻る** / **X 目次ページに戻る**

用法:
  python3 scripts/lint/fix_back_to_links.py                   # dry-run，默认 zh
  python3 scripts/lint/fix_back_to_links.py --lang ja --apply # 切到 ja 并写回
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# zh：动词「返回」在行首
ZH_MAIN_RE = re.compile(r"▍返回「\s*(.*?)\s*」目录页[^\n]*")
# ja：动词「戻る」在末尾，可选「の」、可选「に」/「へ」
JA_MAIN_RE = re.compile(r"▍「\s*(.*?)\s*」(?:の)?目次ページ[にへ]戻る[^\n]*")


def transform_inner(inner: str) -> str:
    """把「...」内的 X 部分转成 markdown 链接 / 粗体的正常形态。"""
    # [**X**](href) → [X](href)（剥内嵌粗体避免后续整体加粗时嵌套）
    m = re.fullmatch(r"\[\*\*(.+?)\*\*\]\((.+?)\)", inner)
    if m:
        return f"[{m.group(1)}]({m.group(2)})"
    # [X](href) → 保持
    if re.fullmatch(r"\[.+?\]\(.+?\)", inner):
        return inner
    # **X** → X（外层会整体加粗，避免嵌套粗体）
    m = re.fullmatch(r"\*\*(.+?)\*\*", inner)
    if m:
        return m.group(1)
    # 纯文本
    return inner


def replace_zh(match: re.Match) -> str:
    inner = match.group(1)
    normalized = transform_inner(inner)
    # 链接形态：紧贴 "返回[X](href)目录页"
    if re.fullmatch(r"\[.+?\]\(.+?\)", normalized):
        return f"**返回{normalized}目录页**"
    # 纯文本/粗体：加空格 "返回 X 目录页"
    return f"**返回 {normalized} 目录页**"


def replace_ja(match: re.Match) -> str:
    inner = match.group(1)
    normalized = transform_inner(inner)
    # 链接形态：紧贴 "[X](href)目次ページに戻る"
    if re.fullmatch(r"\[.+?\]\(.+?\)", normalized):
        return f"**{normalized}目次ページに戻る**"
    # 纯文本/粗体：加空格 "X 目次ページに戻る"
    return f"**{normalized} 目次ページに戻る**"


EN_EXCLUDE_TOP = {"zh", "ja", "archive", "scripts", "node_modules", ".git", ".claude", "images"}


def process(path: Path, regex: re.Pattern, replacer, apply: bool) -> int:
    text = path.read_text(encoding="utf-8")
    new_text, n = regex.subn(replacer, text)
    if n and apply:
        path.write_text(new_text, encoding="utf-8")
    return n


def iter_mdx_files(lang: str):
    if lang in ("zh", "ja"):
        yield from sorted((REPO_ROOT / lang).rglob("*.mdx"))
        return
    for p in sorted(REPO_ROOT.rglob("*.mdx")):
        rel_parts = p.relative_to(REPO_ROOT).parts
        if rel_parts and rel_parts[0] in EN_EXCLUDE_TOP:
            continue
        yield p


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", choices=["zh", "ja"], default="zh",
                        help="zh 走『返回...目录页』，ja 走『...目次ページに/へ戻る』")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.lang == "zh":
        regex, replacer = ZH_MAIN_RE, replace_zh
    else:
        regex, replacer = JA_MAIN_RE, replace_ja

    total_files = 0
    total_hits = 0
    for p in iter_mdx_files(args.lang):
        n = process(p, regex, replacer, args.apply)
        if n:
            total_files += 1
            total_hits += n
            rel = p.relative_to(REPO_ROOT)
            print(f"  {rel}  ({n} hits)")

    print()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] lang={args.lang} {total_files} files, {total_hits} back-to-link lines normalized")
    return 0


if __name__ == "__main__":
    sys.exit(main())
