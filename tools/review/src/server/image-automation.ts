import { execFile, spawn } from 'node:child_process';
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  rmSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { basename, dirname, extname, join, relative } from 'node:path';
import { promisify } from 'node:util';
import type {
  ImageAutomationItem,
  ImageAutomationJob,
  ImageAutomationStage,
  StartImageAutomationInput,
} from '../shared/image-automation';
import type { BatchImageItem } from '../shared/image-batch';
import {
  applyImageBatch,
  inspectImagesSafety,
  preflightImageBatchTargets,
  prepareImageBatch,
  scanImageBatch,
  updateImageBatch,
} from './image-batch';

const execFileAsync = promisify(execFile);
const running = new Map<string, Promise<void>>();
const PREPARE_CHUNK_SIZE = 40;
const UPLOAD_BATCH_SIZE = 20;
const MAX_GENERATION_ATTEMPTS = 3;
const lastJobSave = new WeakMap<ImageAutomationJob, number>();

interface ImageDimensions {
  width: number;
  height: number;
}

interface UploadResult {
  ok?: boolean;
  error?: string;
  authRequired?: boolean;
  items?: Array<{ id: string; cdnUrl?: string; error?: string }>;
}

function automationKey(scope: string): string {
  return scope.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'images';
}

function statePath(repoRoot: string, scope: string): string {
  return join(repoRoot, 'tools', 'review', '.cache', 'image-automation', `${automationKey(scope)}.json`);
}

function saveJob(repoRoot: string, job: ImageAutomationJob): void {
  const file = statePath(repoRoot, job.scope);
  mkdirSync(dirname(file), { recursive: true });
  job.updatedAt = new Date().toISOString();
  refreshStats(job);
  const temporary = `${file}.tmp.${process.pid}.${Date.now()}`;
  writeFileSync(temporary, JSON.stringify(job, null, 2) + '\n', 'utf8');
  renameSync(temporary, file);
  lastJobSave.set(job, Date.now());
}

function saveJobThrottled(repoRoot: string, job: ImageAutomationJob): void {
  if (Date.now() - (lastJobSave.get(job) ?? 0) >= 1000) saveJob(repoRoot, job);
}

function refreshStats(job: ImageAutomationJob): void {
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
}

function event(repoRoot: string, job: ImageAutomationJob, stage: ImageAutomationStage, message: string): void {
  job.stage = stage;
  job.message = message;
  job.events.push({ at: new Date().toISOString(), stage, message });
  if (job.events.length > 200) job.events.splice(0, job.events.length - 200);
  saveJob(repoRoot, job);
}

function emptyJob(scope: string): ImageAutomationJob {
  const now = new Date().toISOString();
  return {
    version: 1,
    id: `${automationKey(scope)}-${Date.now().toString(36)}`,
    scope,
    stage: 'queued',
    createdAt: now,
    updatedAt: now,
    message: '任务已进入后台队列',
    stats: {
      discovered: 0,
      eligible: 0,
      deferred: 0,
      generated: 0,
      qualityPassed: 0,
      mapped: 0,
      applied: 0,
      failed: 0,
    },
    items: [],
    changedFiles: [],
    events: [{ at: now, stage: 'queued', message: '任务已进入后台队列' }],
  };
}

export function readImageAutomationJob(repoRoot: string, scope: string): ImageAutomationJob | null {
  const file = statePath(repoRoot, scope);
  if (!existsSync(file)) return null;
  try {
    return JSON.parse(readFileSync(file, 'utf8')) as ImageAutomationJob;
  } catch {
    return null;
  }
}

function updateItem(job: ImageAutomationJob, id: string, patch: Partial<ImageAutomationItem>): void {
  const item = job.items.find((candidate) => candidate.id === id);
  if (item) Object.assign(item, patch);
}

function shouldStop(repoRoot: string, job: ImageAutomationJob): boolean {
  const latest = readImageAutomationJob(repoRoot, job.scope);
  if (!latest?.cancelRequested) return false;
  job.cancelRequested = true;
  job.stage = 'cancelled';
  job.finishedAt = new Date().toISOString();
  job.message = '任务已取消；已完成结果保留，可下次恢复';
  saveJob(repoRoot, job);
  return true;
}

