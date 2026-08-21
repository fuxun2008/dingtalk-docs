#!/usr/bin/env node
/**
 * 修复图片行与 HTML 表格/MDX 组件标签之间的格式问题
 * 
 * 主要修复：
 * 1. 图片行追加到 HTML 表格标签行末尾（</td>![](...), </tr>![](...)）
 * 2. 图片行前/后是 MDX 组件标签但没有空行
 * 3. 图片行前/后是标题但没有空行
 * 4. 连续 3+ 空行压缩为 1 个
 */

import { readFileSync, writeFileSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');

function collectMdx(dir) {
  const results = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) results.push(...collectMdx(fullPath));
    else if (entry.name.endsWith('.mdx')) results.push(fullPath);
  }
  return results;
}

const errorSlugs = [
  'yida/app-admin/kqs39s',
  'yida/developer-features/athbne',
  'yida/exclusive/bmx12h03mcw81n9i',
  'yida/form/dh7m8n',
  'yida/form/ku34el',
  'yida/form/ud8nze',
  'yida/form/vz0ebe',
  'yida/platform-admin/fb7uip',
  'yida/platform-admin/fkfhud',
  'yida/portal/bd77lg07oxxuuhcg',
  'yida/portal/kb5a0gh7oq93ffgl',
  'yida/portal/xbn4iv7pclumwhep',
];

let totalFixed = 0;

for (const slug of errorSlugs) {
  const filePath = join(repoRoot, slug + '.mdx');
  let lines = readFileSync(filePath, 'utf8').split('\n');
  let modified = false;

  // 1. 修复图片追加到 HTML 表格标签行末尾的情况
  // 例如: </td>![](url) → </td>\n![](url)
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    // 检查是否在一行中同时有 HTML 表格标签和图片
    const htmlTagMatch = line.match(/(<\/?(?:td|tr|table|th)\b[^>]*>)/);
    const imgMatch = line.match(/(!\[[^\]]*\]\([^)]+\)|<img[^>]+src="[^"]+"[^>]*>)/);
    if (htmlTagMatch && imgMatch && htmlTagMatch.index < (imgMatch.index || 0)) {
      // 将图片分离到新行
      const beforeImg = line.substring(0, imgMatch.index);
      const imgAndAfter = line.substring(imgMatch.index);
      lines[i] = beforeImg.trimEnd();
      lines.splice(i + 1, 0, '  ' + imgAndAfter.trim());
      modified = true;
    }
  }

  // 2. 修复图片追加到 MDX 组件标签行末尾的情况
  // 例如: <Steps>![](url) → <Steps>\n![](url)
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const mdxTagMatch = line.match(/(<\/?(?:Steps|Step|Note|Frame|Accordion|Card|Tabs|Tab)\b[^>]*>)/);
    const imgMatch = line.match(/(!\[[^\]]*\]\([^)]+\)|<img[^>]+src="[^"]+"[^>]*>)/);
    if (mdxTagMatch && imgMatch && mdxTagMatch.index < (imgMatch.index || 0)) {
      const beforeImg = line.substring(0, imgMatch.index);
      const imgAndAfter = line.substring(imgMatch.index);
      lines[i] = beforeImg.trimEnd();
      lines.splice(i + 1, 0, '  ' + imgAndAfter.trim());
      modified = true;
    }
  }

  // 3. 在图片行前/后添加空行（如果相邻行是标题或组件标签）
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trim();
    if (trimmed.startsWith('![') || trimmed.startsWith('<img')) {
      // 检查前一行
      if (i > 0) {
        const prev = lines[i - 1].trim();
        if (prev !== '' && !prev.startsWith('![') && !prev.startsWith('<img') && !prev.startsWith('|') &&
            (prev.match(/^#+\s/) || prev.match(/<\/?(Steps|Step|Note|Frame|Accordion|Card|Tabs|Tab)\b/) ||
             prev.match(/<\/?(td|tr|table|th)\b/) || prev.match(/^\d+\.\s/))) {
          lines.splice(i, 0, '');
          i++;
          modified = true;
        }
      }
      // 检查后一行
      if (i < lines.length - 1) {
        const next = lines[i + 1].trim();
        if (next !== '' && !next.startsWith('![') && !next.startsWith('<img') && !next.startsWith('|') &&
            (next.match(/^#+\s/) || next.match(/<\/?(Steps|Step|Note|Frame|Accordion|Card|Tabs|Tab)\b/) ||
             next.match(/<\/?(td|tr|table|th)\b/))) {
          lines.splice(i + 1, 0, '');
          i++;
          modified = true;
        }
      }
    }
  }

  // 4. 压缩连续 3+ 空行为 1 个
  const compressed = [];
  let blankCount = 0;
  for (const line of lines) {
    if (line.trim() === '') {
      blankCount++;
      if (blankCount <= 2) {
        compressed.push(line);
      }
    } else {
      blankCount = 0;
      compressed.push(line);
    }
  }
  if (compressed.length !== lines.length) {
    lines = compressed;
    modified = true;
  }

  // 5. 修复无缩进图片行（应该有缩进但缺失）
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].startsWith('![') && !lines[i].startsWith('  ')) {
      // 检查上下文是否有缩进的图片行
      if (i > 0 && lines[i - 1].trim() === '' && i > 1 && lines[i - 2].trim().startsWith('  ![')) {
        lines[i] = '  ' + lines[i];
        modified = true;
      }
    }
  }

  if (modified) {
    writeFileSync(filePath, lines.join('\n'));
    totalFixed++;
    console.log(`  修复: ${slug}`);
  }
}

console.log(`\n总共修复 ${totalFixed} 个文件`);
