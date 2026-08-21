#!/usr/bin/env node
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');

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

for (const slug of errorSlugs) {
  const filePath = join(repoRoot, slug + '.mdx');
  const lines = readFileSync(filePath, 'utf8').split('\n');
  console.log(`\n=== ${slug} ===`);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // 1. 图片行前一行是 MDX 组件标签且无空行
    if (trimmed.startsWith('![') || trimmed.startsWith('<img')) {
      if (i > 0) {
        const prev = lines[i - 1].trim();
        if (prev !== '' && !prev.startsWith('![') && !prev.startsWith('<img') &&
            (prev.match(/<(Steps|Step|Note|Frame|Accordion|Card|Tabs|Tab)\b/) ||
             prev.match(/^#+\s/) ||
             prev.match(/^\d+\.\s/))) {
          console.log(`  行${i + 1}: 图片前无空行, prev="${prev.substring(0, 60)}"`);
        }
      }
      // 2. 图片行后一行是标题或组件标签且无空行
      if (i < lines.length - 1) {
        const next = lines[i + 1].trim();
        if (next !== '' && !next.startsWith('![') && !next.startsWith('<img') &&
            (next.match(/^#+\s/) ||
             next.match(/<\/?(Steps|Step|Note|Frame|Accordion|Card|Tabs|Tab)\b/))) {
          console.log(`  行${i + 1}: 图片后无空行, next="${next.substring(0, 60)}"`);
        }
      }
    }

    // 3. 无缩进图片行（不以空格开头）
    if (trimmed.startsWith('![') && !line.startsWith('  ') && !line.startsWith('![')) {
      // 检查上下文 - 这可能是正确的（如表格内），也可能不是
      const prev = i > 0 ? lines[i - 1].trim() : '';
      const next = i < lines.length - 1 ? lines[i + 1].trim() : '';
      if (prev !== '' && !prev.includes('|') && next !== '' && !next.includes('|')) {
        console.log(`  行${i + 1}: 无缩进图片行 (prev="${prev.substring(0, 40)}", next="${next.substring(0, 40)}")`);
      }
    }

    // 4. 连续 3+ 空行
    if (line.trim() === '' && i > 1 && lines[i - 1].trim() === '' && i > 2 && lines[i - 2].trim() === '') {
      console.log(`  行${i + 1}: 连续3+空行`);
    }
  }
}
