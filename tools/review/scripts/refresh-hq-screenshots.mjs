#!/usr/bin/env node

import { spawn, spawnSync } from 'node:child_process';
import {
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const reviewRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = resolve(reviewRoot, '../..');
const cacheRoot = join(reviewRoot, '.cache');
const automationPath = join(cacheRoot, 'image-automation', 'yida.json');
const provenancePath = join(cacheRoot, 'image-output-provenance.json');
const batchPath = join(cacheRoot, 'image-batches', 'yida-zh-en.json');
const statePath = join(cacheRoot, 'image-hq-refresh.json');
const outputRoot = join(reviewRoot, 'output', 'image-batch', 'yida-zh-en', 'generated-hq');
const workerRoot = join(reviewRoot, 'output', 'image-automation-hq');
const ocrSource = join(reviewRoot, 'scripts', 'ocr-sensitive.swift');
const ocrBinary = join(cacheRoot, 'bin', 'ocr-sensitive');
const glossaryPath = join(repoRoot, 'scripts', 'glossary', 'zh-en.json');

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

function writeJsonAtomic(path, value) {
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.tmp.${process.pid}.${Date.now()}`;
  writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
  renameSync(temporary, path);
}

function parseArgs(argv) {
  const options = {
    mode: 'all',
    limit: 10,
    concurrency: 2,
    attempts: 2,
    dryRun: false,
    verifyOnly: false,
    repairState: false,
    includeVideoPosters: false,
    ids: [],
  };
  for (let index = 0; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === '--') continue;
    if (value === '--dry-run') options.dryRun = true;
    else if (value === '--verify-only') options.verifyOnly = true;
    else if (value === '--repair-state') options.repairState = true;
    else if (value === '--include-video-posters') options.includeVideoPosters = true;
    else if (value === '--mode') options.mode = argv[++index] ?? options.mode;
    else if (value === '--limit') options.limit = Number(argv[++index] ?? options.limit);
    else if (value === '--concurrency') options.concurrency = Number(argv[++index] ?? options.concurrency);
    else if (value === '--attempts') options.attempts = Number(argv[++index] ?? options.attempts);
    else if (value === '--ids') options.ids = (argv[++index] ?? '').split(',').filter(Boolean);
    else throw new Error(`unknown argument: ${value}`);
  }
  if (!['failed', 'degraded', 'all'].includes(options.mode)) throw new Error('mode must be failed, degraded, or all');
  if (!Number.isInteger(options.limit) || options.limit < 1) throw new Error('limit must be a positive integer');
  if (!Number.isInteger(options.concurrency) || options.concurrency < 1 || options.concurrency > 8) {
    throw new Error('concurrency must be an integer between 1 and 8');
  }
  if (!Number.isInteger(options.attempts) || options.attempts < 1 || options.attempts > 3) {
    throw new Error('attempts must be an integer between 1 and 3');
  }
  return options;
}

function probeImage(path) {
  const result = spawnSync('sips', ['-g', 'pixelWidth', '-g', 'pixelHeight', path], { encoding: 'utf8' });
  if (result.status !== 0) throw new Error('image dimensions unavailable');
  const width = Number(/pixelWidth:\s*(\d+)/.exec(result.stdout)?.[1]);
  const height = Number(/pixelHeight:\s*(\d+)/.exec(result.stdout)?.[1]);
  if (!width || !height) throw new Error('invalid image dimensions');
  return { width, height };
}

function ensureOcrBinary() {
  if (existsSync(ocrBinary) && statSync(ocrBinary).mtimeMs >= statSync(ocrSource).mtimeMs) return;
  mkdirSync(dirname(ocrBinary), { recursive: true });
  const result = spawnSync('swiftc', ['-O', ocrSource, '-o', ocrBinary], { encoding: 'utf8' });
  if (result.status !== 0) throw new Error('OCR checker build failed');
}

function sensitiveFindings(texts, qrCount, confidences = [], languages = []) {
  const text = texts.join('\n');
  // Vision can return `https://` and the safe host as separate text rows.
  const withoutSafeUrls = text.replace(/https?:\/\/\s*(?:example\.(?:com|invalid)|localhost)\b\S*/gi, '');
  const safe = withoutSafeUrls
    .replace(/\b[A-Z0-9._%+-]+@example\.(?:com|invalid)\b/gi, '')
    .replace(/\b(?:token|access[_ -]?key|secret|authorization)\s*[:=]\s*(?:TEST_VALUE|REDACTED)\b/gi, '')
    .replace(/\b(?:uid|user[_ -]?id|account[_ -]?id)\s*[:=]\s*(?:TEST_ID|REDACTED)\b/gi, '');
  const findings = new Set();
  if (/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i.test(safe)) findings.add('email');
  if (/(?:^|\D)1[3-9]\d{9}(?:\D|$)/.test(safe)) findings.add('phone');
  if (/\b(?:token|access[_ -]?key|secret|authorization)\s*[:=]\s*\S{4,}|\bbearer\s+\S{4,}/i.test(safe)) findings.add('token');
  if (/\b(?:uid|user[_ -]?id|account[_ -]?id)\s*[:=]\s*\S{2,}|(?:工号|账号)\s*[:：=]\s*\S{2,}/i.test(safe)) findings.add('uid/account');
  if (/https?:\/\//i.test(withoutSafeUrls)) findings.add('url');
  if (texts.some((value, index) => {
    const count = value.match(/[\u3400-\u9fff]/gu)?.length ?? 0;
    const language = languages[index] ?? 'und';
    if (language === 'ja' || language === 'ko') return false;
    const confidence = confidences[index] ?? 0;
    if (language.startsWith('zh')) return count >= 2 && confidence >= 0.75;
    return count >= 4 && confidence >= 0.75;
  })) findings.add('chinese-text');
  if (qrCount > 0) findings.add('qr-code');
  return [...findings];
}

function inspectCandidate(path) {
  ensureOcrBinary();
  const result = spawnSync(ocrBinary, [path], { encoding: 'utf8', maxBuffer: 16 * 1024 * 1024 });
  if (result.status !== 0) return { ok: false, findings: ['ocr-unavailable'], textCount: 0, qrCount: 0 };
  const [inspection] = JSON.parse(result.stdout);
  if (!inspection || inspection.error) return { ok: false, findings: ['ocr-unavailable'], textCount: 0, qrCount: 0 };
  const findings = sensitiveFindings(
    inspection.texts ?? [],
    inspection.qrCount ?? 0,
    inspection.confidences ?? [],
    inspection.languages ?? [],
  );
  return {
    ok: findings.length === 0,
    findings,
    textCount: inspection.texts?.length ?? 0,
    qrCount: inspection.qrCount ?? 0,
  };
}

function verifyPassedCandidates(repairState = false, selectedIds = []) {
  const state = loadState();
  const selected = new Set(selectedIds);
  const passed = Object.values(state.items).filter((item) => item.status === 'quality_passed'
    && (selected.size === 0 || selected.has(item.id)));
  const failures = [];
  const verified = new Set();
  let staleErrors = 0;
  for (const item of passed) {
    if (item.error) staleErrors += 1;
    if (!item.sourcePath || !item.outputPath || !existsSync(item.sourcePath) || !existsSync(item.outputPath)) {
      failures.push({ id: item.id, reason: 'missing source or output' });
      continue;
    }
    try {
      const sourceDimensions = probeImage(item.sourcePath);
      const outputDimensions = probeImage(item.outputPath);
      if (sourceDimensions.width !== outputDimensions.width || sourceDimensions.height !== outputDimensions.height) {
        failures.push({ id: item.id, reason: 'dimension mismatch' });
        continue;
      }
      const inspection = inspectCandidate(item.outputPath);
      if (!inspection.ok) failures.push({ id: item.id, reason: 'quality gate failed', findings: inspection.findings });
      else verified.add(item.id);
    } catch {
      failures.push({ id: item.id, reason: 'candidate inspection failed' });
    }
  }
  let cleanedErrors = 0;
  if (repairState) {
    for (const id of verified) {
      if (state.items[id]?.error) {
        delete state.items[id].error;
        cleanedErrors += 1;
      }
    }
    if (cleanedErrors > 0) {
      state.updatedAt = new Date().toISOString();
      writeJsonAtomic(statePath, state);
    }
  }
  const result = {
    checked: passed.length,
    passed: passed.length - failures.length,
    failed: failures.length,
    staleErrors,
    cleanedErrors,
    failures,
  };
  console.log(JSON.stringify(result, null, 2));
  if (failures.length > 0) process.exitCode = 1;
}

function promptFor(item, batchItem, dimensions, outputPath, feedback) {
  const feedbackInstructions = [];
  if (feedback?.includes('url')) {
    feedbackInstructions.push(
      '上次仍检出 URL：把所有可见的网址、域名、IP、地址栏、路径、查询参数和片段完整替换为 https://example.invalid/test；不得保留原 host、IP、path、query 或 fragment。',
    );
  }
  if (feedback?.includes('email')) {
    feedbackInstructions.push('上次仍检出邮箱：所有可见邮箱统一替换为 user@example.invalid。');
  }
  if (feedback?.includes('phone')) {
    feedbackInstructions.push('上次仍检出手机号：所有可见手机号统一替换为 13800000000。');
  }
  if (feedback?.includes('token') || feedback?.includes('uid/account')) {
    feedbackInstructions.push('上次仍检出账号或凭证：统一替换为 TEST_ID、TEST_VALUE 或 REDACTED，不得保留原值。');
  }
  if (feedback?.includes('qr-code')) {
    feedbackInstructions.push('上次仍检出二维码：将二维码区域替换为纯色占位框并标注 REDACTED。');
  }
  if (feedback?.includes('chinese-text')) {
    feedbackInstructions.push('上次仍检出中文：逐区域检查全部可见文字并翻译为英文，不得遗漏小字号标签、提示、菜单或弹窗文字。');
  }
  return [
    '使用 imagegen 技能编辑附加的宜搭中文产品截图。',
    'Use case: text-localization。',
    '只替换截图中的可见中文文字；严格保持布局、颜色、图标、边框、留白、交互状态和非文字像素。',
    `最终尺寸必须为 ${dimensions.width}x${dimensions.height}。`,
    `宜搭术语以只读词库 ${glossaryPath} 为准；只读取相关词条，不得修改词库。`,
    '手机号、邮箱、姓名、工号、账号、UID、token、二维码和内部 URL 必须替换为明显无效的测试数据或安全占位内容。',
    '不得残留中文，不得新增真实个人信息，不得改变产品结构。',
    '本工作单元只允许调用一次内置 image_gen；不要自行发起第二轮生成。',
    '若生成尺寸不同，只用本地工具缩放到目标尺寸；不要用本地文字覆盖方案。',
    feedback ? `上次自动验收未通过，必须修复：${feedback}` : '',
    ...feedbackInstructions,
    batchItem?.sourceAlt ? `文档原始 alt：${batchItem.sourceAlt}` : '',
    `将最终 PNG 保存到绝对路径 ${outputPath}。`,
    '除该 PNG 外不要创建或修改任何项目文件。最终只返回一行 JSON。',
  ].filter(Boolean).join('\n');
}

async function runCodex(item, batchItem, outputPath, feedback) {
  const dimensions = probeImage(item.sourcePath);
  const worker = join(workerRoot, item.id);
  mkdirSync(worker, { recursive: true });
  mkdirSync(dirname(outputPath), { recursive: true });
  const args = [
    'exec',
    '--ephemeral',
    '--skip-git-repo-check',
    '--sandbox',
    'workspace-write',
    '-C',
    worker,
    '--add-dir',
    dirname(outputPath),
    '-c',
    'model_reasoning_effort="low"',
    promptFor(item, batchItem, dimensions, outputPath, feedback),
    '--image',
    item.sourcePath,
  ];
  const detail = await new Promise((resolveRun, rejectRun) => {
    const child = spawn('codex', args, { cwd: worker, stdio: ['ignore', 'pipe', 'pipe'] });
    let output = '';
    let timedOut = false;
    const append = (chunk) => { output = `${output}${chunk}`.slice(-8000); };
    child.stdout.on('data', append);
    child.stderr.on('data', append);
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
      setTimeout(() => child.kill('SIGKILL'), 2000).unref();
    }, 10 * 60 * 1000);
    child.once('error', rejectRun);
    child.once('close', (code) => {
      clearTimeout(timer);
      if (code === 0) resolveRun(output);
      else rejectRun(new Error(timedOut ? 'generation timeout' : `codex generation failed: ${output.slice(-1000)}`));
    });
  });
  if (!existsSync(outputPath)) throw new Error(`candidate not produced: ${detail.slice(-200)}`);
  const outputDimensions = probeImage(outputPath);
  if (outputDimensions.width !== dimensions.width || outputDimensions.height !== dimensions.height) {
    throw new Error(`dimension mismatch: ${outputDimensions.width}x${outputDimensions.height}`);
  }
}

