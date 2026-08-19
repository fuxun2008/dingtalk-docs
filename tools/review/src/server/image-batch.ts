import { createHash } from 'node:crypto';
import { execFile } from 'node:child_process';
import {
  existsSync,
  copyFileSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { promisify } from 'node:util';
import { basename, dirname, extname, join, relative, resolve, sep } from 'node:path';
import { computeAlignment, resolveMediaTarget } from '../lib/align-blocks';
import { buildMediaRaw, parseMediaRaw } from '../lib/media';
import type {
  BatchApplyResult,
  BatchImageItem,
  BatchImageJob,
  BatchImageStats,
  BatchMappingInput,
  BatchMediaKind,
} from '../shared/image-batch';
import type { Block, Lang } from '../shared/types';
import { deriveProductPrefixes, readMdx, resolveMdxPath, writeMdxAtomic } from './fs-safe';
import { parseMdxBlocks, validateMdxSyntax } from './mdx-parse';

const SCOPE_RE = /^[a-z0-9][a-z0-9._/-]*$/i;
const HTTP_URL_RE = /^https?:\/\/\S+$/i;
const MARKDOWN_IMAGE_RE = /!\[([^\]]*)\]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)/g;
const HTML_MEDIA_RE = /<(img|video|source)\b[\s\S]*?>/gi;
const ATTRIBUTE_RE = /\b(src|poster|alt)\s*=\s*(["'])([\s\S]*?)\2/gi;
const PRIVACY_HINT_RE = /(phone|mobile|email|token|secret|uid|user|member|account|qr|二维码|手机|邮箱|姓名|成员|账号|工号|人员)/i;
const COMPLEX_HINT_RE = /(dashboard|designer|report|workflow|api|notification|通知|报表|流程|设计器|接口)/i;
const execFileAsync = promisify(execFile);
const PREPARE_CONCURRENCY = 6;
const OCR_CHUNK_SIZE = 32;
const OCR_CONCURRENCY = 8;

interface OcrResult {
  path: string;
  texts: string[];
  qrCount: number;
  error?: string;
}

export interface ImageSafetyInspection {
  ok: boolean;
  findings: string[];
  textCount: number;
  qrCount: number;
}

interface MediaOccurrence {
  start: number;
  end: number;
  urlStart: number;
  urlEnd: number;
  url: string;
  alt: string;
  tag: 'image' | 'video';
  format: string;
  blockIndex: number;
  ordinalInBlock: number;
}

interface ScanContext {
  sourceContent: string;
  targetContent: string;
  sourceBlocks: Block[];
  targetBlocks: Block[];
  sourceOccurrences: MediaOccurrence[];
  targetOccurrences: MediaOccurrence[];
}

interface ApplyEdit {
  start: number;
  end: number;
  replacement: string;
  order: number;
  id: string;
}

export interface BatchOutputFile {
  path: string;
  filename: string;
  contentType: string;
  size: number;
}

function assertScope(repoRoot: string, scope: string): string {
  const clean = scope.replace(/^\/+|\/+$/g, '');
  if (!clean || clean.includes('..') || !SCOPE_RE.test(clean)) {
    throw new Error(`invalid scope: ${scope}`);
  }
  const product = clean.split('/', 1)[0].toLowerCase();
  if (!deriveProductPrefixes(repoRoot).has(product)) {
    throw new Error(`scope product is not in docs.json: ${product}`);
  }
  return clean;
}

function langRoot(repoRoot: string, lang: Lang, scope: string): string {
  return resolve(repoRoot, lang === 'en' ? scope : join(lang, scope));
}

function ensureInside(root: string, candidate: string): void {
  const prefix = root.endsWith(sep) ? root : root + sep;
  if (candidate !== root && !candidate.startsWith(prefix)) throw new Error(`path escapes root: ${candidate}`);
}

function listMdx(root: string): string[] {
  if (!existsSync(root) || !statSync(root).isDirectory()) return [];
  const out: string[] = [];
  const walk = (dir: string): void => {
    for (const name of readdirSync(dir)) {
      const full = join(dir, name);
      const stat = statSync(full);
      if (stat.isDirectory()) walk(full);
      else if (stat.isFile() && name.endsWith('.mdx')) out.push(full);
    }
  };
  walk(root);
  return out.sort();
}

function blockIndexAt(blocks: Block[], offset: number): number {
  return blocks.findIndex((block) => offset >= block.startOffset && offset < block.endOffset);
}

function extractHtmlAttributes(raw: string): Record<string, { value: string; start: number; end: number }> {
  const out: Record<string, { value: string; start: number; end: number }> = {};
  ATTRIBUTE_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = ATTRIBUTE_RE.exec(raw))) {
    const valueStart = match.index + match[0].indexOf(match[3]);
    out[match[1].toLowerCase()] = { value: match[3], start: valueStart, end: valueStart + match[3].length };
  }
  return out;
}