async function probeImage(path: string): Promise<ImageDimensions> {
  const { stdout } = await execFileAsync('sips', ['-g', 'pixelWidth', '-g', 'pixelHeight', path], {
    maxBuffer: 1024 * 1024,
  });
  const width = Number(/pixelWidth:\s*(\d+)/.exec(stdout)?.[1]);
  const height = Number(/pixelHeight:\s*(\d+)/.exec(stdout)?.[1]);
  if (!width || !height) throw new Error(`无法读取图片尺寸：${basename(path)}`);
  return { width, height };
}

async function runCodex(args: string[], cwd: string): Promise<void> {
  await new Promise<void>((resolveRun, rejectRun) => {
    const child = spawn('codex', args, {
      cwd,
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    const stdout: Buffer[] = [];
    const stderr: Buffer[] = [];
    let timedOut = false;
    child.stdout.on('data', (chunk: Buffer) => stdout.push(chunk));
    child.stderr.on('data', (chunk: Buffer) => stderr.push(chunk));
    child.stdin.end();
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
      setTimeout(() => child.kill('SIGKILL'), 2000).unref();
    }, 5 * 60 * 1000);
    child.once('error', (error) => {
      clearTimeout(timer);
      rejectRun(error);
    });
    child.once('close', (code, signal) => {
      clearTimeout(timer);
      if (code === 0) {
        resolveRun();
        return;
      }
      const detail = Buffer.concat([...stderr, ...stdout]).toString('utf8').slice(-4000).trim();
      rejectRun(new Error(timedOut
        ? 'Codex 图片生成超过 5 分钟，已终止'
        : `Codex 图片生成失败（${code ?? signal ?? 'unknown'}）${detail ? `：${detail}` : ''}`));
    });
  });
}

function complexityReason(item: BatchImageItem, dimensions: ImageDimensions, sourcePath: string): string | null {
  if (item.mediaKind !== 'raster') return `暂不处理 ${item.mediaKind.toUpperCase()}`;
  const aspect = Math.max(dimensions.width / dimensions.height, dimensions.height / dimensions.width);
  const pixels = dimensions.width * dimensions.height;
  if (item.complexityReasons.includes('dense-ui') && (pixels > 8_000_000 || Math.max(dimensions.width, dimensions.height) > 3000)) {
    return '高密度复杂产品界面留待后续批次';
  }
  if (aspect > 4 || dimensions.width > 5000 || dimensions.height > 5000) return '复杂长图留待后续批次';
  if (pixels > 20_000_000) return '超大分辨率图片留待后续批次';
  if (statSync(sourcePath).size > 12 * 1024 * 1024) return '大文件留待后续批次';
  return null;
}

function generationPrompt(
  repoRoot: string,
  item: BatchImageItem,
  source: ImageDimensions,
  outputPath: string,
  retryFeedback?: string,
): string {
  const glossary = join(repoRoot, 'scripts', 'glossary', 'zh-en.json');
  return [
    '使用 imagegen 技能编辑附加的宜搭中文产品截图。',
    'Use case: text-localization。',
    '只把截图中可见中文替换为英文；保持布局、颜色、图标、边框、留白、交互状态和所有非文字像素。',
    `最终尺寸必须为 ${source.width}x${source.height}。`,
    `宜搭术语以只读词库 ${glossary} 为准；只读取相关词条，不得修改词库。`,
    '手机号、邮箱、姓名、工号、账号、UID、token、二维码和内部 URL 必须替换为明显无效的测试数据或安全占位内容。',
    '本工作单元只允许调用一次内置 image_gen；不要自行发起第二轮图片生成，不要在本任务中执行 OCR 或目视迭代。',
    '如果 image_gen 输出尺寸不同，只用本地无损工具缩放到目标尺寸；中文残留和隐私风险由外层批量质检与定向重试处理。',
    '不得新增真实个人信息，不得改变产品结构。',
    retryFeedback ? `上次自动验收未通过，必须修复后重做：${retryFeedback}` : '',
    `将最终 PNG 保存到绝对路径 ${outputPath}。`,
    '除该 PNG 外不要创建或修改任何项目文件。最终只返回一行 JSON，包含 ok、output、error。',
    item.sourceAlt ? `文档中的原始 alt：${item.sourceAlt}` : '',
  ].filter(Boolean).join('\n');
}

