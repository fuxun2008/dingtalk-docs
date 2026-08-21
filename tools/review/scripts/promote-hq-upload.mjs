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
const uploadRoot = join(reviewRoot, '.cache', 'image-hq-upload');
const replacementPath = join(reviewRoot, '.cache', 'image-hq-replacement-manifest.json');
const uploadManifestPath = join(uploadRoot, 'cdn-upload-job.json');
const uploadResultPath = join(uploadRoot, 'cdn-upload-result.json');
const batchStatePath = join(reviewRoot, '.cache', 'image-batches', 'yida-zh-en.json');
const promotionResultPath = join(uploadRoot, 'promotion-result.json');
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

function countOccurrences(content, needle) {
  return needle ? content.split(needle).length - 1 : 0;
}

async function runPool(values, concurrency, work) {
  let cursor = 0;
  let completed = 0;
  const failures = [];
  const worker = async () => {
    while (cursor < values.length) {
      const value = values[cursor++];
      try {
        await work(value);
      } catch (error) {
        failures.push({ id: value.id, error: error instanceof Error ? error.message : String(error) });
      }
      completed += 1;
      if (completed % 100 === 0 || completed === values.length) {
        console.log(`CDN 验证 ${completed}/${values.length}，失败 ${failures.length}`);
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(concurrency, values.length) }, () => worker()));
  return failures;
}

