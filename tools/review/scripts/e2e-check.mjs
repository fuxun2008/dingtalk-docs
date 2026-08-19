#!/usr/bin/env node
import { readFileSync, existsSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');

function collectMdx(dir) {
  const results = [];
  const entries = readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = join(dir, entry.name);
    if (entry.isDirectory()) results.push(...collectMdx(fullPath));
    else if (entry.name.endsWith('.mdx')) results.push(fullPath);
  }
  return results;
}

const enFiles = collectMdx(join(repoRoot, 'yida'));
const problems = [];

for (const enFile of enFiles) {
  const zhFile = enFile.replace(/^.*\/yida\//, join(repoRoot, 'zh', 'yida') + '/');
  if (!existsSync(zhFile)) continue;

  const zhContent = readFileSync(zhFile, 'utf8');
  const enContent = readFileSync(enFile, 'utf8');
  const enLines = enContent.split('\n');

  const slug = enFile.replace(/\.mdx$/, '').replace(/^.*\/(yida\/)/, '$1');

  // 1. 图片数量匹配
  const zhImgs = (zhContent.match(/!\[.*?\]\([^)]+\)/g) || []).length
    + (zhContent.match(/<img[^>]+src/g) || []).length
    + (zhContent.match(/<video[^>]+poster/g) || []).length;
  const enImgs = (enContent.match(/!\[.*?\]\([^)]+\)/g) || []).length
    + (enContent.match(/<img[^>]+src/g) || []).length
    + (enContent.match(/<video[^>]+poster/g) || []).length;

  // 2. 中文残留（排除 frontmatter、代码块、className 属性）
  let chineseResidue = 0;
  let inFrontmatter = false;
  let inCodeBlock = false;
  for (const line of enLines) {
    if (line.trim() === '---') { inFrontmatter = !inFrontmatter; continue; }
    if (inFrontmatter) continue;
    if (line.startsWith('```')) { inCodeBlock = !inCodeBlock; continue; }
    if (inCodeBlock) continue;
    const chinese = line.match(/[\u4e00-\u9fff]/g);
    if (chinese && chinese.length > 3 && !line.includes('className')) {
      chineseResidue++;
    }
  }

  // 3. 连续空行
  let consecutiveBlanks = 0;
  let maxConsecutiveBlanks = 0;
  for (const line of enLines) {
    if (line.trim() === '') {
      consecutiveBlanks++;
      maxConsecutiveBlanks = Math.max(maxConsecutiveBlanks, consecutiveBlanks);
    } else {
      consecutiveBlanks = 0;
    }
  }

  // 4. 图片行前无空行分隔
  let imgNoBlankBefore = 0;
  for (let i = 1; i < enLines.length; i++) {
    const trimmed = enLines[i].trim();
    if (/^!\[|<img|<video.*poster/.test(trimmed)
      && enLines[i - 1].trim() !== ''
      && !enLines[i - 1].includes('|')
      && !enLines[i - 1].includes('<Step')
      && !enLines[i - 1].includes('<Note')
    ) {
      imgNoBlankBefore++;
    }
  }

  // 5. 表格结构异常
  let tableStructureIssue = 0;
  let inTable = false;
  let tablePipeCount = 0;
  for (const line of enLines) {
    if (line.includes('|') && !line.startsWith('#')) {
      const pipes = (line.match(/\|/g) || []).length;
      if (line.match(/^\s*\|.*\|\s*$/)) {
        if (!inTable) {
          inTable = true;
          tablePipeCount = pipes;
        } else if (pipes !== tablePipeCount && pipes > 0) {
          tableStructureIssue++;
        }
      } else {
        inTable = false;
      }
    } else {
      inTable = false;
    }
  }

  // 6. 检查 MDX 组件标签是否闭合
  const openTags = (enContent.match(/<(Steps|Accordion|Tabs|Frame|Note|Card)\b/g) || []).length;
  const closeTags = (enContent.match(/<\/(Steps|Accordion|Tabs|Frame|Note|Card)>/g) || []).length;
  const tagMismatch = openTags !== closeTags;

  // 汇总
  const issues = [];
  if (zhImgs !== enImgs) issues.push(`图片数量不匹配(ZH=${zhImgs} EN=${enImgs})`);
  if (chineseResidue > 0) issues.push(`中文残留(${chineseResidue}行)`);
  if (maxConsecutiveBlanks > 2) issues.push(`连续空行过多(max=${maxConsecutiveBlanks})`);
  if (imgNoBlankBefore > 0) issues.push(`图片行前无空行(${imgNoBlankBefore}处)`);
  if (tableStructureIssue > 0) issues.push(`表格结构异常(${tableStructureIssue}处)`);
  if (tagMismatch) issues.push(`MDX标签不闭合(open=${openTags} close=${closeTags})`);

  if (issues.length > 0) {
    problems.push({ slug, issues, zhImgs, enImgs });
  }
}

console.log('=== 全面 E2E 自动扫描结果 ===');
console.log(`检查文件数: ${enFiles.length}`);
console.log(`有问题的文件数: ${problems.length}`);
console.log('\n问题分类统计:');

const issueTypes = {};
for (const p of problems) {
  for (const issue of p.issues) {
    const type = issue.split('(')[0];
    issueTypes[type] = (issueTypes[type] || 0) + 1;
  }
}
for (const [type, count] of Object.entries(issueTypes).sort((a, b) => b[1] - a[1])) {
  console.log(`  ${type}: ${count} 个文件`);
}

console.log('\n=== 问题文件列表（前 30 个）===');
for (const p of problems.slice(0, 30)) {
  console.log(`  ${p.slug}: ${p.issues.join(', ')}`);
}
