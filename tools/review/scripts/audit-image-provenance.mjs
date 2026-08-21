#!/usr/bin/env node

import { createHash } from 'node:crypto';
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const reviewRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = resolve(reviewRoot, '..', '..');
const cacheRoot = join(reviewRoot, '.cache');
const batchPath = join(cacheRoot, 'image-batches', 'yida-zh-en.json');
const provenancePath = join(cacheRoot, 'image-output-provenance.json');
const contentAuditPath = join(cacheRoot, 'image-english-audit', 'result.json');
const resultPath = join(cacheRoot, 'image-english-audit', 'provenance-result.json');

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function walk(directory, predicate, output = []) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) walk(path, predicate, output);
    else if (predicate(path)) output.push(path);
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

function resolveRoot(item, byId) {
  const seen = new Set();
  let current = item;
  while (current?.duplicateOf && !seen.has(current.id)) {
    seen.add(current.id);
    current = byId.get(current.duplicateOf) ?? current;
    if (current.id === item.id) break;
  }
  return current ?? item;
}

function hashUrl(url) {
  return createHash('sha256').update(url).digest('hex').slice(0, 16);
}

function main() {
  const batch = readJson(batchPath);
  const provenance = readJson(provenancePath);
  const contentAudit = readJson(contentAuditPath);
  const batchById = new Map(batch.items.map((item) => [item.id, item]));
  const provenanceById = new Map(provenance.items.map((item) => [item.id, item]));
  const auditedNonBatch = new Map(contentAudit.items.map((item) => [item.hash, item]));

  const hqUploadByUrl = new Map();
  for (const path of walk(cacheRoot, (value) => /image-hq[^/]*\/cdn-upload-result\.json$/.test(value))) {
    const upload = readJson(path);
    for (const item of upload.items ?? []) {
      if (item.id && item.cdnUrl) hqUploadByUrl.set(item.cdnUrl, { id: item.id, result: relative(reviewRoot, path) });
    }
  }

  const batchItemsByUrl = new Map();
  for (const item of batch.items) {
    if (!item.cdnUrl) continue;
    const values = batchItemsByUrl.get(item.cdnUrl) ?? [];
    values.push(item);
    batchItemsByUrl.set(item.cdnUrl, values);
  }

  const occurrences = [];
  for (const file of walk(join(repoRoot, 'yida'), (value) => value.endsWith('.mdx'))) {
    for (const url of extract(readFileSync(file, 'utf8'))) occurrences.push({ file: relative(repoRoot, file), url });
  }
  const unique = new Map();
  for (const occurrence of occurrences) {
    const entry = unique.get(occurrence.url) ?? { url: occurrence.url, files: [] };
    entry.files.push(occurrence.file);
    unique.set(occurrence.url, entry);
  }

  const entries = [];
  for (const entry of unique.values()) {
    const hash = hashUrl(entry.url);
    const hqUpload = hqUploadByUrl.get(entry.url);
    const candidates = batchItemsByUrl.get(entry.url) ?? [];
    let category;
    const ids = candidates.map((item) => item.id);
    if (hqUpload) {
      category = 'hq-imagegen';
    } else if (candidates.length > 0) {
      const roots = [...new Map(candidates.map((item) => {
        const root = resolveRoot(item, batchById);
        return [root.id, root];
      })).values()];
      const rootProvenance = roots.map((root) => provenanceById.get(root.id)).filter(Boolean);
      if (rootProvenance.some((item) => item.inferred === 'local-overlay' && Number(item.exactPixelRatio) < 1)) {
        category = 'ocr-overlay-risk';
      } else if (rootProvenance.some((item) => item.inferred === 'imagegen')) {
        category = 'imagegen';
      } else if (rootProvenance.length > 0 && rootProvenance.every((item) => item.inferred === 'local-overlay'
        && Number(item.exactPixelRatio) === 1 && Number(item.meanAbsDiff) === 0)) {
        category = 'exact-source';
      } else if (rootProvenance.length === 0) {
        category = 'reviewed-existing-or-manual';
      } else {
        category = 'unresolved-batch-provenance';
      }
    } else {
      const audit = auditedNonBatch.get(hash);
      category = audit?.ok ? 'audited-non-batch' : 'unresolved-non-batch';
    }
    entries.push({ hash, category, ids, files: [...new Set(entry.files)] });
  }

  const counts = entries.reduce((value, entry) => {
    value[entry.category] = (value[entry.category] ?? 0) + 1;
    return value;
  }, {});
  const blockers = entries.filter((entry) => ['ocr-overlay-risk', 'unresolved-batch-provenance', 'unresolved-non-batch'].includes(entry.category));
  const result = {
    version: 1,
    createdAt: new Date().toISOString(),
    mdxFiles: new Set(occurrences.map((item) => item.file)).size,
    occurrences: occurrences.length,
    uniqueUrls: entries.length,
    counts,
    lowQualityOcrReferences: entries.filter((entry) => entry.category === 'ocr-overlay-risk').length,
    unresolvedReferences: blockers.filter((entry) => entry.category !== 'ocr-overlay-risk').length,
    passed: blockers.length === 0,
    blockers,
  };
  writeFileSync(resultPath, `${JSON.stringify(result, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify(result, null, 2));
  if (!result.passed) process.exitCode = 1;
}

main();
