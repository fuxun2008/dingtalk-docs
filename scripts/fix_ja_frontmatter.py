#!/usr/bin/env python3
"""
一次性修复：部分 en→ja 译文被模型漏掉了 frontmatter 块（直接以正文开头）。
本脚本只补 frontmatter（title + SEO description），不动已译好的正文。

逻辑：
- 扫描 ja/<modules> 下首个非空行不是 `---` 的 mdx（= 缺 frontmatter）。
- 读取 en 母版的 title / description。
- 调 claude -p 生成日语 title + SEO 日语 description（复用 en2ja 引擎的 SEO 规则）。
- 把 `---\ntitle\ndescription\n---\n\n` 前置到 ja 正文。

用法：
  python3 scripts/fix_ja_frontmatter.py --dry-run
  python3 scripts/fix_ja_frontmatter.py --roots meetings drive mail ai-minutes calendar im contacts open aitable
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from translate_mdx_en2ja import call_claude_cli, SEO_DESCRIPTION_RULE, STYLE_JA  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def read_frontmatter(text: str) -> dict[str, str]:
    m = FM_RE.match(text)
    if not m:
        return {}
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        mm = re.match(r"^(\w+):\s*(.*)$", line)
        if mm:
            fm[mm.group(1)] = mm.group(2).strip().strip('"').strip("'")
    return fm


def has_frontmatter(text: str) -> bool:
    return text.lstrip().startswith("---")


SYS_PROMPT = (
    "あなたはDingTalk国際版ヘルプセンターのシニア日本語テクニカルライターです。"
    "英語ページの title と description を、日本語の公式ドキュメント用に変換します。\n\n"
    + SEO_DESCRIPTION_RULE
    + "\n\n"
    + STYLE_JA
    + "\n\n出力は厳密に JSON のみ：{\"title\": \"...\", \"description\": \"...\"}。前後に説明やコードフェンスを付けないこと。"
)


def build_user(en_title: str, en_desc: str, body_excerpt: str) -> str:
    return (
        f"英語 title: {en_title}\n"
        f"英語 description: {en_desc}\n\n"
        f"ページ本文の冒頭（文脈把握用、訳さない）：\n{body_excerpt[:800]}\n\n"
        "上記を踏まえ、日本語の title（簡潔・自然）と SEO 最適化された日本語 description を生成し、JSON だけ返してください。"
    )


def extract_json(s: str) -> dict[str, str]:
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*\n?", "", s)
    s = re.sub(r"\n?```\s*$", "", s)
    m = re.search(r"\{.*\}", s, re.DOTALL)
    return json.loads(m.group(0)) if m else {}


async def fix_one(ja_path: Path, model: str, sem: asyncio.Semaphore, dry: bool) -> str:
    rel = str(ja_path.relative_to(REPO_ROOT))
    ja_text = ja_path.read_text(encoding="utf-8")
    if has_frontmatter(ja_text):
        return f"skip(has-fm) {rel}"
    en_path = REPO_ROOT / ja_path.relative_to(REPO_ROOT / "ja")
    if not en_path.exists():
        return f"NO-EN {rel}"
    en_fm = read_frontmatter(en_path.read_text(encoding="utf-8"))
    en_title = en_fm.get("title", "")
    en_desc = en_fm.get("description", "")
    if dry:
        return f"[dry] would fix {rel}  (en_title={en_title!r})"
    async with sem:
        for attempt in range(3):
            try:
                out, _ = await call_claude_cli(SYS_PROMPT, build_user(en_title, en_desc, ja_text), model, 120)
                data = extract_json(out)
                title = data.get("title", "").strip()
                desc = data.get("description", "").strip()
                if not title or not desc:
                    raise RuntimeError("empty title/desc")
                fm_block = f'---\ntitle: "{title}"\ndescription: "{desc}"\n---\n\n'
                ja_path.write_text(fm_block + ja_text.lstrip(), encoding="utf-8")
                return f"FIXED {rel}  title={title!r}"
            except Exception as e:
                last = f"{type(e).__name__}: {e}"
                await asyncio.sleep(3 * (attempt + 1))
        return f"FAILED {rel}  {last}"


async def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--roots", nargs="+", default=["meetings", "drive", "mail", "ai-minutes",
                                                  "calendar", "im", "contacts", "open", "aitable"])
    p.add_argument("--model", default="claude-opus-4-8")
    p.add_argument("--concurrency", type=int, default=3)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    targets: list[Path] = []
    for root in args.roots:
        for mdx in sorted((REPO_ROOT / "ja" / root).rglob("*.mdx")):
            if not has_frontmatter(mdx.read_text(encoding="utf-8")):
                targets.append(mdx)
    print(f"[info] 缺 frontmatter 的 ja 文件: {len(targets)}")
    sem = asyncio.Semaphore(args.concurrency)
    results = await asyncio.gather(*[fix_one(t, args.model, sem, args.dry_run) for t in targets])
    fixed = sum(1 for r in results if r.startswith("FIXED"))
    failed = sum(1 for r in results if r.startswith("FAILED"))
    for r in results:
        print(" ", r)
    print(f"\n[done] fixed={fixed} failed={failed} total={len(targets)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
