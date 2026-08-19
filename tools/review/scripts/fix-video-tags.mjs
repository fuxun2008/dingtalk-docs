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
  let content = readFileSync(file, 'utf8');
  let modified = false;
  const lines = content.split('\n');

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    // 检查是否有 <video ...> 行，以 > 结尾但没有 </video>
    const videoMatch = line.match(/^(<video\b[^>]*?)(>?)$/);
    if (videoMatch && line.includes('<video') && !line.includes('</video>') && !line.includes('/>')) {
      // 替换行末的 > 为 ></video>
      lines[i] = line.replace(/^(<video\b[^>]*?)>$/, '$1></video>');
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
