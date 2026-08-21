#!/usr/bin/env node
/**
 * embed-table-images.mjs
 *
 * 将中文版表格/行内嵌入的图片，用 CDN URL 正确嵌入到英文版对应位置。
 *
 * 三类处理：
 * 1. HTML <td> 内 markdown 图片  — 按表格序号 + 行号对齐，在 <td> 对应位置插入
 * 2. Markdown 表格行内图片       — 按表格序号 + 行号对齐，在单元格内插入
 * 3. 普通行内 <img> inline-icon — 在英文版对应行中语义位置插入
 */
import { readFileSync, writeFileSync } from 'node:fs';
import { execSync } from 'node:child_process';

// ── 1. 加载 batch JSON，构建 sourceUrl → cdnUrl 映射 ──
const batchPath = 'tools/review/.cache/image-batches/yida-zh-en.json';
const batch = JSON.parse(readFileSync(batchPath, 'utf8'));
const batchItems = batch.items || batch;

/** @type {Map<string, Map<string, string>>} slug → (sourceUrl → cdnUrl) */
const slugMap = new Map();
for (const m of batchItems) {
  const cdn = m.cdnUrl || m.target?.currentUrl || '';
  if (!cdn) continue;
  if (!slugMap.has(m.slug)) slugMap.set(m.slug, new Map());
  slugMap.get(m.slug).set(m.sourceUrl, cdn);
}

console.log(`batch JSON: ${batchItems.length} 条映射, ${slugMap.size} 个 slug`);

// ── 2. 找到所有中文版 yida 文件 ──
const zhFiles = execSync('find zh/yida -name "*.mdx" -type f', { encoding: 'utf8' })
  .trim().split('\n').filter(Boolean);

let totalFiles = 0;
let totalInserted = 0;
const stats = { htmlTd: 0, mdTable: 0, inlineImg: 0, skipped: 0 };

