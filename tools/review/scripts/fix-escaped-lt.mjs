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
  let inCode = false;
  let inFrontmatter = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === '---') { inFrontmatter = !inFrontmatter; continue; }
    if (inFrontmatter) continue;
    if (line.startsWith('```')) { inCode = !inCode; continue; }
    if (inCode) continue;

    // 将代码块外的 \< 替换为 &lt;
    if (line.includes('\\<')) {
      lines[i] = line.replace(/\\</g, '&lt;');
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