async function verifyUrl(item) {
  const url = new URL(item.cdnUrl);
  if (url.protocol !== 'https:' || !/(^|\.)alicdn\.com$/i.test(url.hostname)) {
    throw new Error('CDN 域名或协议不受信任');
  }
  const response = await fetch(url, {
    method: 'GET',
    headers: { Range: 'bytes=0-0' },
    redirect: 'follow',
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  if (!/^image\//i.test(response.headers.get('content-type') ?? '')) throw new Error('响应内容类型不是图片');
  await response.body?.cancel();
}

async function post(path, payload, parse = true) {
  const response = await fetch(`${localApi}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(10 * 60_000),
  });
  const text = await response.text();
  if (!response.ok) {
    let message = text;
    try { message = JSON.parse(text).error || text; } catch {}
    throw new Error(`本地 API ${path} 失败：${message}`);
  }
  return parse ? JSON.parse(text) : undefined;
}

function backupFiles(paths, backupRoot) {
  for (const path of paths) {
    const relativePath = relative(repoRoot, path);
    const extensionIndex = relativePath.lastIndexOf('.');
    const backupRelative = extensionIndex >= 0
      ? `${relativePath.slice(0, extensionIndex)}.local${relativePath.slice(extensionIndex)}`
      : `${relativePath}.local`;
    const destination = join(backupRoot, backupRelative);
    mkdirSync(dirname(destination), { recursive: true });
    copyFileSync(path, destination);
  }
}

async function main() {
  const apply = process.argv.includes('--apply');
  const replacement = readJson(replacementPath);
  const uploadManifest = readJson(uploadManifestPath);
  const uploadResult = readJson(uploadResultPath);
  const entries = replacement.entries.filter((entry) => entry.status === 'ready' && entry.action === 'replace-existing-cdn');
  if (entries.length !== 942) throw new Error(`HQ 替换范围漂移：预期 942，实际 ${entries.length}`);
  if (!uploadResult.ok) throw new Error('CDN 上传结果尚未完成');

  const expectedIds = new Set(entries.map((entry) => entry.id));
  const uploaded = (uploadResult.items ?? []).filter((item) => item.cdnUrl && expectedIds.has(item.id));
  const uploadedById = new Map(uploaded.map((item) => [item.id, item]));
  if (uploadedById.size !== entries.length) throw new Error(`CDN 映射不完整：${uploadedById.size}/${entries.length}`);
  if (new Set(uploadManifest.items.map((item) => item.id)).size !== entries.length) throw new Error('上传清单 ID 不完整或重复');

  const oldReferenceGroups = new Map();
  for (const entry of entries) {
    const path = repoPath(entry.mdxPath);
    if (!existsSync(path)) throw new Error(`英文 MDX 不存在：${entry.id}`);
    const content = readFileSync(path, 'utf8');
    if (countOccurrences(content, entry.currentReference) < 1) throw new Error(`当前低质量引用无法定位：${entry.id}`);
    const key = `${entry.mdxPath}\n${entry.currentReference}`;
    oldReferenceGroups.set(key, (oldReferenceGroups.get(key) ?? 0) + 1);
  }

  const verificationFailures = await runPool(uploaded, 8, verifyUrl);
  if (verificationFailures.length > 0) {
    writeJsonAtomic(promotionResultPath, { ok: false, stage: 'cdn-verification', failures: verificationFailures });
    throw new Error(`有 ${verificationFailures.length} 个 CDN 地址未通过验证`);
  }

  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  const backupRoot = join(uploadRoot, 'backups', timestamp);
  mkdirSync(backupRoot, { recursive: true, mode: 0o700 });
  copyFileSync(batchStatePath, join(backupRoot, 'yida-zh-en.before.json'));
  const updates = entries.map((entry) => ({ id: entry.id, cdnUrl: uploadedById.get(entry.id).cdnUrl }));
  await post('/image-batch/update', { scope: 'yida', updates }, false);

  const ids = entries.map((entry) => entry.id);
  const preview = await post('/image-batch/apply', { scope: 'yida', ids, dryRun: true });
  if (preview.skipped.length > 0 || new Set(preview.appliedIds).size !== entries.length) {
    writeJsonAtomic(promotionResultPath, {
      ok: false,
      stage: 'mdx-preflight',
      applied: new Set(preview.appliedIds).size,
      skipped: preview.skipped,
    });
    throw new Error(`MDX 预检未完全通过：applied=${new Set(preview.appliedIds).size}, skipped=${preview.skipped.length}`);
  }

  const changedFiles = [...new Set(preview.changedFiles.map((path) => resolve(path)))];
  if (!apply) {
    writeJsonAtomic(promotionResultPath, {
      ok: true,
      dryRun: true,
      verifiedCdn: uploaded.length,
      applicable: new Set(preview.appliedIds).size,
      changedFiles: changedFiles.length,
      backupRoot,
    });
    console.log(JSON.stringify({ ok: true, dryRun: true, verifiedCdn: uploaded.length, applicable: entries.length, changedFiles: changedFiles.length }, null, 2));
    return;
  }

  backupFiles(changedFiles, backupRoot);
  const applied = await post('/image-batch/apply', { scope: 'yida', ids, dryRun: false });
  if (applied.skipped.length > 0 || new Set(applied.appliedIds).size !== entries.length) {
    throw new Error(`MDX 正式回写不完整：applied=${new Set(applied.appliedIds).size}, skipped=${applied.skipped.length}`);
  }

  const missingNewReferences = [];
  const staleOldReferences = [];
  for (const entry of entries) {
    const content = readFileSync(repoPath(entry.mdxPath), 'utf8');
    const cdnUrl = uploadedById.get(entry.id).cdnUrl;
    if (countOccurrences(content, cdnUrl) < 1) missingNewReferences.push(entry.id);
  }
  for (const [key, replacements] of oldReferenceGroups) {
    const separator = key.indexOf('\n');
    const mdxPath = key.slice(0, separator);
    const oldReference = key.slice(separator + 1);
    const entry = entries.find((candidate) => candidate.mdxPath === mdxPath && candidate.currentReference === oldReference);
    const before = entry?.referenceOccurrences ?? replacements;
    const after = countOccurrences(readFileSync(repoPath(mdxPath), 'utf8'), oldReference);
    if (after > Math.max(0, before - replacements)) staleOldReferences.push(entry?.id ?? mdxPath);
  }
  if (missingNewReferences.length || staleOldReferences.length) {
    throw new Error(`回写后引用验证失败：缺少新引用 ${missingNewReferences.length}，残留旧引用 ${staleOldReferences.length}`);
  }

  writeJsonAtomic(promotionResultPath, {
    ok: true,
    dryRun: false,
    completedAt: new Date().toISOString(),
    verifiedCdn: uploaded.length,
    applied: entries.length,
    changedFiles: new Set(applied.changedFiles).size,
    missingNewReferences: 0,
    staleOldReferences: 0,
    backupRoot,
  });
  console.log(JSON.stringify({ ok: true, verifiedCdn: uploaded.length, applied: entries.length, changedFiles: new Set(applied.changedFiles).size }, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
