#!/usr/bin/env node
import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');
const batch = JSON.parse(readFileSync(join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'yida-zh-en.json'), 'utf8'));

// 所有 batch items 的 sourceUrl 集合
const allSourceUrls = new Set();
for (const item of batch.items || []) {
  const url = item.sourceUrl || item.sourceImageUrl || '';
  if (url) allSourceUrls.add(url);
}

// 检查 54 个遗漏文件的图片 URL 是否在 batch 中
const missingSlugs = [
  'yida/intro/br66fh', 'yida/intro/kab9piibinwhk1zn', 'yida/intro/le1tkr', 'yida/intro/sbg6g2nsoxacis5y',
  'yida/form/uyznm2o4advaans7', 'yida/form/qtvvfx4e7ze0vvbb', 'yida/form/hf8nma', 'yida/form/rea5br',
  'yida/report/sfbgoc', 'yida/process/ywnn9itpk2e52332',
  'yida/form/apl8y7', 'yida/form/dzzlham7l7xfr6wo', 'yida/form/zas20t', 'yida/custom-page/eab1wa',
  'yida/portal/wohqsumlwfir3d4u',
];

for (const slug of missingSlugs) {
  const zhFile = join(repoRoot, 'zh', slug + '.mdx');
  if (!existsSync(zhFile)) continue;

  const zhContent = readFileSync(zhFile, 'utf8');
  // 提取所有图片 URL
  const mdUrls = [...zhContent.matchAll(/!\[.*?\]\(([^)\s]+)\)/g)].map(m => m[1]);
  const imgUrls = [...zhContent.matchAll(/<img[^>]+src="([^"]+)"/g)].map(m => m[1]);
  const videoUrls = [...zhContent.matchAll(/<video[^>]+poster="([^"]+)"/g)].map(m => m[1]);
  const allUrls = [...new Set([...mdUrls, ...imgUrls, ...videoUrls])];

  let inBatch = 0;
  let notInBatch = 0;
  const notInBatchUrls = [];
  for (const u of allUrls) {
    if (allSourceUrls.has(u)) {
      inBatch++;
    } else {
      notInBatch++;
      notInBatchUrls.push(u);
    }
  }

  // 检查 batch items 中的状态
  const batchItems = (batch.items || []).filter(i => i.slug === slug);
  const statuses = {};
  for (const i of batchItems) {
    statuses[i.status] = (statuses[i.status] || 0) + 1;
  }

  console.log(`\n=== ${slug} ===`);
  console.log(`  ZH 图片 URL 数: ${allUrls.length}`);
  console.log(`  在 batch 中: ${inBatch}, 不在 batch 中: ${notInBatch}`);
  console.log(`  batch items: ${batchItems.length} (${JSON.stringify(statuses)})`);
  if (notInBatchUrls.length > 0) {
    console.log(`  不在 batch 中的 URL:`);
    for (const u of notInBatchUrls.slice(0, 3)) {
      console.log(`    ${u.substring(0, 100)}`);
    }
  }
}
