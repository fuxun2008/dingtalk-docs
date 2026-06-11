# Translation Batch Report

- 开始：2026-06-11 09:30:58
- 结束：2026-06-11 09:32:00
- 用时：62.7s

- 总：1 / ok: 1 / skipped: 0 / failed: 0 / dry-run: 0
- input tokens: 6
- output tokens: 7,815
- cost: $0.2653

## 全量明细（前 100）

| rel | status | elapsed | in | out | cost | hits |
|---|---|---|---|---|---|---|
| open/development/api-queryconferenceinfobyroomcode.mdx | ok | 62.67s | 6 | 7815 | $0.2653 | 58 |

## 补译批次：server-api-error-codes-1.mdx（超大表 5 片切翻 + shard 4 单独补译）

- 2026-06-11 15:25：首次 5 片切翻（`translate_large_error_codes.py --shards 5`）
  - shard 1 done 220.4s out=27,030 cost=$0.8485
  - shard 2 done 224.8s out=29,543 cost=$0.9295
  - shard 3 done 187.1s out=24,102 cost=$0.7624
  - shard 4 **FAILED** 192.1s（empty result, stop_reason=None）→ 中文兜底
  - shard 5 done 249.2s out=32,831 cost=$1.0190
  - 总：5 片 / 4 ok / 1 failed / 1073.7s / $3.5594 / cache_hit_rate 0%
- 2026-06-11 15:46：shard 4 单独补译（`patch_error_codes_shard.py --shard-idx 3 --retry 2`）
  - attempt 1 done 204.8s out=25,652 cost=$0.8103 ✓
  - 替换 ja 文件行 1515-2014（500 行）
- **累计成本 $4.37 / 21 分钟**，ja 文件最终 2513 行 / 402,266 bytes
- 至此 ja/open 达成 **416/416** 全量翻译