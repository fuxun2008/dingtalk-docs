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

const knownTags = new Set([
  'video', 'img', 'Frame', 'Note', 'Steps', 'Accordion', 'Card', 'Tabs',
  'Step', 'Tab', 'br', 'source', 'Warning', 'Update', 'AccordionGroup',
  'TabsOptions', 'Icon', 'StepsOptions', 'CardGroup', 'CodeGroup',
  'Expandable', 'InlineCard',
]);

for (const slug of errorSlugs) {
  const filePath = join(repoRoot, slug + '.mdx');
  const content = readFileSync(filePath, 'utf8');
  const lines = content.split('\n');
  let inCode = false;
  let inFrontmatter = false;

  console.log(`\n=== ${slug} ===`);

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (line.trim() === '---') { inFrontmatter = !inFrontmatter; continue; }
    if (inFrontmatter) continue;
    if (line.startsWith('```')) { inCode = !inCode; continue; }
    if (inCode) continue;

    // 1. 检查代码块外的未转义 < 后面跟字母
    const ltMatches = [...line.matchAll(/<(?!\/?(video|img|Frame|Note|Steps|Accordion|Card|Tabs|Step|Tab|br|source|Warning|Update|AccordionGroup|TabsOptions|Icon|StepsOptions|CardGroup|CodeGroup|Expandable|InlineCard)\b)([a-zA-Z])/g)];
    if (ltMatches.length > 0) {
      for (const m of ltMatches) {
        const idx = m.index;
        const context = line.substring(Math.max(0, idx - 20), Math.min(line.length, idx + 30));
        console.log(`  行${i + 1} 代码块外未转义<: ...${context.trim()}...`);
      }
    }

    // 2. 检查反引号内的 < 后面跟字母
    const inlineCodeRe = /`([^`]+)`/g;
    let m2;
    while ((m2 = inlineCodeRe.exec(line)) !== null) {
      const codeContent = m2[1];
      const ltInCode = codeContent.match(/<([a-zA-Z])/g);
      if (ltInCode) {
        for (const lt of ltInCode) {
          const tag = lt.substring(1);
          if (!knownTags.has(tag)) {
            const idx = m2.index;
            const context = line.substring(Math.max(0, idx - 10), Math.min(line.length, idx + 60));
            console.log(`  行${i + 1} 反引号内<${tag}: ...${context.trim()}...`);
          }
        }
      }
    }
  }
}
