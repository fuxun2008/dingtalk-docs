#!/usr/bin/env node
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');
const batchPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'yida-zh-en.json');
const problemsPath = '/tmp/img-size-check/size-mismatch-problems.json';

const batch = JSON.parse(readFileSync(batchPath, 'utf8'));
const problems = JSON.parse(readFileSync(problemsPath, 'utf8'));

function getCdnSize(url) {
  const m = url.match(/tps-(\d+)-(\d+)/);
  return m ? { w: parseInt(m[1]), h: parseInt(m[2]) } : null;
}

function extractImageUrlsWithPos(content) {
  const results = [];
  for (const m of content.matchAll(/!\[[^\]]*\]\(([^)\s]+)\)/g)) {
    const urlStart = m.index + m[0].indexOf(m[1]);
    results.push({ url: m[1], start: urlStart, end: urlStart + m[1].length });
  }
  for (const m of content.matchAll(/<img[^>]+src="([^"]+)"/g)) {
    const urlStart = m.index + m[0].indexOf('"' + m[1]) + 1;
    results.push({ url: m[1], start: urlStart, end: urlStart + m[1].length });
  }
  for (const m of content.matchAll(/<video[^>]+poster="([^"]+)"/g)) {
    const urlStart = m.index + m[0].indexOf('"' + m[1]) + 1;
    results.push({ url: m[1], start: urlStart, end: urlStart + m[1].length });
  }
  return results.sort((a, b) => a.start - b.start);
}

let totalFixed = 0;

for (const problem of problems) {
  const { slug, mismatches } = problem;
  const enFile = join(repoRoot, slug + '.mdx');
  if (!existsSync(enFile)) continue;

  const enContent = readFileSync(enFile, 'utf8');

  // 获取该 slug 的所有 completed batch items（按顺序）
  const items = (batch.items || []).filter(i => i.slug === slug && i.status === 'completed');
  const cdnToSource = new Map();
  for (const item of items) {
    const cdn = item.cdnUrl || item.target?.currentUrl;
    cdnToSource.set(cdn, item.sourceUrl);
  }

  // EN 文件中所有 CDN URL 的位置（按位置排序）
  const enImages = extractImageUrlsWithPos(enContent);
  const enCdnImages = enImages.filter(e => cdnToSource.has(e.url));

  if (mismatches.length === 0) continue;

  // 不匹配的位置索引（在 enCdnImages 中的索引）
  const mismatchIndices = mismatches.map(m => m.index);

  // 收集不匹配位置的 cdnUrl 和 ZH 尺寸
  const availableCdns = []; // 不匹配位置当前的 cdnUrl（可以重新分配）
  const neededSizes = [];   // 不匹配位置需要的 ZH 尺寸

  for (const m of mismatches) {
    const currentCdn = m.currentCdn;
    const cdnSize = getCdnSize(currentCdn);
    if (cdnSize) availableCdns.push(currentCdn);
    neededSizes.push({
      index: m.index,
      w: parseInt(m.zhSize.split('x')[0]),
      h: parseInt(m.zhSize.split('x')[1]),
      currentCdn: m.currentCdn,
    });
  }

  // 在可用 cdnUrl 中为每个不匹配位置找到尺寸匹配的 cdnUrl
  const usedCdns = new Set();
  const replacements = []; // { start, end, oldUrl, newUrl }

  for (const need of neededSizes) {
    // 在可用 cdnUrl 中找到尺寸匹配且未被使用的
    const match = availableCdns.find(cdn => {
      if (usedCdns.has(cdn)) return false;
      const size = getCdnSize(cdn);
      return size && size.w === need.w && size.h === need.h;
    });

    if (match && match !== need.currentCdn) {
      // 找到 EN 文件中该位置的 cdnUrl
      const enImg = enCdnImages[need.index];
      if (enImg) {
        replacements.push({
          start: enImg.start,
          end: enImg.end,
          oldUrl: enImg.url,
          newUrl: match,
        });
        usedCdns.add(match);
      }
    } else if (match === need.currentCdn) {
      // 已经正确，不需要替换
      usedCdns.add(match);
    } else {
      console.log(`  警告: ${slug} 位置 ${need.index} 找不到匹配的 cdnUrl (需要 ${need.w}x${need.h})`);
    }
  }

  if (replacements.length === 0) {
    console.log(`  跳过: ${slug} (无需替换)`);
    continue;
  }

  // 从后往前替换（避免位置偏移）
  replacements.sort((a, b) => b.start - a.start);
  let newContent = enContent;
  for (const r of replacements) {
    newContent = newContent.substring(0, r.start) + r.newUrl + newContent.substring(r.end);
  }

  // 验证：替换后所有不匹配位置的 cdnUrl 尺寸是否匹配
  const fixedImages = extractImageUrlsWithPos(newContent).filter(e => cdnToSource.has(e.url));
  let allOk = true;
  for (const m of mismatches) {
    const fixedUrl = fixedImages[m.index]?.url;
    const fixedSize = getCdnSize(fixedUrl);
    const needW = parseInt(m.zhSize.split('x')[0]);
    const needH = parseInt(m.zhSize.split('x')[1]);
    if (!fixedSize || fixedSize.w !== needW || fixedSize.h !== needH) {
      allOk = false;
      console.log(`  验证失败: ${slug} 位置 ${m.index} 期望 ${m.zhSize} 实际 ${fixedSize ? fixedSize.w + 'x' + fixedSize.h : 'null'}`);
    }
  }

  if (allOk) {
    writeFileSync(enFile, newContent, 'utf8');
    totalFixed++;
    console.log(`  修复: ${slug} (${replacements.length} 处替换)`);
    for (const r of replacements) {
      console.log(`    ${r.oldUrl.substring(0, 50)} → ${r.newUrl.substring(0, 50)}`);
    }

    // 同时更新 batch items 中的 cdnUrl
    for (const r of replacements) {
      const item = items.find(it => {
        const cdn = it.cdnUrl || it.target?.currentUrl;
        return cdn === r.oldUrl;
      });
      if (item) {
        // 找到这个 item 对应的 sourceUrl（通过位置）
        const enImg = enCdnImages.find(e => e.url === r.oldUrl);
        if (enImg) {
          const idx = enCdnImages.indexOf(enImg);
          const sourceItem = items[idx];
          if (sourceItem) {
            sourceItem.cdnUrl = r.newUrl;
            if (!sourceItem.target) sourceItem.target = {};
            sourceItem.target.currentUrl = r.newUrl;
          }
        }
      }
    }
  } else {
    console.log(`  跳过(验证失败): ${slug}`);
  }
}

// 保存更新后的 batch job
writeFileSync(batchPath, JSON.stringify(batch, null, 2), 'utf8');
console.log(`\n总共修复 ${totalFixed} 个文件`);
console.log('batch job 已更新');
