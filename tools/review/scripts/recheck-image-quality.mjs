#!/usr/bin/env node

import { existsSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { createServer } from 'vite';

const reviewRoot = resolve(import.meta.dirname, '..');
const repoRoot = resolve(process.argv[2] ?? join(reviewRoot, '..', '..'));
const scope = process.argv[3] ?? 'yida';
const statePath = join(repoRoot, 'tools', 'review', '.cache', 'image-automation', `${scope}.json`);
const reportPath = join(repoRoot, 'tools', 'review', '.cache', `image-quality-recheck-${scope}.json`);
const vite = await createServer({ root: reviewRoot, appType: 'custom', server: { middlewareMode: true } });

try {
  const { inspectImagesSafety } = await vite.ssrLoadModule('/src/server/image-batch.ts');
  const job = JSON.parse(readFileSync(statePath, 'utf8'));
  const items = job.items.filter((item) => item.status === 'quality_failed' && item.outputPath && existsSync(item.outputPath));
  const paths = items.flatMap((item) => item.outputPath ? [item.outputPath] : []);
  const inspections = await inspectImagesSafety(repoRoot, paths);
  const findings = {};
  let passed = 0;
  let failed = 0;
  for (const item of items) {
    const inspection = item.outputPath ? inspections.get(item.outputPath) : undefined;
    if (inspection?.ok) {
      item.status = 'quality_passed';
      item.reason = undefined;
      passed += 1;
      continue;
    }
    const reasons = inspection?.findings ?? ['ocr-unavailable'];
    item.status = 'quality_failed';
    item.reason = `自动验收未通过：${reasons.join(', ')}`;
    for (const reason of reasons) findings[reason] = (findings[reason] ?? 0) + 1;
    failed += 1;
  }

  job.updatedAt = new Date().toISOString();
  job.message = `二次质检完成：通过 ${passed} 张，仍需复核 ${failed} 张`;
  job.events.push({ at: job.updatedAt, stage: job.stage, message: job.message });
  if (job.events.length > 200) job.events = job.events.slice(-200);
  job.stats = {
    discovered: job.stats.discovered,
    eligible: job.items.filter((item) => !['deferred', 'quality_failed', 'failed'].includes(item.status)).length,
    deferred: job.items.filter((item) => item.status === 'deferred').length,
    generated: job.items.filter((item) => ['generated', 'quality_passed', 'mapped', 'applied'].includes(item.status)).length,
    qualityPassed: job.items.filter((item) => ['quality_passed', 'mapped', 'applied'].includes(item.status)).length,
    mapped: job.items.filter((item) => ['mapped', 'applied'].includes(item.status)).length,
    applied: job.items.filter((item) => item.status === 'applied').length,
    failed: job.items.filter((item) => ['quality_failed', 'failed'].includes(item.status)).length,
  };

  const temporary = `${statePath}.tmp.${process.pid}`;
  writeFileSync(temporary, `${JSON.stringify(job, null, 2)}\n`, 'utf8');
  renameSync(temporary, statePath);
  writeFileSync(reportPath, `${JSON.stringify({ checked: items.length, passed, failed, findings }, null, 2)}\n`, 'utf8');
  console.log(JSON.stringify({ checked: items.length, passed, failed, findings }));
} finally {
  await vite.close();
}
