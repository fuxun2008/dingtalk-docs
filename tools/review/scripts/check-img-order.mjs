#!/usr/bin/env node
import { readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');
const batchPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'yida-zh-en.json');
const batch = JSON.parse(readFileSync(batchPath, 'utf8'));

// 构建 sourceUrl → cdnUrl 映射
const urlMap = new Map();
const slugItems = new Map(); // slug → [{sourceUrl, cdnUrl, id}]
for (const item of batch.items || []) {
  const cdnUrl = item.cdnUrl || item.target?.currentUrl;
  if (item.status === 'completed' && cdnUrl) {
    urlMap.set(item.sourceUrl, cdnUrl);
    if (!slugItems.has(item.slug)) slugItems.set(item.slug, []);
    slugItems.get(item.slug).push({ sourceUrl: item.sourceUrl, cdnUrl, id: item.id });
  }
}

function extractImageUrls(content) {
  const results = [];
  // 提取 markdown 图片 URL
  for (const m of content.matchAll(/!\[[^\]]*\]\(([^)\s]+)\)/g)) {
    results.push({ url: m[1], index: m.index });
  }
  // 提取 <img src="..."> URL
  for (const m of content.matchAll(/<img[^>]+src="([^"]+)"/g)) {
    results.push({ url: m[1], index: m.index });
  }
  // 提取 <video poster="..."> URL
  for (const m of content.matchAll(/<video[^>]+poster="([^"]+)"/g)) {
    results.push({ url: m[1], index: m.index });
  }
  // 按位置排序
  return results.sort((a, b) => a.index - b.index).map(e => e.url);
}

// 遍历所有有 completed items 的 slug
const problems = [];
let checkedCount = 0;

for (const [slug, items] of slugItems) {
  const zhFile = join(repoRoot, 'zh', slug + '.mdx');
  const enFile = join(repoRoot, slug + '.mdx');
  if (!existsSync(zhFile) || !existsSync(enFile)) continue;

  const zhContent = readFileSync(zhFile, 'utf8');
  const enContent = readFileSync(enFile, 'utf8');

  // ZH 文件中图片 URL 的出现顺序（只取 batch 中的 sourceUrl）
  const zhAllUrls = extractImageUrls(zhContent);
  const zhBatchUrls = zhAllUrls.filter(u => urlMap.has(u)); // 只取在 batch 中的 URL

  // EN 文件中 CDN URL 的出现顺序
  const enAllUrls = extractImageUrls(enContent);

  // 将 EN 中的 CDN URL 反向映射回 sourceUrl
  const cdnToSource = new Map();
  for (const item of items) {
    cdnToSource.set(item.cdnUrl, item.sourceUrl);
  }

  // 获取 EN 文件中 CDN URL 的顺序，映射回 sourceUrl
  const enSourceOrder = [];
  for (const url of enAllUrls) {
    if (cdnToSource.has(url)) {
      enSourceOrder.push(cdnToSource.get(url));
    }
  }

  // 对比顺序
  // ZH 中 batch URL 的顺序
  const zhOrder = zhBatchUrls;
  // EN 中对应 sourceUrl 的顺序
  const enOrder = enSourceOrder;

  if (zhOrder.length !== enOrder.length) {
    // 数量不一致，跳过（已在其他检查中处理）
    continue;
  }

  // 检查顺序是否一致
  let orderMismatch = false;
  const mismatches = [];
  for (let i = 0; i < zhOrder.length; i++) {
    if (zhOrder[i] !== enOrder[i]) {
      orderMismatch = true;
      mismatches.push({
        index: i,
        zhUrl: zhOrder[i],
        enUrl: enOrder[i],
        zhShort: zhOrder[i].split('/').pop().substring(0, 30),
        enShort: enOrder[i].split('/').pop().substring(0, 30),
      });
    }
  }

  checkedCount++;
  if (orderMismatch) {
    problems.push({ slug, itemCount: items.length, mismatches, zhOrder, enOrder });
  }
}

console.log('=== 图片顺序检查 ===');
console.log('检查文件数:', checkedCount);
console.log('有顺序问题的文件数:', problems.length);

if (problems.length > 0) {
  console.log('\n=== 有顺序问题的文件 ===');
  for (const p of problems) {
    console.log(`\n--- ${p.slug} (${p.mismatches.length} 处不匹配) ---`);
    console.log('  ZH 顺序:');
    for (let i = 0; i < p.zhOrder.length; i++) {
      const m = p.mismatches.find(m => m.index === i);
      const marker = m ? ' ← 不匹配' : '';
      console.log(`    ${i + 1}. ${p.zhOrder[i].split('/').pop().substring(0, 40)}${marker}`);
    }
    console.log('  EN 顺序:');
    for (let i = 0; i < p.enOrder.length; i++) {
      const m = p.mismatches.find(m => m.index === i);
      const marker = m ? ' ← 应为 ' + p.zhOrder[i].split('/').pop().substring(0, 30) : '';
      console.log(`    ${i + 1}. ${p.enOrder[i].split('/').pop().substring(0, 40)}${marker}`);
    }
  }
}