function extractMedia(content: string, blocks: Block[]): MediaOccurrence[] {
  const found: MediaOccurrence[] = [];
  MARKDOWN_IMAGE_RE.lastIndex = 0;
  let markdown: RegExpExecArray | null;
  while ((markdown = MARKDOWN_IMAGE_RE.exec(content))) {
    const url = markdown[2];
    const urlStart = markdown.index + markdown[0].indexOf(url);
    found.push({
      start: markdown.index,
      end: markdown.index + markdown[0].length,
      urlStart,
      urlEnd: urlStart + url.length,
      url,
      alt: markdown[1],
      tag: 'image',
      format: 'markdown',
      blockIndex: -1,
      ordinalInBlock: 0,
    });
  }

  HTML_MEDIA_RE.lastIndex = 0;
  let html: RegExpExecArray | null;
  while ((html = HTML_MEDIA_RE.exec(content))) {
    const attrs = extractHtmlAttributes(html[0]);
    const tagName = html[1].toLowerCase();
    const primary = attrs.src;
    if (primary) {
      found.push({
        start: html.index,
        end: html.index + html[0].length,
        urlStart: html.index + primary.start,
        urlEnd: html.index + primary.end,
        url: primary.value,
        alt: attrs.alt?.value ?? '',
        tag: tagName === 'img' ? 'image' : 'video',
        format: tagName,
        blockIndex: -1,
        ordinalInBlock: 0,
      });
    }
    if (tagName === 'video' && attrs.poster) {
      found.push({
        start: html.index,
        end: html.index + html[0].length,
        urlStart: html.index + attrs.poster.start,
        urlEnd: html.index + attrs.poster.end,
        url: attrs.poster.value,
        alt: 'Video poster',
        tag: 'image',
        format: 'poster',
        blockIndex: -1,
        ordinalInBlock: 0,
      });
    }
  }

  found.sort((a, b) => a.start - b.start || a.urlStart - b.urlStart);
  const ordinals = new Map<number, number>();
  for (const item of found) {
    item.blockIndex = blockIndexAt(blocks, item.start);
    const ordinal = ordinals.get(item.blockIndex) ?? 0;
    item.ordinalInBlock = ordinal;
    ordinals.set(item.blockIndex, ordinal + 1);
  }
  return found;
}

