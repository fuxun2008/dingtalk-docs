#!/usr/bin/env node

import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  renameSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { dirname, extname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const reviewRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = resolve(reviewRoot, '..', '..');
const uploadRoot = join(reviewRoot, '.cache', 'image-hq-upload');
const replacementPath = join(reviewRoot, '.cache', 'image-hq-replacement-manifest.json');
const uploadResultPath = join(uploadRoot, 'cdn-upload-result.json');
const promotionResultPath = join(uploadRoot, 'promotion-result.json');

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function writeAtomic(path, content) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, content, 'utf8');
  renameSync(temporary, path);
}

function repoPath(relativePath) {
  const path = resolve(repoRoot, relativePath);
  const rel = relative(repoRoot, path);
  if (!rel || rel === '..' || rel.startsWith(`..${sep}`)) throw new Error(`路径越出仓库：${relativePath}`);
  return path;
}

function backupRelative(relativePath) {
  const extension = extname(relativePath);
  return extension
    ? `${relativePath.slice(0, -extension.length)}.local${extension}`
    : `${relativePath}.local`;
}

function count(content, needle) {
  return content.split(needle).length - 1;
}

function findMdxBackup() {
  const root = join(uploadRoot, 'backups');
  const candidates = readdirSync(root)
    .map((name) => join(root, name))
    .filter((path) => statSync(path).isDirectory() && existsSync(join(path, 'yida')))
    .sort();
  const selected = candidates.at(-1);
  if (!selected) throw new Error('没有找到正式回写前的 MDX 备份');
  return selected;
}

function main() {
  const replacement = readJson(replacementPath);
  const upload = readJson(uploadResultPath);
  const entries = replacement.entries.filter((entry) => entry.status === 'ready' && entry.action === 'replace-existing-cdn');
  const uploadedById = new Map((upload.items ?? []).filter((item) => item.cdnUrl).map((item) => [item.id, item.cdnUrl]));
  if (entries.length !== 942 || uploadedById.size !== 942) throw new Error('HQ 修复输入不完整');
  const sourceBackupRoot = findMdxBackup();
  const recoveryRoot = join(uploadRoot, 'backups', `${new Date().toISOString().replace(/[:.]/g, '-')}-post-generic-apply`);
  const byFile = new Map();
  for (const entry of entries) {
    const current = byFile.get(entry.mdxPath) ?? [];
    current.push(entry);
    byFile.set(entry.mdxPath, current);
  }

  let replacements = 0;
  for (const [mdxPath, fileEntries] of byFile) {
    const destination = repoPath(mdxPath);
    const sourceBackup = join(sourceBackupRoot, backupRelative(mdxPath));
    if (!existsSync(sourceBackup)) throw new Error(`缺少回写前备份：${mdxPath}`);
    const erroneous = readFileSync(destination, 'utf8');
    writeAtomic(join(recoveryRoot, backupRelative(mdxPath)), erroneous);
    let content = readFileSync(sourceBackup, 'utf8');
    for (const entry of fileEntries) {
      const before = count(content, entry.currentReference);
      if (before !== entry.referenceOccurrences) {
        throw new Error(`备份中的旧引用数量漂移：${entry.id}，预期 ${entry.referenceOccurrences}，实际 ${before}`);
      }
      const cdnUrl = uploadedById.get(entry.id);
      if (!/^https:\/\/[^\s)"']+$/.test(cdnUrl)) throw new Error(`新 CDN 地址格式无效：${entry.id}`);
      content = content.split(entry.currentReference).join(cdnUrl);
      replacements += before;
    }
    writeAtomic(destination, content);
  }

  const missingNew = [];
  const staleOld = [];
  for (const entry of entries) {
    const content = readFileSync(repoPath(entry.mdxPath), 'utf8');
    if (count(content, uploadedById.get(entry.id)) < entry.referenceOccurrences) missingNew.push(entry.id);
    if (count(content, entry.currentReference) > 0) staleOld.push(entry.id);
  }
  if (missingNew.length || staleOld.length) {
    throw new Error(`精确替换验证失败：缺少新引用 ${missingNew.length}，残留旧引用 ${staleOld.length}`);
  }

  const result = {
    ok: true,
    dryRun: false,
    completedAt: new Date().toISOString(),
    verifiedCdn: 942,
    applied: entries.length,
    replacements,
    changedFiles: byFile.size,
    missingNewReferences: 0,
    staleOldReferences: 0,
    sourceBackupRoot,
    recoveryRoot,
  };
  writeAtomic(promotionResultPath, `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify({ ok: true, applied: entries.length, replacements, changedFiles: byFile.size }, null, 2));
}

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