function buildQueue(options) {
  const automation = readJson(automationPath);
  const provenance = readJson(provenancePath);
  const batch = readJson(batchPath);
  const provenanceById = new Map(provenance.items.map((item) => [item.id, item]));
  const batchById = new Map(batch.items.map((item) => [item.id, item]));
  const selectedIds = new Set(options.ids);
  const failed = automation.items.filter((item) => item.status === 'quality_failed');
  const degraded = automation.items.filter((item) => {
    const audit = provenanceById.get(item.id);
    return item.status === 'applied'
      && audit?.inferred === 'local-overlay'
      && Number(audit.exactPixelRatio) < 1;
  });
  const requested = options.mode === 'failed' ? failed : options.mode === 'degraded' ? degraded : [...failed, ...degraded];
  if (selectedIds.size) {
    for (const batchItem of batch.items) {
      if (!selectedIds.has(batchItem.id) || requested.some((item) => item.id === batchItem.id)) continue;
      requested.push({
        id: batchItem.id,
        slug: batchItem.slug,
        sourcePath: batchItem.prepared?.sourcePath,
        status: batchItem.status,
      });
    }
  }
  const deferredMedia = requested.filter((item) => {
    const batchItem = batchById.get(item.id);
    if (batchItem?.mediaKind !== 'raster') return true;
    return !options.includeVideoPosters && /video\s*poster|视频封面/i.test(batchItem?.sourceAlt ?? '');
  });
  let queue = requested.filter((item) => !deferredMedia.some((candidate) => candidate.id === item.id));
  if (selectedIds.size) queue = queue.filter((item) => selectedIds.has(item.id));
  queue = queue.filter((item, index, values) => item.sourcePath && values.findIndex((candidate) => candidate.id === item.id) === index);
  const selected = queue.length;
  const queued = Math.min(selected, options.limit);
  return {
    automation,
    batchById,
    deferredMedia,
    totals: {
      failed: failed.length,
      degraded: degraded.length,
      deferredMedia: deferredMedia.length,
      selected,
      queued,
    },
    queue: queue.slice(0, options.limit),
  };
}