async function generateOne(
  repoRoot: string,
  batchItem: BatchImageItem,
  item: ImageAutomationItem,
  retryFeedback?: string,
): Promise<void> {
  if (!item.sourcePath || !item.outputPath) throw new Error('任务缺少本地输入或输出路径');
  const sourceDimensions = await probeImage(item.sourcePath);
  const workerDir = join(repoRoot, 'tools', 'review', 'output', 'image-automation', item.id);
  mkdirSync(workerDir, { recursive: true });
  mkdirSync(dirname(item.outputPath), { recursive: true });
  const candidatePath = `${item.outputPath}.attempt-${item.attempts}.${process.pid}.png`;
  if (existsSync(candidatePath)) rmSync(candidatePath, { force: true });
  const args = [
    'exec',
    '--ephemeral',
    '--skip-git-repo-check',
    '--sandbox',
    'workspace-write',
    '-C',
    workerDir,
    '--add-dir',
    dirname(item.outputPath),
    '-c',
    'model_reasoning_effort="low"',
    generationPrompt(repoRoot, batchItem, sourceDimensions, candidatePath, retryFeedback),
    '--image',
    item.sourcePath,
  ];
  try {
    await runCodex(args, workerDir);
    if (!existsSync(candidatePath) || !statSync(candidatePath).isFile()) {
      throw new Error('生成任务结束但没有产生新的候选图片');
    }
    const outputDimensions = await probeImage(candidatePath);
    if (outputDimensions.width !== sourceDimensions.width || outputDimensions.height !== sourceDimensions.height) {
      throw new Error(`输出尺寸不一致：${outputDimensions.width}x${outputDimensions.height}，预期 ${sourceDimensions.width}x${sourceDimensions.height}`);
    }
    renameSync(candidatePath, item.outputPath);
  } finally {
    if (existsSync(candidatePath)) rmSync(candidatePath, { force: true });
  }
}

async function runPool<T>(values: T[], concurrency: number, work: (value: T) => Promise<void>): Promise<void> {
  let cursor = 0;
  const worker = async (): Promise<void> => {
    while (cursor < values.length) {
      const value = values[cursor++];
      await work(value);
    }
  };
  await Promise.all(Array.from({ length: Math.min(concurrency, values.length) }, () => worker()));
}

function copyBackups(repoRoot: string, job: ImageAutomationJob, changedFiles: string[]): void {
  const root = join(repoRoot, 'tools', 'review', '.cache', 'image-automation', 'backups', job.id);
  for (const file of changedFiles) {
    const relativePath = relative(repoRoot, file);
    const extension = extname(relativePath);
    const destination = join(root, `${relativePath.slice(0, -extension.length)}.local${extension}`);
    mkdirSync(dirname(destination), { recursive: true });
    copyFileSync(file, destination);
  }
}

async function verifyCdnUrl(url: string): Promise<boolean> {
  try {
    const response = await fetch(url, { method: 'GET', headers: { Range: 'bytes=0-0' }, redirect: 'follow' });
    return response.ok && /^image\//i.test(response.headers.get('content-type') ?? '');
  } catch {
    return false;
  }
}

async function runUpload(
  repoRoot: string,
  job: ImageAutomationJob,
  items: ImageAutomationItem[],
  uploadPage: string | undefined,
): Promise<UploadResult> {
  if (!uploadPage) throw new Error('缺少 CDN 上传页地址，请在批处理面板中配置后重试');
  const workDir = join(repoRoot, 'tools', 'review', '.cache', 'image-automation', 'uploads', job.id);
  mkdirSync(workDir, { recursive: true });
  const manifestPath = join(workDir, 'cdn-upload-job.json');
  const resultPath = join(workDir, 'cdn-upload-result.json');
  writeFileSync(manifestPath, JSON.stringify({
    version: 1,
    items: items.map((item) => ({ id: item.id, path: item.outputPath, filename: basename(item.outputPath ?? '') })),
  }, null, 2) + '\n', 'utf8');
  const script = join(repoRoot, 'tools', 'review', 'scripts', 'cdn-browser-upload.mjs');
  try {
    await execFileAsync(process.execPath, [
      script,
      '--manifest', manifestPath,
      '--result', resultPath,
      '--batch-size', String(UPLOAD_BATCH_SIZE),
      '--upload-page', uploadPage,
    ], {
      cwd: repoRoot,
      timeout: 20 * 60 * 1000,
      maxBuffer: 16 * 1024 * 1024,
    });
  } catch (error) {
    if (existsSync(resultPath)) return JSON.parse(readFileSync(resultPath, 'utf8')) as UploadResult;
    throw error;
  }
  if (!existsSync(resultPath)) throw new Error('CDN 上传脚本没有生成结果文件');
  return JSON.parse(readFileSync(resultPath, 'utf8')) as UploadResult;
}

