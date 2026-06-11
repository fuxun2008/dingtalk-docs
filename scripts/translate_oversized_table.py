#!/usr/bin/env python3
"""
超大表格 mdx 分片翻译工具。

适用：单文件结构是一张超大 markdown 表格（行间无上下文依赖），
单次 LLM 调用 timeout 跑不完时，按表格行分块翻译再合并。

设计：复用 translate_mdx_batch.py 的 system prompt（含 OPEN_PLATFORM_RULES）
+ call_claude_cli 子进程调用。

用法：
  python3 scripts/translate_oversized_table.py \\
      --source zh/open/development/server-api-error-codes-1.mdx \\
      --target open/development/server-api-error-codes-1.mdx \\
      --lang en --root open \\
      --chunk-rows 300 --concurrency 4

  # dry-run：只切片不调 LLM
  python3 scripts/translate_oversized_table.py ... --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from pathlib import Path

# 复用现有翻译脚本的工具
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from translate_mdx_batch import (  # noqa: E402
    build_system_prompt,
    load_glossary,
    extract_hit_terms,
    build_user_message,
    call_claude_cli,
    sanitize_media,
    strip_code_fence_wrapper,
)


TABLE_ROW_RE = re.compile(r"^\|")
TABLE_HEADER_SEP_RE = re.compile(r"^\|[\s\-:|]+\|\s*$")


def split_mdx(text: str) -> tuple[str, str, list[str]]:
    """把 mdx 切成 (prologue, table_header_block, data_rows)。

    prologue：直到第一个表格行之前的所有内容（frontmatter / 段落 / Note / 等）
    table_header_block：表头行 + 分隔行 (`| --- | --- |`) — 2 行
    data_rows：从分隔行之后的所有 `|...|` 表格行
    """
    lines = text.splitlines()
    first_table_idx = None
    for i, line in enumerate(lines):
        if TABLE_ROW_RE.match(line):
            first_table_idx = i
            break
    if first_table_idx is None:
        sys.exit("ERROR: 文件中找不到 markdown 表格行（以 `|` 开头）")

    # 找表头分隔行
    sep_idx = None
    for i in range(first_table_idx + 1, min(first_table_idx + 5, len(lines))):
        if TABLE_HEADER_SEP_RE.match(lines[i]):
            sep_idx = i
            break
    if sep_idx is None:
        sys.exit(f"ERROR: 在表头行 {first_table_idx} 后未找到分隔行 `| --- | --- |`")

    prologue = "\n".join(lines[:first_table_idx]).rstrip() + "\n\n"
    header_block = "\n".join(lines[first_table_idx : sep_idx + 1]) + "\n"
    # 剩余的全部表格数据行
    data_rows = []
    for line in lines[sep_idx + 1 :]:
        if TABLE_ROW_RE.match(line):
            data_rows.append(line)
        elif line.strip() == "":
            continue  # 容忍表格内空行
        else:
            # 出现非表格行（页尾文本？）— 此版本视为表格结束
            print(f"[warn] 表格在第 {sep_idx + 1 + len(data_rows)} 行后出现非表格行 {line[:50]!r}，截断", file=sys.stderr)
            break
    return prologue, header_block, data_rows


def chunk_rows(rows: list[str], chunk_size: int) -> list[list[str]]:
    return [rows[i : i + chunk_size] for i in range(0, len(rows), chunk_size)]


def build_chunk_mdx(prologue: str, header: str, rows: list[str], chunk_idx: int, total_chunks: int) -> str:
    """构造一块独立的合法 mdx：prologue + header + rows + 块标记注释。"""
    chunk_note = f"\n<!-- internal: chunk {chunk_idx + 1}/{total_chunks} for offline translation; not shown to readers -->\n"
    return prologue + chunk_note + header + "\n".join(rows) + "\n"


def extract_data_rows(translated: str) -> list[str]:
    """从翻译产物中提取 `^|` 数据行，剥掉 frontmatter/prologue/表头/分隔行。"""
    lines = translated.splitlines()
    # 找最后一个分隔行 `| --- | --- |`
    last_sep = None
    for i, line in enumerate(lines):
        if TABLE_HEADER_SEP_RE.match(line):
            last_sep = i
    if last_sep is None:
        # LLM 未生成表格 — fallback：抓所有 ^| 行除第一行
        rows = [l for l in lines if TABLE_ROW_RE.match(l)]
        if rows:
            # 去掉表头 + 分隔行（如果存在）
            return rows[2:] if len(rows) > 2 and "---" not in rows[1] else rows[1:]
        return []
    return [l for l in lines[last_sep + 1 :] if TABLE_ROW_RE.match(l)]


async def translate_chunk(
    chunk_idx: int,
    total_chunks: int,
    mdx_text: str,
    glossary: dict,
    system_prompt: str,
    model: str,
    timeout_s: int,
    sem: asyncio.Semaphore,
) -> tuple[int, str, dict]:
    hits = extract_hit_terms(mdx_text, glossary)
    user_msg = build_user_message(hits, mdx_text)
    last_err = ""
    for attempt in range(3):
        async with sem:
            t0 = time.time()
            try:
                result_text, usage = await call_claude_cli(system_prompt, user_msg, model, timeout_s)
                elapsed = round(time.time() - t0, 1)
                cleaned = sanitize_media(strip_code_fence_wrapper(result_text))
                print(
                    f"  [{chunk_idx + 1}/{total_chunks}] ✓ {elapsed}s "
                    f"in={usage.get('input_tokens', 0)} out={usage.get('output_tokens', 0)} "
                    f"${usage.get('cost_usd', 0):.3f} hits={len(hits)}"
                )
                return chunk_idx, cleaned, usage
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
        backoff = 2 ** attempt * 3
        print(f"  [{chunk_idx + 1}/{total_chunks}] ✗ attempt {attempt + 1}: {last_err}; retry in {backoff}s", file=sys.stderr)
        await asyncio.sleep(backoff)
    raise RuntimeError(f"chunk {chunk_idx + 1} 失败 3 次：{last_err}")


async def main_async(args) -> int:
    src = Path(args.source)
    tgt = Path(args.target)
    if not src.exists():
        sys.exit(f"source not found: {src}")

    print(f"[info] source: {src} ({src.stat().st_size:,} bytes)")
    text = src.read_text(encoding="utf-8")

    prologue, header, data_rows = split_mdx(text)
    print(f"[info] prologue: {len(prologue)} chars")
    print(f"[info] header: {header.strip()[:80]!r}")
    print(f"[info] data rows: {len(data_rows)}")

    chunks = chunk_rows(data_rows, args.chunk_rows)
    print(f"[info] split into {len(chunks)} chunks of {args.chunk_rows} rows each (last: {len(chunks[-1])} rows)")

    if args.dry_run:
        for i, chunk in enumerate(chunks):
            mdx = build_chunk_mdx(prologue, header, chunk, i, len(chunks))
            print(f"  chunk {i + 1}: {len(chunk)} rows, {len(mdx):,} chars")
        print("[dry-run] not calling LLM, not writing target")
        return 0

    glossary = load_glossary(args.lang)
    system_prompt = build_system_prompt(args.lang, args.root)
    sem = asyncio.Semaphore(args.concurrency)
    model = args.model or "claude-opus-4-7"

    chunk_mdx_list = [build_chunk_mdx(prologue, header, c, i, len(chunks)) for i, c in enumerate(chunks)]

    started = time.time()
    coros = [
        translate_chunk(i, len(chunks), mdx, glossary, system_prompt, model, args.timeout, sem)
        for i, mdx in enumerate(chunk_mdx_list)
    ]
    results: list[tuple[int, str, dict]] = []
    for coro in asyncio.as_completed(coros):
        try:
            r = await coro
            results.append(r)
        except Exception as e:
            print(f"[fatal] {e}", file=sys.stderr)
            return 1
    elapsed = time.time() - started

    results.sort(key=lambda x: x[0])
    sum_in = sum(r[2].get("input_tokens", 0) or 0 for r in results)
    sum_out = sum(r[2].get("output_tokens", 0) or 0 for r in results)
    sum_cost = sum(r[2].get("cost_usd", 0) or 0 for r in results)
    print(
        f"\n[done] {len(chunks)} chunks in {elapsed:.0f}s  "
        f"in={sum_in} out={sum_out} ${sum_cost:.2f}"
    )

    # 合并：第 1 块取完整；第 2-N 块只取数据行
    first_text = results[0][1]
    # 兜底：删除块注释（如果还在译文里）
    first_text = re.sub(r"<!--\s*internal:\s*chunk[^>]*-->\s*\n?", "", first_text)

    extra_rows = []
    for _, txt, _ in results[1:]:
        extra_rows += extract_data_rows(txt)

    # 把第 1 块末尾的数据行 + 后续块的数据行串接
    # 第 1 块本身已经包含其数据行，所以直接 append extra_rows 即可
    final_text = first_text.rstrip() + "\n" + "\n".join(extra_rows) + "\n"

    # 校验
    final_data_row_count = sum(1 for l in final_text.splitlines() if TABLE_ROW_RE.match(l))
    src_data_row_count = sum(1 for l in text.splitlines() if TABLE_ROW_RE.match(l))
    print(f"[verify] target data row count: {final_data_row_count} (source: {src_data_row_count})")
    if abs(final_data_row_count - src_data_row_count) > 5:
        print(f"[warn] 行数差异 {abs(final_data_row_count - src_data_row_count)} 行 > 容忍 5；保留产物供人工 review", file=sys.stderr)

    tgt.parent.mkdir(parents=True, exist_ok=True)
    tgt.write_text(final_text, encoding="utf-8")
    print(f"[ok] wrote {tgt} ({tgt.stat().st_size:,} bytes)")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--lang", required=True, choices=["en", "ja"])
    p.add_argument("--root", default="open", help="用于决定是否注入 OPEN_PLATFORM_RULES")
    p.add_argument("--chunk-rows", type=int, default=300)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--model", default=None)
    p.add_argument("--timeout", type=int, default=240, help="单块 LLM 调用超时秒（块小所以 240s 够）")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async(parse_args())))
