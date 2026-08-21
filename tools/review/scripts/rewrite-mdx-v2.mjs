#!/usr/bin/env node
/**
 * MDX 图片回写脚本 v2（安全版）
 *
 * 核心改进（相比 v1）：
 * 1. 只插入新行，不修改/删除任何原有行
 * 2. 用标题对齐 + 段落比例定位（而非行号比例）
 * 3. 只在段落边界（空行）插入，不在表格/组件内部插入
 * 4. 保留 <Frame> 组件包裹
 * 5. 跳过表格行内图片（不破坏表格结构）
 * 6. 跳过内联图片（不修改原有行）
 *
 * 处理类型：
 * - <Frame> 块（84.1%）：整块替换 URL 后插入
 * - <video poster>（1.7%）：替换 URL 后插入
 * - 独立图片行（部分 7.0%）：替换 URL 后插入
 * - 表格行内图片（6.3%）：跳过
 * - 内联图片（部分 7.0%）：跳过
 * - <Step> 内图片（1.0%）：在 <Step> 后插入 <Frame>
 */

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');
const batchPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'yida-zh-en.json');

// ─── 工具函数 ───

/**
 * 找到所有标题行
 */
function findHeadings(lines) {
  const headings = [];
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^(#+)\s/);
    if (m) headings.push({ lineIdx: i, level: m[1].length });
  }
  return headings;
}

/**
 * 找到 frontmatter 结束位置
 */
function findFrontmatterEnd(lines) {
  if (lines[0]?.trim() !== '---') return 0;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === '---') return i + 1;
  }
  return 0;
}

/**
 * 将行列表按空行分段（段落）
 * 返回 [{ start, end }] 数组，start/end 为行索引
 */
function segmentParagraphs(lines, startIdx, endIdx) {
  const paragraphs = [];
  let paraStart = -1;
  for (let i = startIdx; i < endIdx; i++) {
    if (lines[i].trim() !== '') {
      if (paraStart === -1) paraStart = i;
    } else {
      if (paraStart !== -1) {
        paragraphs.push({ start: paraStart, end: i });
        paraStart = -1;
      }
    }
  }
  if (paraStart !== -1) {
    paragraphs.push({ start: paraStart, end: endIdx });
  }
  return paragraphs;
}

/**
 * 替换文本中的所有 URL（sourceUrl → cdnUrl）
 */
function replaceAllUrls(text, urlMap) {
  let result = text;
  for (const [sourceUrl, cdnUrl] of urlMap) {
    if (result.includes(sourceUrl)) {
      result = result.split(sourceUrl).join(cdnUrl);
    }
  }
  return result;
}

/**
 * 检查行是否包含任何 sourceUrl
 */
function findSourceUrl(line, urlMap) {
  for (const [sourceUrl, cdnUrl] of urlMap) {
    if (line.includes(sourceUrl)) {
      return { sourceUrl, cdnUrl };
    }
  }
  return null;
}

// ─── 主逻辑 ───

const batch = JSON.parse(readFileSync(batchPath, 'utf8'));
const applied = batch.items.filter(
  (i) => i.status === 'completed' && (i.cdnUrl || i.target?.currentUrl)
);

const bySlug = new Map();
for (const item of applied) {
  const arr = bySlug.get(item.slug) || [];
  arr.push(item);
  bySlug.set(item.slug, arr);
}

let totalInserted = 0;
let totalSkippedTable = 0;
let totalSkippedInline = 0;
let totalFiles = 0;

const testSlugs = process.env.TEST_SLUGS;
const testFilter = testSlugs
  ? new Set(testSlugs.split(',').map((s) => s.trim()))
  : null;

