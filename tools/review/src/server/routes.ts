import type { IncomingMessage, ServerResponse } from 'node:http';
import { parseAITableNav } from './nav-parse';
import { readMdx, resolveMdxPath, writeMdxAtomic } from './fs-safe';
import { parseMdxBlocks, validateMdxSyntax } from './mdx-parse';
import { parseFrontmatter } from '../shared/frontmatter';
import type { FrontmatterMeta, Lang, PageBundle, PageContent } from '../shared/types';

const VALID_LANGS: Lang[] = ['en', 'zh', 'ja'];

function json(res: ServerResponse, data: unknown, status = 200): void {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify(data));
}

function fail(res: ServerResponse, status: number, message: string): void {
  json(res, { error: message }, status);
}

function getQuery(req: IncomingMessage): URLSearchParams {
  const url = new URL(req.url ?? '', 'http://localhost');
  return url.searchParams;
}

async function readBody(req: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  return Buffer.concat(chunks).toString('utf8');
}

function toFrontmatterMeta(content: string): FrontmatterMeta | null {
  const parsed = parseFrontmatter(content);
  if (!parsed) return null;
  return {
    title: parsed.title,
    description: parsed.description,
    rest: parsed.rest,
    raw: parsed.raw,
    startOffset: 0,
    endOffset: parsed.raw.length,
  };
}

function buildPageContent(repoRoot: string, lang: Lang, slug: string, content: string): PageContent {
  return {
    path: resolveMdxPath(repoRoot, lang, slug),
    content,
    blocks: parseMdxBlocks(content),
    frontmatter: toFrontmatterMeta(content),
  };
}

export async function handleNav(repoRoot: string, res: ServerResponse): Promise<void> {
  try {
    json(res, { tree: parseAITableNav(repoRoot) });
  } catch (err) {
    fail(res, 500, err instanceof Error ? err.message : 'nav parse failed');
  }
}

export async function handleGetPage(
  repoRoot: string,
  req: IncomingMessage,
  res: ServerResponse,
): Promise<void> {
  const slug = getQuery(req).get('slug');
  if (!slug) return fail(res, 400, 'missing slug');
  try {
    const enContent = readMdx(repoRoot, 'en', slug);
    const zhContent = readMdx(repoRoot, 'zh', slug);
    const bundle: PageBundle = {
      slug,
      en: buildPageContent(repoRoot, 'en', slug, enContent),
      zh: buildPageContent(repoRoot, 'zh', slug, zhContent),
    };
    json(res, bundle);
  } catch (err) {
    fail(res, 404, err instanceof Error ? err.message : 'page not found');
  }
}

export async function handlePostPage(
  repoRoot: string,
  req: IncomingMessage,
  res: ServerResponse,
): Promise<void> {
  try {
    const body = JSON.parse(await readBody(req)) as { slug?: string; lang?: string; content?: string };
    const { slug, lang, content } = body;
    if (!slug) return fail(res, 400, 'missing slug');
    if (!lang || !VALID_LANGS.includes(lang as Lang)) return fail(res, 400, 'invalid lang');
    if (typeof content !== 'string') return fail(res, 400, 'missing content');
    const check = validateMdxSyntax(content);
    if (!check.ok) {
      return fail(res, 422, `mdx syntax invalid: ${check.error}${check.line ? ` (line ${check.line})` : ''}`);
    }
    const path = writeMdxAtomic(repoRoot, lang as Lang, slug, content);
    json(res, { ok: true, path, bytes: Buffer.byteLength(content, 'utf8') });
  } catch (err) {
    fail(res, 500, err instanceof Error ? err.message : 'save failed');
  }
}
