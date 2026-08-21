#!/usr/bin/env node

import { copyFileSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const reviewRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = resolve(reviewRoot, '..', '..');
const batchStatePath = join(reviewRoot, '.cache', 'image-batches', 'yida-zh-en.json');
const localApi = 'http://127.0.0.1:5173/api';

function parseArgs(argv) {
  const options = { ids: [], uploadResult: '', output: join(reviewRoot, '.cache', 'image-hq-selected'), apply: false };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--ids') options.ids = (argv[++index] ?? '').split(',').filter(Boolean);
    else if (argv[index] === '--upload-result') options.uploadResult = resolve(argv[++index] ?? '');
    else if (argv[index] === '--output') options.output = resolve(argv[++index] ?? options.output);
    else if (argv[index] === '--apply') options.apply = true;
    else throw new Error(`未知参数：${argv[index]}`);
  }
  if (!options.ids.length || !options.uploadResult) throw new Error('需要 --ids 和 --upload-result');
  return options;
}

function writeJsonAtomic(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  renameSync(temporary, path);
}

async function post(path, payload) {
  const response = await fetch(`${localApi}${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    signal: AbortSignal.timeout(10 * 60_000),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`本地 API ${path} 失败：${text}`);
  return text ? JSON.parse(text) : undefined;
}

async function verify(cdnUrl) {
  const url = new URL(cdnUrl);
  if (url.protocol !== 'https:' || !/(^|\.)alicdn\.com$/i.test(url.hostname)) throw new Error('CDN 域名或协议不受信任');
  const response = await fetch(url, { method: 'GET', headers: { Range: 'bytes=0-0' }, redirect: 'follow', signal: AbortSignal.timeout(20_000) });
  if (!response.ok || !/^image\//i.test(response.headers.get('content-type') ?? '')) throw new Error(`CDN 图片验证失败：HTTP ${response.status}`);
  await response.body?.cancel();
}

function backup(paths, output) {
  const root = join(output, 'backups', new Date().toISOString().replace(/[:.]/g, '-'));
  mkdirSync(root, { recursive: true, mode: 0o700 });
  copyFileSync(batchStatePath, join(root, 'yida-zh-en.before.json'));
  for (const path of paths) {
    const destination = join(root, relative(repoRoot, path));
    mkdirSync(dirname(destination), { recursive: true });
    copyFileSync(path, destination);
  }
  return root;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const upload = JSON.parse(readFileSync(options.uploadResult, 'utf8'));
  const wanted = new Set(options.ids);
  const mapped = (upload.items ?? []).filter((item) => wanted.has(item.id) && item.cdnUrl);
  if (!upload.ok || mapped.length !== wanted.size) throw new Error(`CDN 映射不完整：${mapped.length}/${wanted.size}`);
  await Promise.all(mapped.map((item) => verify(item.cdnUrl)));
  await post('/image-batch/update', { scope: 'yida', updates: mapped.map((item) => ({ id: item.id, cdnUrl: item.cdnUrl })) });
  const preview = await post('/image-batch/apply', { scope: 'yida', ids: options.ids, dryRun: true });
  if (preview.skipped.length || new Set(preview.appliedIds).size !== wanted.size) throw new Error(`回写预检失败：applied=${new Set(preview.appliedIds).size}, skipped=${preview.skipped.length}`);
  const changedFiles = [...new Set(preview.changedFiles.map((path) => resolve(path)))];
  if (!options.apply) {
    console.log(JSON.stringify({ ok: true, dryRun: true, verified: mapped.length, applicable: wanted.size, changedFiles: changedFiles.length }, null, 2));
    return;
  }
  const backupRoot = backup(changedFiles, options.output);
  const applied = await post('/image-batch/apply', { scope: 'yida', ids: options.ids, dryRun: false });
  if (applied.skipped.length || new Set(applied.appliedIds).size !== wanted.size) throw new Error('正式回写不完整');
  const batch = JSON.parse(readFileSync(batchStatePath, 'utf8'));
  const missing = mapped.filter((mapping) => {
    const item = batch.items.find((candidate) => candidate.id === mapping.id);
    return !item || !readFileSync(resolve(repoRoot, `${item.slug}.mdx`), 'utf8').includes(mapping.cdnUrl);
  });
  if (missing.length) throw new Error(`回写后缺少 ${missing.length} 个新引用`);
  const result = { ok: true, completedAt: new Date().toISOString(), verified: mapped.length, applied: wanted.size, changedFiles: changedFiles.length, backupRoot };
  writeJsonAtomic(join(options.output, 'promotion-result.json'), result);
  console.log(JSON.stringify(result, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