async function runJob(repoRoot: string, job: ImageAutomationJob, input: StartImageAutomationInput): Promise<void> {
  try {
    job.startedAt ??= new Date().toISOString();
    event(repoRoot, job, 'scanning', `正在扫描 ${job.scope}`);
    let batch = scanImageBatch(repoRoot, job.scope);
    job.stats.discovered = batch.items.length;
    const existingById = new Map(job.items.map((item) => [item.id, item]));
    const initialBatchById = new Map(batch.items.map((item) => [item.id, item]));
    let candidates = batch.items.filter((item) => item.status !== 'completed');
    if (input.maxItems && input.maxItems > 0) candidates = candidates.slice(0, input.maxItems);
    job.items = candidates.map((item) => {
      const existing = existingById.get(item.id);
      if (existing) {
        if (item.cdnUrl && !existing.cdnUrl) {
          existing.cdnUrl = item.cdnUrl;
          existing.status = item.status === 'completed' ? 'applied' : 'mapped';
          existing.reason = '检测到外部浏览器已完成 CDN 映射，已自动恢复后续流程';
        }
        if (existing.status === 'failed' && /usage limit|purchase more credits/i.test(existing.reason ?? '') && existing.sourcePath) {
          existing.status = existing.outputPath && existsSync(existing.outputPath) ? 'generated' : 'prepared';
          existing.attempts = 0;
          existing.reason = '额度恢复后自动重新入队';
        }
        if (existing.status === 'generating' || (existing.status === 'failed' && existing.outputPath && existsSync(existing.outputPath))) {
          if (existing.status === 'generating' && (!existing.outputPath || !existsSync(existing.outputPath))) {
            existing.attempts = Math.max(0, existing.attempts - 1);
          }
          existing.status = existing.outputPath && existsSync(existing.outputPath)
            ? 'generated'
            : existing.sourcePath
              ? 'prepared'
              : 'queued';
          existing.reason = existing.status === 'generated'
            ? '检测到已有英文图片，已自动恢复并等待质量检查'
            : '检测到上次进程中断，已自动恢复任务';
        }
        return existing;
      }
      const primary = item.duplicateOf ? initialBatchById.get(item.duplicateOf) : undefined;
      const reusableUrl = primary?.status === 'completed' && primary.target.currentUrl !== primary.sourceUrl
        ? primary.target.currentUrl
        : primary?.cdnUrl;
      return {
        id: item.id,
        slug: item.slug,
        sourceUrl: item.sourceUrl,
        status: reusableUrl ? 'mapped' : item.mediaKind === 'raster' ? 'queued' : 'deferred',
        reason: reusableUrl
          ? `复用相同源图 ${item.duplicateOf} 的英文 CDN 地址`
          : item.mediaKind === 'raster'
            ? item.duplicateOf ? `等待复用相同源图 ${item.duplicateOf} 的生成结果` : undefined
            : `暂不处理 ${item.mediaKind.toUpperCase()}`,
        cdnUrl: reusableUrl,
        attempts: 0,
      } satisfies ImageAutomationItem;
    });
    saveJob(repoRoot, job);
    if (input.planOnly) {
      event(repoRoot, job, 'completed', `规划完成：发现 ${batch.items.length} 个媒体，候选 ${job.items.filter((item) => item.status === 'queued').length} 个`);
      job.finishedAt = new Date().toISOString();
      saveJob(repoRoot, job);
      return;
    }

    const rasterIds = job.items
      .filter((item) => item.status === 'queued' && !initialBatchById.get(item.id)?.duplicateOf)
      .map((item) => item.id);
    for (let index = 0; index < rasterIds.length; index += PREPARE_CHUNK_SIZE) {
      if (shouldStop(repoRoot, job)) return;
      const chunk = rasterIds.slice(index, index + PREPARE_CHUNK_SIZE);
      event(repoRoot, job, 'preparing', `正在准备普通截图 ${Math.min(index + chunk.length, rasterIds.length)}/${rasterIds.length}`);
      batch = await prepareImageBatch(repoRoot, job.scope, chunk);
      const byId = new Map(batch.items.map((item) => [item.id, item]));
      for (const id of chunk) {
        const source = byId.get(id);
        if (!source?.prepared?.sourcePath || !source.prepared.outputPath) {
          updateItem(job, id, { status: 'failed', reason: source?.note ?? '资源准备失败' });
          continue;
        }
        try {
          const dimensions = await probeImage(source.prepared.sourcePath);
          const reason = complexityReason(source, dimensions, source.prepared.sourcePath);
          updateItem(job, id, reason ? {
            status: 'deferred',
            reason,
            sourcePath: source.prepared.sourcePath,
            outputPath: source.prepared.outputPath,
          } : {
            status: source.cdnUrl ? 'mapped' : source.localOutput ? 'generated' : 'prepared',
            reason: undefined,
            sourcePath: source.prepared.sourcePath,
            outputPath: source.localOutput ?? source.prepared.outputPath,
            cdnUrl: source.cdnUrl,
          });
        } catch (error) {
          updateItem(job, id, { status: 'failed', reason: error instanceof Error ? error.message : '图片分类失败' });
        }
      }
      saveJob(repoRoot, job);
    }

    batch = scanImageBatch(repoRoot, job.scope);
    const batchById = new Map(batch.items.map((item) => [item.id, item]));
    const toGenerate = job.items.filter((item) => ['prepared', 'generated'].includes(item.status) && !item.cdnUrl);
    const generatedUpdates: Array<{ id: string; localOutput?: string; status: 'generated' }> = [];
    let fatalGenerationError = '';
    const generationConcurrency = Math.max(1, Math.min(36, Number(process.env.YIDA_IMAGE_GENERATION_CONCURRENCY) || 4));
    event(repoRoot, job, 'generating', `开始后台生成 ${toGenerate.length} 张普通英文截图，并发 ${generationConcurrency}`);
    await runPool(toGenerate, generationConcurrency, async (item) => {
      if (fatalGenerationError) return;
      if (shouldStop(repoRoot, job)) return;
      job.currentItemId = item.id;
      item.status = 'generating';
      saveJobThrottled(repoRoot, job);
      const batchItem = batchById.get(item.id);
      if (!batchItem) {
        item.status = 'failed';
        item.reason = '扫描状态中找不到任务';
        saveJobThrottled(repoRoot, job);
        return;
      }
      if (item.sourcePath && item.outputPath && existsSync(item.outputPath)) {
        try {
          const [sourceDimensions, outputDimensions] = await Promise.all([
            probeImage(item.sourcePath),
            probeImage(item.outputPath),
          ]);
          if (
            sourceDimensions.width === outputDimensions.width
            && sourceDimensions.height === outputDimensions.height
          ) {
            item.status = 'generated';
            item.reason = undefined;
            generatedUpdates.push({ id: item.id, localOutput: item.outputPath, status: 'generated' });
            saveJobThrottled(repoRoot, job);
            return;
          }
        } catch {
          // Fall through to the normal generation retry path for unreadable output files.
        }
      }
      let lastError = '';
      while (item.attempts < MAX_GENERATION_ATTEMPTS) {
        try {
          let needsGeneration = !item.outputPath || !existsSync(item.outputPath);
          if (!needsGeneration && item.sourcePath && item.outputPath) {
            try {
              const [sourceDimensions, outputDimensions] = await Promise.all([
                probeImage(item.sourcePath),
                probeImage(item.outputPath),
              ]);
              needsGeneration = sourceDimensions.width !== outputDimensions.width
                || sourceDimensions.height !== outputDimensions.height;
            } catch {
              needsGeneration = true;
            }
          }
          if (needsGeneration) {
            item.attempts += 1;
            await generateOne(repoRoot, batchItem, item);
          }
          item.status = 'generated';
          item.reason = undefined;
          generatedUpdates.push({ id: item.id, localOutput: item.outputPath, status: 'generated' });
          break;
        } catch (error) {
          lastError = error instanceof Error ? error.message : '图片生成失败';
          if (/usage limit|purchase more credits/i.test(lastError)) {
            item.attempts = Math.max(0, item.attempts - 1);
            item.status = 'prepared';
            item.reason = '图片生成额度暂不可用，任务已保留等待恢复';
            fatalGenerationError = '图片生成额度暂不可用，已停止新任务并保留全部断点';
            break;
          }
        }
      }
      if (!['generated', 'prepared'].includes(item.status)) {
        item.status = 'failed';
        item.reason = lastError;
      }
      saveJobThrottled(repoRoot, job);
    });
    if (fatalGenerationError) throw new Error(fatalGenerationError);
    if (generatedUpdates.length) updateImageBatch(repoRoot, job.scope, generatedUpdates);

    const generated = job.items.filter((item) => item.status === 'generated' && item.outputPath);
    event(repoRoot, job, 'quality_check', `正在自动验收 ${generated.length} 张英文截图`);
    const inspections = await inspectImagesSafety(repoRoot, generated.flatMap((item) => item.outputPath ? [item.outputPath] : []));
    const qualityRetries: ImageAutomationItem[] = [];
    for (const item of generated) {
      const inspection = inspections.get(item.outputPath ?? '')
        ?? { ok: false, findings: ['ocr-unavailable'], textCount: 0, qrCount: 0 };
      if (!inspection.ok) {
        item.reason = `自动验收未通过：${inspection.findings.join(', ')}`;
        if (item.attempts < MAX_GENERATION_ATTEMPTS) {
          item.status = 'generating';
          qualityRetries.push(item);
        } else {
          item.status = 'quality_failed';
        }
      } else {
        item.status = 'quality_passed';
        item.reason = undefined;
      }
      saveJobThrottled(repoRoot, job);
    }

    let pendingQualityRetries = qualityRetries;
    while (pendingQualityRetries.length) {
      event(repoRoot, job, 'generating', `自动验收发现问题，正在定向修复 ${pendingQualityRetries.length} 张截图`);
      const retryRound = pendingQualityRetries;
      const retryAgain: ImageAutomationItem[] = [];
      await runPool(retryRound, generationConcurrency, async (item) => {
        const batchItem = batchById.get(item.id);
        if (!batchItem) {
          item.status = 'failed';
          item.reason = '重试时找不到扫描任务';
          return;
        }
        item.attempts += 1;
        try {
          await generateOne(repoRoot, batchItem, item, item.reason);
          item.status = 'generated';
        } catch (error) {
          item.reason = error instanceof Error ? error.message : '自动修复生成失败';
          if (item.attempts < MAX_GENERATION_ATTEMPTS) {
            item.status = 'generating';
            retryAgain.push(item);
          } else {
            item.status = 'failed';
          }
        }
        saveJobThrottled(repoRoot, job);
      });
      const regenerated = retryRound.filter((item) => item.status === 'generated' && item.outputPath);
      if (regenerated.length) {
        event(repoRoot, job, 'quality_check', `正在复检 ${regenerated.length} 张修复后的截图`);
        const retryInspections = await inspectImagesSafety(repoRoot, regenerated.flatMap((item) => item.outputPath ? [item.outputPath] : []));
        for (const item of regenerated) {
          const inspection = retryInspections.get(item.outputPath ?? '')
            ?? { ok: false, findings: ['ocr-unavailable'], textCount: 0, qrCount: 0 };
          if (inspection.ok) {
            item.status = 'quality_passed';
            item.reason = undefined;
          } else if (item.attempts < MAX_GENERATION_ATTEMPTS) {
            item.status = 'generating';
            item.reason = `自动复检未通过：${inspection.findings.join(', ')}`;
            retryAgain.push(item);
          } else {
            item.status = 'quality_failed';
            item.reason = `自动复检未通过：${inspection.findings.join(', ')}`;
          }
          saveJobThrottled(repoRoot, job);
        }
      }
      pendingQualityRetries = retryAgain;
    }

    const qualityPassed = job.items.filter((item) => item.status === 'quality_passed' && item.outputPath);
    const targetPreflight = preflightImageBatchTargets(repoRoot, job.scope, qualityPassed.map((item) => item.id));
    for (const skipped of targetPreflight.skipped) {
      updateItem(job, skipped.id, { status: 'failed', reason: `MDX 目标预检失败：${skipped.reason}` });
    }
    const applicable = new Set(targetPreflight.appliedIds);
    const uploadable = qualityPassed.filter((item) => applicable.has(item.id));
    saveJob(repoRoot, job);
    if (uploadable.length) {
      let pendingUpload = uploadable;
      let lastUploadError = '';
      for (let attempt = 1; attempt <= 3 && pendingUpload.length; attempt += 1) {
        event(repoRoot, job, 'uploading', `正在通过 Chrome 批量上传 ${pendingUpload.length} 张图片${attempt > 1 ? `（自动重试 ${attempt}/3）` : ''}`);
        const upload = await runUpload(repoRoot, job, pendingUpload, input.uploadPage);
        if (upload.authRequired) {
          event(repoRoot, job, 'awaiting_auth', 'CDN 的 SSO 登录已过期；在自动打开的 Chrome 中完成登录后再次点击一键任务即可恢复');
          return;
        }
        const updates: Array<{ id: string; cdnUrl: string }> = [];
        for (const result of upload.items ?? []) {
          if (!result.cdnUrl) continue;
          updates.push({ id: result.id, cdnUrl: result.cdnUrl });
          updateItem(job, result.id, { status: 'mapped', cdnUrl: result.cdnUrl, reason: undefined });
        }
        if (updates.length) updateImageBatch(repoRoot, job.scope, updates);
        const completed = new Set(updates.map((item) => item.id));
        pendingUpload = pendingUpload.filter((item) => !completed.has(item.id));
        lastUploadError = upload.error ?? (pendingUpload.length ? '部分图片没有返回 CDN 地址' : '');
        saveJob(repoRoot, job);
        if (!pendingUpload.length) break;
        if (attempt < 3) await new Promise((done) => setTimeout(done, attempt * 2000));
      }
      if (pendingUpload.length) {
        for (const item of pendingUpload) updateItem(job, item.id, { status: 'failed', reason: lastUploadError || 'CDN 上传失败' });
        saveJob(repoRoot, job);
        throw new Error(`CDN 批量上传重试后仍有 ${pendingUpload.length} 张失败：${lastUploadError || '未知错误'}`);
      }
    }

    const duplicateMappings: Array<{ id: string; cdnUrl: string }> = [];
    for (const item of job.items) {
      const source = batchById.get(item.id);
      if (!source?.duplicateOf) continue;
      if (item.cdnUrl) {
        if (source.cdnUrl !== item.cdnUrl) duplicateMappings.push({ id: item.id, cdnUrl: item.cdnUrl });
        continue;
      }
      const primaryJob = job.items.find((candidate) => candidate.id === source.duplicateOf);
      const primaryBatch = batchById.get(source.duplicateOf);
      const reusableUrl = primaryJob?.cdnUrl
        ?? (primaryBatch?.status === 'completed' && primaryBatch.target.currentUrl !== primaryBatch.sourceUrl
          ? primaryBatch.target.currentUrl
          : primaryBatch?.cdnUrl);
      if (reusableUrl) {
        item.status = 'mapped';
        item.cdnUrl = reusableUrl;
        item.reason = `复用相同源图 ${source.duplicateOf} 的英文 CDN 地址`;
        duplicateMappings.push({ id: item.id, cdnUrl: reusableUrl });
      } else if (primaryJob && ['deferred', 'quality_failed', 'failed'].includes(primaryJob.status)) {
        item.status = primaryJob.status === 'deferred' ? 'deferred' : 'failed';
        item.reason = `相同源图 ${source.duplicateOf} 未通过处理：${primaryJob.reason ?? primaryJob.status}`;
      }
    }
    if (duplicateMappings.length) updateImageBatch(repoRoot, job.scope, duplicateMappings);
    saveJob(repoRoot, job);

    const mapped = job.items.filter((item) => item.status === 'mapped' && item.cdnUrl);
    if (mapped.length) {
      event(repoRoot, job, 'verifying', `正在回写前验证 ${mapped.length} 条 CDN 图片地址`);
      await runPool(mapped, 8, async (item) => {
        if (!await verifyCdnUrl(item.cdnUrl ?? '')) {
          item.status = 'failed';
          item.reason = 'CDN 地址无法访问或内容类型不是图片，已阻止回写';
        }
      });
      const verified = mapped.filter((item) => item.status === 'mapped');
      if (verified.length) {
        event(repoRoot, job, 'applying', `正在预检并回写 ${verified.length} 张图片对应的英文 MDX`);
        const ids = verified.map((item) => item.id);
        const preview = applyImageBatch(repoRoot, job.scope, ids, true);
        for (const skipped of preview.skipped) {
          updateItem(job, skipped.id, { status: 'failed', reason: `MDX 预检失败：${skipped.reason}` });
        }
        const applicableIds = preview.appliedIds.filter((id) => !preview.skipped.some((item) => item.id === id));
        if (applicableIds.length) {
          copyBackups(repoRoot, job, preview.changedFiles);
          const applied = applyImageBatch(repoRoot, job.scope, applicableIds, false);
          job.changedFiles = applied.changedFiles;
          for (const id of applied.appliedIds) updateItem(job, id, { status: 'applied' });
        }
        saveJob(repoRoot, job);
      }
    }

    event(repoRoot, job, 'verifying', '正在验证 CDN 可访问性与最终任务状态');
    const applied = job.items.filter((item) => item.status === 'applied' && item.cdnUrl);
    await runPool(applied, 8, async (item) => {
      if (!await verifyCdnUrl(item.cdnUrl ?? '')) {
        item.status = 'failed';
        item.reason = 'CDN 地址无法访问或内容类型不是图片';
      }
    });
    job.currentItemId = undefined;
    job.finishedAt = new Date().toISOString();
    event(repoRoot, job, 'completed', `后台任务完成：回写 ${job.items.filter((item) => item.status === 'applied').length} 张，延后 ${job.items.filter((item) => item.status === 'deferred').length} 张，失败 ${job.items.filter((item) => ['quality_failed', 'failed'].includes(item.status)).length} 张`);
  } catch (error) {
    job.error = error instanceof Error ? error.message : '后台自动化任务失败';
    job.finishedAt = new Date().toISOString();
    event(repoRoot, job, 'failed', job.error);
  }
}

