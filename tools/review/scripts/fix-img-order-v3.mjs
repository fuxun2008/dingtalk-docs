#!/usr/bin/env node
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');
const batchPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'yida-zh-en.json');
const batch = JSON.parse(readFileSync(batchPath, 'utf8'));

const urlMap = new Map();
const slugItems = new Map();
for (const item of batch.items || []) {
  const cdnUrl = item.cdnUrl || item.target?.currentUrl;
  if (item.status === 'completed' && cdnUrl) {
    urlMap.set(item.sourceUrl, cdnUrl);
    if (!slugItems.has(item.slug)) slugItems.set(item.slug, []);
    slugItems.get(item.slug).push({ sourceUrl: item.sourceUrl, cdnUrl });
  }
}

// 提取所有图片 URL 及其在内容中的位置
function extractImageUrlsWithPos(content) {
  const results = [];
  // markdown 图片
  for (const m of content.matchAll(/!\[[^\]]*\]\(([^)\s]+)\)/g)) {
    results.push({ url: m[1], start: m.index + m[0].indexOf(m[1]), end: m.index + m[0].indexOf(m[1]) + m[1].length });
  }
  // <img src="...">
  for (const m of content.matchAll(/<img[^>]+src="([^"]+)"/g)) {
    results.push({ url: m[1], start: m.index + m[0].indexOf('"' + m[1]) + 1, end: m.index + m[0].indexOf('"' + m[1]) + 1 + m[1].length });
  }
  // <video poster="...">
  for (const m of content.matchAll(/<video[^>]+poster="([^"]+)"/g)) {
    results.push({ url: m[1], start: m.index + m[0].indexOf('"' + m[1]) + 1, end: m.index + m[0].indexOf('"' + m[1]) + 1 + m[1].length });
  }
  return results.sort((a, b) => a.start - b.start);
}

let totalFixed = 0;

for (const [slug, items] of slugItems) {
  const zhFile = join(repoRoot, 'zh', slug + '.mdx');
  const enFile = join(repoRoot, slug + '.mdx');
  if (!existsSync(zhFile) || !existsSync(enFile)) continue;

  const zhContent = readFileSync(zhFile, 'utf8');
  const enContent = readFileSync(enFile, 'utf8');

  // ZH 文件中 batch sourceUrl 的出现顺序
  const zhAllUrls = extractImageUrlsWithPos(zhContent);
  const zhBatchUrls = zhAllUrls.filter(e => urlMap.has(e.url)).map(e => e.url);

  const cdnToSource = new Map();
  for (const item of items) cdnToSource.set(item.cdnUrl, item.sourceUrl);

  // EN 文件中所有 CDN URL 的位置
  const enImages = extractImageUrlsWithPos(enContent);
  const enCdnImages = enImages.filter(e => cdnToSource.has(e.url));

  if (zhBatchUrls.length !== enCdnImages.length) continue;

  // 正确的 CDN URL 顺序
  const correctCdnOrder = zhBatchUrls.map(src => urlMap.get(src));
  const currentCdnOrder = enCdnImages.map(e => e.url);

  let hasIssue = false;
  for (let i = 0; i < correctCdnOrder.length; i++) {
    if (correctCdnOrder[i] !== currentCdnOrder[i]) { hasIssue = true; break; }
  }
  if (!hasIssue) continue;

  // 基于位置的精确替换：从后往前替换每个 URL
  // 先收集所有需要替换的位置
  const replacements = [];
  for (let i = 0; i < enCdnImages.length; i++) {
    const oldUrl = enCdnImages[i].url;
    const newUrl = correctCdnOrder[i];
    if (oldUrl !== newUrl) {
      replacements.push({
        start: enCdnImages[i].start,
        end: enCdnImages[i].end,
        newUrl,
      });
    }
  }

  if (replacements.length === 0) continue;

  // 从后往前替换，避免偏移
  replacements.sort((a, b) => b.start - a.start);
  let newContent = enContent;
  for (const r of replacements) {
    newContent = newContent.substring(0, r.start) + r.newUrl + newContent.substring(r.end);
  }

  // 验证
  const fixedImages = extractImageUrlsWithPos(newContent).filter(e => cdnToSource.has(e.url));
  const fixedOrder = fixedImages.map(e => e.url);
  let fixedOk = true;
  for (let i = 0; i < correctCdnOrder.length; i++) {
    if (correctCdnOrder[i] !== fixedOrder[i]) { fixedOk = false; break; }
  }

  if (fixedOk) {
    writeFileSync(enFile, newContent, 'utf8');
    totalFixed++;
    console.log(`  修复: ${slug} (${replacements.length}/${enCdnImages.length} 处替换)`);
  } else {
    console.log(`  跳过(验证失败): ${slug}`);
    for (let i = 0; i < correctCdnOrder.length; i++) {
      if (correctCdnOrder[i] !== fixedOrder[i]) {
        console.log(`    位置 ${i}: 期望 ${correctCdnOrder[i].substring(0, 60)}, 实际 ${fixedOrder[i]?.substring(0, 60)}`);
      }
    }
  }
}

console.log(`\n总共修复 ${totalFixed} 个文件`);