function extensionFromUrl(url: string): string {
  try {
    return extname(new URL(url, 'http://local').pathname).toLowerCase().replace(/^\./, '');
  } catch {
    return extname(url.split(/[?#]/, 1)[0]).toLowerCase().replace(/^\./, '');
  }
}

function mediaKind(tag: 'image' | 'video', format: string): BatchMediaKind {
  if (tag === 'video' || ['mp4', 'webm', 'mov', 'm4v'].includes(format)) return 'video';
  if (format === 'gif') return 'gif';
  if (format === 'svg') return 'svg';
  if (['png', 'jpg', 'jpeg', 'webp', 'avif'].includes(format)) return 'raster';
  return 'unknown';
}

function stableId(slug: string, occurrence: MediaOccurrence): string {
  return createHash('sha1')
    .update(`${slug}\n${occurrence.url}\n${occurrence.start}`)
    .digest('hex')
    .slice(0, 14);
}

function jobKey(scope: string, sourceLang: Lang, targetLang: Lang): string {
  return `${scope.replace(/[^a-z0-9]+/gi, '-')}-${sourceLang}-${targetLang}`.replace(/^-|-$/g, '');
}

function statePath(repoRoot: string, key: string): string {
  return join(repoRoot, 'tools', 'review', '.cache', 'image-batches', `${key}.json`);
}

function loadStoredItems(repoRoot: string, key: string): Map<string, BatchImageItem> {
  const file = statePath(repoRoot, key);
  if (!existsSync(file)) return new Map();
  try {
    const parsed = JSON.parse(readFileSync(file, 'utf8')) as BatchImageJob;
    return new Map(parsed.items.map((item) => [item.id, item]));
  } catch {
    return new Map();
  }
}

function outputCandidates(repoRoot: string, sourceUrl: string, kind: BatchMediaKind): string[] {
  const sourceName = basename(new URL(sourceUrl, 'http://local').pathname);
  const stem = sourceName.replace(/\.[^.]+$/, '');
  const timestamp = stem.split('-', 1)[0];
  const extension = kind === 'gif' ? 'gif' : kind === 'svg' ? 'svg' : 'png';
  const base = join(repoRoot, 'tools', 'review', 'output', 'image-localization');
  return [join(base, `${stem}-en.${extension}`), join(base, `${timestamp}-en.${extension}`)];
}

function findLocalOutput(repoRoot: string, sourceUrl: string, kind: BatchMediaKind): string | undefined {
  return outputCandidates(repoRoot, sourceUrl, kind).find((candidate) => existsSync(candidate));
}

function buildPrompt(item: {
  sourceUrl: string;
  sourceAlt: string;
  mediaKind: BatchMediaKind;
  localOutput?: string;
}): string {
  const formatInstruction = item.mediaKind === 'gif'
    ? '这是 GIF 动图：保持原尺寸、帧顺序、帧率和循环方式；对去重后的关键帧进行一致的文字替换，避免闪烁。'
    : item.mediaKind === 'svg'
      ? '这是 SVG：优先翻译可编辑的 text/tspan 节点；路径化文字或嵌入位图再按图像方式处理，并保持 viewBox。'
      : '保持原图尺寸、布局、颜色、图标和交互状态，只替换图中可见的中文文字。';
  return [
    '将该宜搭中文产品媒体转换为英文版。',
    formatInstruction,
    '英文文案必须符合宜搭产品术语。',
    '发现手机号、邮箱、姓名、企业账号、token、二维码、UID、内部 URL 等信息时，不要跳过：替换成明确的无效测试数据、通用头像或遮挡内容。',
    '生成后再次检查中文残留和敏感信息；不得自行编造真实姓名或邮箱。',
    `原始媒体：${item.sourceUrl}`,
    item.sourceAlt ? `原始 alt：${item.sourceAlt}` : '',
    item.localOutput ? `可复用的本地输出：${item.localOutput}` : '',
  ].filter(Boolean).join('\n');
}

function stats(items: BatchImageItem[]): BatchImageStats {
  const byKind: Record<BatchMediaKind, number> = { raster: 0, gif: 0, svg: 0, video: 0, unknown: 0 };
  for (const item of items) byKind[item.mediaKind]++;
  return {
    total: items.length,
    pending: items.filter((item) => item.status === 'pending').length,
    prepared: items.filter((item) => item.status === 'prepared').length,
    generated: items.filter((item) => item.status === 'generated').length,
    mapped: items.filter((item) => item.status === 'mapped').length,
    completed: items.filter((item) => item.status === 'completed').length,
    skipped: items.filter((item) => item.status === 'skipped').length,
    needsReview: items.filter((item) => item.status === 'needs_review').length,
    duplicates: items.filter((item) => item.duplicateOf).length,
    byKind,
  };
}

function saveJob(repoRoot: string, job: BatchImageJob): void {
  const file = statePath(repoRoot, job.key);
  mkdirSync(dirname(file), { recursive: true });
  job.updatedAt = new Date().toISOString();
  job.stats = stats(job.items);
  writeFileSync(file, JSON.stringify(job, null, 2) + '\n', 'utf8');
}

function locateTarget(
  sourceOccurrence: MediaOccurrence,
  context: ScanContext,
): { mode: 'replace'; occurrence: MediaOccurrence } | { mode: 'insert'; afterBlockIndex: number | null } {
  const alignment = computeAlignment(context.sourceBlocks, context.targetBlocks);
  const sourceBlock = context.sourceBlocks[sourceOccurrence.blockIndex];
  if (sourceBlock && parseMediaRaw(sourceBlock.raw)) {
    const target = resolveMediaTarget(
      sourceOccurrence.blockIndex,
      context.sourceBlocks,
      context.targetBlocks,
      alignment.leftToRight,
    );
    if (target.mode === 'replace') {
      const occurrence = context.targetOccurrences.find((item) => item.blockIndex === target.blockIndex);
      if (occurrence) return { mode: 'replace', occurrence };
    }
    return { mode: 'insert', afterBlockIndex: target.mode === 'insert' ? target.afterBlockIndex : target.blockIndex };
  }

  const targetBlockIndex = alignment.leftToRight.get(sourceOccurrence.blockIndex);
  if (targetBlockIndex !== undefined) {
    let nextTargetBlock = context.targetBlocks.length;
    for (let sourceIndex = sourceOccurrence.blockIndex + 1; sourceIndex < context.sourceBlocks.length; sourceIndex++) {
      const peer = alignment.leftToRight.get(sourceIndex);
      if (peer !== undefined) {
        nextTargetBlock = peer;
        break;
      }
    }
    // Inline images are commonly embedded in one Chinese list block while the
    // English images are standalone <Frame> blocks immediately after the
    // translated list. Match all media in that structural interval by order.
    const peers = context.targetOccurrences.filter(
      (item) => item.blockIndex >= targetBlockIndex && item.blockIndex < nextTargetBlock,
    );
    const occurrence = peers[sourceOccurrence.ordinalInBlock];
    if (occurrence) return { mode: 'replace', occurrence };
    return { mode: 'insert', afterBlockIndex: targetBlockIndex };
  }

  let previousTarget: number | null = null;
  for (let index = sourceOccurrence.blockIndex - 1; index >= 0; index--) {
    const peer = alignment.leftToRight.get(index);
    if (peer !== undefined) {
      previousTarget = peer;
      break;
    }
  }
  return { mode: 'insert', afterBlockIndex: previousTarget };
}

function scanFile(repoRoot: string, slug: string): { context: ScanContext; items: BatchImageItem[] } | null {
  let sourceContent: string;
  let targetContent: string;
  try {
    sourceContent = readMdx(repoRoot, 'zh', slug);
    targetContent = readMdx(repoRoot, 'en', slug);
  } catch {
    return null;
  }
  const sourceBlocks = parseMdxBlocks(sourceContent);
  const targetBlocks = parseMdxBlocks(targetContent);
  const context: ScanContext = {
    sourceContent,
    targetContent,
    sourceBlocks,
    targetBlocks,
    sourceOccurrences: extractMedia(sourceContent, sourceBlocks),
    targetOccurrences: extractMedia(targetContent, targetBlocks),
  };
  const items = context.sourceOccurrences.map((occurrence, order) => {
    const format = extensionFromUrl(occurrence.url);
    const kind = mediaKind(occurrence.tag, format);
    const target = locateTarget(occurrence, context);
    const localOutput = findLocalOutput(repoRoot, occurrence.url, kind);
    const complexityReasons: string[] = [];
    if (kind === 'gif') complexityReasons.push('animated');
    if (kind === 'svg') complexityReasons.push('vector');
    if (COMPLEX_HINT_RE.test(`${occurrence.alt} ${occurrence.url}`)) complexityReasons.push('dense-ui');
    const privacyReview = kind !== 'video' && (PRIVACY_HINT_RE.test(`${occurrence.alt} ${occurrence.url}`) || kind !== 'svg');
    const targetUrl = target.mode === 'replace' ? target.occurrence.url : undefined;
    const base = {
      sourceUrl: occurrence.url,
      sourceAlt: occurrence.alt,
      mediaKind: kind,
      localOutput,
    };
    const status = kind === 'video'
      ? 'skipped'
      : targetUrl && targetUrl !== occurrence.url
        ? 'completed'
        : localOutput
          ? 'generated'
          : 'pending';
    const item: BatchImageItem = {
      id: stableId(slug, occurrence),
      order,
      slug,
      sourceUrl: occurrence.url,
      sourceAlt: occurrence.alt,
      sourceFormat: format || occurrence.format,
      mediaKind: kind,
      target: { mode: target.mode, currentUrl: targetUrl },
      status,
      privacyReview,
      complexityReasons,
      prompt: buildPrompt(base),
      localOutput,
    };
    return item;
  });
  return { context, items };
}

export function scanImageBatch(
  repoRoot: string,
  scopeInput: string,
  sourceLang: Lang = 'zh',
  targetLang: Lang = 'en',
): BatchImageJob {
  if (sourceLang !== 'zh' || targetLang !== 'en') throw new Error('image batch currently supports zh → en only');
  const scope = assertScope(repoRoot, scopeInput);
  const root = langRoot(repoRoot, sourceLang, scope);
  ensureInside(repoRoot, root);
  const key = jobKey(scope, sourceLang, targetLang);
  const stored = loadStoredItems(repoRoot, key);
  const items: BatchImageItem[] = [];
  let globalOrder = 0;
  for (const file of listMdx(root)) {
    const slug = relative(join(repoRoot, sourceLang), file).replace(/\.mdx$/, '').split(sep).join('/');
    const scanned = scanFile(repoRoot, slug);
    if (!scanned) continue;
    for (const item of scanned.items) {
      item.order = globalOrder++;
      const previous = stored.get(item.id);
      if (previous) {
        item.cdnUrl = previous.cdnUrl;
        item.englishAlt = previous.englishAlt;
        item.note = previous.note;
        item.prepared = previous.prepared;
        item.sourceHash = previous.sourceHash;
        item.localOutput = previous.localOutput ?? item.localOutput;
        if (item.status !== 'completed' && previous.status !== 'pending' && previous.status !== 'completed') {
          item.status = previous.status;
        }
        if (item.cdnUrl && item.status !== 'completed') item.status = 'mapped';
        const preservedOutput = item.localOutput && existsSync(item.localOutput)
          ? item.localOutput
          : item.prepared?.outputPath;
        if (item.status !== 'completed' && preservedOutput && existsSync(preservedOutput)) {
          item.localOutput = preservedOutput;
          if (previous.status !== 'needs_review') {
            item.status = item.cdnUrl ? 'mapped' : 'generated';
          }
        }
      }
      items.push(item);
    }
  }
  const firstBySource = new Map<string, string>();
  const firstByHash = new Map<string, string>();
  for (const item of items) {
    const first = firstBySource.get(item.sourceUrl);
    if (first) item.duplicateOf = first;
    else firstBySource.set(item.sourceUrl, item.id);
    if (item.sourceHash) {
      const hashFirst = firstByHash.get(item.sourceHash);
      if (hashFirst) item.duplicateOf = hashFirst;
      else firstByHash.set(item.sourceHash, item.id);
    }
  }
  const now = new Date().toISOString();
  const job: BatchImageJob = {
    version: 2,
    key,
    scope,
    sourceLang,
    targetLang,
    createdAt: now,
    updatedAt: now,
    items,
    stats: stats(items),
  };
  saveJob(repoRoot, job);
  return job;
}

export function updateImageBatch(
  repoRoot: string,
  scope: string,
  updates: BatchMappingInput[],
): BatchImageJob {
  const job = scanImageBatch(repoRoot, scope);
  const byId = new Map(job.items.map((item) => [item.id, item]));
  for (const update of updates) {
    const item = byId.get(update.id);
    if (!item) continue;
    if (update.cdnUrl !== undefined) {
      if (update.cdnUrl && !HTTP_URL_RE.test(update.cdnUrl)) throw new Error(`invalid CDN URL for ${update.id}`);
      item.cdnUrl = update.cdnUrl.trim() || undefined;
    }
    if (update.englishAlt !== undefined) item.englishAlt = update.englishAlt.trim();
    if (update.localOutput !== undefined) item.localOutput = update.localOutput.trim() || undefined;
    if (update.note !== undefined) item.note = update.note.trim() || undefined;
    if (update.status !== undefined) item.status = update.status;
    if (item.cdnUrl && item.status !== 'completed') item.status = 'mapped';
  }
  const mappedById = new Map(job.items.map((item) => [item.id, item]));
  for (const item of job.items) {
    if (!item.duplicateOf || item.cdnUrl) continue;
    const original = mappedById.get(item.duplicateOf);
    if (!original?.cdnUrl) continue;
    item.cdnUrl = original.cdnUrl;
    item.englishAlt = item.englishAlt || original.englishAlt;
    if (item.status !== 'completed') item.status = 'mapped';
  }
  saveJob(repoRoot, job);
  return job;
}

export function resolveImageBatchOutput(repoRoot: string, scope: string, id: string): BatchOutputFile {
  if (!/^[a-f0-9]{14}$/i.test(id)) throw new Error('invalid image task id');
  const job = scanImageBatch(repoRoot, scope);
  const item = job.items.find((candidate) => candidate.id === id);
  if (!item) throw new Error(`image task not found: ${id}`);
  if (item.status === 'needs_review' || item.privacyFindings?.length) {
    throw new Error(`image task requires review before upload: ${id}`);
  }
  const candidate = item.localOutput ?? item.prepared?.outputPath;
  if (!candidate) throw new Error(`generated output missing: ${id}`);
  const path = resolve(candidate);
  const generatedRoot = resolve(repoRoot, 'tools', 'review', 'output', 'image-batch', job.key, 'generated');
  if (path !== generatedRoot && !path.startsWith(generatedRoot + sep)) throw new Error('output path escapes generated directory');
  if (!existsSync(path) || !statSync(path).isFile()) throw new Error(`generated output not found: ${id}`);
  const extension = extname(path).toLowerCase();
  const contentTypes: Record<string, string> = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
  };
  const contentType = contentTypes[extension];
  if (!contentType) throw new Error(`unsupported generated media format: ${extension}`);
  return { path, filename: basename(path), contentType, size: statSync(path).size };
}

async function download(repoRoot: string, url: string, target: string): Promise<void> {
  if (!/^https?:\/\//i.test(url)) {
    const local = resolve(repoRoot, `.${url.startsWith('/') ? url : `/${url}`}`);
    ensureInside(repoRoot, local);
    if (!existsSync(local) || !statSync(local).isFile()) throw new Error(`local media not found: ${url}`);
    mkdirSync(dirname(target), { recursive: true });
    copyFileSync(local, target);
    return;
  }
  const response = await fetch(url, { redirect: 'follow' });
  if (!response.ok) throw new Error(`download failed ${response.status}: ${url}`);
  const bytes = Buffer.from(await response.arrayBuffer());
  mkdirSync(dirname(target), { recursive: true });
  writeFileSync(target, bytes);
}

function extractSvgTexts(path: string): string[] {
  const raw = readFileSync(path, 'utf8');
  const texts: string[] = [];
  for (const match of raw.matchAll(/<(?:text|tspan)\b[^>]*>([\s\S]*?)<\/(?:text|tspan)>/gi)) {
    const text = match[1].replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').trim();
    if (text) texts.push(text);
  }
  return [...new Set(texts)];
}

function sensitiveFindings(texts: string[], qrCount: number): string[] {
  const text = texts.join('\n');
  const textWithoutSafeUrls = text.replace(/https?:\/\/(?:example\.(?:com|invalid)|localhost)\b\S*/gi, '');
  const textWithoutSafePlaceholders = textWithoutSafeUrls
    .replace(/\b(?:test|user)@example\.com\b/gi, '')
    .replace(/\b(?:token|access[_ -]?key|secret|authorization)\s*[:=]\s*(?:TEST_VALUE|REDACTED)\b/gi, '')
    .replace(/\b(?:uid|user[_ -]?id|account[_ -]?id)\s*[:=]\s*(?:TEST_ID|REDACTED)\b/gi, '');
  const findings = new Set<string>();
  if (/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/i.test(textWithoutSafePlaceholders)) findings.add('email');
  if (/(?:^|\D)1[3-9]\d{9}(?:\D|$)/.test(textWithoutSafePlaceholders)) findings.add('phone');
  if (/\b(?:token|access[_ -]?key|secret|authorization)\s*[:=]\s*\S{4,}|\bbearer\s+\S{4,}/i.test(textWithoutSafePlaceholders)) findings.add('token');
  if (/\b(?:uid|user[_ -]?id|account[_ -]?id)\s*[:=]\s*\S{2,}|(?:工号|账号)\s*[:：=]\s*\S{2,}/i.test(textWithoutSafePlaceholders)) findings.add('uid/account');
  if (/https?:\/\//i.test(textWithoutSafeUrls)) findings.add('url');
  if (/[\u3400-\u9fff]/u.test(text)) findings.add('chinese-text');
  if (qrCount > 0) findings.add('qr-code');
  return [...findings];
}

async function runOcr(repoRoot: string, paths: string[]): Promise<Map<string, OcrResult>> {
  const unique = [...new Set(paths.filter((path) => existsSync(path)))];
  const out = new Map<string, OcrResult>();
  const script = join(repoRoot, 'tools', 'review', 'scripts', 'ocr-sensitive.swift');
  const binary = join(repoRoot, 'tools', 'review', '.cache', 'bin', 'ocr-sensitive');
  try {
    if (!existsSync(binary) || statSync(binary).mtimeMs < statSync(script).mtimeMs) {
      mkdirSync(dirname(binary), { recursive: true });
      await execFileAsync('swiftc', ['-O', script, '-o', binary], { maxBuffer: 16 * 1024 * 1024 });
    }
  } catch {
    return out;
  }
  const chunks = Array.from(
    { length: Math.ceil(unique.length / OCR_CHUNK_SIZE) },
    (_, index) => unique.slice(index * OCR_CHUNK_SIZE, (index + 1) * OCR_CHUNK_SIZE),
  );
  let cursor = 0;
  const worker = async (): Promise<void> => {
    while (cursor < chunks.length) {
      const chunk = chunks[cursor++];
      try {
        const { stdout } = await execFileAsync(binary, chunk, { maxBuffer: 16 * 1024 * 1024 });
        const parsed = JSON.parse(stdout) as OcrResult[];
        for (const result of parsed) out.set(result.path, result);
      } catch {
        // OCR is a safety enhancement. Preparation remains usable on non-macOS
        // environments, but the item stays flagged for privacy review.
      }
    }
  };
  await Promise.all(Array.from({ length: Math.min(OCR_CONCURRENCY, chunks.length) }, () => worker()));
  return out;
}

export async function inspectImageSafety(repoRoot: string, path: string): Promise<ImageSafetyInspection> {
  return (await inspectImagesSafety(repoRoot, [path])).get(path)
    ?? { ok: false, findings: ['ocr-unavailable'], textCount: 0, qrCount: 0 };
}

export async function inspectImagesSafety(
  repoRoot: string,
  paths: string[],
): Promise<Map<string, ImageSafetyInspection>> {
  const results = await runOcr(repoRoot, paths);
  const inspections = new Map<string, ImageSafetyInspection>();
  for (const path of paths) {
    const result = results.get(path);
    if (!result || result.error) {
      inspections.set(path, { ok: false, findings: ['ocr-unavailable'], textCount: 0, qrCount: 0 });
      continue;
    }
    const findings = sensitiveFindings(result.texts, result.qrCount);
    inspections.set(path, {
      ok: findings.length === 0,
      findings,
      textCount: result.texts.length,
      qrCount: result.qrCount,
    });
  }
  return inspections;
}

export async function prepareImageBatch(
  repoRoot: string,
  scope: string,
  ids: string[],
): Promise<BatchImageJob> {
  const job = scanImageBatch(repoRoot, scope);
  const selected = new Set(ids);
  const base = join(repoRoot, 'tools', 'review', 'output', 'image-batch', job.key);
  const work = job.items.filter(
    (item) => selected.has(item.id) && item.status !== 'completed' && item.mediaKind !== 'video',
  );
  let cursor = 0;
  const worker = async (): Promise<void> => {
    while (cursor < work.length) {
      const item = work[cursor++];
    try {
      const extension = item.sourceFormat || (item.mediaKind === 'svg' ? 'svg' : item.mediaKind === 'gif' ? 'gif' : 'png');
      const sourcePath = join(base, 'source', `${item.id}.${extension}`);
      if (!existsSync(sourcePath)) await download(repoRoot, item.sourceUrl, sourcePath);
      item.sourceHash = createHash('sha256').update(readFileSync(sourcePath)).digest('hex');
      const outputExtension = item.mediaKind === 'gif' ? 'gif' : item.mediaKind === 'svg' ? 'svg' : 'png';
      const outputPath = join(base, 'generated', `${item.id}-en.${outputExtension}`);
      const prepared = { sourcePath, outputPath } as NonNullable<BatchImageItem['prepared']>;
      if (item.mediaKind === 'gif') {
        const frameDir = join(base, 'frames', item.id);
        mkdirSync(frameDir, { recursive: true });
        const pattern = join(frameDir, '%03d.png');
        await execFileAsync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', sourcePath, '-vf', 'fps=2', '-frames:v', '40', pattern]);
        prepared.framePaths = readdirSync(frameDir).filter((name) => name.endsWith('.png')).sort().map((name) => join(frameDir, name));
      } else if (item.mediaKind === 'svg') {
        prepared.svgTexts = extractSvgTexts(sourcePath);
      }
      item.prepared = prepared;
      if (existsSync(outputPath)) item.localOutput = outputPath;
      item.status = item.localOutput ? 'generated' : 'prepared';
      item.prompt = buildPrompt({ ...item, localOutput: item.localOutput ?? outputPath });
    } catch (error) {
      item.status = 'needs_review';
      item.note = error instanceof Error ? error.message : 'prepare failed';
    }
    }
  };
  await Promise.all(Array.from({ length: Math.min(PREPARE_CONCURRENCY, work.length) }, () => worker()));

  const ocrPaths: string[] = [];
  for (const item of work) {
    if (!item.prepared) continue;
    if (item.localOutput && existsSync(item.localOutput) && item.mediaKind !== 'svg') {
      ocrPaths.push(item.localOutput);
    } else if (item.mediaKind === 'raster') {
      ocrPaths.push(item.prepared.sourcePath);
    } else if (item.mediaKind === 'gif') {
      ocrPaths.push(...(item.prepared.framePaths ?? []).slice(0, 8));
    }
  }
  const ocr = await runOcr(repoRoot, ocrPaths);
  for (const item of work) {
    if (!item.prepared) continue;
    const paths = item.localOutput && existsSync(item.localOutput)
      ? [item.localOutput]
      : item.mediaKind === 'gif'
        ? (item.prepared.framePaths ?? []).slice(0, 8)
        : item.mediaKind === 'raster'
          ? [item.prepared.sourcePath]
          : [];
    const texts: string[] = [];
    let qrCount = 0;
    for (const path of paths) {
      const result = ocr.get(path);
      if (!result) continue;
      texts.push(...result.texts);
      qrCount += result.qrCount;
    }
    if (item.mediaKind === 'svg') texts.push(...(item.prepared.svgTexts ?? []));
    item.privacyFindings = sensitiveFindings(texts, qrCount);
    item.privacyReview = item.privacyReview || item.privacyFindings.length > 0;
    if (item.localOutput && item.privacyFindings.length > 0) {
      item.status = 'needs_review';
      item.note = `英文输出仍检测到：${item.privacyFindings.join(', ')}`;
    }
    if (item.privacyFindings.length > 0) {
      item.prompt += `\nOCR/二维码预检命中风险类型：${item.privacyFindings.join(', ')}。必须替换或遮挡后再输出。`;
    }
  }

  const firstByHash = new Map<string, BatchImageItem>();
  for (const item of job.items) {
    if (!item.sourceHash) continue;
    const first = firstByHash.get(item.sourceHash);
    if (!first) firstByHash.set(item.sourceHash, item);
    else item.duplicateOf = first.id;
  }
  saveJob(repoRoot, job);
  return job;
}

function freshContext(repoRoot: string, slug: string): ScanContext {
  const sourceContent = readMdx(repoRoot, 'zh', slug);
  const targetContent = readMdx(repoRoot, 'en', slug);
  const sourceBlocks = parseMdxBlocks(sourceContent);
  const targetBlocks = parseMdxBlocks(targetContent);
  return {
    sourceContent,
    targetContent,
    sourceBlocks,
    targetBlocks,
    sourceOccurrences: extractMedia(sourceContent, sourceBlocks),
    targetOccurrences: extractMedia(targetContent, targetBlocks),
  };
}

export function applyImageBatch(repoRoot: string, scope: string, ids: string[], dryRun = false): BatchApplyResult {
  const key = jobKey(scope, 'zh', 'en');
  const cacheFile = statePath(repoRoot, key);
  const job = existsSync(cacheFile)
    ? JSON.parse(readFileSync(cacheFile, 'utf8')) as BatchImageJob
    : scanImageBatch(repoRoot, scope);
  const selected = new Set(ids);
  const result: BatchApplyResult = { dryRun, changedFiles: [], appliedIds: [], skipped: [] };
  const bySlug = new Map<string, BatchImageItem[]>();
  for (const item of job.items) {
    if (!selected.has(item.id)) continue;
    if (!item.cdnUrl) {
      result.skipped.push({ id: item.id, reason: 'missing CDN URL' });
      continue;
    }
    const current = bySlug.get(item.slug) ?? [];
    current.push(item);
    bySlug.set(item.slug, current);
  }

  for (const [slug, items] of bySlug) {
    const context = freshContext(repoRoot, slug);
    const sourceById = new Map(context.sourceOccurrences.map((occurrence) => [stableId(slug, occurrence), occurrence]));
    const edits: ApplyEdit[] = [];
    for (const item of items) {
      const sourceOccurrence = sourceById.get(item.id);
      if (!sourceOccurrence) {
        result.skipped.push({ id: item.id, reason: 'source occurrence changed; rescan required' });
        continue;
      }
      const target = locateTarget(sourceOccurrence, context);
      if (target.mode === 'replace') {
        edits.push({
          start: target.occurrence.urlStart,
          end: target.occurrence.urlEnd,
          replacement: item.cdnUrl ?? '',
          order: item.order,
          id: item.id,
        });
      } else {
        const anchorEnd = target.afterBlockIndex === null
          ? context.targetBlocks[0]?.endOffset ?? 0
          : context.targetBlocks[target.afterBlockIndex]?.endOffset;
        if (anchorEnd === undefined) {
          result.skipped.push({ id: item.id, reason: 'target anchor not found' });
          continue;
        }
        const sourceBlock = context.sourceBlocks[sourceOccurrence.blockIndex];
        const raw = buildMediaRaw('image', item.cdnUrl ?? '', item.englishAlt ?? '', sourceBlock?.raw ?? '');
        edits.push({ start: anchorEnd, end: anchorEnd, replacement: `\n\n${raw}\n`, order: item.order, id: item.id });
      }
    }
    edits.sort((left, right) => right.start - left.start || right.order - left.order);
    let next = context.targetContent;
    for (const edit of edits) next = next.slice(0, edit.start) + edit.replacement + next.slice(edit.end);
    const validation = validateMdxSyntax(next);
    if (!validation.ok) throw new Error(`batch apply produced invalid MDX for ${slug}: ${validation.error}`);
    if (next !== context.targetContent) {
      const path = dryRun ? resolveMdxPath(repoRoot, 'en', slug) : writeMdxAtomic(repoRoot, 'en', slug, next);
      result.changedFiles.push(path);
      result.appliedIds.push(...edits.map((edit) => edit.id));
    }
  }

  for (const item of job.items) {
    if (!dryRun && result.appliedIds.includes(item.id)) item.status = 'completed';
  }
  if (!dryRun) saveJob(repoRoot, job);
  return result;
}

export function preflightImageBatchTargets(repoRoot: string, scope: string, ids: string[]): BatchApplyResult {
  const job = scanImageBatch(repoRoot, scope);
  const selected = new Set(ids);
  const result: BatchApplyResult = { dryRun: true, changedFiles: [], appliedIds: [], skipped: [] };
  const bySlug = new Map<string, BatchImageItem[]>();
  for (const item of job.items) {
    if (!selected.has(item.id)) continue;
    const current = bySlug.get(item.slug) ?? [];
    current.push(item);
    bySlug.set(item.slug, current);
  }
  for (const [slug, items] of bySlug) {
    const context = freshContext(repoRoot, slug);
    const sourceById = new Map(context.sourceOccurrences.map((occurrence) => [stableId(slug, occurrence), occurrence]));
    for (const item of items) {
      const sourceOccurrence = sourceById.get(item.id);
      if (!sourceOccurrence) {
        result.skipped.push({ id: item.id, reason: 'source occurrence changed; rescan required' });
        continue;
      }
      const target = locateTarget(sourceOccurrence, context);
      if (target.mode === 'insert') {
        const anchorEnd = target.afterBlockIndex === null
          ? context.targetBlocks[0]?.endOffset ?? 0
          : context.targetBlocks[target.afterBlockIndex]?.endOffset;
        if (anchorEnd === undefined) {
          result.skipped.push({ id: item.id, reason: 'target anchor not found' });
          continue;
        }
      }
      result.appliedIds.push(item.id);
    }
  }
  return result;
}