for (const [slug, items] of bySlug) {
  if (testFilter && !testFilter.has(slug)) continue;

  const zhPath = join(repoRoot, 'zh', slug + '.mdx');
  const enPath = join(repoRoot, slug + '.mdx');

  if (!existsSync(zhPath) || !existsSync(enPath)) continue;

  const zhContent = readFileSync(zhPath, 'utf8');
  const enContent = readFileSync(enPath, 'utf8');
  const zhLines = zhContent.split('\n');
  const enLines = enContent.split('\n');

  // 构建 sourceUrl → cdnUrl 映射
  const urlMap = new Map();
  for (const item of items) {
    const cdnUrl = item.cdnUrl || item.target?.currentUrl;
    if (cdnUrl) urlMap.set(item.sourceUrl, cdnUrl);
  }

  // ── 1. 在中文版中找到所有图片块 ──
  const imgBlocks = [];
  const processedFrameStarts = new Set(); // 避免重复处理同一 Frame 块

  for (let i = 0; i < zhLines.length; i++) {
    const line = zhLines[i];
    const urlMatch = findSourceUrl(line, urlMap);
    if (!urlMatch) continue;

    // ── 1a. 检查是否在 <Frame> 块内 ──
    let frameStart = -1;
    let frameEnd = -1;
    for (let j = i - 1; j >= Math.max(0, i - 5); j--) {
      if (zhLines[j].trim() === '<Frame>') {
        frameStart = j;
        break;
      }
      // 如果遇到其他非空行（非 Frame 标签），停止向上搜索
      if (zhLines[j].trim() !== '' && !zhLines[j].match(/^\s*$/)) {
        break;
      }
    }
    if (frameStart >= 0) {
      for (let j = i + 1; j < Math.min(zhLines.length, i + 5); j++) {
        if (zhLines[j].trim() === '</Frame>') {
          frameEnd = j;
          break;
        }
      }
    }

    if (frameStart >= 0 && frameEnd >= 0) {
      if (processedFrameStarts.has(frameStart)) continue;
      processedFrameStarts.add(frameStart);

      // 提取 Frame 块中的纯图片行（跳过包含中文文字的行）
      const rawLines = zhLines.slice(frameStart, frameEnd + 1);
      const imgOnlyLines = [];
      for (const l of rawLines) {
        const trimmed = l.trim();
        // 保留 <Frame> 和 </Frame> 标签
        if (trimmed === '<Frame>' || trimmed === '</Frame>') {
          imgOnlyLines.push(l);
          continue;
        }
        // 保留纯图片行：整行只有 ![](url) 或 <img.../>
        if (
          /^\s*(!\[.*\]\([^)]+\)|<img\b[^>]*\/??>)\s*$/i.test(l)
        ) {
          imgOnlyLines.push(replaceAllUrls(l, urlMap));
        }
        // 包含中文文字+图片的行：跳过（不把中文文字带入英文版）
      }
      // 只有当提取出至少一个图片行时才插入
      if (imgOnlyLines.length > 2) {
        // >2 因为至少有 <Frame>、图片行、</Frame>
        imgBlocks.push({
          zhLineIdx: frameStart,
          zhLineEnd: frameEnd,
          type: 'frame',
          content: imgOnlyLines.join('\n'),
        });
      }
      continue;
    }

    // ── 1b. 检查是否是 <video poster="url"> 标签 ──
    if (line.includes('<video') && line.includes('poster=')) {
      imgBlocks.push({
        zhLineIdx: i,
        zhLineEnd: i,
        type: 'video',
        content: replaceAllUrls(line, urlMap),
      });
      continue;
    }

    // ── 1c. 检查是否在表格行中（markdown 表格或 HTML table） ──
    if (
      line.match(/^\s*\|/) ||
      line.includes('<td') ||
      line.includes('<tr') ||
      line.match(/^\s*\|[-:|\s]+\|/)
    ) {
      totalSkippedTable++;
      continue;
    }

    // ── 1d. 检查是否在 <Step> 组件内 ──
    let inStep = false;
    for (let j = i - 1; j >= Math.max(0, i - 10); j--) {
      if (zhLines[j].includes('<Step')) {
        inStep = true;
        break;
      }
      if (zhLines[j].includes('</Step>') || zhLines[j].includes('</Steps>')) {
        break;
      }
    }
    if (inStep) {
      // 在 <Step> 内的图片：只处理纯图片行，跳过文字+图片混合行
      const trimmed = line.trim();
      if (/^(!\[.*\]\([^)]+\)|<img\b[^>]*\/??>)\s*$/i.test(trimmed)) {
        const newContent = replaceAllUrls(line, urlMap);
        imgBlocks.push({
          zhLineIdx: i,
          zhLineEnd: i,
          type: 'step-img',
          content: `<Frame>\n  ${newContent.trim()}\n</Frame>`,
        });
      } else {
        // 文字+图片混合行：跳过
        totalSkippedInline++;
      }
      continue;
    }

    // ── 1e. 检查是否是独立图片行（整行只有图片） ──
    const trimmed = line.trim();
    if (
      /^(!\[.*\]\([^)]+\)|<img\b[^>]*\/?>)\s*$/i.test(trimmed) ||
      /^\s*(!\[.*\]\([^)]+\)|<img\b[^>]*\/?>)\s*$/i.test(line)
    ) {
      imgBlocks.push({
        zhLineIdx: i,
        zhLineEnd: i,
        type: 'standalone',
        content: replaceAllUrls(line, urlMap),
      });
      continue;
    }

    // ── 1f. 内联图片（与文字混合在同一行） ──
    // 跳过，不修改原有行
    totalSkippedInline++;
  }

  if (imgBlocks.length === 0) continue;

  // ── 2. 找到中英文版的标题和 frontmatter ──
  const zhHeadings = findHeadings(zhLines);
  const enHeadings = findHeadings(enLines);
  const zhFmEnd = findFrontmatterEnd(zhLines);
  const enFmEnd = findFrontmatterEnd(enLines);

  // ── 3. 对于每个图片块，找到英文版中的插入位置 ──
  const insertions = [];

  for (const block of imgBlocks) {
    // 找到图片块所在标题区间
    let zhHeadingBefore = -1;
    let zhHeadingAfter = -1;
    for (let h = 0; h < zhHeadings.length; h++) {
      if (zhHeadings[h].lineIdx <= block.zhLineIdx) zhHeadingBefore = h;
      if (zhHeadings[h].lineIdx > block.zhLineIdx && zhHeadingAfter === -1) {
        zhHeadingAfter = h;
        break;
      }
    }

    let enInsertLine;

    if (zhHeadingBefore >= 0 && zhHeadingBefore < enHeadings.length) {
      const enHeadingBefore = enHeadings[zhHeadingBefore];
      const zhStart = zhHeadings[zhHeadingBefore].lineIdx;
      const zhEnd =
        zhHeadingAfter >= 0 ? zhHeadings[zhHeadingAfter].lineIdx : zhLines.length;
      const enStart = enHeadingBefore.lineIdx;
      const enEnd =
        zhHeadingAfter >= 0 && zhHeadingAfter < enHeadings.length
          ? enHeadings[zhHeadingAfter].lineIdx
          : enLines.length;

      // 计算中文版中图片块的段落序号
      const zhParas = segmentParagraphs(zhLines, zhStart, zhEnd);
      let zhParaIdx = 0;
      for (let p = 0; p < zhParas.length; p++) {
        if (block.zhLineIdx >= zhParas[p].start && block.zhLineIdx < zhParas[p].end) {
          zhParaIdx = p;
          break;
        }
        if (block.zhLineIdx >= zhParas[p].end) zhParaIdx = p + 1;
      }

      // 计算英文版中对应的段落位置
      const enParas = segmentParagraphs(enLines, enStart, enEnd);

      if (enParas.length === 0) {
        enInsertLine = enEnd;
      } else {
        // 用段落比例计算
        const paraRatio = zhParas.length > 0 ? zhParaIdx / zhParas.length : 0;
        const enParaIdx = Math.min(
          Math.floor(paraRatio * enParas.length),
          enParas.length - 1
        );
        // 在对应段落之后插入
        enInsertLine = enParas[enParaIdx].end;
      }
    } else if (zhHeadingBefore === -1 && zhFmEnd > 0) {
      // 在 frontmatter 之后
      const zhParas = segmentParagraphs(zhLines, zhFmEnd, zhLines.length);
      let zhParaIdx = 0;
      for (let p = 0; p < zhParas.length; p++) {
        if (block.zhLineIdx >= zhParas[p].start && block.zhLineIdx < zhParas[p].end) {
          zhParaIdx = p;
          break;
        }
        if (block.zhLineIdx >= zhParas[p].end) zhParaIdx = p + 1;
      }

      const enParas = segmentParagraphs(enLines, enFmEnd, enLines.length);
      if (enParas.length === 0) {
        enInsertLine = enLines.length;
      } else {
        const paraRatio = zhParas.length > 0 ? zhParaIdx / zhParas.length : 0;
        const enParaIdx = Math.min(
          Math.floor(paraRatio * enParas.length),
          enParas.length - 1
        );
        enInsertLine = enParas[enParaIdx].end;
      }
    } else {
      enInsertLine = enLines.length;
    }

    // 确保插入位置在 frontmatter 之后
    enInsertLine = Math.max(enFmEnd, Math.min(enInsertLine, enLines.length));

    insertions.push({
      enInsertLine,
      content: block.content,
      type: block.type,
    });
  }

  // ── 4. 处理插入（从后往前，避免偏移） ──
  insertions.sort((a, b) => b.enInsertLine - a.enInsertLine);

  const newEnLines = [...enLines];
  for (const ins of insertions) {
    const lines = ins.content.split('\n');

    // 检查前一行是否是空行
    const prevLine = newEnLines[ins.enInsertLine - 1];
    const needBlankBefore =
      prevLine !== undefined && prevLine.trim() !== '';

    // 检查后一行是否是空行
    const nextLine = newEnLines[ins.enInsertLine];
    const needBlankAfter =
      nextLine !== undefined && nextLine.trim() !== '';

    // 构建插入内容（前后加空行）
    const parts = [];
    if (needBlankBefore) parts.push('');
    parts.push(...lines);
    if (needBlankAfter) parts.push('');

    newEnLines.splice(ins.enInsertLine, 0, ...parts);
    totalInserted++;
  }

  // ── 5. 写入文件 ──
  writeFileSync(enPath, newEnLines.join('\n'));
  totalFiles++;
}

console.log(`\n=== 回写完成 v2 ===`);
console.log(`文件数: ${totalFiles}`);
console.log(`插入图片块: ${totalInserted}`);
console.log(`跳过表格图片: ${totalSkippedTable}`);
console.log(`跳过内联图片: ${totalSkippedInline}`);
