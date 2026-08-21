#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, linkSync, mkdirSync, readFileSync, renameSync, statSync, writeFileSync } from 'node:fs';
import { basename, dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const reviewRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const hqStatePath = join(reviewRoot, '.cache', 'image-hq-refresh.json');

function parseArgs(argv) {
  const options = { ids: [], output: join(reviewRoot, '.cache', 'image-hq-selected') };
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] === '--ids') options.ids = (argv[++index] ?? '').split(',').filter(Boolean);
    else if (argv[index] === '--output') options.output = resolve(argv[++index] ?? options.output);
    else throw new Error(`未知参数：${argv[index]}`);
  }
  if (!options.ids.length) throw new Error('需要通过 --ids 指定图片 ID');
  return options;
}

function digest(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex');
}

function writeJsonAtomic(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.${process.pid}.tmp`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  renameSync(temporary, path);
}

function stage(source, destination) {
  if (existsSync(destination)) {
    if (statSync(destination).size !== statSync(source).size || digest(destination) !== digest(source)) {
      throw new Error(`暂存文件内容冲突：${basename(destination)}`);
    }
    return;
  }
  try { linkSync(source, destination); } catch (error) {
    if (error?.code !== 'EXDEV') throw error;
    copyFileSync(source, destination);
  }
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const state = JSON.parse(readFileSync(hqStatePath, 'utf8'));
  const stagingRoot = join(options.output, 'files');
  mkdirSync(stagingRoot, { recursive: true, mode: 0o700 });
  const items = options.ids.map((id) => {
    const entry = state.items[id];
    if (!entry || entry.status !== 'quality_passed' || !entry.outputPath || !existsSync(entry.outputPath)) {
      throw new Error(`HQ 产物未通过质检或不存在：${id}`);
    }
    const hash = digest(entry.outputPath).slice(0, 12);
    const extension = extname(entry.outputPath).toLowerCase() || '.png';
    const filename = `${id}-hq-${hash}${extension}`;
    const path = join(stagingRoot, filename);
    stage(entry.outputPath, path);
    return { id, path, filename, sha256: hash };
  });
  const manifestPath = join(options.output, 'cdn-upload-job.json');
  writeJsonAtomic(manifestPath, { version: 1, createdAt: new Date().toISOString(), scope: 'selected-hq', items });
  console.log(JSON.stringify({ ok: true, items: items.length, manifestPath }, null, 2));
}

try { main(); } catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
