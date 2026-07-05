#!/usr/bin/env python3
"""gen_id_glossary.py — 给官方词库 csv 追加第 4 列「印尼语」。

数据流：
  scripts/glossary/import/*.csv  （原 3 列：中文,英语,日语）
      ↓ 逐行取「英语」列（缺则回退中文）作源
      ↓ 分批走 `claude -p --bare` 生成高质量印尼语本地化
      ↓ 品牌名 / 专有名词 / 技术缩写保留原样
  同名 csv 就地重写为 4 列：中文,英语,日语,印尼语

生成后再跑 `glossary_sync.py` 产出 scripts/glossary/zh-id.json。

实现方式：通过 `claude -p --bare` 子进程调用（同 translate_mdx_batch.py）。
幂等：已含第 4 列的行跳过；--force 覆盖。

CLI:
  python3 scripts/gen_id_glossary.py --dry-run          # 只统计待生成条数
  python3 scripts/gen_id_glossary.py                    # 生成并回写 csv
  python3 scripts/gen_id_glossary.py --batch-size 40 --concurrency 4
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
IMPORT_DIR = REPO_ROOT / "scripts" / "glossary" / "import"

HEADER_TOKENS_ZH = {"中文文案", "中文术语", "中文", "原文"}
HEADER_TOKENS_EN = {"英语", "English", "Eng", "EN", "英文"}
HEADER_TOKENS_JA = {"日语", "日本語", "Japanese", "JA", "日文"}

ID_HEADER_DEFAULT = "印尼语"
ID_HEADER_EN = "Indonesian"  # 用于第二级英文表头行（悟空版 row2）

SYSTEM_PROMPT = """You are a senior localization specialist translating a DingTalk (enterprise collaboration software) terminology glossary from English into Indonesian (Bahasa Indonesia).

Produce high-quality, natural, business-register Indonesian (bahasa baku) suitable for official product documentation and UI. Do NOT translate literally word-for-word; localize idiomatically.

Hard rules (violating any makes the output invalid):
1. Preserve ALL brand names and proper nouns verbatim, unchanged: DingTalk, DingTalk Docs, DingTalk Spreadsheet, DingTalk Mind, DingTalk Whiteboard, AI Table, AI Minutes, Knowledge Base, and any capitalized product/feature brand name.
2. Keep established technical acronyms/terms in English: API, SDK, URL, URI, JSON, XML, HTTP, HTTPS, SaaS, SSO, OAuth, Webhook, JSAPI, H5, QR, UID, ID, IP, PDF, CSV, Excel, Word, Token.
3. Use mainstream Indonesian IT vocabulary: Pengaturan (settings), Fitur (feature), Izin (permission), File, Folder, Unduh (download), Unggah (upload), Masuk (log in), Keluar (log out), Kelola (manage), Bagikan (share), Hapus (delete), Simpan (save), Kirim (send).
4. For a term that is already an English acronym or a proper noun, output it unchanged.
5. Keep the translation concise — it is a glossary term, not a sentence.

