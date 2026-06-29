import { readFileSync, writeFileSync, renameSync, existsSync, unlinkSync, statSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join, normalize, sep } from 'node:path';
import { ALL_LANGS, type Lang } from '../shared/types';
import { deleteMdx, readMdx } from './fs-safe';

export interface DeletePageResult {
  slug: string;
  deletedFiles: string[];
  removedNavLines: string[];
  deletedImages: string[];
}

/** The docs.json nav entry string for a slug in a given language block. */
function navEntry(lang: Lang, slug: string): string {
  return lang === 'en' ? slug : `${lang}/${slug}`;
}

/** Local (repo-hosted) image paths referenced by an mdx body. CDN/http refs are ignored. */
function collectLocalImages(content: string): Set<string> {
  const out = new Set<string>();
  const re = /\/?images\/[A-Za-z0-9._\-/]+?\.(?:png|jpe?g|gif|webp|svg)/gi;
  for (const m of content.matchAll(re)) {
    out.add(m[0].replace(/^\//, ''));
  }
  return out;
}

/**
 * Remove the single array-element line whose trimmed text is exactly `"target"`
 * (optionally trailing comma). If the removed element was the array's last item
 * (no trailing comma), strip the now-dangling comma off the previous sibling.
 * Returns null when not found.
 */
function removeNavLine(text: string, target: string): { text: string; line: string } | null {
  const lines = text.split('\n');
  const bare = `"${target}"`;
  const withComma = `"${target}",`;
  const idx = lines.findIndex((l) => {
    const t = l.trim();
    return t === bare || t === withComma;
  });
  if (idx < 0) return null;

  const removedLine = lines[idx];
  const hadComma = removedLine.trim().endsWith(',');
  lines.splice(idx, 1);

  if (!hadComma) {
    // The removed element was the last in its array → fix the previous sibling's comma.
    const prev = lines[idx - 1];
    if (prev && prev.trim().endsWith(',')) {
      lines[idx - 1] = prev.replace(/,(\s*)$/, '$1');
    }
  }
  return { text: lines.join('\n'), line: removedLine.trim() };
}

function writeFileAtomic(path: string, content: string): void {
  const tmp = `${path}.tmp.${process.pid}.${Date.now()}`;
  writeFileSync(tmp, content, 'utf8');
  renameSync(tmp, path);
}

/** True when the image path is still referenced by any remaining .mdx in the repo. */
function isImageReferenced(repoRoot: string, imageRel: string): boolean {
  try {
    execFileSync('grep', ['-rlF', '--include=*.mdx', imageRel, repoRoot], { stdio: 'ignore' });
    return true; // exit 0 → at least one match
  } catch (err) {
    const status = (err as { status?: number }).status;
    if (status === 1) return false; // no matches
    return true; // grep error → be conservative, keep the image
  }
}

function safeImagePath(repoRoot: string, imageRel: string): string | null {
  if (imageRel.includes('..')) return null;
  const normalized = normalize(imageRel);
  if (!normalized.startsWith(`images${sep}`) && normalized !== 'images') return null;
  const abs = join(repoRoot, normalized);
  if (!abs.startsWith(repoRoot + sep)) return null;
  return abs;
}

export function deletePage(repoRoot: string, slug: string): DeletePageResult {
  // 1. Gather local images referenced by any existing language version (before deletion).
  const images = new Set<string>();
  for (const lang of ALL_LANGS) {
    try {
      collectLocalImages(readMdx(repoRoot, lang, slug)).forEach((i) => images.add(i));
    } catch {
      /* missing language file — skip */
    }
  }

  // 2. Delete the three-language mdx files.
  const deletedFiles: string[] = [];
  for (const lang of ALL_LANGS) {
    const p = deleteMdx(repoRoot, lang, slug);
    if (p) deletedFiles.push(p);
  }

  // 3. Surgically remove the three nav entries from docs.json (raw line removal).
  const docsPath = join(repoRoot, 'docs.json');
  let text = readFileSync(docsPath, 'utf8');
  const removedNavLines: string[] = [];
  for (const lang of ALL_LANGS) {
    const res = removeNavLine(text, navEntry(lang, slug));
    if (res) {
      text = res.text;
      removedNavLines.push(res.line);
    }
  }
  if (removedNavLines.length > 0) writeFileAtomic(docsPath, text);

  // 4. Orphan-image cleanup: delete local images no longer referenced anywhere.
  const deletedImages: string[] = [];
  for (const imageRel of images) {
    if (isImageReferenced(repoRoot, imageRel)) continue;
    const abs = safeImagePath(repoRoot, imageRel);
    if (abs && existsSync(abs) && statSync(abs).isFile()) {
      unlinkSync(abs);
      deletedImages.push(imageRel);
    }
  }

  return { slug, deletedFiles, removedNavLines, deletedImages };
}
