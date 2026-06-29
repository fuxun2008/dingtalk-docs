import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import type { Lang, NavNode, ProductTab } from '../shared/types';
import { resolveMdxPath } from './fs-safe';
import { readTitle } from '../shared/frontmatter';

interface DocsJsonTab {
  tab: string;
  groups?: DocsJsonGroup[];
}

interface DocsJsonGroup {
  group: string;
  pages?: Array<string | DocsJsonGroup>;
}

interface DocsJsonProduct {
  product: string;
  tabs?: DocsJsonTab[];
}

interface DocsJsonLanguage {
  language: string;
  products?: DocsJsonProduct[];
}

interface DocsJson {
  navigation?: { languages?: DocsJsonLanguage[] };
}

function loadDocsJson(repoRoot: string): DocsJson {
  return JSON.parse(readFileSync(join(repoRoot, 'docs.json'), 'utf8'));
}

function findLanguageBlock(docs: DocsJson, lang: string): DocsJsonLanguage | null {
  return docs.navigation?.languages?.find((l) => l.language === lang) ?? null;
}

/** Resolve a `p{pi}t{ti}` key against a language block's products/tabs. */
function tabByKey(lang: DocsJsonLanguage | null, key: string): DocsJsonTab | null {
  const m = /^p(\d+)t(\d+)$/.exec(key);
  if (!m) return null;
  const pi = Number(m[1]);
  const ti = Number(m[2]);
  return lang?.products?.[pi]?.tabs?.[ti] ?? null;
}

/** All proofreading units (one per tab) from the en block, position-keyed. */
export function listProductTabs(repoRoot: string): ProductTab[] {
  const docs = loadDocsJson(repoRoot);
  const en = findLanguageBlock(docs, 'en');
  const out: ProductTab[] = [];
  (en?.products ?? []).forEach((product, pi) => {
    (product.tabs ?? []).forEach((tab, ti) => {
      out.push({ key: `p${pi}t${ti}`, product: product.product, tab: tab.tab });
    });
  });
  return out;
}

function readPageTitle(repoRoot: string, lang: Lang, slug: string): string | undefined {
  try {
    const path = resolveMdxPath(repoRoot, lang, slug);
    if (!existsSync(path)) return undefined;
    return readTitle(readFileSync(path, 'utf8'));
  } catch {
    return undefined;
  }
}

function isFileMissing(repoRoot: string, slug: string): boolean {
  try {
    return !existsSync(resolveMdxPath(repoRoot, 'en', slug));
  } catch {
    return true;
  }
}

/** Walk the en canonical tree, attaching left/right group + page titles by position. */
function walkPages(
  repoRoot: string,
  leftLang: Lang,
  rightLang: Lang,
  enItems: Array<string | DocsJsonGroup>,
  leftItems: Array<string | DocsJsonGroup> = [],
  rightItems: Array<string | DocsJsonGroup> = [],
): NavNode[] {
  return enItems.map((item, i): NavNode => {
    if (typeof item === 'string') {
      return {
        type: 'page',
        slug: item,
        titleLeft: readPageTitle(repoRoot, leftLang, item),
        titleRight: readPageTitle(repoRoot, rightLang, item),
        missing: isFileMissing(repoRoot, item),
      };
    }
    const leftGroup = asGroup(leftItems[i]);
    const rightGroup = asGroup(rightItems[i]);
    return {
      type: 'group',
      titleLeft: leftGroup?.group ?? item.group,
      titleRight: rightGroup?.group,
      children: walkPages(
        repoRoot,
        leftLang,
        rightLang,
        item.pages ?? [],
        leftGroup?.pages ?? [],
        rightGroup?.pages ?? [],
      ),
    };
  });
}

function asGroup(item: string | DocsJsonGroup | undefined): DocsJsonGroup | undefined {
  return typeof item === 'object' && item !== null ? item : undefined;
}

/** Navigation tree for one product tab, with titles in the chosen left/right langs. */
export function parseNavigation(
  repoRoot: string,
  productKey: string,
  leftLang: Lang,
  rightLang: Lang,
): NavNode[] {
  const docs = loadDocsJson(repoRoot);
  const enTab = tabByKey(findLanguageBlock(docs, 'en'), productKey);
  if (!enTab) throw new Error(`product tab not found in docs.json (en): ${productKey}`);
  const leftTab = tabByKey(findLanguageBlock(docs, leftLang), productKey);
  const rightTab = tabByKey(findLanguageBlock(docs, rightLang), productKey);
  return walkPages(
    repoRoot,
    leftLang,
    rightLang,
    enTab.groups ?? [],
    leftTab?.groups ?? [],
    rightTab?.groups ?? [],
  );
}
