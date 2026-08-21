#!/usr/bin/env node

import { createHash } from 'node:crypto';
import {
  copyFileSync,
  existsSync,
  linkSync,
  mkdirSync,
  readFileSync,
  renameSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { basename, dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const reviewRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = resolve(reviewRoot, '..', '..');
const replacementPath = join(reviewRoot, '.cache', 'image-hq-replacement-manifest.json');
function parseArgs(argv) {
  const options = { actions: ['replace-existing-cdn'], output: join(reviewRoot, '.cache', 'image-hq-upload') };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === '--actions') options.actions = (argv[++index] ?? '').split(',').filter(Boolean);
    else if (value === '--output') options.output = resolve(argv[++index] ?? options.output);
    else throw new Error(`未知参数：${value}`);
  }
  if (options.actions.length === 0) throw new Error('至少需要一个 HQ 操作类型');
  return options;
}

function writeJsonAtomic(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  renameSync(temporary, path);
}

function digest(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function stage(source, destination) {
  if (existsSync(destination)) {
    if (statSync(destination).size !== statSync(source).size || digest(destination) !== digest(source)) {
      throw new Error(`暂存文件内容冲突：${basename(destination)}`);
    }
    return;
  }
  try {
    linkSync(source, destination);
  } catch (error) {
    if (error?.code !== 'EXDEV') throw error;
    copyFileSync(source, destination);
  }
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const uploadRoot = options.output;
  const stagingRoot = join(uploadRoot, 'files');
  const uploadManifestPath = join(uploadRoot, 'cdn-upload-job.json');
  const replacement = JSON.parse(readFileSync(replacementPath, 'utf8'));
  const selectedActions = new Set(options.actions);
  const selected = replacement.entries.filter((entry) => entry.status === 'ready' && selectedActions.has(entry.action));
  if (selected.length === 0) throw new Error(`没有符合操作类型的 HQ 图片：${options.actions.join(', ')}`);
  mkdirSync(stagingRoot, { recursive: true, mode: 0o700 });
  const items = selected.map((entry) => {
    const source = resolve(repoRoot, entry.hqPath);
    if (!existsSync(source) || !statSync(source).isFile()) throw new Error(`HQ 文件不存在：${entry.id}`);
    const hash = digest(source).slice(0, 12);
    const extension = extname(source).toLowerCase() || '.png';
    const filename = `${entry.id}-hq-${hash}${extension}`;
    const path = join(stagingRoot, filename);
    stage(source, path);
    return { id: entry.id, path, filename, sha256: hash };
  });
  writeJsonAtomic(uploadManifestPath, {
    version: 1,
    createdAt: new Date().toISOString(),
    sourceManifest: replacementPath,
    scope: options.actions.join(','),
    items,
  });
  console.log(JSON.stringify({ ok: true, items: items.length, uploadManifestPath }, null, 2));
}

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
