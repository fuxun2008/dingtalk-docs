import { readFileSync, renameSync, writeFileSync, existsSync } from 'node:fs';
import { join, normalize, sep } from 'node:path';
import type { Lang } from '../shared/types';

const ALLOWED_PREFIXES: Record<Lang, string> = {
  en: 'aitable/',
  zh: 'zh/aitable/',
  ja: 'ja/aitable/',
};

export function resolveMdxPath(repoRoot: string, lang: Lang, slug: string): string {
  if (!/^aitable\/[a-z0-9._\-/]+$/i.test(slug)) {
    throw new Error(`invalid slug: ${slug}`);
  }
  if (slug.includes('..')) throw new Error(`slug contains parent traversal: ${slug}`);

  const relative = (lang === 'en' ? slug : `${lang}/${slug}`) + '.mdx';
  const expectedPrefix = ALLOWED_PREFIXES[lang].replace(/\//g, sep);
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