for (const zhFile of zhFiles) {
  let zhContent;
  try { zhContent = readFileSync(zhFile, 'utf8'); } catch { continue; }

  const zhLines = zhContent.split('\n');

  // 快速检查：是否有需要处理的图片
  let hasTableImage = false;
  for (const line of zhLines) {
    if ((line.includes('<td') && (line.match(/!\[/) || line.includes('<img ')))) hasTableImage = true;
    if (line.match(/^\s*\|/) && line.match(/!\[/) && !line.match(/^\s*\|[-:|\s]+\|/)) hasTableImage = true;
    if (!line.includes('<td') && line.includes('<img ') && !line.match(/^\s*\|/)) hasTableImage = true;
  }
  if (!hasTableImage) continue;

  const slug = zhFile.replace(/^zh\//, '').replace(/\.mdx$/, '');
  const enFile = zhFile.replace(/^zh\//, '');

  let enContent;
  try { enContent = readFileSync(enFile, 'utf8'); } catch { continue; }

  const srcToCdn = slugMap.get(slug);
  if (!srcToCdn || srcToCdn.size === 0) continue;

  const enLines = enContent.split('\n');
  let fileInserted = 0;

  // ── 3. 处理表格块 ──
  const zhTables = findTableBlocks(zhLines);
  const enTables = findTableBlocks(enLines);

  const maxTables = Math.min(zhTables.length, enTables.length);
  for (let t = 0; t < maxTables; t++) {
    const zhTable = zhTables[t];
    const enTable = enTables[t];
    if (zhTable.type !== enTable.type) continue;

    if (zhTable.type === 'html') {
      const { inserted, newLines } = processHtmlTable(zhTable.lines, enTable.lines, srcToCdn);
      for (let i = 0; i < newLines.length; i++) {
        enLines[enTable.start + i] = newLines[i];
      }
      fileInserted += inserted;
      stats.htmlTd += inserted;
    } else if (zhTable.type === 'markdown') {
      const { inserted, newLines } = processMdTable(zhTable.lines, enTable.lines, srcToCdn);
      for (let i = 0; i < newLines.length; i++) {
        enLines[enTable.start + i] = newLines[i];
      }
      fileInserted += inserted;
      stats.mdTable += inserted;
    }
  }

  // ── 4. 处理普通行内的 <img> inline-icon ──
  const { inserted: imgInserted, newLines: imgNewLines } = processInlineImgs(zhLines, enLines, srcToCdn);
  for (let i = 0; i < imgNewLines.length; i++) {
    enLines[i] = imgNewLines[i];
  }
  fileInserted += imgInserted;
  stats.inlineImg += imgInserted;

  if (fileInserted > 0) {
    writeFileSync(enFile, enLines.join('\n'));
    totalFiles++;
    totalInserted += fileInserted;
    if (totalFiles <= 5 || fileInserted > 10) {
      console.log(`  ${slug}: ${fileInserted} 图片嵌入`);
    }
  }
}

console.log(`\n=== 完成 ===`);
console.log(`文件: ${totalFiles}`);
console.log(`总插入: ${totalInserted}`);
console.log(`详情: HTML td=${stats.htmlTd}, Markdown 表格=${stats.mdTable}, inline <img>=${stats.inlineImg}`);

// ── 函数定义 ──

/**
 * 找到所有表格块（HTML table 和 markdown table）
 */
function findTableBlocks(lines) {
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    if (lines[i].includes('<table')) {
      const start = i;
      while (i < lines.length && !lines[i].includes('</table>')) i++;
      if (i < lines.length) i++;
      blocks.push({ type: 'html', start, end: i, lines: lines.slice(start, i) });
    } else if (lines[i].match(/^\s*\|.*\|/)) {
      const start = i;
      while (i < lines.length && lines[i].match(/^\s*\|.*\|/)) i++;
      blocks.push({ type: 'markdown', start, end: i, lines: lines.slice(start, i) });
    } else {
      i++;
    }
  }
  return blocks;
}

/**
 * 处理 HTML table 内的图片
 * 对齐行号后，对每对 <td> 提取中文版图片，插入英文版对应位置
 */
function processHtmlTable(zhLines, enLines, srcToCdn) {
  const newLines = [...enLines];
  let inserted = 0;

  for (let i = 0; i < Math.min(zhLines.length, enLines.length); i++) {
    const zhLine = zhLines[i];
    const enLine = enLines[i];

    if (!zhLine.includes('<td')) continue;
    if (!zhLine.match(/!\[.*\]\(/) && !zhLine.includes('<img ')) continue;

    // 提取所有 <td>...</td> 对
    const tdRegex = /<td[^>]*>.*?<\/td>/g;
    const zhTds = zhLine.match(tdRegex) || [];
    const enTds = enLine.match(tdRegex) || [];

    if (zhTds.length === 0 || zhTds.length !== enTds.length) continue;

    let newEnLine = enLine;
    // 从后往前替换，避免偏移
    for (let j = enTds.length - 1; j >= 0; j--) {
      const result = insertImagesIntoTd(zhTds[j], enTds[j], srcToCdn);
      if (result.changed) {
        newEnLine = newEnLine.replace(enTds[j], result.newTd);
        inserted += result.inserted;
      }
    }
    newLines[i] = newEnLine;
  }

  return { inserted, newLines };
}

/**
 * 在英文版 <td> 内插入中文版 <td> 中的图片
 */
function insertImagesIntoTd(zhTd, enTd, srcToCdn) {
  // 提取 <td> 属性和内容
  const zhMatch = zhTd.match(/^(<td[^>]*>)([\s\S]*)<\/td>$/);
  const enMatch = enTd.match(/^(<td[^>]*>)([\s\S]*)<\/td>$/);
  if (!zhMatch || !enMatch) return { changed: false, newTd: enTd, inserted: 0 };

  const zhContent = zhMatch[2];
  let enContent = enMatch[2];

  // 提取中文版 td 内的所有图片
  const images = [];

  // markdown 图片 ![](url) 或 ![alt](url)
  const mdImgRegex = /!\[([^\]]*)\]\(([^)]+)\)/g;
  let m;
  while ((m = mdImgRegex.exec(zhContent)) !== null) {
    const cdn = srcToCdn.get(m[2]);
    if (cdn) {
      images.push({
        src: m[2],
        cdn,
        replacement: `![${m[1]}](${cdn})`,
        index: m.index,
        endIndex: m.index + m[0].length,
      });
    }
  }

  // <img> 标签
  const htmlImgRegex = /<img\b[^>]*>/gi;
  while ((m = htmlImgRegex.exec(zhContent)) !== null) {
    const srcMatch = m[0].match(/src=["']([^"']+)["']/);
    if (srcMatch) {
      const cdn = srcToCdn.get(srcMatch[1]);
      if (cdn) {
        images.push({
          src: srcMatch[1],
          cdn,
          replacement: m[0].replace(srcMatch[1], cdn),
          index: m.index,
          endIndex: m.index + m[0].length,
        });
      }
    }
  }

  if (images.length === 0) return { changed: false, newTd: enTd, inserted: 0 };

  images.sort((a, b) => a.index - b.index);

  let inserted = 0;

  // 按从后往前处理，避免位置偏移
  for (let k = images.length - 1; k >= 0; k--) {
    const img = images[k];
    // 图片前面的中文内容
    const before = zhContent.substring(0, img.index);

    if (before.trim() === '') {
      // ── 模式 A：纯图片 td ──
      // 中文版：<td>![](url)</td> 或 <td attrs>![](url)</td>
      // 英文版：<td></td> 或 <td attrs></td>
      // 修复：直接在 <td> 开头插入
      enContent = img.replacement + enContent;
      inserted++;
    } else if (before.match(/<br\s*\/?>\s*$/)) {
      // ── 模式 B：图片在 <br /> 后 ──
      // 中文版：<td>文本<br />![](url)</td>
      // 英文版：<td>Text<br /></td> 或 <td>Text</td>
      if (enContent.match(/<br\s*\/?>\s*$/)) {
        // 英文版已有 <br />，直接追加图片
        enContent = enContent + img.replacement;
      } else {
        // 英文版没有 <br />，添加 <br /> 后再追加图片
        enContent = enContent + '<br />' + img.replacement;
      }
      inserted++;
    } else if (before.match(/<\/[ou]l>\s*$/)) {
      // ── 模式 C：图片在 </ol> 或 </ul> 后 ──
      // 中文版：<td><ol>...</ol>![](url)</td> 或 <td><ol>...</ol><br />![](url)</td>
      // 英文版：<td><ol>...</ol></td> 或 <td><ol>...</ol><br /></td>
      const lastListClose = Math.max(
        enContent.lastIndexOf('</ol>'),
        enContent.lastIndexOf('</ul>')
      );
      if (lastListClose !== -1) {
        // 在最后一个 </ol>/</ul> 后插入
        const afterList = enContent.substring(lastListClose + 5);
        if (afterList.match(/<br\s*\/?>/)) {
          // 已有 <br />，替换为 <br /> + 图片
          enContent = enContent.substring(0, lastListClose + 5)
            + afterList.replace(/(<br\s*\/?>)/, '$1' + img.replacement);
        } else {
          // 没有 <br />，添加 <br /> + 图片
          enContent = enContent.substring(0, lastListClose + 5)
            + '<br />' + img.replacement + afterList;
        }
      } else {
        enContent = enContent + '<br />' + img.replacement;
      }
      inserted++;
    } else {
      // ── 模式 D：其他位置 ──
      // 在英文版 td 末尾追加
      if (enContent.trim() === '') {
        enContent = img.replacement;
      } else {
        enContent = enContent + '<br />' + img.replacement;
      }
      inserted++;
    }
  }

  return {
    changed: inserted > 0,
    newTd: enMatch[1] + enContent + '</td>',
    inserted,
  };
}

/**
 * 处理 Markdown 表格行内的图片
 */
function processMdTable(zhLines, enLines, srcToCdn) {
  const newLines = [...enLines];
  let inserted = 0;

  for (let i = 0; i < Math.min(zhLines.length, enLines.length); i++) {
    const zhLine = zhLines[i];
    if (!zhLine.match(/^\s*\|/) || !zhLine.match(/!\[/)) continue;
    if (zhLine.match(/^\s*\|[-:|\s]+\|/)) continue;

    const enLine = enLines[i];
    if (!enLine.match(/^\s*\|/)) continue;

    // 分割单元格
    const zhCells = splitMdCells(zhLine);
    const enCells = splitMdCells(enLine);

    if (zhCells.length !== enCells.length) continue;

    let changed = false;
    for (let j = 0; j < zhCells.length; j++) {
      if (!zhCells[j].includes('![')) continue;

      // 提取中文版单元格中的图片
      const mdImgRegex = /!\[([^\]]*)\]\(([^)]+)\)/g;
      let m;
      const cellImages = [];
      while ((m = mdImgRegex.exec(zhCells[j])) !== null) {
        const cdn = srcToCdn.get(m[2]);
        if (cdn) cellImages.push(`![${m[1]}](${cdn})`);
      }

      if (cellImages.length === 0) continue;

      // 在英文版单元格中插入图片
      if (enCells[j].trim() === '') {
        // 空单元格：直接填充
        enCells[j] = ' ' + cellImages.join(' ') + ' ';
      } else {
        // 非空单元格：在内容后添加 <br /> + 图片
        enCells[j] = ' ' + enCells[j].trim() + '<br />' + cellImages.join('<br />') + ' ';
      }
      inserted += cellImages.length;
      changed = true;
    }

    if (changed) {
      newLines[i] = '| ' + enCells.map(c => c.trim()).join(' | ') + ' |';
    }
  }

  return { inserted, newLines };
}

/**
 * 分割 Markdown 表格行的单元格
 */
function splitMdCells(line) {
  const trimmed = line.trim();
  const inner = trimmed.substring(1, trimmed.length - 1);
  return inner.split('|').map(c => c.trim());
}

/**
 * 处理普通行内的 <img> inline-icon
 * 在英文版对应行中找到语义位置插入
 */
function processInlineImgs(zhLines, enLines, srcToCdn) {
  const newLines = [...enLines];
  let inserted = 0;

  for (let i = 0; i < zhLines.length; i++) {
    const zhLine = zhLines[i];
    // 跳过表格行
    if (zhLine.includes('<td') || zhLine.match(/^\s*\|/)) continue;
    if (!zhLine.includes('<img ')) continue;

    // 提取所有 <img> 标签
    const imgRegex = /<img\b[^>]*>/gi;
    let m;
    const imgs = [];
    while ((m = imgRegex.exec(zhLine)) !== null) {
      const srcMatch = m[0].match(/src=["']([^"']+)["']/);
      if (srcMatch) {
        const cdn = srcToCdn.get(srcMatch[1]);
        if (cdn) {
          imgs.push({
            tag: m[0],
            src: srcMatch[1],
            cdn,
            newTag: m[0].replace(srcMatch[1], cdn),
            index: m.index,
            // <img> 前后的中文文字
            before: zhLine.substring(0, m.index).trim(),
            after: zhLine.substring(m.index + m[0].length).trim(),
          });
        }
      }
    }

    if (imgs.length === 0) continue;

    // 在英文版中找到对应的行
    // 策略：用中文 <img> 前后的文字关键词在英文版附近行中搜索
    for (const img of imgs) {
      // 提取中文文字的关键词
      // before 通常是 "单击左上角" 之类，after 通常是 "号" 之类
      // 英文版对应的行可能包含 "Click", "icon", "upper-left" 等

      // 找到英文版中最可能对应的行
      let bestEnLine = -1;
      let bestScore = 0;

      // 搜索范围：当前行附近 ±5 行
      const searchStart = Math.max(0, i - 5);
      const searchEnd = Math.min(enLines.length, i + 6);

      for (let j = searchStart; j < searchEnd; j++) {
        const enLine = enLines[j];
        if (enLine.includes('<img ')) continue; // 已有 <img>，跳过

        let score = 0;
        // 检查是否包含相似关键词
        if (img.before.includes('单击') && enLine.match(/click/i)) score += 2;
        if (img.before.includes('左上角') && enLine.match(/upper-left|upper left|top-left|top left/i)) score += 2;
        if (img.before.includes('右上角') && enLine.match(/upper-right|upper right|top-right|top right/i)) score += 2;
        if (img.before.includes('按钮') && enLine.match(/button/i)) score += 1;
        if (img.before.includes('图标') && enLine.match(/icon/i)) score += 1;
        if (img.after.includes('号') && enLine.match(/icon|button|symbol/i)) score += 1;
        // 如果英文版行号和中文版行号接近
        if (Math.abs(j - i) <= 1) score += 1;

        if (score > bestScore) {
          bestScore = score;
          bestEnLine = j;
        }
      }

      if (bestEnLine === -1 || bestScore === 0) continue;

      // 在英文版行中找到合适位置插入 <img>
      const enLine = newLines[bestEnLine];

      // 策略：如果是 inline-icon，在第一个匹配的关键词后插入
      const isInlineIcon = img.tag.includes('inline-icon');

      let newEnLine = enLine;

      if (isInlineIcon) {
        // 在 "icon" 或 "button" 或 "symbol" 后插入
        const keywordMatch = enLine.match(/\b(icon|button|symbol|Icon|Button|Symbol)\b/);
        if (keywordMatch) {
          const insertPos = keywordMatch.index + keywordMatch[0].length;
          newEnLine = enLine.substring(0, insertPos) + ' ' + img.newTag + enLine.substring(insertPos);
        } else if (img.before.includes('左上角') && enLine.match(/upper-left|upper left/)) {
          // 在 "upper-left corner" 后插入
          const pos = enLine.match(/upper-left corner|upper left corner/i);
          if (pos) {
            const insertPos = pos.index + pos[0].length;
            newEnLine = enLine.substring(0, insertPos) + ' ' + img.newTag + enLine.substring(insertPos);
          }
        } else {
          // 在行末插入
          newEnLine = enLine.trimEnd() + ' ' + img.newTag;
        }
      } else {
        // 非 inline-icon：在行末插入
        newEnLine = enLine.trimEnd() + ' ' + img.newTag;
      }

      if (newEnLine !== enLine) {
        newLines[bestEnLine] = newEnLine;
        inserted++;
      }
    }
  }

  return { inserted, newLines };
}
