"""
fix_priority_placeholders.py

把三语 mdx 中钉钉编辑器导出的 `[优先级: N]` / `[優先度: N]` / `[Priority: N]` 编号占位符
转为 markdown 数字列表前缀 `N. `。

输入示例：
  [优先级: 1] 新建一个钉钉文档
  [优先级: 2]点击插入功能里的"快速分栏"
  \[优先级: 1\] 文档管理
  [優先度: 1] DingTalkドキュメントを新規作成します
  [Priority: 1] Create a new DingTalk Doc
输出：
  1. 新建一个钉钉文档
  2. 点击插入功能里的"快速分栏"
  1. 文档管理
  1. DingTalkドキュメントを新規作成します
  1. Create a new DingTalk Doc

对齐英文 commit cae9ac8 的 `[Priority: N]` → markdown 数字列表风格。

用法:
  python3 scripts/lint/fix_priority_placeholders.py                       # dry-run，默认 zh
  python3 scripts/lint/fix_priority_placeholders.py --lang ja --apply    # 切到 ja 并写回
  python3 scripts/lint/fix_priority_placeholders.py --lang en --apply    # en（仓库根，排除 zh/ja/archive/scripts）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EN_EXCLUDE_TOP = {"zh", "ja", "archive", "scripts", "node_modules", ".git", ".claude", "images"}

# 兼容转义 `\[...\]` 与非转义 `[...]`；冒号兼容半角全角；编号后空格 0 或多个
# 占位符词头三语兼容：优先级（zh）/ 優先度（ja）/ Priority（en，大小写兼容）
PRIORITY_RE = re.compile(
    r"\\?\[(?:优先级|優先度|[Pp]riority)\s*[:：]\s*(\d+)\\?\]\s*"
)


def process(path: Path, apply: bool) -> int:
    text = path.read_text(encoding="utf-8")
    new_text, n = PRIORITY_RE.subn(lambda m: f"{m.group(1)}. ", text)
    if n and apply:
        path.write_text(new_text, encoding="utf-8")
    return n


def iter_mdx_files(lang: str):
    """根据 lang 返回需处理的 mdx 列表。en 走仓库根但排除 zh/ja/archive/scripts。"""
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
    parser.add_argument("--lang", choices=["zh", "ja", "en"], default="zh")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    total_files = 0
    total_hits = 0
    for p in iter_mdx_files(args.lang):
        n = process(p, args.apply)
        if n:
            total_files += 1
            total_hits += n
            rel = p.relative_to(REPO_ROOT)
            print(f"  {rel}  ({n} hits)")

    print()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}] lang={args.lang} {total_files} files, {total_hits} priority placeholders normalized")
    return 0


if __name__ == "__main__":
    sys.exit(main())
