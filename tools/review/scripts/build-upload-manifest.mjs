#!/usr/bin/env node
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join, dirname, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(__dirname, '..', '..', '..');
const batchPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'yida-zh-en.json');
const batch = JSON.parse(readFileSync(batchPath, 'utf8'));

// 找出所有 generated items 且有本地文件的
const generated = (batch.items || []).filter(i => {
  if (i.status !== 'generated') return false;
  if (!i.localOutput) return false;
  const localPath = i.localOutput.replace(/^file:\/\//, '');
  return existsSync(localPath);
});

console.log('=== 构建上传清单 ===');
console.log('generated items 总数:', (batch.items || []).filter(i => i.status === 'generated').length);
console.log('有本地文件:', generated.length);

// 构建 manifest v1 格式
const manifest = {
  version: 1,
  items: generated.map(item => {
    const localPath = item.localOutput.replace(/^file:\/\//, '');
    return {
      id: item.id,
      path: localPath,
      filename: basename(localPath),
    };
  }),
};

const manifestPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'upload-manifest-generated.json');
const resultPath = join(repoRoot, 'tools', 'review', '.cache', 'image-batches', 'upload-result-generated.json');

writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n', 'utf8');
console.log('清单文件:', manifestPath);
console.log('结果文件:', resultPath);
console.log('清单 items 数:', manifest.items.length);

// 输出命令
console.log('\n=== 执行上传命令 ===');
console.log(`node tools/review/scripts/cdn-api-upload.mjs --manifest ${manifestPath} --result ${resultPath} --concurrency 8`);
