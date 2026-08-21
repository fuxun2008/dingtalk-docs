#!/usr/bin/env node

import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const reviewRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const refreshScript = join(reviewRoot, 'scripts', 'refresh-hq-screenshots.mjs');
const statePath = join(reviewRoot, '.cache', 'image-hq-refresh.json');

function run(args) {
  return new Promise((resolveRun, rejectRun) => {
    const child = spawn(process.execPath, [refreshScript, ...args], {
      cwd: reviewRoot,
      stdio: 'inherit',
    });
    child.once('error', rejectRun);
    child.once('close', (code) => {
      if (code === 0) resolveRun();
      else rejectRun(new Error(`HQ command failed with exit code ${code}`));
    });
  });
}

async function main() {
  // Rewalk every ordinary screenshot. Existing passing outputs are inspected and
  // reused; only unresolved entries receive their final generation attempt.
  await run([
    '--mode', 'all',
    '--limit', '100000',
    '--concurrency', '2',
    '--attempts', '3',
  ]);
  await run(['--verify-only', '--repair-state']);

  const state = JSON.parse(readFileSync(statePath, 'utf8'));
  const counts = Object.values(state.items).reduce((result, item) => {
    result[item.status] = (result[item.status] ?? 0) + 1;
    return result;
  }, {});
  const unresolved = (counts.failed ?? 0) + (counts.quality_failed ?? 0) + (counts.generating ?? 0);
  console.log(JSON.stringify({ counts, unresolved }, null, 2));
  if (unresolved > 0) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
