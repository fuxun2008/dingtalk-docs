import { readFileSync, renameSync, writeFileSync, existsSync, unlinkSync } from 'node:fs';
import { join, normalize, sep } from 'node:path';
import type { Lang } from '../shared/types';

/** Slug body charset (after the product prefix). */
const SLUG_BODY_PATTERN = /^[a-z0-9._\-/]+$/i;

interface DocsJsonNode {
  pages?: Array<string | DocsJsonNode>;
  tabs?: DocsJsonNode[];
  products?: DocsJsonNode[];
  groups?: DocsJsonNode[];
}
interface DocsJsonRoot {
  navigation?: { languages?: Array<{ language: string; products?: DocsJsonNode[] }> };
}

const prefixCache = new Map<string, Set<string>>();

/** Allowed product prefixes = first path segment of every page slug in docs.json (en block). */
export function deriveProductPrefixes(repoRoot: string): Set<string> {
  const cached = prefixCache.get(repoRoot);
  if (cached) return cached;
  const docs: DocsJsonRoot = JSON.parse(readFileSync(join(repoRoot, 'docs.json'), 'utf8'));
  const en = docs.navigation?.languages?.find((l) => l.language === 'en');
  const prefixes = new Set<string>();
  const walk = (nodes: Array<string | DocsJsonNode> | undefined): void => {
    for (const n of nodes ?? []) {
      if (typeof n === 'string') {
        const seg = n.split('/', 1)[0];
        if (seg) prefixes.add(seg.toLowerCase());
      } else {
        walk(n.pages);
        for (const g of n.groups ?? []) walk(g.pages);
      }
    }
  };
  for (const product of en?.products ?? []) {
    for (const tab of product.tabs ?? []) {
      for (const group of tab.groups ?? []) walk(group.pages);
    }
  }
  prefixCache.set(repoRoot, prefixes);
  return prefixes;
}

function allowedFsPrefix(lang: Lang, productPrefix: string): string {
  const rel = lang === 'en' ? `${productPrefix}/` : `${lang}/${productPrefix}/`;
  return rel.replace(/\//g, sep);
}

export function resolveMdxPath(repoRoot: string, lang: Lang, slug: string): string {
  if (slug.includes('..')) throw new Error(`slug contains parent traversal: ${slug}`);
  if (!SLUG_BODY_PATTERN.test(slug) || !slug.includes('/')) {
    throw new Error(`invalid slug: ${slug}`);
  }

  const productPrefix = slug.split('/', 1)[0].toLowerCase();
  if (!deriveProductPrefixes(repoRoot).has(productPrefix)) {
    throw new Error(`slug product prefix not in docs.json whitelist: ${productPrefix}`);
  }

  const relative = (lang === 'en' ? slug : `${lang}/${slug}`) + '.mdx';
  const expectedPrefix = allowedFsPrefix(lang, productPrefix);
  const normalized = normalize(relative);
  if (!normalized.startsWith(expectedPrefix)) {
    throw new Error(`path escapes whitelist: ${normalized}`);
  }

  return join(repoRoot, normalized);
}

export function readMdx(repoRoot: string, lang: Lang, slug: string): string {
  const path = resolveMdxPath(repoRoot, lang, slug);
  if (!existsSync(path)) throw new Error(`file not found: ${path}`);
  return readFileSync(path, 'utf8');
}

export function writeMdxAtomic(repoRoot: string, lang: Lang, slug: string, content: string): string {
  const path = resolveMdxPath(repoRoot, lang, slug);
  if (!existsSync(path)) throw new Error(`file not found (refusing to create): ${path}`);
  const tmp = `${path}.tmp.${process.pid}.${Date.now()}`;
  writeFileSync(tmp, content, 'utf8');
  renameSync(tmp, path);
  return path;
}

/** Delete the mdx for one language if it exists; returns the path when removed. */
export function deleteMdx(repoRoot: string, lang: Lang, slug: string): string | null {
  const path = resolveMdxPath(repoRoot, lang, slug);
  if (!existsSync(path)) return null;
  unlinkSync(path);
  return path;
}
