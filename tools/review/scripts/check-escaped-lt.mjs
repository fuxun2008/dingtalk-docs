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
let totalEscaped = 0;
let fileCount = 0;

for (const f of files) {
  const lines = readFileSync(f, 'utf8').split('\n');
  let inCode = false;
  let inFrontmatter = false;
  let fileHas = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === '---') { inFrontmatter = !inFrontmatter; continue; }
    if (inFrontmatter) continue;
    if (line.startsWith('```')) { inCode = !inCode; continue; }
    if (inCode) continue;

    // 检查 \< 后面跟字母的（正则：反斜杠 + < + 字母）
    const matches = line.match(/\\<[a-zA-Z]/g);
    if (matches) {
      totalEscaped += matches.length;
      if (!fileHas) {
        fileHas = true;
        fileCount++;
        const slug = f.replace(/\.mdx$/, '').replace(/^.*\/(yida\/)/, '$1');
        console.log(`  ${slug}: 行${i + 1} ${matches.length}处`);
      }
    }
  }
}

console.log(`\n代码块外有 \\<字母> 转义的文件数: ${fileCount}`);
console.log(`总转义数: ${totalEscaped}`);