Input: a JSON array of English terms (strings).
Output: ONLY a JSON object mapping each input term EXACTLY (verbatim key) to its Indonesian translation. No prose, no explanation, no markdown code fence. First character must be '{'."""


def is_header_row(zh: str, en: str, ja: str) -> bool:
    return zh in HEADER_TOKENS_ZH or en in HEADER_TOKENS_EN or ja in HEADER_TOKENS_JA


def normalize(s: str) -> str:
    if s is None:
        return ""
    return s.replace(" ", " ").strip()


def source_term(zh: str, en: str) -> str:
    """取英语列作源；缺失回退中文列。"""
    return en if en else zh


def strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t)
    return t.strip()


async def call_claude(terms: list[str], model: str, timeout_s: int) -> dict[str, str]:
    user_msg = json.dumps(terms, ensure_ascii=False)
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", "--bare",
        "--model", model,
        "--system-prompt", SYSTEM_PROMPT,
        "--tools", "",
        "--no-session-persistence",
        "--output-format", "json",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=user_msg.encode("utf-8")), timeout=timeout_s
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        raise RuntimeError(f"timeout after {timeout_s}s")
    if proc.returncode != 0:
        raise RuntimeError(f"claude exit {proc.returncode}: {stderr.decode('utf-8', 'replace')[:400]}")
    data = json.loads(stdout.decode("utf-8"))
    if data.get("is_error"):
        raise RuntimeError(f"api_error: {data.get('api_error_status')}")
    result = data.get("result", "")
    if not result:
        raise RuntimeError(f"empty result; stop_reason={data.get('stop_reason')}")
    mapping = json.loads(strip_fence(result))
    if not isinstance(mapping, dict):
        raise RuntimeError("result is not a JSON object")
    return {str(k): str(v) for k, v in mapping.items()}


async def translate_terms(
    terms: list[str], model: str, batch_size: int, concurrency: int, timeout_s: int
) -> dict[str, str]:
    batches = [terms[i : i + batch_size] for i in range(0, len(terms), batch_size)]
    sem = asyncio.Semaphore(concurrency)
    result: dict[str, str] = {}

    async def run_batch(idx: int, batch: list[str]) -> None:
        last_err = ""
        for attempt in range(3):
            async with sem:
                t0 = time.time()
                try:
                    m = await call_claude(batch, model, timeout_s)
                    for term in batch:
                        if term in m and m[term].strip():
                            result[term] = m[term].strip()
                    got = sum(1 for term in batch if term in m)
                    print(f"[batch {idx+1}/{len(batches)}] {got}/{len(batch)} terms  {time.time()-t0:.1f}s")
                    return
                except Exception as e:  # noqa: BLE001
                    last_err = str(e)
                    await asyncio.sleep(2 ** attempt)
        print(f"[batch {idx+1}/{len(batches)}] FAILED after 3 tries: {last_err}", file=sys.stderr)

    await asyncio.gather(*(run_batch(i, b) for i, b in enumerate(batches)))
    return result


def read_rows(csv_path: Path) -> list[list[str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def has_id_column(rows: list[list[str]]) -> bool:
    """首个数据行已有 >=4 列即视为已生成。"""
    for row in rows:
        if len(row) >= 3:
            zh, en, ja = normalize(row[0]), normalize(row[1]), normalize(row[2])
            if is_header_row(zh, en, ja):
                continue
            return len(row) >= 4 and normalize(row[3]) != ""
    return False


def collect_terms(csv_files: list[Path]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for p in csv_files:
        for row in read_rows(p):
            if len(row) < 3:
                continue
            zh, en, ja = normalize(row[0]), normalize(row[1]), normalize(row[2])
            if is_header_row(zh, en, ja):
                continue
            term = source_term(zh, en)
            if not term or term in seen:
                continue
            seen.add(term)
            ordered.append(term)
    return ordered


def rewrite_csv(csv_path: Path, id_map: dict[str, str], *, force: bool) -> tuple[int, int]:
    rows = read_rows(csv_path)
    out: list[list[str]] = []
    filled = missing = 0
    for row in rows:
        if len(row) < 3:
            out.append(row)
            continue
        zh, en, ja = normalize(row[0]), normalize(row[1]), normalize(row[2])
        existing = normalize(row[3]) if len(row) >= 4 else ""
        if is_header_row(zh, en, ja):
            label = ID_HEADER_EN if en == "English" else ID_HEADER_DEFAULT
            out.append(row[:3] + [label])
            continue
        if existing and not force:
            out.append(row[:4])
            continue
        term = source_term(zh, en)
        id_val = id_map.get(term, "")
        if id_val:
            filled += 1
        else:
            missing += 1
        out.append(row[:3] + [id_val])
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(out)
    return filled, missing


def main() -> int:
    ap = argparse.ArgumentParser(description="给词库 csv 生成印尼语第 4 列")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="覆盖已有第 4 列")
    ap.add_argument("--batch-size", type=int, default=40)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    model = args.model or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
    csv_files = sorted(IMPORT_DIR.glob("*.csv"))
    if not csv_files:
        print(f"错误：未找到 csv 于 {IMPORT_DIR}", file=sys.stderr)
        return 1

    for p in csv_files:
        rows = read_rows(p)
        if has_id_column(rows) and not args.force:
            print(f"[skip] {p.name} 已有印尼语列（--force 覆盖）")

    terms = collect_terms(csv_files)
    print(f"[*] 待翻译唯一术语：{len(terms)} 条（源 csv {len(csv_files)} 个，模型 {model}）")

    if args.dry_run:
        print("[dry-run] 前 10 条源术语：")
        for t in terms[:10]:
            print(f"    - {t}")
        print(f"[dry-run] 预计 {(len(terms) + args.batch_size - 1)//args.batch_size} 个批次")
        return 0

    id_map = asyncio.run(
        translate_terms(terms, model, args.batch_size, args.concurrency, args.timeout)
    )
    print(f"[*] 生成成功 {len(id_map)}/{len(terms)} 条")

    total_filled = total_missing = 0
    for p in csv_files:
        filled, missing = rewrite_csv(p, id_map, force=args.force)
        total_filled += filled
        total_missing += missing
        print(f"[write] {p.name}: 填充 {filled} 行，缺失 {missing} 行")
    print(f"[*] 完成：共填充 {total_filled} 行，缺失 {total_missing} 行")
    if total_missing:
        print("    （缺失行 id 留空；可 --force 重跑或人工补）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
