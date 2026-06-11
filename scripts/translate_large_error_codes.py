#!/usr/bin/env python3
"""
一次性脚本：分片翻译 zh/open/development/server-api-error-codes-1.mdx (272KB 大表)。

策略：把单一大表按行数等分 5 片，每片自带表头 + frontmatter 作为合法 mdx；
单片调 claude -p --bare 翻译；
最终去掉 2-5 片的 frontmatter + 表头，拼接到第 1 片末尾。

用法：
  python3 scripts/translate_large_error_codes.py            # 翻译并写入
  python3 scripts/translate_large_error_codes.py --shards 6 # 自定义分片数
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from translate_mdx_batch import (  # noqa: E402
    call_claude_cli,
    build_system_prompt,
    load_glossary,
    extract_hit_terms,
    build_user_message,
    strip_code_fence_wrapper,
)


REPO_ROOT = SCRIPT_DIR.parent
ZH_FILE = REPO_ROOT / "zh" / "open" / "development" / "server-api-error-codes-1.mdx"
JA_FILE = REPO_ROOT / "ja" / "open" / "development" / "server-api-error-codes-1.mdx"


def split_source(src: str) -> tuple[list[str], list[str], list[str], list[str], list[str]]:
    """切：frontmatter / intro / table_header(2 行) / table_data / tail。"""
    lines = src.split("\n")
    fm_end = 0
    if lines and lines[0] == "---":
        for i in range(1, len(lines)):
            if lines[i] == "---":
                fm_end = i + 1
                break
    frontmatter = lines[:fm_end]
    rest = lines[fm_end:]
    table_start = next((i for i, l in enumerate(rest) if l.startswith("|")), len(rest))
    intro = rest[:table_start]
    table_block = rest[table_start:]
    # 假设：表头(1) + 分隔行(1) + 数据行(N) + [可选 trailing 非表格行]
    table_header = table_block[:2]
    rest_after_header = table_block[2:]
    last_table_row = 0
    for i, l in enumerate(rest_after_header):
        if l.startswith("|"):
            last_table_row = i + 1
    table_data = rest_after_header[:last_table_row]
    tail = rest_after_header[last_table_row:]
    return frontmatter, intro, table_header, table_data, tail


def chunk_rows(rows: list[str], n: int) -> list[list[str]]:
    size = (len(rows) + n - 1) // n
    return [rows[i * size : (i + 1) * size] for i in range(n) if rows[i * size : (i + 1) * size]]


def assemble_shard(
    idx: int,
    frontmatter: list[str],
    intro: list[str],
    table_header: list[str],
    table_data_chunk: list[str],
) -> str:
    """生成第 idx 片的源 mdx。第 1 片含完整 frontmatter+intro；其余仅含表头+数据。"""
    if idx == 0:
        parts = frontmatter + [""] + intro + [""] + table_header + table_data_chunk
    else:
        parts = ["---", f'title: "shard-{idx}"', "---", ""] + table_header + table_data_chunk
    return "\n".join(parts) + "\n"


def strip_shard_overhead(translated: str) -> str:
    """从第 2 片起，去掉译文中的 frontmatter + 表头 2 行，仅保留数据行。"""
    text = strip_code_fence_wrapper(translated).strip()
    lines = text.split("\n")
    # 去 frontmatter
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                lines = lines[i + 1 :]
                break
    # 跳前导空行
    while lines and not lines[0].strip():
        lines.pop(0)
    # 去表头 2 行（表头 + 分隔）
    if len(lines) >= 2 and lines[0].startswith("|") and re.match(r"^\|[\s\-:|]+\|?\s*$", lines[1]):
        lines = lines[2:]
    while lines and not lines[0].strip():
        lines.pop(0)
    # 去尾部 LLM 可能加的非表格段落（只保留表格行）
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


async def main(shards: int, timeout_s: int, model: str) -> int:
    if not ZH_FILE.exists():
        print(f"[error] {ZH_FILE} 不存在", file=sys.stderr)
        return 1

    src = ZH_FILE.read_text(encoding="utf-8")
    frontmatter, intro, table_header, table_data, tail = split_source(src)
    print(f"[info] source: {len(src):,} bytes / {sum(map(len, (frontmatter, intro, table_header, table_data, tail)))} lines")
    print(f"  frontmatter={len(frontmatter)} intro={len(intro)} header={len(table_header)} data={len(table_data)} tail={len(tail)}")

    chunks = chunk_rows(table_data, shards)
    print(f"[info] split into {len(chunks)} shards, sizes={[len(c) for c in chunks]}", flush=True)

    glossary = load_glossary("ja")
    sys_prompt = build_system_prompt("ja", "open")
    print(f"[info] system prompt: {len(sys_prompt):,} chars / glossary: {len(glossary)} terms", flush=True)

    translated_parts: list[str] = []
    total_cost = 0.0
    total_in = total_out = total_ccr = total_crd = 0
    started = time.time()
    failed_shards: list[int] = []

    for i, chunk in enumerate(chunks):
        src_part = assemble_shard(i, frontmatter, intro, table_header, chunk)
        hits = extract_hit_terms(src_part, glossary)
        user_msg = build_user_message(hits, src_part)
        t0 = time.time()
        print(f"\n[shard {i+1}/{len(chunks)}] src={len(src_part):,} chars, rows={len(chunk)}, hits={len(hits)}", flush=True)
        try:
            result, usage = await call_claude_cli(sys_prompt, user_msg, model, timeout_s)
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  ! shard {i+1} FAILED after {elapsed:.1f}s: {e}", flush=True)
            print(f"  → 用中文原文兜底（不重试）", flush=True)
            failed_shards.append(i + 1)
            translated_parts.append(src_part)
            continue
        elapsed = time.time() - t0
        inp = usage.get("input_tokens", 0)
        out = usage.get("output_tokens", 0)
        ccr = usage.get("cache_creation_input_tokens", 0) or 0
        crd = usage.get("cache_read_input_tokens", 0) or 0
        cost = usage.get("cost_usd", 0.0)
        total_in += inp
        total_out += out
        total_ccr += ccr
        total_crd += crd
        total_cost += cost
        print(f"  done {elapsed:.1f}s  in={inp} out={out} cache_creation={ccr} cache_read={crd} cost=${cost:.4f}", flush=True)
        translated_parts.append(strip_code_fence_wrapper(result))

    final = translated_parts[0].rstrip() + "\n"
    for i in range(1, len(translated_parts)):
        body = strip_shard_overhead(translated_parts[i])
        final += body + "\n"

    if tail:
        # tail 是原文未译的非表格段（一般无），原样追加
        tail_text = "\n".join(tail).strip()
        if tail_text:
            final += "\n" + tail_text + "\n"

    JA_FILE.parent.mkdir(parents=True, exist_ok=True)
    JA_FILE.write_text(final, encoding="utf-8")

    elapsed_total = time.time() - started
    hit_rate = total_crd / (total_crd + total_ccr) * 100 if (total_crd + total_ccr) else 0
    print(f"\n[ok] wrote {JA_FILE} ({len(final):,} bytes / {len(final.split(chr(10)))} lines)", flush=True)
    print(f"[stat] shards={len(chunks)} ok={len(chunks)-len(failed_shards)} failed={len(failed_shards)} total={elapsed_total:.1f}s", flush=True)
    print(f"[stat] tokens in={total_in:,} out={total_out:,} cache_creation={total_ccr:,} cache_read={total_crd:,}", flush=True)
    print(f"[stat] cost=${total_cost:.4f}  cache_hit_rate={hit_rate:.1f}%", flush=True)
    if failed_shards:
        print(f"[warn] failed shards (用中文兜底): {failed_shards}", flush=True)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shards", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--model", default="claude-opus-4-7")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.shards, args.timeout, args.model)))
