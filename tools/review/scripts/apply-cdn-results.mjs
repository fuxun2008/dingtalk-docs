#!/usr/bin/env node
import { readFileSync, writeFileSync, renameSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');
const batchPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'yida-zh-en.json');
const resultPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'upload-result-generated.json');

const batch = JSON.parse(readFileSync(batchPath, 'utf8'));
const uploadResult = JSON.parse(readFileSync(resultPath, 'utf8'));

// 构建 id -> cdnUrl 映射
const cdnMap = new Map();
for (const item of uploadResult.items || []) {
  if (item.cdnUrl) cdnMap.set(item.id, item.cdnUrl);
}

console.log('=== 直接更新 batch job ===');
console.log('上传结果 CDN URL 数:', cdnMap.size);

// 更新 batch items
let updated = 0;
const byId = new Map((batch.items || []).map(i => [i.id, i]));

for (const [id, cdnUrl] of cdnMap) {
  const item = byId.get(id);
  if (!item) {
    console.log('  未找到 item:', id);
    continue;
  }

  const oldStatus = item.status;
  item.status = 'completed';
  if (!item.target) item.target = {};
  if (!item.target.currentUrl || item.target.currentUrl !== cdnUrl) {
    // 保留旧的 currentUrl 如果与新的一样，否则更新
    item.target.currentUrl = cdnUrl;
  }
  // 同时设置 cdnUrl 属性（兼容旧格式）
  item.cdnUrl = cdnUrl;

  updated++;
  if (updated <= 5 || updated === cdnMap.size) {
    console.log(`  ${item.slug} [${id}]: ${oldStatus} -> completed, cdnUrl=${cdnUrl.substring(0, 60)}...`);
  }
}

console.log(`\n总计更新: ${updated} 个 items`);

// 更新 batch stats
const stats = { ...batch.stats };
stats.completed = (stats.completed || 0) + updated;
stats.generated = (stats.generated || 0) - updated;
if (stats.generated < 0) stats.generated = 0;
batch.stats = stats;
batch.updatedAt = new Date().toISOString();

console.log('更新后 stats:', JSON.stringify(stats));

// 原子写入
const tmp = `${batchPath}.tmp.${process.pid}.${Date.now()}`;
writeFileSync(tmp, JSON.stringify(batch, null, 2) + '\n', 'utf8');
renameSync(tmp, batchPath);
console.log('batch job 已保存');
