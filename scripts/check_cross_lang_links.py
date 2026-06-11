#!/usr/bin/env python3
"""跨语种内链 lint — 防止开放平台 mdx 文档跨语种跳转。

规则：
- en 文档（open/**/*.mdx）：内链应只用 /open/...，禁止 /zh/open/ 或 /ja/open/
- ja 文档（ja/open/**/*.mdx）：内链应只用 /ja/open/...，禁止 /zh/open/ 或 /open/（无前缀会跳 en）

用法：
    python scripts/check_cross_lang_links.py [--root <repo-root>]

退出码：
    0 — 全部通过
    1 — 命中跨语种链接（逐行打印 file:line:content）
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# (目录前缀, [(正则, 说明)]) — 每条规则就是一个绝对禁止出现的 pattern
_INVALID_DOMAIN = (
    re.compile(r"open\.dingtalk\.io"),
    "open.dingtalk.io 域名未部署，应改为内部相对路径 /open/...",
)

RULES: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "open": [
        (re.compile(r"\]\(/zh/open/"), "en 文档不应跳转到 zh 文档"),
        (re.compile(r"\]\(/ja/open/"), "en 文档不应跳转到 ja 文档"),
        (re.compile(r'href="/zh/open'), "en 文档 href 不应跳转到 zh 文档"),
        (re.compile(r'href="/ja/open'), "en 文档 href 不应跳转到 ja 文档"),
        _INVALID_DOMAIN,
    ],
    "ja/open": [
        (re.compile(r"\]\(/zh/open/"), "ja 文档不应跳转到 zh 文档"),
        (re.compile(r"\]\(/open/"), "ja 文档不应跳转到 en 文档（无语言前缀）"),
        (re.compile(r'href="/zh/open'), "ja 文档 href 不应跳转到 zh 文档"),
        (re.compile(r'href="/open'), "ja 文档 href 不应跳转到 en 文档（无语言前缀）"),
        _INVALID_DOMAIN,
    ],
}


def scan(repo_root: Path) -> int:
    hits: list[str] = []
    for rel_dir, rules in RULES.items():
        base = repo_root / rel_dir
        if not base.exists():
            continue
        for mdx in base.rglob("*.mdx"):
            try:
                lines = mdx.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for lineno, line in enumerate(lines, start=1):
                for pattern, why in rules:
                    if pattern.search(line):
                        rel = mdx.relative_to(repo_root)
                        hits.append(f"{rel}:{lineno}: [{why}] {line.strip()}")
    if hits:
        print(f"跨语种内链 lint 失败 — 命中 {len(hits)} 处：", file=sys.stderr)
        for h in hits:
            print(h, file=sys.stderr)
        return 1
    print("跨语种内链 lint 通过 — 0 命中")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="仓库根目录（默认：脚本所在 scripts/ 的父目录）",
    )
    args = parser.parse_args()
    return scan(args.root.resolve())


if __name__ == "__main__":
    sys.exit(main())
