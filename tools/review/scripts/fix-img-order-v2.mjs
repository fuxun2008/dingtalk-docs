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

function extractImageUrls(content) {
  const mdUrls = [...content.matchAll(/!\[[^\]]*\]\(([^)\s]+)\)/g)].map(m => ({ url: m[1], full: m[0], index: m.index }));
  const imgUrls = [...content.matchAll(/<img[^>]+src="([^"]+)"/g)].map(m => ({ url: m[1], full: m[0], index: m.index }));
  const posterUrls = [...content.matchAll(/<video[^>]+poster="([^"]+)"/g)].map(m => ({ url: m[1], full: m[0], index: m.index }));
  return [...mdUrls, ...imgUrls, ...posterUrls].sort((a, b) => a.index - b.index);
}

let totalFixed = 0;

for (const [slug, items] of slugItems) {
  const zhFile = join(repoRoot, 'zh', slug + '.mdx');
  const enFile = join(repoRoot, slug + '.mdx');
  if (!existsSync(zhFile) || !existsSync(enFile)) continue;

  const zhContent = readFileSync(zhFile, 'utf8');
  const enContent = readFileSync(enFile, 'utf8');

  // ZH 文件中 batch sourceUrl 的出现顺序
  const zhAllUrls = extractImageUrls(zhContent).map(e => e.url);
  const zhBatchUrls = zhAllUrls.filter(u => urlMap.has(u));

  const cdnToSource = new Map();
  for (const item of items) cdnToSource.set(item.cdnUrl, item.sourceUrl);

  // EN 文件中所有 CDN URL 的出现位置（按位置排序）
  const enImages = extractImageUrls(enContent);
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

  // 用占位符策略修复
  // 第一步：将每个 CDN URL 出现位置替换为唯一占位符
  let newContent = enContent;
  const placeholders = [];
  for (let i = 0; i < enCdnImages.length; i++) {
    const oldUrl = enCdnImages[i].url;
    const placeholder = `__IMG_PLACEHOLDER_${i}__`;
    // 只替换第一个出现的 oldUrl（从左到右逐个替换）
    newContent = newContent.replace(oldUrl, placeholder);
    placeholders.push({ placeholder, newUrl: correctCdnOrder[i] });
  }

  // 第二步：将占位符替换为正确的 CDN URL
  for (const p of placeholders) {
    newContent = newContent.split(p.placeholder).join(p.newUrl);
  }

  // 验证
  const fixedImages = extractImageUrls(newContent).filter(e => cdnToSource.has(e.url));
  const fixedOrder = fixedImages.map(e => e.url);
  let fixedOk = true;
  for (let i = 0; i < correctCdnOrder.length; i++) {
    if (correctCdnOrder[i] !== fixedOrder[i]) { fixedOk = false; break; }
  }

  if (fixedOk) {
    writeFileSync(enFile, newContent, 'utf8');
    totalFixed++;
    console.log(`  修复: ${slug} (${enCdnImages.length} 张图片)`);
  } else {
    console.log(`  跳过(验证失败): ${slug}`);
    // 调试信息
    for (let i = 0; i < correctCdnOrder.length; i++) {
      if (correctCdnOrder[i] !== fixedOrder[i]) {
        console.log(`    位置 ${i}: 期望 ${correctCdnOrder[i].substring(0, 50)}, 实际 ${fixedOrder[i]?.substring(0, 50)}`);
      }
    }
  }
}

console.log(`\n总共修复 ${totalFixed} 个文件`);
