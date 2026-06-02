"""strip_alidocs_referrer.py — 把 mdx 里 ![alt](alidocs-url) 改写成 <img referrerPolicy="no-referrer">

用法:
  python scripts/strip_alidocs_referrer.py --root zh/docs              # dry-run
  python scripts/strip_alidocs_referrer.py --root zh/docs --apply      # 落盘
  python scripts/strip_alidocs_referrer.py --root zh/aitable --apply
  python scripts/strip_alidocs_referrer.py --root ja/docs --apply

为什么要改:
  alidocs.oss-cn-zhangjiakou.aliyuncs.com 这个 OSS bucket 配了 referer 防盗链黑名单，
  把 *.dingtalk.io 拒掉。线上 help.dingtalk.io 加载这些图片全 403 + ORB 破图。
  改成 <img referrerPolicy="no-referrer"> 后浏览器不发 Referer 头，OSS 黑名单 miss → 200。

策略:
  - 仅匹配 markdown ![alt](url) 形式中 url 是 alidocs.oss-cn-zhangjiakou.aliyuncs.com 的
  - 跳过已经是 <img referrerPolicy="no-referrer"> 的（幂等）
  - alt-text HTML escape：& < > "
  - URL 整体保留（含 ?x-oss-process= 等 query）
  - 仅改 mdx 文件的字符串，不动其它结构
  - 默认 dry-run，--apply 才落盘
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ALIDOCS_HOST = "alidocs.oss-cn-zhangjiakou.aliyuncs.com"
# 匹配 ![alt](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/...)
# alt 允许换行外的任意字符（不含 ]）；url 不含空格、不含 )
PATTERN = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<url>https://" + re.escape(ALIDOCS_HOST) + r"/[^)\s]+)\)"
)


def html_escape_attr(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def replace_in_text(text: str) -> tuple[str, int]:
    count = 0

    def _sub(m: re.Match) -> str:
        nonlocal count
        alt = m.group("alt")
        url = m.group("url")
        count += 1
        alt_attr = html_escape_attr(alt)
        return f'<img src="{url}" referrerPolicy="no-referrer" alt="{alt_attr}" />'

    new_text = PATTERN.sub(_sub, text)
    return new_text, count


def process_file(path: Path, apply: bool) -> int:
    original = path.read_text(encoding="utf-8")
    new_text, count = replace_in_text(original)
    if count == 0:
        return 0
    if apply and new_text != original:
        path.write_text(new_text, encoding="utf-8")
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, help="相对仓库根的目录，如 zh/docs / ja/docs / zh/aitable")
    parser.add_argument("--apply", action="store_true", help="不加 --apply 即 dry-run")
    args = parser.parse_args()

    root = (REPO_ROOT / args.root).resolve()
    if not root.is_dir():
        print(f"ERROR: {root} 不存在或不是目录", file=sys.stderr)
        return 2

    mdx_files = sorted(root.rglob("*.mdx"))
    print(f"扫描 {len(mdx_files)} 篇 mdx，root={root.relative_to(REPO_ROOT)}，apply={args.apply}")

    total = 0
    changed_files = 0
    per_file: list[tuple[Path, int]] = []
    for f in mdx_files:
        n = process_file(f, args.apply)
        if n:
            changed_files += 1
            total += n
            per_file.append((f, n))

    print()
    print(f"结果：命中 {total} 处，覆盖 {changed_files} 篇 mdx")
    if per_file:
        print("Top 20 改动最多文件：")
        for f, n in sorted(per_file, key=lambda x: -x[1])[:20]:
            print(f"  {n:4d}  {f.relative_to(REPO_ROOT)}")

    if not args.apply:
        print()
        print("[DRY-RUN] 加 --apply 落盘")
    else:
        print()
        print("[APPLIED]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
