#!/usr/bin/env node
import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');
const batch = JSON.parse(readFileSync(join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'yida-zh-en.json'), 'utf8'));

// 按slug分组 completed items（兼容 cdnUrl 和 target.currentUrl）
const bySlug = new Map();
for (const item of batch.items || []) {
  const cdnUrl = item.cdnUrl || item.target?.currentUrl;
  if (item.status === 'completed' && cdnUrl) {
    if (!bySlug.has(item.slug)) bySlug.set(item.slug, []);
    bySlug.get(item.slug).push({ ...item, resolvedCdnUrl: cdnUrl });
  }
}

let totalItems = 0;
let totalMissing = 0;
const missingSlugs = [];

for (const [slug, items] of bySlug) {
  const enFile = join(repoRoot, slug + '.mdx');
  if (!existsSync(enFile)) {
    totalMissing += items.length;
    missingSlugs.push({ slug, missing: items.length, total: items.length, reason: '文件不存在' });
    continue;
  }

  const content = readFileSync(enFile, 'utf8');
  let missing = 0;
  for (const item of items) {
    if (item.resolvedCdnUrl && !content.includes(item.resolvedCdnUrl)) {
      missing++;
    }
  }

  totalItems += items.length;
  if (missing > 0) {
    totalMissing += missing;
    missingSlugs.push({ slug, missing, total: items.length });
  }
}

console.log('=== 全局验证（兼容 cdnUrl + target.currentUrl）===');
console.log('总 completed items:', totalItems);
console.log('未找到的 CDN URL 数:', totalMissing);
console.log('有遗漏的 slug 数:', missingSlugs.length);

if (missingSlugs.length > 0) {
  console.log('\n=== 有遗漏的 slug 列表 ===');
  for (const m of missingSlugs.sort((a, b) => b.missing - a.missing)) {
    console.log(`  ${m.slug}: 缺 ${m.missing}/${m.total}${m.reason ? ' (' + m.reason + ')' : ''}`);
  }
}
