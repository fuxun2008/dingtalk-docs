#!/usr/bin/env node
/**
 * MDX 图片回写脚本（重写版）
 *
 * 核心策略：逐行扫描中文 MDX，找到所有图片行，按类型分别处理：
 * - standalone（独立图片行）：直接插入替换 URL 后的整行
 * - inline（内联图片行）：提取图片标签，在英文 MDX 对应行中追加
 * - table（表格图片行）：提取图片标签，在英文 MDX 对应表格行中追加
 *
 * 插入位置用"标题对齐 + 行号比例"确定。
 */

import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');
const batchPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'yida-zh-en.json');

// ─── 工具函数 ───

function escapeRegex(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * 从中文 MDX 行中提取所有图片标签（保留完整属性）
 * 返回 [{ tag, url, sourceUrl }] 数组
 */
function extractImgTags(line, urlMap) {
  const tags = [];
  // 匹配 Markdown 图片 ![alt](url)
  const mdRe = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)/g;
  let m;
  while ((m = mdRe.exec(line))) {
    const url = m[2];
    if (urlMap.has(url)) {
      tags.push({ tag: m[0], sourceUrl: url, cdnUrl: urlMap.get(url), format: 'markdown' });
    }
  }
  // 匹配 HTML <img> 标签（保留完整属性）
  const htmlRe = /<img\b[^>]*\/?>/gi;
  while ((m = htmlRe.exec(line))) {
    const srcMatch = /\bsrc\s*=\s*(["'])(.*?)\1/i.exec(m[0]);
    if (srcMatch && urlMap.has(srcMatch[2])) {
      tags.push({ tag: m[0], sourceUrl: srcMatch[2], cdnUrl: urlMap.get(srcMatch[2]), format: 'img' });
    }
  }
  // 匹配 <video poster="url">
  const videoRe = /<video\b[^>]*>/gi;
  while ((m = videoRe.exec(line))) {
    const posterMatch = /\bposter\s*=\s*(["'])(.*?)\1/i.exec(m[0]);
    if (posterMatch && urlMap.has(posterMatch[2])) {
      tags.push({ tag: m[0], sourceUrl: posterMatch[2], cdnUrl: urlMap.get(posterMatch[2]), format: 'video-poster' });
    }
  }
  return tags;
}

/**
 * 替换行中的所有图片 URL
 */
function replaceUrls(line, urlMap) {
  let result = line;
  for (const [sourceUrl, cdnUrl] of urlMap) {
    if (result.includes(sourceUrl)) {
      result = result.split(sourceUrl).join(cdnUrl);
    }
  }
  return result;
}

/**
 * 判断图片行类型
 */
function classifyLine(line) {
  if (!line.includes('|')) {
    // 检查是否整行只有图片（含空格）
    if (/^\s*(!\[.*?\]\([^)]+\)|<img\b[^>]*\/?>)\s*$/i.test(line)) {
      return 'standalone';
    }
  }
  if (line.includes('|') && /!\[|<img/i.test(line)) {
    return 'table';
  }
  if (line.includes('<video') && /poster=/.test(line)) {
    return 'video-poster';
  }
  return 'inline';
}

/**
 * 在英文 MDX 中找到所有标题
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

// ─── 主逻辑 ───

const batch = JSON.parse(readFileSync(batchPath, 'utf8'));
// 兼容两种 CDN URL 属性：cdnUrl（旧格式）和 target.currentUrl（新格式）
const applied = batch.items.filter((i) => i.status === 'completed' && (i.cdnUrl || i.target?.currentUrl));

// 按 slug 分组
const bySlug = new Map();
for (const item of applied) {
  const arr = bySlug.get(item.slug) || [];
  arr.push(item);
  bySlug.set(item.slug, arr);
}

let totalApplied = 0;
let totalSkipped = 0;
let totalFiles = 0;
const problemSlugs = [];

// 测试模式：只处理指定 slug（逗号分隔）
const testSlugs = process.env.TEST_SLUGS;
const testFilter = testSlugs ? new Set(testSlugs.split(',').map((s) => s.trim())) : null;

for (const [slug, items] of bySlug) {
  const zhPath = join(repoRoot, 'zh', slug + '.mdx');
  const enPath = join(repoRoot, slug + '.mdx');

  if (testFilter && !testFilter.has(slug)) continue;

  if (!existsSync(zhPath) || !existsSync(enPath)) {
    totalSkipped += items.length;
    continue;
  }

  const zhContent = readFileSync(zhPath, 'utf8');
  const enContent = readFileSync(enPath, 'utf8');
  const zhLines = zhContent.split('\n');
  const enLines = enContent.split('\n');

  // 构建 sourceUrl → cdnUrl 映射（兼容 cdnUrl 和 target.currentUrl）
  const urlMap = new Map();
  for (const item of items) {
    const cdnUrl = item.cdnUrl || item.target?.currentUrl;
    if (cdnUrl) urlMap.set(item.sourceUrl, cdnUrl);
  }

  // 1. 在中文 MDX 中找到所有图片行
  const imgLines = [];
  for (let i = 0; i < zhLines.length; i++) {
    const line = zhLines[i];
    // 检查这行是否包含任何 sourceUrl
    let hasImg = false;
    for (const [sourceUrl] of urlMap) {
      if (line.includes(sourceUrl)) {
        hasImg = true;
        break;
      }
    }
    if (hasImg) {
      const type = classifyLine(line);
      const tags = extractImgTags(line, urlMap);
      imgLines.push({ zhLineIdx: i, line, type, tags });
    }
  }

  if (imgLines.length === 0) {
    totalSkipped += items.length;
    continue;
  }

  // 2. 找到中英文 MDX 的标题
  const zhHeadings = findHeadings(zhLines);
  const enHeadings = findHeadings(enLines);
  const zhFrontmatterEnd = findFrontmatterEnd(zhLines);
  const enFrontmatterEnd = findFrontmatterEnd(enLines);

  // 3. 对于每个图片行，找到英文 MDX 中的插入位置
  //    用「标题范围内比例」对齐：找到图片行所在标题区间 [N, N+1)，
  //    在英文 MDX 对应区间内按比例计算插入位置
  const insertions = [];
  for (const imgLine of imgLines) {
    // 找到图片行之前和之后最近的标题
    let zhHeadingBefore = -1;
    let zhHeadingAfter = -1;
    for (let i = 0; i < zhHeadings.length; i++) {
      if (zhHeadings[i].lineIdx < imgLine.zhLineIdx) zhHeadingBefore = i;
      if (zhHeadings[i].lineIdx > imgLine.zhLineIdx && zhHeadingAfter === -1) { zhHeadingAfter = i; break; }
    }

    let enInsertLine;
    if (zhHeadingBefore >= 0 && zhHeadingBefore < enHeadings.length) {
      const enHeadingBefore = enHeadings[zhHeadingBefore];
      // 计算中文标题区间范围
      const zhStart = zhHeadings[zhHeadingBefore].lineIdx;
      const zhEnd = zhHeadingAfter >= 0 ? zhHeadings[zhHeadingAfter].lineIdx : zhLines.length;
      // 计算英文标题区间范围
      const enStart = enHeadingBefore.lineIdx;
      const enEnd = (zhHeadingAfter >= 0 && zhHeadingAfter < enHeadings.length)
        ? enHeadings[zhHeadingAfter].lineIdx : enLines.length;
      // 在区间内按比例对齐
      const zhRange = zhEnd - zhStart;
      const enRange = enEnd - enStart;
      const ratio = zhRange > 0 ? enRange / zhRange : 1;
      const relPos = imgLine.zhLineIdx - zhStart;
      enInsertLine = enStart + Math.round(relPos * ratio);
    } else if (zhHeadingBefore === -1 && zhFrontmatterEnd > 0) {
      // 在 frontmatter 之后，用行号比例
      const zhBody = zhLines.length - zhFrontmatterEnd;
      const enBody = enLines.length - enFrontmatterEnd;
      const ratio = zhBody > 0 ? enBody / zhBody : 1;
      const relPos = imgLine.zhLineIdx - zhFrontmatterEnd;
      enInsertLine = enFrontmatterEnd + Math.round(relPos * ratio);
    } else {
      // 没有标题和 frontmatter，用行号比例
      const ratio = enLines.length / Math.max(zhLines.length, 1);
      enInsertLine = Math.round(imgLine.zhLineIdx * ratio);
    }

    enInsertLine = Math.max(enFrontmatterEnd, Math.min(enInsertLine, enLines.length - 1));

    // 生成插入内容
    if (imgLine.type === 'standalone') {
      // 独立图片行：替换 URL，保留缩进
      const newLine = replaceUrls(imgLine.line, urlMap);
      insertions.push({ enInsertLine, content: newLine, type: 'standalone' });
    } else if (imgLine.type === 'table') {
      // 表格图片：提取图片标签，替换 URL
      const imgTags = imgLine.tags
        .map((t) => {
          // 保留完整标签，只替换 URL
          if (t.format === 'img') {
            // HTML <img> 标签：替换 src 属性
            return t.tag.replace(
              new RegExp('(\\bsrc\\s*=\\s*)(["\'])' + escapeRegex(t.sourceUrl) + '\\2', 'i'),
              `$1$2${t.cdnUrl}$2`,
            );
          } else {
            // Markdown 图片：替换 URL
            return t.tag.replace(t.sourceUrl, t.cdnUrl);
          }
        })
        .join('<br />');
      insertions.push({ enInsertLine, content: imgTags, type: 'table' });
    } else if (imgLine.type === 'video-poster') {
      // video poster：提取 <video> 标签，替换 poster URL
      const videoTags = imgLine.tags
        .map((t) =>
          t.tag.replace(
            new RegExp('(\\bposter\\s*=\\s*)(["\'])' + escapeRegex(t.sourceUrl) + '\\2', 'i'),
            `$1$2${t.cdnUrl}$2`,
          ),
        )
        .join('');
      insertions.push({ enInsertLine, content: videoTags, type: 'video-poster' });
    } else {
      // 内联图片：提取图片标签，替换 URL
      const imgTags = imgLine.tags
        .map((t) => {
          if (t.format === 'img') {
            return t.tag.replace(
              new RegExp('(\\bsrc\\s*=\\s*)(["\'])' + escapeRegex(t.sourceUrl) + '\\2', 'i'),
              `$1$2${t.cdnUrl}$2`,
            );
          } else {
            return t.tag.replace(t.sourceUrl, t.cdnUrl);
          }
        })
        .join('');
      insertions.push({ enInsertLine, content: imgTags, type: 'inline' });
    }
  }

  // 4. 处理插入（从后往前，避免偏移）
  insertions.sort((a, b) => b.enInsertLine - a.enInsertLine);

  const newEnLines = [...enLines];
  for (const ins of insertions) {
    if (ins.type === 'standalone') {
      // 独立图片行：在插入位置之后插入图片行
      // 如果当前行不是空行，先加一个空行分隔
      const curLine = newEnLines[ins.enInsertLine];
      const needBlankBefore = curLine !== undefined && curLine.trim() !== '';
      // 检查下一行是否是空行
      const nextIdx = ins.enInsertLine + (needBlankBefore ? 1 : 0);
      const nextLine = newEnLines[nextIdx + 1];
      const needBlankAfter = nextLine !== undefined && nextLine.trim() !== '';
      const parts = [ins.content];
      if (needBlankBefore) parts.unshift('');
      if (needBlankAfter) parts.push('');
      newEnLines.splice(ins.enInsertLine + 1, 0, ...parts);
      totalApplied++;
    } else if (ins.type === 'video-poster') {
      // video poster：直接插入替换后的 <video> 标签
      const line = newEnLines[ins.enInsertLine];
      if (line && line.includes('<video')) {
        // 英文已有 <video> 标签，替换整行
        newEnLines[ins.enInsertLine] = ins.content;
      } else {
        // 直接插入
        newEnLines.splice(ins.enInsertLine + 1, 0, ins.content);
      }
      totalApplied++;
    } else if (ins.type === 'table') {
      // 表格图片：在对应位置的表格行中追加
      const line = newEnLines[ins.enInsertLine];
      if (line && line.includes('|')) {
        const lastPipeIdx = line.lastIndexOf('|');
        if (lastPipeIdx > 0) {
          const before = line.slice(0, lastPipeIdx);
          const after = line.slice(lastPipeIdx);
          newEnLines[ins.enInsertLine] = before + '<br />' + ins.content + after;
          totalApplied++;
        } else {
          newEnLines.splice(ins.enInsertLine + 1, 0, '  ' + ins.content);
          totalApplied++;
        }
      } else {
        newEnLines.splice(ins.enInsertLine + 1, 0, '  ' + ins.content);
        totalApplied++;
      }
    } else {
      // 内联图片：在对应位置的行末尾追加图片标签
      const line = newEnLines[ins.enInsertLine];
      if (line !== undefined) {
        newEnLines[ins.enInsertLine] = line + ins.content;
        totalApplied++;
      } else {
        newEnLines.splice(ins.enInsertLine + 1, 0, ins.content);
        totalApplied++;
      }
    }
  }

  // 5. 写入文件
  writeFileSync(enPath, newEnLines.join('\n'));
  totalFiles++;
}

console.log(`\n=== 回写完成 ===`);
console.log(`文件数: ${totalFiles}`);
console.log(`图片行数: ${totalApplied}`);
console.log(`跳过: ${totalSkipped}`);
if (problemSlugs.length > 0) {
  console.log(`问题 slug: ${problemSlugs.length}`);
}
