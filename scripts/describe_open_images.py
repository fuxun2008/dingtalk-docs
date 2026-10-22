#!/usr/bin/env python3
"""
zh 母版图片 → 英文文字描述（供 zh→en 翻译时替换图片，避免非中文版去图后丢信息）。

对 --pages-dir 下每篇 zh mdx 的每张图（Markdown `![]()` 语法）：
  1. 取图片前后各 2 个段落作上下文，命中的 zh-en 词库术语作强约束
  2. claude -p（默认 Opus，串行，网关限流要求）读本地图片，分类：
     - redundant   ：装饰图 / 正文已写全的信息 → 翻译时直接剥离
     - informative ：含正文未写的关键信息 → 输出英文描述（句子 / 列表 / 表格），翻译时并入正文
  3. 结果按 key=<slug>#<序号> 写入 --out/image_descriptions_en.json（断点续跑），并出 report.md

本地图片定位：--local-manifest 为 cdn-api-upload 清单（items[].source / path），
--cdn-map 为 {源图 URL: CDN URL}；页面里是 CDN URL 时反查源图再找本地文件。

用法：
  CLAUDE_CLI=/path/to/claude python3 scripts/describe_open_images.py \\
    --pages-dir scripts/output/open_platform_attend_oa/stage/zh/open/development \\
    --local-manifest scripts/output/open_platform_attend_oa/upload_manifest.json \\
    --cdn-map scripts/output/open_platform_attend_oa/cdn_map.json \\
    --out scripts/output/open_platform_attend_oa [--limit N] [--model claude-opus-4-8]
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GLOSSARY = REPO / "scripts" / "glossary" / "zh-en.json"
IMG_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")

SYSTEM = """You document the DingTalk Open Platform for international developers.
The English edition removes all screenshots, so information that only exists in an image must be turned into text.

Look at the image (read the local file) together with the surrounding Chinese text, then answer with ONE JSON object and nothing else:
{"class": "redundant" | "informative", "en": "<English text or empty>"}

