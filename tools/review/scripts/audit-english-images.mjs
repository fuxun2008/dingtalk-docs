#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from 'node:fs';
import { dirname, extname, join, relative, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const reviewRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = resolve(reviewRoot, '..', '..');
const cacheRoot = join(reviewRoot, '.cache', 'image-english-audit');
const filesRoot = join(cacheRoot, 'files');
const batchPath = join(reviewRoot, '.cache', 'image-batches', 'yida-zh-en.json');
const ocrBinary = join(reviewRoot, '.cache', 'bin', 'ocr-sensitive');

function walk(directory, output = []) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) walk(path, output);
    else if (entry.name.endsWith('.mdx')) output.push(path);
  }
  return output;
}

function extract(content) {
  const urls = [];
  const patterns = [
    /!\[[^\]]*\]\((https?:\/\/[^\s)]+)(?:\s+[^)]*)?\)/g,
    /<(?:img|source)\b[^>]*\b(?:src|srcSet)=["'](https?:\/\/[^"']+)["'][^>]*>/gi,
    /\bposter=["'](https?:\/\/[^"']+)["']/gi,
  ];
  for (const pattern of patterns) {
    let match;
    while ((match = pattern.exec(content))) urls.push(match[1]);
  }
  return urls;
}

function imageDimensions(path) {
  const result = spawnSync('sips', ['-g', 'pixelWidth', '-g', 'pixelHeight', path], { encoding: 'utf8' });
  const width = Number(/pixelWidth:\s*(\d+)/.exec(result.stdout)?.[1]);
  const height = Number(/pixelHeight:\s*(\d+)/.exec(result.stdout)?.[1]);
  if (result.status !== 0 || !width || !height) throw new Error('图片尺寸不可读');
  return { width, height };
}

function inspect(path) {
  const result = spawnSync(ocrBinary, [path], { encoding: 'utf8', maxBuffer: 32 * 1024 * 1024 });
  if (result.status !== 0) throw new Error('OCR 检查失败');
  const [value] = JSON.parse(result.stdout);
  if (!value || value.error) throw new Error('OCR 结果无效');
  const chinese = (value.texts ?? []).some((text, index) => {
    const count = text.match(/[\u3400-\u9fff]/gu)?.length ?? 0;
    const language = value.languages?.[index] ?? 'und';
    const confidence = value.confidences?.[index] ?? 0;
    if (language === 'ja' || language === 'ko') return false;
    if (language.startsWith('zh')) return count >= 2 && confidence >= 0.75;
    return count >= 4 && confidence >= 0.75;
  });
  const text = (value.texts ?? []).join('\n');
  const safeText = text.replace(/\b[A-Z0-9._%+-]+@example\.(?:com|invalid)\b/gi, '');
  return {
    textCount: value.texts?.length ?? 0,
    qrCount: value.qrCount ?? 0,
    chinese,
    email: /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i.test(safeText),
    phone: /(?:^|\D)1[3-9]\d{9}(?:\D|$)/.test(safeText),
    credential: /\b(?:token|access[_ -]?key|secret|authorization)\s*[:=]\s*\S{4,}|\bbearer\s+\S{4,}/i.test(safeText),
    uid: /\b(?:uid|user[_ -]?id|account[_ -]?id)\s*[:=]\s*\S{2,}|(?:工号|账号)\s*[:：=]\s*\S{2,}/i.test(safeText),
  };
}

