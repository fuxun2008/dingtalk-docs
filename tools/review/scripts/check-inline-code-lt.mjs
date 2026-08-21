#!/usr/bin/env node
import { readFileSync, readdirSync } from 'node:fs';
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

const files = collectMdx(join(repoRoot, 'yida'));
const knownTags = new Set(['video', 'img', 'Frame', 'Note', 'Steps', 'Accordion', 'Card', 'Tabs', 'Step', 'Tab', 'br', 'source', 'Warning', 'Update', 'AccordionGroup', 'TabsOptions', 'Frame', 'Icon']);

let totalIssues = 0;
let fileCount = 0;

for (const file of files) {
  const content = readFileSync(file, 'utf8');
  const lines = content.split('\n');
  let inCode = false;
  let inFrontmatter = false;
  let fileHas = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === '---') { inFrontmatter = !inFrontmatter; continue; }
    if (inFrontmatter) continue;
    if (line.startsWith('```')) { inCode = !inCode; continue; }
    if (inCode) continue;

    // 检查反引号内的 < 后面跟字母
    const inlineCodeRe = /`([^`]+)`/g;
    let m;
    while ((m = inlineCodeRe.exec(line)) !== null) {
      const codeContent = m[1];
      const ltMatches = codeContent.match(/<([a-zA-Z])/g);
      if (ltMatches) {
        for (const lt of ltMatches) {
          const tag = lt.substring(1);
          if (!knownTags.has(tag)) {
            totalIssues++;
            if (!fileHas) {
              fileHas = true;
              fileCount++;
              const slug = file.replace(/\.mdx$/, '').replace(/^.*\/(yida\/)/, '$1');
              console.log(`  ${slug}: 行${i + 1}`);
            }
          }
        }
      }
    }
  }
}

console.log(`\n反引号内有未转义 <字母> 的文件数: ${fileCount}`);
console.log(`总问题数: ${totalIssues}`);
