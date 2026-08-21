#!/usr/bin/env node

import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  writeFileSync,
} from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const reviewRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = resolve(reviewRoot, '..', '..');
const replacementPath = join(reviewRoot, '.cache', 'image-hq-replacement-manifest.json');
const uploadRoot = join(reviewRoot, '.cache', 'image-hq-followup');
const uploadResultPath = join(uploadRoot, 'cdn-upload-result.json');
const batchStatePath = join(reviewRoot, '.cache', 'image-batches', 'yida-zh-en.json');
const resultPath = join(uploadRoot, 'promotion-result.json');
const localApi = 'http://127.0.0.1:5173/api';

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function writeJsonAtomic(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  renameSync(temporary, path);
}

function repoPath(relativePath) {
  const path = resolve(repoRoot, relativePath);
  const rel = relative(repoRoot, path);
  if (!rel || rel === '..' || rel.startsWith(`..${sep}`)) throw new Error(`路径越出仓库：${relativePath}`);
  return path;
}

async function post(path, payload) {
  const response = await fetch(`${localApi}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(10 * 60_000),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`本地 API ${path} 失败：${text}`);
  return text ? JSON.parse(text) : undefined;
}

async function verifyUrl(cdnUrl) {
  const url = new URL(cdnUrl);
  if (url.protocol !== 'https:' || !/(^|\.)alicdn\.com$/i.test(url.hostname)) throw new Error('CDN 域名或协议不受信任');
  const response = await fetch(url, {
    method: 'GET', headers: { Range: 'bytes=0-0' }, redirect: 'follow', signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok || !/^image\//i.test(response.headers.get('content-type') ?? '')) throw new Error(`CDN 图片验证失败：HTTP ${response.status}`);
  await response.body?.cancel();
}

function backup(paths) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const root = join(uploadRoot, 'backups', timestamp);
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
  const apply = process.argv.includes('--apply');
  const replacement = readJson(replacementPath);
  const upload = readJson(uploadResultPath);
  const entries = replacement.entries.filter((entry) => entry.status === 'ready'
    && ['replace-existing-english-image', 'insert-missing-english-image'].includes(entry.action));
  if (entries.length !== 41) throw new Error(`HQ 后续范围漂移：预期 41，实际 ${entries.length}`);
  const uploadedById = new Map((upload.items ?? []).filter((item) => item.cdnUrl).map((item) => [item.id, item.cdnUrl]));
  if (!upload.ok || uploadedById.size !== entries.length) throw new Error(`CDN 映射不完整：${uploadedById.size}/${entries.length}`);
  await Promise.all(entries.map((entry) => verifyUrl(uploadedById.get(entry.id))));

  await post('/image-batch/update', {
    scope: 'yida',
    updates: entries.map((entry) => ({ id: entry.id, cdnUrl: uploadedById.get(entry.id) })),
  });
  const ids = entries.map((entry) => entry.id);
  const preview = await post('/image-batch/apply', { scope: 'yida', ids, dryRun: true });
  if (preview.skipped.length || new Set(preview.appliedIds).size !== ids.length) {
    throw new Error(`回写预检未完全通过：applied=${new Set(preview.appliedIds).size}, skipped=${preview.skipped.length}`);
  }
  const changedPaths = new Set(preview.changedFiles.map((path) => resolve(path)));
  if (!apply) {
    console.log(JSON.stringify({ ok: true, dryRun: true, verified: entries.length, applicable: ids.length, changedFiles: changedPaths.size }, null, 2));
    return;
  }

  const backupRoot = backup([...changedPaths]);
  const applied = await post('/image-batch/apply', { scope: 'yida', ids, dryRun: false });
  if (applied.skipped.length || new Set(applied.appliedIds).size !== ids.length) throw new Error('正式回写不完整');

  const missing = entries.filter((entry) => !readFileSync(repoPath(entry.mdxPath), 'utf8').includes(uploadedById.get(entry.id)));
  if (missing.length) throw new Error(`回写验证失败：缺少新引用 ${missing.length}`);
  writeJsonAtomic(resultPath, {
    ok: true, completedAt: new Date().toISOString(), verified: entries.length, applied: entries.length,
    changedFiles: changedPaths.size, backupRoot,
  });
  console.log(JSON.stringify(readJson(resultPath), null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
