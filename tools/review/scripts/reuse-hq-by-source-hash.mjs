#!/usr/bin/env node

import { copyFileSync, mkdirSync, readFileSync, readdirSync, renameSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const reviewRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = resolve(reviewRoot, '..', '..');
const cacheRoot = join(reviewRoot, '.cache');
const batchPath = join(cacheRoot, 'image-batches', 'yida-zh-en.json');
const auditPath = join(cacheRoot, 'image-english-audit', 'provenance-result.json');
const outputRoot = join(cacheRoot, 'image-hq-reuse');

function walk(directory, predicate, output = []) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) walk(path, predicate, output);
    else if (predicate(path)) output.push(path);
  }
  return output;
}

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function writeAtomic(path, content) {
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, content, 'utf8');
  renameSync(temporary, path);
}

async function verify(url) {
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:' || !/(^|\.)alicdn\.com$/i.test(parsed.hostname)) throw new Error('不受信任的 HQ CDN 地址');
  const response = await fetch(url, {
    method: 'GET', headers: { Range: 'bytes=0-0' }, redirect: 'follow', signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok || !/^image\//i.test(response.headers.get('content-type') ?? '')) throw new Error(`HQ CDN 验证失败：HTTP ${response.status}`);
  await response.body?.cancel();
}

async function main() {
  const apply = process.argv.includes('--apply');
  const batch = readJson(batchPath);
  const audit = readJson(auditPath);
  const byId = new Map(batch.items.map((item) => [item.id, item]));
  const resolveRoot = (item) => {
    const seen = new Set();
    let current = item;
    while (current?.duplicateOf && !seen.has(current.id)) {
      seen.add(current.id);
      current = byId.get(current.duplicateOf) ?? current;
    }
    return current;
  };

  const uploadedById = new Map();
  for (const path of walk(cacheRoot, (value) => /image-hq[^/]*\/cdn-upload-result\.json$/.test(value))) {
    for (const item of readJson(path).items ?? []) uploadedById.set(item.id, item.cdnUrl);
  }

  const mappings = [];
  const noReusableHq = [];
  for (const blocker of audit.blockers.filter((item) => item.category === 'ocr-overlay-risk')) {
    const candidates = blocker.ids.map((id) => byId.get(id)).filter(Boolean);
    const oldUrl = candidates[0]?.cdnUrl;
    const roots = [...new Map(candidates.map((item) => {
      const root = resolveRoot(item);
      return [root.id, root];
    })).values()];
    const uploadedRoots = roots.filter((item) => uploadedById.get(item.id) === item.cdnUrl);
    const urls = new Set(uploadedRoots.map((item) => item.cdnUrl));
    const primary = uploadedRoots[0];
    if (!oldUrl || uploadedRoots.length !== roots.length || urls.size !== 1 || !primary) {
      noReusableHq.push(...blocker.ids);
      continue;
    }
    mappings.push({ oldUrl, newUrl: primary.cdnUrl, primaryId: primary.id, files: blocker.files });
  }

  const uniqueMappings = [...new Map(mappings.map((item) => [item.oldUrl, item])).values()];
  await Promise.all([...new Set(uniqueMappings.map((item) => item.newUrl))].map(verify));
  const changes = new Map();
  let replacements = 0;
  for (const mapping of uniqueMappings) {
    for (const file of mapping.files) {
      const path = resolve(repoRoot, file);
      const current = changes.get(path) ?? readFileSync(path, 'utf8');
      const count = current.split(mapping.oldUrl).length - 1;
      if (count === 0) continue;
      changes.set(path, current.split(mapping.oldUrl).join(mapping.newUrl));
      replacements += count;
    }
  }

  const result = {
    ok: true,
    dryRun: !apply,
    reusableUrls: uniqueMappings.length,
    noReusableHqIds: [...new Set(noReusableHq)].length,
    changedFiles: changes.size,
    replacements,
  };
  if (!apply) {
    console.log(JSON.stringify(result, null, 2));
    return;
  }

  const backupRoot = join(outputRoot, 'backups', new Date().toISOString().replace(/[:.]/g, '-'));
  mkdirSync(backupRoot, { recursive: true, mode: 0o700 });
  copyFileSync(batchPath, join(backupRoot, 'yida-zh-en.before.json'));
  for (const [path] of changes) {
    const destination = join(backupRoot, relative(repoRoot, path));
    mkdirSync(dirname(destination), { recursive: true });
    copyFileSync(path, destination);
  }
  for (const [path, content] of changes) writeAtomic(path, content);

  for (const mapping of uniqueMappings) {
    for (const item of batch.items) {
      if (item.cdnUrl !== mapping.oldUrl) continue;
      item.cdnUrl = mapping.newUrl;
      item.duplicateOf = mapping.primaryId;
      item.status = 'completed';
    }
  }
  batch.updatedAt = new Date().toISOString();
  writeAtomic(batchPath, `${JSON.stringify(batch, null, 2)}\n`);
  mkdirSync(outputRoot, { recursive: true });
  const completed = { ...result, dryRun: false, backupRoot };
  writeAtomic(join(outputRoot, 'result.json'), `${JSON.stringify(completed, null, 2)}\n`);
  console.log(JSON.stringify(completed, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
