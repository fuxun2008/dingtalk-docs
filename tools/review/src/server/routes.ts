import type { IncomingMessage, ServerResponse } from 'node:http';
import { parseAITableNav } from './nav-parse';
import { readMdx, resolveMdxPath, writeMdxAtomic } from './fs-safe';
import { parseMdxBlocks, validateMdxSyntax } from './mdx-parse';
import { parseFrontmatter } from '../shared/frontmatter';
import type { FrontmatterMeta, Lang, NavNode, PageBundle, PageContent } from '../shared/types';

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

interface AlignmentItem {
  slug: string;
  titleEn?: string;
  titleZh?: string;
  zhCount: number;
  enCount: number;
  diff: number;
  error?: string;
}

function collectNavMeta(tree: NavNode[]): { slugs: string[]; titles: Map<string, { titleEn?: string; titleZh?: string; missing?: boolean }> } {
  const slugs: string[] = [];
  const titles = new Map<string, { titleEn?: string; titleZh?: string; missing?: boolean }>();
  const walk = (nodes: NavNode[]): void => {
    for (const n of nodes) {
      if (n.type === 'page') {
        slugs.push(n.slug);
        titles.set(n.slug, { titleEn: n.titleEn, titleZh: n.titleZh, missing: n.missing });
      } else {
        walk(n.children);
      }
    }
  };
  walk(tree);
  return { slugs, titles };
}

export async function handleAlignment(repoRoot: string, res: ServerResponse): Promise<void> {
  try {
    const tree = parseAITableNav(repoRoot);
    const { slugs, titles } = collectNavMeta(tree);
    const items: AlignmentItem[] = [];
    for (const slug of slugs) {
      const meta = titles.get(slug) ?? {};
      if (meta.missing) {
        items.push({ slug, titleEn: meta.titleEn, titleZh: meta.titleZh, zhCount: 0, enCount: 0, diff: 0, error: 'en mdx 缺失' });
        continue;
      }
      try {
        const enCount = parseMdxBlocks(readMdx(repoRoot, 'en', slug)).length;
        const zhCount = parseMdxBlocks(readMdx(repoRoot, 'zh', slug)).length;
        items.push({ slug, titleEn: meta.titleEn, titleZh: meta.titleZh, zhCount, enCount, diff: zhCount - enCount });
      } catch (err) {
        items.push({
          slug,
          titleEn: meta.titleEn,
          titleZh: meta.titleZh,
          zhCount: 0,
          enCount: 0,
          diff: 0,
          error: err instanceof Error ? err.message : 'parse failed',
        });
      }
    }
    const mismatches = items.filter((i) => i.diff !== 0 || i.error);
    json(res, { total: items.length, mismatchCount: mismatches.length, mismatches });
  } catch (err) {
    fail(res, 500, err instanceof Error ? err.message : 'alignment scan failed');
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