- "redundant": decorative, a logo/QR code, or everything it shows is already stated in the surrounding text. "en" must be "".
- "informative": it carries key facts missing from the text (console navigation path, button/menu/field names, config options and values,
  permission names, step order, flow/architecture relations, sample responses). Write "en" so it can be dropped into the English page:
  * only facts visible in the image and NOT already in the text; no "the figure/screenshot shows", "as shown below"
  * UI labels in **bold**, navigation as **A** > **B** > **C**, sequences as a numbered list, several fields as a Markdown table
  * concise: usually 1–4 sentences or a short list
  * follow the glossary strictly; keep product names in English (DingTalk, OA Approval, Attendance)
  * never write phone numbers, emails, corpId, tokens, user IDs or personal names seen in the image
  * do not mention attendance machines, Bluetooth/beacon punch, face recognition, paid/premium editions or mini programs"""


def paragraphs_around(text: str, start: int, end: int, n: int = 2) -> tuple[str, str]:
    before = [p for p in re.split(r"\n\s*\n", text[:start]) if p.strip()][-n:]
    after = [p for p in re.split(r"\n\s*\n", text[end:]) if p.strip()][:n]
    return "\n\n".join(before)[-1200:], "\n\n".join(after)[:1200]


def local_path(url: str, src_to_path: dict, cdn_to_src: dict, cache_dir: Path) -> str | None:
    """优先用清单里的本地文件；源站原本就在 CDN 上的图不在清单里，下载到 cache_dir。"""
    hit = src_to_path.get(cdn_to_src.get(url, url))
    if hit:
        return hit
    suffix = Path(url.split("?")[0]).suffix or ".png"
    target = cache_dir / f"{hashlib.sha1(url.encode()).hexdigest()[:12]}{suffix}"
    if not target.exists():
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(url, timeout=30) as resp:
                target.write_bytes(resp.read())
        except OSError:
            return None
    return str(target.resolve())


def ask(image: str, before: str, after: str, alt: str, terms: dict, model: str) -> dict:
    glossary = json.dumps(terms, ensure_ascii=False) if terms else "{}"
    prompt = (
        f"{SYSTEM}\n\nGlossary (zh → en, mandatory): {glossary}\n\n"
        f"Image file: {image}\nImage alt text: {alt}\n\n"
        f"--- Text before the image ---\n{before}\n\n--- Text after the image ---\n{after}\n"
    )
    r = subprocess.run(
        [os.environ.get("CLAUDE_CLI", "claude"), "-p", "--model", model, "--allowedTools=Read"],
        input=prompt, capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: {r.stderr[:300]}")
    m = re.search(r"\{.*\}", r.stdout, re.S)
    if not m:
        raise RuntimeError(f"no JSON in output: {r.stdout[:200]}")
    data = json.loads(m.group(0))
    if data.get("class") not in ("redundant", "informative"):
        raise RuntimeError(f"bad class: {data}")
    return data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pages-dir", required=True)
    ap.add_argument("--local-manifest", required=True)
    ap.add_argument("--cdn-map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    out = Path(args.out)
    result_path = out / "image_descriptions_en.json"
    results = json.loads(result_path.read_text()) if result_path.exists() else {}
    src_to_path = {i["source"]: i["path"] for i in json.loads(Path(args.local_manifest).read_text())["items"]}
    cdn_to_src = {v: k for k, v in json.loads(Path(args.cdn_map).read_text()).items()}
    glossary = json.loads(GLOSSARY.read_text())

    jobs = []
    for page in sorted(Path(args.pages_dir).glob("*.mdx")):
        text = page.read_text()
        for idx, m in enumerate(IMG_RE.finditer(text), 1):
            before, after = paragraphs_around(text, m.start(), m.end())
            jobs.append((f"{page.stem}#{idx}", page.stem, m.group(1), m.group(2), before, after))
    (out / "image_manifest.json").write_text(json.dumps(
        [{"key": k, "slug": s, "alt": a, "url": u} for k, s, a, u, _, _ in jobs], ensure_ascii=False, indent=1))
    todo = [j for j in jobs if j[0] not in results]
    if args.limit:
        todo = todo[: args.limit]
    print(f"images {len(jobs)}, done {len(jobs) - len([j for j in jobs if j[0] not in results])}, todo {len(todo)}", flush=True)

    for i, (key, slug, alt, url, before, after) in enumerate(todo, 1):
        path = local_path(url, src_to_path, cdn_to_src, out / "images")
        if not path:
            print(f"[{i}] SKIP {key}: no local file for {url}", flush=True)
            continue
        ctx = before + after + alt
        terms = {zh: en for zh, en in glossary.items() if zh and zh in ctx}
        try:
            data = ask(path, before, after, alt, terms, args.model)
        except Exception as e:  # 记录后跳过，重跑续传
            print(f"[{i}] FAIL {key}: {e}", flush=True)
            continue
        results[key] = {"slug": slug, "url": url, **data}
        result_path.write_text(json.dumps(results, ensure_ascii=False, indent=1))
        print(f"[{i}/{len(todo)}] {key} {data['class']}: {data.get('en', '')[:80]}", flush=True)

    write_report(out, jobs, results)
    return 0


def write_report(out: Path, jobs: list, results: dict) -> None:
    info = sum(1 for r in results.values() if r["class"] == "informative")
    lines = ["# 图片 → 英文描述 报告", "",
             f"- 图片总数：{len(jobs)}；已处理：{len(results)}；informative：{info}；redundant：{len(results) - info}", ""]
    for key, slug, alt, url, _, _ in jobs:
        r = results.get(key)
        if not r:
            lines.append(f"## {key} — 未处理\n")
            continue
        lines += [f"## {key} — {r['class']}", "", f"<img src=\"{url}\" width=\"360\" />", ""]
        if r["en"]:
            lines += [r["en"], ""]
    (out / "image_descriptions_report.md").write_text("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
