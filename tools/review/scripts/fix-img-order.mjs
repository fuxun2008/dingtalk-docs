#!/usr/bin/env node
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');
const batchPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'yida-zh-en.json');
const batch = JSON.parse(readFileSync(batchPath, 'utf8'));

// 构建 sourceUrl → cdnUrl 映射，和 slug → items 映射
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

function extractImageUrls(content) {
  const mdUrls = [...content.matchAll(/!\[[^\]]*\]\(([^)\s]+)\)/g)].map(m => ({ url: m[1], full: m[0] }));
  const imgUrls = [...content.matchAll(/<img[^>]+src="([^"]+)"/g)].map(m => ({ url: m[1], full: m[0] }));
  const posterUrls = [...content.matchAll(/<video[^>]+poster="([^"]+)"/g)].map(m => ({ url: m[1], full: m[0] }));
  return [...mdUrls, ...imgUrls, ...posterUrls];
}

let totalFixed = 0;
const fixedSlugs = [];

for (const [slug, items] of slugItems) {
  const zhFile = join(repoRoot, 'zh', slug + '.mdx');
  const enFile = join(repoRoot, slug + '.mdx');
  if (!existsSync(zhFile) || !existsSync(enFile)) continue;

  const zhContent = readFileSync(zhFile, 'utf8');
  const enContent = readFileSync(enFile, 'utf8');

  // ZH 文件中 batch sourceUrl 的出现顺序
  const zhAllUrls = extractImageUrls(zhContent).map(e => e.url);
  const zhBatchUrls = zhAllUrls.filter(u => urlMap.has(u));

  // cdnToSource 反向映射
  const cdnToSource = new Map();
  for (const item of items) cdnToSource.set(item.cdnUrl, item.sourceUrl);

  // EN 文件中所有 CDN URL 的出现位置
  const enImages = extractImageUrls(enContent);
  const enCdnImages = enImages.filter(e => cdnToSource.has(e.url));

  if (zhBatchUrls.length !== enCdnImages.length) continue;

  // 正确的 CDN URL 顺序（根据 ZH 文件中 sourceUrl 的顺序）
  const correctCdnOrder = zhBatchUrls.map(src => urlMap.get(src));

  // 当前的 CDN URL 顺序
  const currentCdnOrder = enCdnImages.map(e => e.url);

  // 检查是否有顺序问题
  let hasIssue = false;
  for (let i = 0; i < correctCdnOrder.length; i++) {
    if (correctCdnOrder[i] !== currentCdnOrder[i]) { hasIssue = true; break; }
  }
  if (!hasIssue) continue;

  // 修复：将 EN 文件中每个 CDN URL 替换为正确顺序的 CDN URL
  // 策略：逐个替换。对于 EN 中第 i 个 CDN URL 出现位置，用 correctCdnOrder[i] 替换
  let newContent = enContent;
  for (let i = 0; i < enCdnImages.length; i++) {
    const oldUrl = enCdnImages[i].url;
    const newUrl = correctCdnOrder[i];
    if (oldUrl !== newUrl) {
      // 替换 URL（精确匹配整个 URL 字符串）
      newContent = newContent.split(oldUrl).join(newUrl);
    }
  }

  // 验证修复后的顺序
  const fixedImages = extractImageUrls(newContent).filter(e => cdnToSource.has(e.url));
  const fixedOrder = fixedImages.map(e => e.url);
  let fixedOk = true;
  for (let i = 0; i < correctCdnOrder.length; i++) {
    if (correctCdnOrder[i] !== fixedOrder[i]) { fixedOk = false; break; }
  }

  if (fixedOk) {
    writeFileSync(enFile, newContent, 'utf8');
    totalFixed++;
    fixedSlugs.push(slug);
    console.log(`  修复: ${slug} (${enCdnImages.length} 张图片)`);
  } else {
    console.log(`  跳过(验证失败): ${slug}`);
  }
}

console.log(`\n总共修复 ${totalFixed} 个文件`);