async function download(entry) {
  const url = new URL(entry.url);
  if (url.protocol !== 'https:' || !/(^|\.)alicdn\.com$/i.test(url.hostname)) throw new Error('不受信任的图片域名');
  const response = await fetch(url, { redirect: 'follow', signal: AbortSignal.timeout(30_000) });
  if (!response.ok || !/^image\//i.test(response.headers.get('content-type') ?? '')) throw new Error(`HTTP ${response.status}`);
  const buffer = Buffer.from(await response.arrayBuffer());
  if (buffer.length > 20 * 1024 * 1024) throw new Error('图片超过 20MB 审计上限');
  const type = response.headers.get('content-type')?.split(';')[0] ?? 'image/png';
  const extension = type === 'image/jpeg' ? '.jpg' : type === 'image/gif' ? '.gif' : type === 'image/svg+xml' ? '.svg' : extname(url.pathname) || '.png';
  const path = join(filesRoot, `${entry.hash}${extension}`);
  if (!existsSync(path) || statSync(path).size !== buffer.length) writeFileSync(path, buffer);
  return path;
}

async function verifyReachable(entry) {
  try {
    const url = new URL(entry.url);
    if (url.protocol !== 'https:' || !/(^|\.)alicdn\.com$/i.test(url.hostname)) throw new Error('不受信任的图片域名');
    const response = await fetch(url, {
      method: 'GET', headers: { Range: 'bytes=0-0' }, redirect: 'follow', signal: AbortSignal.timeout(20_000),
    });
    if (!response.ok || !/^image\//i.test(response.headers.get('content-type') ?? '')) throw new Error(`HTTP ${response.status}`);
    await response.body?.cancel();
    entry.reachable = true;
  } catch (error) {
    entry.reachable = false;
    entry.reachabilityError = error instanceof Error ? error.message : String(error);
  }
}

async function runPool(values, concurrency, work) {
  let cursor = 0;
  const workers = Array.from({ length: Math.min(concurrency, values.length) }, async () => {
    while (cursor < values.length) await work(values[cursor++]);
  });
  await Promise.all(workers);
}

async function main() {
  if (!existsSync(ocrBinary)) throw new Error('OCR 检查器不存在，请先运行 HQ 质检');
  mkdirSync(filesRoot, { recursive: true, mode: 0o700 });
  const batch = JSON.parse(readFileSync(batchPath, 'utf8'));
  const batchCdn = new Set(batch.items.flatMap((item) => item.cdnUrl ? [item.cdnUrl] : []));
  const targetUrls = new Set(batch.items.flatMap((item) => item.target?.currentUrl ? [item.target.currentUrl] : []));
  const sourceUrls = new Set(batch.items.map((item) => item.sourceUrl));
  const occurrences = [];
  for (const file of walk(join(repoRoot, 'yida'))) {
    for (const url of extract(readFileSync(file, 'utf8'))) occurrences.push({ file: relative(repoRoot, file), url });
  }
  const uniqueByUrl = new Map();
  for (const occurrence of occurrences) {
    const current = uniqueByUrl.get(occurrence.url) ?? { url: occurrence.url, files: [] };
    current.files.push(occurrence.file);
    uniqueByUrl.set(occurrence.url, current);
  }
  const entries = [...uniqueByUrl.values()].map((entry) => ({
    ...entry,
    hash: createHash('sha256').update(entry.url).digest('hex').slice(0, 16),
    category: batchCdn.has(entry.url) ? 'batch'
      : targetUrls.has(entry.url) ? 'existing-english-target'
        : sourceUrls.has(entry.url) ? 'chinese-source' : 'unclassified',
  }));
  await runPool(entries, 24, verifyReachable);
  const audit = entries.filter((entry) => entry.category !== 'batch');
  await runPool(audit, 8, async (entry) => {
    try {
      const path = await download(entry);
      entry.dimensions = imageDimensions(path);
      entry.inspection = inspect(path);
      entry.ok = !entry.inspection.chinese && !entry.inspection.email && !entry.inspection.phone
        && !entry.inspection.credential && !entry.inspection.uid && entry.inspection.qrCount === 0;
    } catch (error) {
      entry.ok = false;
      entry.error = error instanceof Error ? error.message : String(error);
    }
    delete entry.url;
  });
  const result = {
    version: 1,
    createdAt: new Date().toISOString(),
    mdxFiles: new Set(occurrences.map((item) => item.file)).size,
    occurrences: occurrences.length,
    uniqueUrls: entries.length,
    categories: entries.reduce((counts, entry) => {
      counts[entry.category] = (counts[entry.category] ?? 0) + 1;
      return counts;
    }, {}),
    auditedNonBatch: audit.length,
    reachable: entries.filter((entry) => entry.reachable).length,
    unreachable: entries.filter((entry) => !entry.reachable).length,
    reachabilityFailures: entries.filter((entry) => !entry.reachable).map((entry) => ({
      hash: entry.hash, files: entry.files, category: entry.category, error: entry.reachabilityError,
    })),
    passed: audit.filter((entry) => entry.ok).length,
    flagged: audit.filter((entry) => !entry.ok).length,
    items: audit,
  };
  writeFileSync(join(cacheRoot, 'result.json'), `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({ ...result, items: result.items.filter((item) => !item.ok) }, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
