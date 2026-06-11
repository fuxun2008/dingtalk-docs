#!/usr/bin/env python3
"""
一次性脚本：单独补译 server-api-error-codes-1.mdx 的某一片（兜底用中文段被替换）。

用法：
  python3 scripts/patch_error_codes_shard.py --shard-idx 3 --shards 5
  python3 scripts/patch_error_codes_shard.py --shard-idx 3 --shards 5 --retry 2
"""

from __future__ import annotations

import argparse
import asyncio
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
from translate_large_error_codes import (  # noqa: E402
    split_source,
    chunk_rows,
    assemble_shard,
    strip_shard_overhead,
    ZH_FILE,
    JA_FILE,
)


async def translate_with_retry(sys_prompt: str, user_msg: str, model: str, timeout_s: int, retry: int) -> str:
    last_err = None
    for attempt in range(retry + 1):
        t0 = time.time()
        try:
            result, usage = await call_claude_cli(sys_prompt, user_msg, model, timeout_s)
            elapsed = time.time() - t0
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            cost = usage.get("cost_usd", 0.0)
            print(f"  attempt {attempt+1} done {elapsed:.1f}s  in={inp} out={out} cost=${cost:.4f}", flush=True)
            return result
        except Exception as e:
            elapsed = time.time() - t0
            last_err = e
            print(f"  attempt {attempt+1} FAILED after {elapsed:.1f}s: {e}", flush=True)
    raise RuntimeError(f"all {retry+1} attempts failed; last: {last_err}")


async def main(shard_idx: int, shards: int, timeout_s: int, model: str, retry: int) -> int:
    zh_src = ZH_FILE.read_text(encoding="utf-8")
    fm, intro, hdr, data, _tail = split_source(zh_src)
    chunks = chunk_rows(data, shards)
    if shard_idx < 0 or shard_idx >= len(chunks):
        print(f"[error] shard-idx {shard_idx} 越界（共 {len(chunks)} 片）", file=sys.stderr)
        return 1
    target = chunks[shard_idx]
    print(f"[info] 补译 shard {shard_idx+1}/{len(chunks)}, rows={len(target)}", flush=True)

    glossary = load_glossary("ja")
    sys_prompt = build_system_prompt("ja", "open")
    src_part = assemble_shard(shard_idx, fm, intro, hdr, target)
    hits = extract_hit_terms(src_part, glossary)
    user_msg = build_user_message(hits, src_part)
    print(f"[info] src={len(src_part):,} chars, hits={len(hits)}", flush=True)

    result = await translate_with_retry(sys_prompt, user_msg, model, timeout_s, retry)
    translated = strip_code_fence_wrapper(result)
    if shard_idx == 0:
        new_segment = translated.rstrip()
    else:
        new_segment = strip_shard_overhead(translated)

    # 定位 ja 文件中该片范围：用 chunks[shard_idx] 首行作 anchor，长度 len(target)
    ja_text = JA_FILE.read_text(encoding="utf-8")
    ja_lines = ja_text.split("\n")
    anchor = target[0]
    start_idx = None
    for i, line in enumerate(ja_lines):
        if line == anchor:
            start_idx = i
            break
    if start_idx is None:
        print(f"[error] 在 ja 文件中找不到 anchor 行：{anchor!r}", file=sys.stderr)
        return 2
    end_idx = start_idx + len(target)
    print(f"[info] ja 替换范围 行 {start_idx+1}-{end_idx}（共 {len(target)} 行）", flush=True)

    new_lines = new_segment.split("\n")
    print(f"[info] 新译文行数 {len(new_lines)}", flush=True)

    patched = ja_lines[:start_idx] + new_lines + ja_lines[end_idx:]
    JA_FILE.write_text("\n".join(patched), encoding="utf-8")
    print(f"[ok] 写入 {JA_FILE}（{sum(len(l)+1 for l in patched):,} bytes / {len(patched)} 行）", flush=True)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard-idx", type=int, required=True, help="0-based 片索引（如 3 表示第 4 片）")
    ap.add_argument("--shards", type=int, default=5, help="原切片总数，须与首次切分一致")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--model", default="claude-opus-4-7")
    ap.add_argument("--retry", type=int, default=2, help="单片重试次数（默认 2 = 总共 3 次）")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args.shard_idx, args.shards, args.timeout, args.model, args.retry)))
