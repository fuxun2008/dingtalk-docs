#!/usr/bin/env node
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';
import https from 'node:https';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');
const batchPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'yida-zh-en.json');
const batch = JSON.parse(readFileSync(batchPath, 'utf8'));
const tmpDir = '/tmp/img-size-check';
if (!existsSync(tmpDir)) mkdirSync(tmpDir, { recursive: true });

// 获取 CDN URL 的尺寸（从 tps 参数）
function getCdnSize(url) {
  const m = url.match(/tps-(\d+)-(\d+)/);
  return m ? { w: parseInt(m[1]), h: parseInt(m[2]) } : null;
}

// 下载图片并获取尺寸
function downloadAndGetSize(url, localPath) {
  if (existsSync(localPath)) {
    // 已下载
  } else {
    execSync(`curl -s "${url}" -o "${localPath}"`, { timeout: 30000 });
  }
  try {
    const out = execSync(`sips -g pixelWidth -g pixelHeight "${localPath}" 2>/dev/null`, { timeout: 5000 }).toString();
    const w = parseInt(out.match(/pixelWidth: (\d+)/)?.[1] || '0');
    const h = parseInt(out.match(/pixelHeight: (\d+)/)?.[1] || '0');
    return { w, h };
  } catch {
    return { w: 0, h: 0 };
  }
}

// 按 slug 分组 completed items
const slugItems = new Map();
for (const item of batch.items || []) {
  const cdnUrl = item.cdnUrl || item.target?.currentUrl;
  if (item.status === 'completed' && cdnUrl) {
    if (!slugItems.has(item.slug)) slugItems.set(item.slug, []);
    slugItems.get(item.slug).push({ sourceUrl: item.sourceUrl, cdnUrl, id: item.id });
  }
}

const problems = [];
let checkedSlugs = 0;
let totalItems = 0;

for (const [slug, items] of slugItems) {
  if (items.length < 2) continue; // 至少 2 张图片才可能有循环移位

  checkedSlugs++;
  totalItems += items.length;

  // 获取所有 EN 图片尺寸
  const cdnSizes = items.map(it => {
    const size = getCdnSize(it.cdnUrl);
    return { ...it, cdnSize: size };
  });

  // 如果有 cdnUrl 没有 tps 参数，跳过
  if (cdnSizes.some(s => !s.cdnSize)) continue;

  // 下载所有 ZH 图片并获取尺寸
  const zhSizes = [];
  for (let i = 0; i < items.length; i++) {
    const sourceUrl = items[i].sourceUrl;
    const ext = sourceUrl.match(/\.(png|jpg|jpeg|gif|webp)/i)?.[1] || 'png';
    const localPath = join(tmpDir, `${slug.replace(/\//g, '_')}_${i}.${ext}`);
    const size = downloadAndGetSize(sourceUrl, localPath);
    zhSizes.push({ ...items[i], zhSize: size, index: i });
  }

  // 检查每个 sourceUrl → cdnUrl 的映射是否尺寸匹配
  const mismatches = [];
  for (let i = 0; i < zhSizes.length; i++) {
    const zh = zhSizes[i];
    const cdn = cdnSizes[i];
    const zhW = zh.zhSize.w;
    const zhH = zh.zhSize.h;
    const cdnW = cdn.cdnSize.w;
    const cdnH = cdn.cdnSize.h;

    if (zhW === 0 || zhH === 0 || cdnW === 0 || cdnH === 0) continue;

    // 尺寸完全匹配（允许 tps 缩放后的尺寸不完全一致，检查宽高比）
    const zhRatio = zhW / zhH;
    const cdnRatio = cdnW / cdnH;
    const ratioDiff = Math.abs(zhRatio - cdnRatio) / Math.max(zhRatio, cdnRatio);

    if (zhW === cdnW && zhH === cdnH) {
      // 尺寸完全匹配
      continue;
    }

    // 检查是否在 cdnSizes 中有尺寸匹配的
    const correctCdn = cdnSizes.find(c => {
      if (!c.cdnSize) return false;
      return c.cdnSize.w === zhW && c.cdnSize.h === zhH;
    });

    if (correctCdn && correctCdn.cdnUrl !== zh.cdnUrl) {
      mismatches.push({
        index: i,
        sourceUrl: zh.sourceUrl,
        currentCdn: zh.cdnUrl,
        correctCdn: correctCdn.cdnUrl,
        zhSize: `${zhW}x${zhH}`,
        currentCdnSize: `${cdnW}x${cdnH}`,
        correctCdnSize: `${correctCdn.cdnSize.w}x${correctCdn.cdnSize.h}`,
      });
    }
  }

  if (mismatches.length > 0) {
    problems.push({ slug, mismatches, itemCount: items.length });
    console.log(`问题: ${slug} (${mismatches.length}/${items.length} 处不匹配)`);
    for (const m of mismatches) {
      console.log(`  位置 ${m.index}: ZH[${m.zhSize}] 当前[${m.currentCdnSize}] 应为[${m.correctCdnSize}]`);
      console.log(`    当前: ${m.currentCdn.substring(0, 60)}`);
      console.log(`    应为: ${m.correctCdn.substring(0, 60)}`);
    }
  }

  // 进度报告
  if (checkedSlugs % 50 === 0) {
    console.log(`进度: ${checkedSlugs}/${slugItems.size} 文件, ${totalItems} 图片`);
  }
}

console.log(`\n=== 检查完成 ===`);
console.log(`检查文件数: ${checkedSlugs}`);
console.log(`有问题的文件数: ${problems.length}`);

// 保存问题列表
writeFileSync(join(tmpDir, 'size-mismatch-problems.json'), JSON.stringify(problems, null, 2), 'utf8');
console.log(`问题列表已保存到 ${tmpDir}/size-mismatch-problems.json`);
