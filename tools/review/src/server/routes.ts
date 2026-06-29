import type { IncomingMessage, ServerResponse } from 'node:http';
import { listProductTabs, parseNavigation } from './nav-parse';
import { readMdx, resolveMdxPath, writeMdxAtomic } from './fs-safe';
import { parseMdxBlocks, validateMdxSyntax } from './mdx-parse';
import { parseFrontmatter } from '../shared/frontmatter';
import { deletePage } from './delete-page';
import { ALL_LANGS } from '../shared/types';
import type { FrontmatterMeta, Lang, NavNode, PageBundle, PageContent } from '../shared/types';

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

function parseLang(value: string | null, fallback: Lang): Lang {
  return value && ALL_LANGS.includes(value as Lang) ? (value as Lang) : fallback;
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

/** Read one language's mdx for a slug; null when the file is missing (untranslated). */
function readSide(repoRoot: string, lang: Lang, slug: string): PageContent | null {
  let content: string;
  try {
    content = readMdx(repoRoot, lang, slug);
  } catch {
    return null;
  }
  return {
    path: resolveMdxPath(repoRoot, lang, slug),
    content,
    blocks: parseMdxBlocks(content),
    frontmatter: toFrontmatterMeta(content),
  };
}

export async function handleProducts(repoRoot: string, res: ServerResponse): Promise<void> {
  try {
    json(res, { products: listProductTabs(repoRoot) });
  } catch (err) {
    fail(res, 500, err instanceof Error ? err.message : 'list products failed');
  }
}

export async function handleNav(repoRoot: string, req: IncomingMessage, res: ServerResponse): Promise<void> {
  try {
    const q = getQuery(req);
    const product = q.get('product');
    if (!product) return fail(res, 400, 'missing product');
    const left = parseLang(q.get('left'), 'zh');
    const right = parseLang(q.get('right'), 'en');
    json(res, { tree: parseNavigation(repoRoot, product, left, right) });
  } catch (err) {
    fail(res, 500, err instanceof Error ? err.message : 'nav parse failed');
  }
}

export async function handleGetPage(
  repoRoot: string,
  req: IncomingMessage,
  res: ServerResponse,
): Promise<void> {
  const q = getQuery(req);
  const slug = q.get('slug');
  if (!slug) return fail(res, 400, 'missing slug');
  const leftLang = parseLang(q.get('left'), 'zh');
  const rightLang = parseLang(q.get('right'), 'en');
  try {
    const bundle: PageBundle = {
      slug,
      leftLang,
      rightLang,
      left: readSide(repoRoot, leftLang, slug),
      right: readSide(repoRoot, rightLang, slug),
    };
    json(res, bundle);
  } catch (err) {
    fail(res, 400, err instanceof Error ? err.message : 'page read failed');
  }
}

interface AlignmentItem {
  slug: string;
  titleLeft?: string;
  titleRight?: string;
  leftCount: number;
  rightCount: number;
  diff: number;
  error?: string;
}

function collectNavMeta(tree: NavNode[]): {
  slugs: string[];
  titles: Map<string, { titleLeft?: string; titleRight?: string; missing?: boolean }>;
} {
  const slugs: string[] = [];
  const titles = new Map<string, { titleLeft?: string; titleRight?: string; missing?: boolean }>();
  const walk = (nodes: NavNode[]): void => {
    for (const n of nodes) {
      if (n.type === 'page') {
        slugs.push(n.slug);
        titles.set(n.slug, { titleLeft: n.titleLeft, titleRight: n.titleRight, missing: n.missing });
      } else {
        walk(n.children);
      }
    }
  };
  walk(tree);
  return { slugs, titles };
}

export async function handleAlignment(
  repoRoot: string,
  req: IncomingMessage,
  res: ServerResponse,
): Promise<void> {
  try {
    const q = getQuery(req);
    const product = q.get('product');
    if (!product) return fail(res, 400, 'missing product');
    const leftLang = parseLang(q.get('left'), 'zh');
    const rightLang = parseLang(q.get('right'), 'en');
    const tree = parseNavigation(repoRoot, product, leftLang, rightLang);
    const { slugs, titles } = collectNavMeta(tree);
    const items: AlignmentItem[] = [];
    for (const slug of slugs) {
      const meta = titles.get(slug) ?? {};
      try {
        const leftCount = parseMdxBlocks(readMdx(repoRoot, leftLang, slug)).length;
        const rightCount = parseMdxBlocks(readMdx(repoRoot, rightLang, slug)).length;
        items.push({
          slug,
          titleLeft: meta.titleLeft,
          titleRight: meta.titleRight,
          leftCount,
          rightCount,
          diff: leftCount - rightCount,
        });
      } catch (err) {
        items.push({
          slug,
          titleLeft: meta.titleLeft,
          titleRight: meta.titleRight,
          leftCount: 0,
          rightCount: 0,
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
    if (!lang || !ALL_LANGS.includes(lang as Lang)) return fail(res, 400, 'invalid lang');
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

export async function handleDeletePage(
  repoRoot: string,
  req: IncomingMessage,
  res: ServerResponse,
): Promise<void> {
  try {
    const body = JSON.parse(await readBody(req)) as { slug?: string };
    const slug = body.slug;
    if (!slug) return fail(res, 400, 'missing slug');
    const result = deletePage(repoRoot, slug);
    json(res, { ok: true, ...result });
  } catch (err) {
    fail(res, 500, err instanceof Error ? err.message : 'delete failed');
  }
}
