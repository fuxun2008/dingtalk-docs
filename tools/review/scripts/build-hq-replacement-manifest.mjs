#!/usr/bin/env node

import {
  existsSync,
  readFileSync,
  renameSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { dirname, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const reviewRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = resolve(reviewRoot, '..', '..');
const hqStatePath = join(reviewRoot, '.cache', 'image-hq-refresh.json');
const automationStatePath = join(reviewRoot, '.cache', 'image-automation', 'yida.json');
const batchStatePath = join(reviewRoot, '.cache', 'image-batches', 'yida-zh-en.json');
const manifestPath = join(reviewRoot, '.cache', 'image-hq-replacement-manifest.json');

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function values(items) {
  return Array.isArray(items) ? items : Object.values(items ?? {});
}

function repoRelative(path) {
  const result = relative(repoRoot, resolve(path));
  if (!result || result === '..' || result.startsWith(`..${sep}`)) {
    throw new Error(`path escapes repository: ${path}`);
  }
  return result.split(sep).join('/');
}

function countOccurrences(content, needle) {
  if (!needle) return 0;
  return content.split(needle).length - 1;
}

function writeJsonAtomic(path, value) {
  const temporary = `${path}.${process.pid}.tmp`;
  try {
    writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
    renameSync(temporary, path);
  } finally {
    if (existsSync(temporary)) rmSync(temporary);
  }
}

function fail(issues) {
  console.error(JSON.stringify({ ok: false, issueCount: issues.length, issues: issues.slice(0, 50) }, null, 2));
  process.exitCode = 1;
}

function main() {
  const hqState = readJson(hqStatePath);
  const automationState = readJson(automationStatePath);
  const batchState = readJson(batchStatePath);
  const hqItems = values(hqState.items);
  const automationById = new Map(values(automationState.items).map((item) => [item.id, item]));
  const batchById = new Map(values(batchState.items).map((item) => [item.id, item]));
  const issues = [];
  const entries = [];

  const unresolved = hqItems.filter((item) => !['quality_passed', 'deferred'].includes(item.status));
  if (unresolved.length > 0) {
    for (const item of unresolved) issues.push({ id: item.id, code: `hq-${item.status}` });
  }

  for (const hqItem of hqItems) {
    if (hqItem.status !== 'quality_passed') continue;
    const automationItem = automationById.get(hqItem.id);
    const batchItem = batchById.get(hqItem.id);
    if (!automationItem) {
      issues.push({ id: hqItem.id, code: 'missing-automation-item' });
      continue;
    }
    if (!batchItem) {
      issues.push({ id: hqItem.id, code: 'missing-batch-item' });
      continue;
    }
    if (automationItem.slug !== hqItem.slug || batchItem.slug !== hqItem.slug) {
      issues.push({ id: hqItem.id, code: 'slug-mismatch' });
      continue;
    }
    if (automationItem.sourceUrl !== batchItem.sourceUrl) {
      issues.push({ id: hqItem.id, code: 'source-reference-mismatch' });
      continue;
    }

    const mdxPath = join(repoRoot, `${hqItem.slug}.mdx`);
    const zhMdxPath = join(repoRoot, 'zh', `${hqItem.slug}.mdx`);
    const requiredFiles = [hqItem.sourcePath, hqItem.outputPath, mdxPath, zhMdxPath];
    const missingFile = requiredFiles.find((path) => !path || !existsSync(path));
    if (missingFile) {
      issues.push({ id: hqItem.id, code: 'missing-local-file' });
      continue;
    }

    const englishContent = readFileSync(mdxPath, 'utf8');
    const chineseContent = readFileSync(zhMdxPath, 'utf8');
    const sourceOccurrences = countOccurrences(chineseContent, automationItem.sourceUrl);
    if (sourceOccurrences < 1) {
      issues.push({ id: hqItem.id, code: 'source-reference-not-found' });
      continue;
    }

    let action;
    let currentReference;
    if (automationItem.status === 'applied' && automationItem.cdnUrl) {
      action = 'replace-existing-cdn';
      currentReference = automationItem.cdnUrl;
    } else if (batchItem.target?.mode === 'replace' && batchItem.target.currentUrl) {
      action = 'replace-existing-english-image';
      currentReference = batchItem.target.currentUrl;
    } else if (batchItem.target?.mode === 'insert') {
      action = 'insert-missing-english-image';
    } else {
      issues.push({ id: hqItem.id, code: 'unresolved-target-action' });
      continue;
    }

    const referenceOccurrences = countOccurrences(englishContent, currentReference);
    if (action !== 'insert-missing-english-image' && referenceOccurrences < 1) {
      issues.push({ id: hqItem.id, code: 'target-reference-not-found' });
      continue;
    }

    entries.push({
      id: hqItem.id,
      slug: hqItem.slug,
      action,
      status: 'ready',
      sourcePath: repoRelative(hqItem.sourcePath),
      hqPath: repoRelative(hqItem.outputPath),
      mdxPath: repoRelative(mdxPath),
      sourceReference: automationItem.sourceUrl,
      currentReference,
      sourceOccurrences,
      referenceOccurrences,
    });
  }

  if (issues.length > 0) {
    fail(issues);
    return;
  }

  entries.sort((left, right) => left.slug.localeCompare(right.slug) || left.id.localeCompare(right.id));
  const actions = entries.reduce((counts, entry) => {
    counts[entry.action] = (counts[entry.action] ?? 0) + 1;
    return counts;
  }, {});
  const manifest = {
    version: 1,
    createdAt: new Date().toISOString(),
    scope: 'yida',
    sourceLanguage: 'zh',
    targetLanguage: 'en',
    sourceStateUpdatedAt: {
      hq: hqState.updatedAt,
      automation: automationState.updatedAt,
      batch: batchState.updatedAt,
    },
    summary: {
      ready: entries.length,
      deferred: hqItems.filter((item) => item.status === 'deferred').length,
      uniqueMdxFiles: new Set(entries.map((entry) => entry.mdxPath)).size,
      actions,
    },
    entries,
  };
  writeJsonAtomic(manifestPath, manifest);
  console.log(JSON.stringify({ ok: true, manifestPath: repoRelative(manifestPath), ...manifest.summary }, null, 2));
}

try {
  main();
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