export function startImageAutomation(
  repoRoot: string,
  input: StartImageAutomationInput,
): ImageAutomationJob {
  const scope = input.scope.replace(/^\/+|\/+$/g, '');
  // scanImageBatch performs the product/path whitelist validation.
  scanImageBatch(repoRoot, scope);
  let job = input.force ? null : readImageAutomationJob(repoRoot, scope);
  if (!job || ['completed', 'failed', 'cancelled'].includes(job.stage)) job = emptyJob(scope);
  job.cancelRequested = false;
  saveJob(repoRoot, job);
  if (!running.has(scope)) {
    const promise = runJob(repoRoot, job, input).finally(() => running.delete(scope));
    running.set(scope, promise);
  }
  return job;
}

export function cancelImageAutomation(repoRoot: string, scope: string): ImageAutomationJob {
  const job = readImageAutomationJob(repoRoot, scope);
  if (!job) throw new Error('automation job not found');
  job.cancelRequested = true;
  job.message = '已请求取消，将在当前图片处理结束后停止';
  saveJob(repoRoot, job);
  return job;
}

export async function importImageAutomationMappings(
  repoRoot: string,
  scope: string,
  updates: Array<{ id: string; cdnUrl: string }>,
): Promise<ImageAutomationJob> {
  const job = readImageAutomationJob(repoRoot, scope);
  if (!job) throw new Error('automation job not found');
  if (!updates.length) throw new Error('CDN mapping updates are empty');
  const byId = new Map(job.items.map((item) => [item.id, item]));
  const seen = new Set<string>();
  for (const update of updates) {
    if (seen.has(update.id)) throw new Error(`duplicate image task id: ${update.id}`);
    seen.add(update.id);
    const item = byId.get(update.id);
    if (!item) throw new Error(`image task not found: ${update.id}`);
    if (!['quality_passed', 'mapped'].includes(item.status)) {
      throw new Error(`image task has not passed quality inspection: ${update.id}`);
    }
    let parsed: URL;
    try {
      parsed = new URL(update.cdnUrl);
    } catch {
      throw new Error(`invalid CDN URL for ${update.id}`);
    }
    if (parsed.protocol !== 'https:') throw new Error(`CDN URL must use HTTPS for ${update.id}`);
  }
  const invalid: string[] = [];
  await runPool(updates, 8, async (update) => {
    if (!await verifyCdnUrl(update.cdnUrl)) invalid.push(update.id);
  });
  if (invalid.length) throw new Error(`CDN verification failed for ${invalid.join(', ')}`);
  updateImageBatch(repoRoot, scope, updates);
  for (const update of updates) {
    updateItem(job, update.id, {
      status: 'mapped',
      cdnUrl: update.cdnUrl,
      reason: undefined,
    });
  }
  job.error = undefined;
  job.finishedAt = undefined;
  event(repoRoot, job, 'uploading', `已从登录浏览器导入并验证 ${updates.length} 条 CDN 映射`);
  return job;
}