function loadState() {
  if (existsSync(statePath)) return readJson(statePath);
  return { version: 1, createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), items: {} };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.verifyOnly) {
    verifyPassedCandidates(options.repairState, options.ids);
    return;
  }
  const { queue, batchById, deferredMedia, totals } = buildQueue(options);
  const state = loadState();
  state.updatedAt = new Date().toISOString();
  state.options = options;
  state.totals = totals;
  for (const item of deferredMedia) {
    state.items[item.id] = {
      ...(state.items[item.id] ?? {}),
      id: item.id,
      slug: item.slug,
      sourcePath: item.sourcePath,
      status: 'deferred',
      reason: 'video or non-raster media is outside the HQ screenshot refresh scope',
      updatedAt: new Date().toISOString(),
    };
  }
  if (options.dryRun) {
    console.log(JSON.stringify({ options, totals, queued: queue.map((item) => item.id) }, null, 2));
    return;
  }
  mkdirSync(outputRoot, { recursive: true });
  let cursor = 0;
  let quotaBlocked = false;
  const worker = async () => {
    while (cursor < queue.length && !quotaBlocked) {
      const item = queue[cursor++];
      const previous = state.items[item.id];
      if (previous?.status === 'quality_passed' && existsSync(previous.outputPath)) continue;
      const outputPath = join(outputRoot, `${item.id}-en-hq.png`);
      const entry = {
        id: item.id,
        slug: item.slug,
        sourcePath: item.sourcePath,
        outputPath,
        status: 'generating',
        attempts: previous?.attempts ?? 0,
        updatedAt: new Date().toISOString(),
      };
      state.items[item.id] = entry;
      if (existsSync(outputPath)) {
        try {
          const sourceDimensions = probeImage(item.sourcePath);
          const outputDimensions = probeImage(outputPath);
          if (sourceDimensions.width === outputDimensions.width && sourceDimensions.height === outputDimensions.height) {
            const inspection = inspectCandidate(outputPath);
            entry.status = inspection.ok ? 'quality_passed' : 'quality_failed';
            entry.findings = inspection.findings;
            entry.textCount = inspection.textCount;
            entry.qrCount = inspection.qrCount;
            entry.updatedAt = new Date().toISOString();
            writeJsonAtomic(statePath, state);
            if (inspection.ok) continue;
          }
        } catch {
          // Regenerate unreadable or uninspectable candidates below.
        }
      }
      writeJsonAtomic(statePath, state);
      while (entry.attempts < options.attempts) {
        entry.status = 'generating';
        entry.attempts += 1;
        delete entry.error;
        entry.updatedAt = new Date().toISOString();
        writeJsonAtomic(statePath, state);
        try {
          await runCodex(item, batchById.get(item.id), outputPath, entry.findings?.join(', '));
          const inspection = inspectCandidate(outputPath);
          entry.status = inspection.ok ? 'quality_passed' : 'quality_failed';
          entry.findings = inspection.findings;
          delete entry.error;
          entry.textCount = inspection.textCount;
          entry.qrCount = inspection.qrCount;
          entry.updatedAt = new Date().toISOString();
          writeJsonAtomic(statePath, state);
          if (inspection.ok) break;
        } catch (error) {
          const message = error instanceof Error ? error.message : 'generation failed';
          entry.status = 'failed';
          entry.error = message.slice(-1200);
          entry.updatedAt = new Date().toISOString();
          if (/usage limit|purchase more credits|quota/i.test(message)) quotaBlocked = true;
          writeJsonAtomic(statePath, state);
          if (quotaBlocked) break;
        }
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(options.concurrency, queue.length) }, () => worker()));
  const values = Object.values(state.items);
  state.summary = values.reduce((summary, item) => {
    summary[item.status] = (summary[item.status] ?? 0) + 1;
    return summary;
  }, {});
  state.quotaBlocked = quotaBlocked;
  state.updatedAt = new Date().toISOString();
  writeJsonAtomic(statePath, state);
  console.log(JSON.stringify({ totals, processed: queue.length, summary: state.summary, quotaBlocked }, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
