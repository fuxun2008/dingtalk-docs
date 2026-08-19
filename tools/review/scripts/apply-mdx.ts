import { readFileSync, existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { applyImageBatch } from '../src/server/image-batch';

const repoRoot = '/Users/huangjian/Documents/ChatGPT/yida帮助中心手册';
const batchPath = resolve(repoRoot, 'tools/review/.cache/image-batches/yida-zh-en.json');

// 读取 batch job，获取所有 mapped items 的 ID
const batch = JSON.parse(readFileSync(batchPath, 'utf8'));
const mapped = batch.items.filter((i: any) => i.status === 'mapped' && i.cdnUrl);
console.log(`Mapped items to apply: ${mapped.length}`);

// 分批处理
const batchSize = 50;
const allAppliedIds: string[] = [];
const allChangedFiles: string[] = [];
let allSkipped: Array<{ id: string; reason: string }> = [];

for (let i = 0; i < mapped.length; i += batchSize) {
  const batch_items = mapped.slice(i, i + batchSize);
  const ids = batch_items.map((item: any) => item.id);
  const batchNum = Math.floor(i / batchSize) + 1;
  const totalBatches = Math.ceil(mapped.length / batchSize);
  console.log(`\nBatch ${batchNum}/${totalBatches}: processing ${ids.length} items...`);

  try {
    // 先 dry-run
    const preview = applyImageBatch(repoRoot, 'yida', ids, true);
    const applicableIds = preview.appliedIds.filter(
      (id) => !preview.skipped.some((s) => s.id === id)
    );

    if (applicableIds.length > 0) {
      // 实际执行
      const applied = applyImageBatch(repoRoot, 'yida', applicableIds, false);
      allAppliedIds.push(...applied.appliedIds);
      allChangedFiles.push(...applied.changedFiles);
      console.log(`  Applied: ${applied.appliedIds.length}, Changed files: ${applied.changedFiles.length}`);
    } else {
      console.log(`  No applicable items in this batch`);
    }

    if (preview.skipped.length > 0) {
      allSkipped.push(...preview.skipped);
      console.log(`  Skipped: ${preview.skipped.length}`);
      for (const s of preview.skipped.slice(0, 3)) {
        console.log(`    ${s.id}: ${s.reason.slice(0, 80)}`);
      }
    }
  } catch (err) {
    console.error(`  Error in batch ${batchNum}:`, err instanceof Error ? err.message : err);
    // 继续处理下一批
  }
}

console.log(`\n=== 总结 ===`);
console.log(`Total applied: ${allAppliedIds.length}`);
console.log(`Total changed files: ${allChangedFiles.length}`);
console.log(`Total skipped: ${allSkipped.length}`);
console.log(`Unique changed files: ${new Set(allChangedFiles).size}`);

// 更新 batch job 中的状态
for (const item of batch.items) {
  if (allAppliedIds.includes(item.id)) {
    item.status = 'completed';
  }
}
const { writeFileSync, renameSync, mkdirSync } = await import('node:fs');
const { dirname } = await import('node:path');
const tmp = batchPath + '.tmp.apply';
mkdirSync(dirname(batchPath), { recursive: true });
writeFileSync(tmp, JSON.stringify(batch, null, 2) + '\n', 'utf8');
renameSync(tmp, batchPath);
console.log('Batch job updated with completed status');
