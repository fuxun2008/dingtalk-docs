import type { Block } from '../shared/types';

export type MediaKind = 'image' | 'video';
export type MediaFormat = 'markdown' | 'img' | 'video';

export interface ParsedMedia {
  kind: MediaKind;
  url: string;
  alt: string;
  format: MediaFormat;
  wrappedInFrame: boolean;
}

const MARKDOWN_IMAGE_RE = /^!\[([^\]]*)\]\(([^)]+)\)$/s;
const VIDEO_TAG_RE = /^<video\b[\s\S]*?(?:\/>|>[\s\S]*?<\/video>)$/i;
const IMG_TAG_RE = /^<img\b[\s\S]*?\/?>$/i;
const FRAME_RE = /^(<Frame\b[^>]*>)[\t ]*\n?([\s\S]*?)\n?[\t ]*(<\/Frame>)$/i;

function unquoteAttribute(value: string): string {
  return value.replace(/&quot;/g, '"').replace(/&amp;/g, '&');
}

function attribute(raw: string, name: string): string {
  const match = new RegExp(`\\b${name}\\s*=\\s*(["'])([\\s\\S]*?)\\1`, 'i').exec(raw);
  return match ? unquoteAttribute(match[2]) : '';
}

function parseBareMedia(raw: string): Omit<ParsedMedia, 'wrappedInFrame'> | null {
  const trimmed = raw.trim();
  const markdown = MARKDOWN_IMAGE_RE.exec(trimmed);
  if (markdown) {
    return {
      kind: 'image',
      url: markdown[2].trim(),
      alt: markdown[1],
      format: 'markdown',
    };
  }
  if (VIDEO_TAG_RE.test(trimmed)) {
    return { kind: 'video', url: attribute(trimmed, 'src'), alt: '', format: 'video' };
  }
  if (IMG_TAG_RE.test(trimmed)) {
    return {
      kind: 'image',
      url: attribute(trimmed, 'src'),
      alt: attribute(trimmed, 'alt'),
      format: 'img',
    };
  }
  return null;
}

/** Parse a standalone media block, including the common Mintlify <Frame> wrapper. */
export function parseMediaRaw(raw: string): ParsedMedia | null {
  const trimmed = raw.trim();
  const frame = FRAME_RE.exec(trimmed);
  const parsed = parseBareMedia(frame ? frame[2] : trimmed);
  if (!parsed || !parsed.url) return null;
  return { ...parsed, wrappedInFrame: !!frame };
}

function escapeMarkdownAlt(value: string): string {
  return value.replace(/[\[\]]/g, '');
}

function escapeAttribute(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;');
}

/** Build replacement MDX while retaining the existing media style and <Frame> wrapper. */
export function buildMediaRaw(kind: MediaKind, url: string, alt: string, templateRaw = ''): string {
  const cleanUrl = url.trim();
  const cleanAlt = alt.trim();
  const template = parseMediaRaw(templateRaw);
  const format: MediaFormat = kind === 'video'
    ? 'video'
    : template?.kind === 'image'
      ? template.format
      : 'markdown';

  let inner: string;
  if (kind === 'video') {
    inner = `<video src="${escapeAttribute(cleanUrl)}" controls width="100%"/>`;
  } else if (format === 'img') {
    inner = `<img src="${escapeAttribute(cleanUrl)}" alt="${escapeAttribute(cleanAlt)}"/>`;
  } else {
    inner = `![${escapeMarkdownAlt(cleanAlt)}](${cleanUrl})`;
  }

  const frame = FRAME_RE.exec(templateRaw.trim());
  if (!frame) return inner;
  return `${frame[1]}\n  ${inner}\n${frame[3]}`;
}

export function isMediaBlock(block: Block): boolean {
  return parseMediaRaw(block.raw) !== null;
}
