#!/usr/bin/env python3
"""
一次性脚本：为 zh/open/**/*.mdx 在 ja/open/ 下生成占位骨架。

占位符与 translate_mdx_batch.py 的 is_placeholder() 完全匹配，
让翻译流水线的"断点续跑 + 跳过已译"机制生效。

占位结构：
  ---
  title: "TODO 翻訳: <zh title>"
  description: ""
  ---
  {/* TODO: <zh 相对路径>から翻訳 */}

用法：
  python3 scripts/scaffold_ja_open.py           # 预演（不写）
  python3 scripts/scaffold_ja_open.py --write   # 写入 ja/open/
  python3 scripts/scaffold_ja_open.py --write --force  # 覆盖已存在的占位
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
ZH_OPEN = REPO_ROOT / "zh" / "open"
JA_OPEN = REPO_ROOT / "ja" / "open"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
TITLE_RE = re.compile(r"^title:\s*[\"']?(.*?)[\"']?\s*$", re.MULTILINE)


def extract_zh_title(text: str) -> str:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return ""
    fm = m.group(1)
    t = TITLE_RE.search(fm)
    return t.group(1).strip() if t else ""


def build_placeholder(zh_title: str, zh_rel: str) -> str:
    safe_title = zh_title.replace('"', '\\"') if zh_title else ""
    return (
        "---\n"
        f'title: "TODO 翻訳: {safe_title}"\n'
        'description: ""\n'
        "---\n"
        "\n"
        f"{{/* TODO: zh/{zh_rel} から翻訳 */}}\n"
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="写入 ja/open/（默认只预演）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的占位文件")
    args = ap.parse_args(argv)

    if not ZH_OPEN.exists():
        print(f"[error] {ZH_OPEN} 不存在", file=sys.stderr)
        return 1

    created = 0
    skipped_exists = 0
    overwritten = 0
    failed: list[tuple[str, str]] = []

    for zh_mdx in sorted(ZH_OPEN.rglob("*.mdx")):
        rel = zh_mdx.relative_to(ZH_OPEN)
        ja_mdx = JA_OPEN / rel
        rel_str = f"open/{rel}"
        try:
            text = zh_mdx.read_text(encoding="utf-8")
        except Exception as e:
            failed.append((rel_str, f"read source: {e}"))
            continue

        zh_title = extract_zh_title(text)
        placeholder = build_placeholder(zh_title, rel_str)

        if ja_mdx.exists() and not args.force:
            skipped_exists += 1
            continue

        if not args.write:
            created += 1
            continue

        ja_mdx.parent.mkdir(parents=True, exist_ok=True)
        try:
            if ja_mdx.exists():
                overwritten += 1
            else:
                created += 1
            ja_mdx.write_text(placeholder, encoding="utf-8")
        except Exception as e:
            failed.append((rel_str, f"write target: {e}"))

    print(f"[scan] 源文件总数: {sum(1 for _ in ZH_OPEN.rglob('*.mdx'))}")
    print(f"[stat] 新建: {created} / 覆盖: {overwritten} / 跳过(已存在): {skipped_exists} / 失败: {len(failed)}")
    if failed:
        print("[failed]")
        for rel, err in failed[:20]:
            print(f"  - {rel}  {err}")
    if not args.write:
        print(f"[hint] 加 --write 才会写入；预览第一篇占位示例：")
        first = next(ZH_OPEN.rglob("*.mdx"), None)
        if first:
            rel = first.relative_to(ZH_OPEN)
            print("---")
            print(build_placeholder(extract_zh_title(first.read_text(encoding="utf-8")), f"open/{rel}"))
            print("---")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
