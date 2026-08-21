#!/usr/bin/env node
/**
 * 分析中文版 yida 文件中表格内图片的分布和模式
 */
import { readFileSync } from 'node:fs';
import { execSync } from 'node:child_process';

const zhFiles = execSync('find zh/yida -name "*.mdx" -type f', { encoding: 'utf8' })
  .trim().split('\n').filter(Boolean);

const stats = {
  htmlTdPure: 0,      // <td>![](url)</td> 或 <td attrs>![](url)</td>
  htmlTdSuffix: 0,    // <td>text<br />![](url)</td> 或 <td><ol>..</ol><br />![](url)</td>
  htmlTdOther: 0,     // 其他 td 内图片位置
  htmlTdImg: 0,       // <td> 内的 <img> 标签
  mdTable: 0,         // markdown 表格行内图片
  inlineImg: 0,       // 普通行内的 <img>（非 td）
};
const fileStats = {};

for (const zhFile of zhFiles) {
  let content;
  try { content = readFileSync(zhFile, 'utf8'); } catch { continue; }
  const lines = content.split('\n');
  let fileCount = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // HTML td 内的 markdown 图片
    if (line.includes('<td') && line.match(/!\[.*\]\(/)) {
      // 检查模式：纯图片 vs 文字+图片
      const tdMatch = line.match(/<td[^>]*>(.*)<\/td>/);
      if (tdMatch) {
        const tdContent = tdMatch[1];
        // 纯图片：以 ![] 开头
        if (tdContent.match(/^\s*!\[.*\]\([^)]+\)\s*$/)) {
          stats.htmlTdPure++;
        }
        // 图片在 <br /> 后
        else if (tdContent.match(/<br\s*\/?>\s*!\[/)) {
          stats.htmlTdSuffix++;
        }
        // 图片在 </ol> 或 </ul> 后
        else if (tdContent.match(/<\/[ou]l>.*?!\[/)) {
          stats.htmlTdSuffix++;
        }
        // 其他
        else {
          stats.htmlTdOther++;
        }
      } else {
        stats.htmlTdOther++;
      }
      fileCount++;
    }

    // HTML td 内的 <img> 标签
    if (line.includes('<td') && line.includes('<img ')) {
      stats.htmlTdImg++;
      fileCount++;
    }

    // Markdown 表格行内的图片（非分隔行）
    if (line.match(/^\s*\|/) && line.match(/!\[.*\]\(/) && !line.match(/^\s*\|[-:|\s]+\|/)) {
      stats.mdTable++;
      fileCount++;
    }

    // 普通行内的 <img>（非 td、非 markdown 表格）
    if (!line.includes('<td') && line.includes('<img ') && !line.match(/^\s*\|/)) {
      stats.inlineImg++;
      fileCount++;
    }
  }

  if (fileCount > 0) {
    const slug = zhFile.replace(/^zh\//, '').replace(/\.mdx$/, '');
    fileStats[slug] = fileCount;
  }
}

console.log('=== 统计 ===');
console.log(JSON.stringify(stats, null, 2));
console.log('\n涉及文件数:', Object.keys(fileStats).length);
console.log('\nTop 15 文件:');
const sorted = Object.entries(fileStats).sort((a, b) => b[1] - a[1]).slice(0, 15);
for (const [f, c] of sorted) console.log(`  ${f}: ${c}`);
