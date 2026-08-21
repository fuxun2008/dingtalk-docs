#!/usr/bin/env node
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

const files = collectMdx(join(repoRoot, 'yida'));
let fixedCount = 0;

for (const file of files) {
  const lines = readFileSync(file, 'utf8').split('\n');
  let modified = false;

  for (let i = 0; i < lines.length - 1; i++) {
    if (lines[i].includes('</video>') && lines[i + 1].trim() !== '' && !lines[i + 1].startsWith('<')) {
      // 在 </video> 行后插入空行
      lines.splice(i + 1, 0, '');
      modified = true;
    }
  }

  if (modified) {
    writeFileSync(file, lines.join('\n'));
    fixedCount++;
    const slug = file.replace(/\.mdx$/, '').replace(/^.*\/(yida\/)/, '$1');
    console.log(`  修复: ${slug}`);
  }
}

console.log(`\n总共修复 ${fixedCount} 个文件`);
