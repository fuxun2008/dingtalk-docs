#!/usr/bin/env python3
"""lint_seo_descriptions.py — 全站 mdx description SEO lint (read-only).

输出三类报告，便于人工补齐文案：
- MISSING   : frontmatter 无 description 或为空字符串
- TOO_SHORT : description < 阈值（按 lang）
- TOO_LONG  : description > 阈值（按 lang，Google SERP 会截断）

CJK 字符按 1 字符算（Python len），但 CJK 在视觉宽度上占双倍，所以 zh/ja
的阈值收紧到 25/80；en 用 50/160。也对外暴露 LANG_THRESHOLDS 常量供其它
脚本（gen_seo_descriptions_batch.py 等）import 复用。

用法：
    python3 scripts/lint_seo_descriptions.py
    python3 scripts/lint_seo_descriptions.py --lang en        # 只扫 en (根目录非 zh/ja)
    python3 scripts/lint_seo_descriptions.py --lang zh
    python3 scripts/lint_seo_descriptions.py --top 50         # 每类只列前 50 条 (default 30)
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# 与 sitemap 脚本保持同一份 valid content 目录白名单
VALID_TOP_DIRS = {
    "ai-minutes", "aitable", "calendar", "contacts", "docs", "drive",
    "im", "mail", "meetings", "oa", "open", "yida", "zh", "ja", "id",
}
# 根目录 .mdx 也算 en (index.mdx / quickstart.mdx 等)
ROOT_MDX_AS_EN = True

# 按语言分阈值：CJK 视觉宽度是 en 的两倍，相同 SEO 容量对应字符数减半。
LANG_THRESHOLDS = {
    "en": {"short": 50, "long": 160},
    "zh": {"short": 25, "long": 80},
    "ja": {"short": 25, "long": 80},
}

DESC_RE = re.compile(
    r'^description:\s*"((?:[^"\\]|\\.)*)"\s*$'
    r'|^description:\s*\'((?:[^\'\\]|\\.)*)\'\s*$'
    r'|^description:\s*(\S.*?)\s*$',
    re.MULTILINE,
)


def extract_description(text: str) -> str | None:
    """Return the frontmatter `description` value, or None if absent."""
    # Only look inside the first frontmatter block (between leading --- pairs).
    if not text.startswith('---'):
        return None
    end = text.find('\n---', 3)
    if end == -1:
        return None
    fm = text[3:end]
    m = DESC_RE.search(fm)
    if not m:
        return None
    return m.group(1) or m.group(2) or m.group(3) or None


def classify(path: Path) -> str:
    """Return 'en' / 'zh' / 'ja' based on the path."""
    parts = path.relative_to(REPO_ROOT).parts
    if parts and parts[0] in ("zh", "ja"):
        return parts[0]
    if ROOT_MDX_AS_EN:
        return "en"
    return "unknown"


def collect_mdx(only_lang: str | None) -> list[Path]:
    """Walk repo and yield .mdx paths under VALID_TOP_DIRS + root."""
    results: list[Path] = []
    for top in sorted(VALID_TOP_DIRS):
        d = REPO_ROOT / top
        if d.is_dir():
            results.extend(d.rglob("*.mdx"))
    # root-level mdx (index, quickstart, etc.)
    for p in REPO_ROOT.glob("*.mdx"):
        results.append(p)
    results.sort()
    if only_lang:
        results = [p for p in results if classify(p) == only_lang]
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--lang", choices=["en", "zh", "ja"], help="filter by language")
    parser.add_argument("--top", type=int, default=30, help="entries per category (default 30)")
    args = parser.parse_args()

    paths = collect_mdx(args.lang)
    print(f"Scanned {len(paths)} .mdx files" + (f" (lang={args.lang})" if args.lang else ""))

    missing: list[Path] = []
    short: list[tuple[Path, int, str, str]] = []  # (path, len, desc, lang)
    long_: list[tuple[Path, int, str, str]] = []
    total_with_desc = 0
    total_chars = 0

    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        desc = extract_description(text)
        if not desc:
            missing.append(p)
            continue
        n = len(desc)
        total_with_desc += 1
        total_chars += n
        lang = classify(p)
        th = LANG_THRESHOLDS.get(lang, LANG_THRESHOLDS["en"])
        if n < th["short"]:
            short.append((p, n, desc, lang))
        elif n > th["long"]:
            long_.append((p, n, desc, lang))

    avg = total_chars / total_with_desc if total_with_desc else 0
    print(
        f"  with description: {total_with_desc}  avg={avg:.0f} chars  "
        f"missing={len(missing)}  short={len(short)}  long={len(long_)}"
    )
    print(f"  thresholds: " + ", ".join(
        f"{lang}=<{th['short']}/>{th['long']}" for lang, th in LANG_THRESHOLDS.items()
    ))

    def show(label: str, items: list, fmt) -> None:
        if not items:
            return
        print(f"\n== {label} ({len(items)}) — first {min(args.top, len(items))} ==")
        for it in items[: args.top]:
            print(fmt(it))

    show(
        "MISSING description",
        missing,
        lambda p: f"  [{classify(p)}]  {p.relative_to(REPO_ROOT)}",
    )
    show(
        "TOO_SHORT",
        sorted(short, key=lambda t: t[1]),
        lambda t: f"  [{t[3]}] {t[1]:3d} chars  {t[0].relative_to(REPO_ROOT)}  — {t[2][:60]}",
    )
    show(
        "TOO_LONG",
        sorted(long_, key=lambda t: -t[1]),
        lambda t: f"  [{t[3]}] {t[1]:3d} chars  {t[0].relative_to(REPO_ROOT)}  — {t[2][:60]}…",
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
