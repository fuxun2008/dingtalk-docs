import { readFileSync, renameSync, writeFileSync, existsSync } from 'node:fs';
import { join, normalize, sep } from 'node:path';
import type { Lang } from '../shared/types';

const PRODUCT_PREFIXES = ['aitable', 'docs'] as const;

const SLUG_PATTERN = new RegExp(`^(?:${PRODUCT_PREFIXES.join('|')})/[a-z0-9._\\-/]+$`, 'i');

function allowedFsPrefix(lang: Lang, productPrefix: string): string {
  const rel = lang === 'en' ? `${productPrefix}/` : `${lang}/${productPrefix}/`;
  return rel.replace(/\//g, sep);
}

export function resolveMdxPath(repoRoot: string, lang: Lang, slug: string): string {
  if (!SLUG_PATTERN.test(slug)) {
    throw new Error(`invalid slug: ${slug}`);
  }
  if (slug.includes('..')) throw new Error(`slug contains parent traversal: ${slug}`);

  const productPrefix = slug.split('/', 1)[0];
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
