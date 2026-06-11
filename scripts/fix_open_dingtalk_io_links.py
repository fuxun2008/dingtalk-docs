#!/usr/bin/env python3
"""open.dingtalk.io 死链批量修复 — 三语开放平台。

背景：commit d3c4d96「mdx 全量替换 dingtalk.com → dingtalk.io」无差别替换了
所有 open.dingtalk.com/document/... 外链，但 open.dingtalk.io 域名未部署，
导致三语镜像（en/zh/ja）共 ~810 文件 ~4668 处死链。

策略：
- 命中 slug 能在仓库 open/development/ 或 open/dingstart/ 找到 → 替换为
  内部相对路径 /{lang}/open/{dir}/{slug}（en 无前缀、zh/ja 带前缀）
- slug 不能映射 → 仅把 .io 改回 .com（指向中文官网，保链接可用）

用法：
    python3 scripts/fix_open_dingtalk_io_links.py            # dry-run，打印 report
    python3 scripts/fix_open_dingtalk_io_links.py --apply    # 落盘修改
    python3 scripts/fix_open_dingtalk_io_links.py --root <repo-root>
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

URL_RE = re.compile(
    r"https?://open\.dingtalk\.io"
    r"(?:/document/[a-z-]+/(?P<slug>[a-zA-Z0-9_.-]+))?"
    r"(?P<anchor>#[^\s)\"']*)?"
)

SCAN_ROOTS = ("open", "zh/open", "ja/open")


def build_slug_index(repo: Path) -> dict[str, str]:
    """slug → directory（development | dingstart），en/zh/ja 镜像 slug 100% 一致用 en 即可。"""
    idx: dict[str, str] = {}
    for d in ("development", "dingstart"):
        base = repo / "open" / d
        if not base.exists():
            continue
        for p in base.glob("*.mdx"):
            idx[p.stem] = d
    return idx


def lang_prefix(rel_path: Path) -> str:
    s = rel_path.as_posix()
    if s.startswith("zh/"):
        return "/zh/open/"
    if s.startswith("ja/"):
        return "/ja/open/"
    return "/open/"


def make_replacer(slug_dir: dict[str, str], rel_path: Path, stats: Counter):
    prefix = lang_prefix(rel_path)

    def replace(m: re.Match[str]) -> str:
        raw_slug = m.group("slug") or ""
        anchor = m.group("anchor") or ""
        # 兼容 obtain-all-worksheets.md 这类源文档残留 .md 后缀
        slug = raw_slug[:-3] if raw_slug.endswith(".md") else raw_slug
        if slug and slug in slug_dir:
            stats["mapped"] += 1
            return f"{prefix}{slug_dir[slug]}/{slug}{anchor}"
        # 回退：仅域名改 .com，path/anchor/查询串原样保留
        stats["fallback"] += 1
        return m.group(0).replace("open.dingtalk.io", "open.dingtalk.com")

    return replace


def process_file(
    mdx: Path, repo: Path, slug_dir: dict[str, str], apply: bool
) -> tuple[Counter, list[tuple[str, str]]]:
    stats: Counter[str] = Counter()
    samples: list[tuple[str, str]] = []
    original = mdx.read_text(encoding="utf-8")
    rel = mdx.relative_to(repo)
    replacer = make_replacer(slug_dir, rel, stats)

    def wrapped(m: re.Match[str]) -> str:
        before = m.group(0)
        after = replacer(m)
        if before != after and len(samples) < 3:
            samples.append((before, after))
        return after

    new = URL_RE.sub(wrapped, original)
    if apply and new != original:
        mdx.write_text(new, encoding="utf-8")
    return stats, samples


def scan(repo: Path, apply: bool) -> int:
    slug_dir = build_slug_index(repo)
    print(f"SLUG_DIR: {len(slug_dir)} slugs indexed from open/development + open/dingstart")
    print()

    total = Counter()
    by_lang: dict[str, Counter[str]] = {"open": Counter(), "zh/open": Counter(), "ja/open": Counter()}
    file_count = 0
    touched = 0
    sample_pool: list[tuple[Path, str, str]] = []

    for root in SCAN_ROOTS:
        base = repo / root
        if not base.exists():
            continue
        for mdx in base.rglob("*.mdx"):
            file_count += 1
            stats, samples = process_file(mdx, repo, slug_dir, apply)
            if stats:
                touched += 1
                total.update(stats)
                by_lang[root].update(stats)
                for b, a in samples:
                    sample_pool.append((mdx.relative_to(repo), b, a))

    mode = "APPLY" if apply else "DRY-RUN"
    print(f"=== {mode} report ===")
    print(f"Scanned files: {file_count}")
    print(f"Touched files: {touched}")
    print(f"Total URL hits: {sum(total.values())}")
    print(f"  Mapped to internal: {total['mapped']}")
    print(f"  Fallback to .com:   {total['fallback']}")
    print()
    print("By language:")
    for lang, c in by_lang.items():
        print(f"  {lang:10s} mapped={c['mapped']:5d}  fallback={c['fallback']:4d}  total={sum(c.values()):5d}")
    print()
    print("Samples (before → after):")
    for rel, b, a in sample_pool[:8]:
        print(f"  [{rel}]")
        print(f"    - {b}")
        print(f"    + {a}")
    fb_samples = [(r, b, a) for r, b, a in sample_pool if "dingtalk.com" in a][:5]
    if fb_samples:
        print()
        print("Fallback samples (.com):")
        for rel, b, a in fb_samples:
            print(f"  [{rel}]")
            print(f"    - {b}")
            print(f"    + {a}")
    if not apply:
        print()
        print("Run with --apply to write changes.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="仓库根目录（默认：脚本所在 scripts/ 的父目录）",
    )
    parser.add_argument("--apply", action="store_true", help="实际写入文件（默认 dry-run）")
    args = parser.parse_args()
    return scan(args.root.resolve(), args.apply)


if __name__ == "__main__":
    sys.exit(main())
