import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import type { NavNode } from '../shared/types';
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

interface DocsJsonLanguage {
  language: string;
  tabs?: DocsJsonTab[];
}

interface DocsJson {
  navigation?: { languages?: DocsJsonLanguage[] };
}

const AITABLE_TAB_NAMES = new Set(['AI Table', 'AI 表格', 'AI テーブル']);

function findLanguageBlock(docs: DocsJson, lang: string): DocsJsonLanguage | null {
  return docs.navigation?.languages?.find((l) => l.language === lang) ?? null;
}

function aitableTabs(lang: DocsJsonLanguage | null): DocsJsonTab[] {
  return (lang?.tabs ?? []).filter((t) => AITABLE_TAB_NAMES.has(t.tab));
}

function readPageTitle(repoRoot: string, lang: 'en' | 'zh', slug: string): string | undefined {
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

function walkPages(
  repoRoot: string,
  enItems: Array<string | DocsJsonGroup>,
  zhItems: Array<string | DocsJsonGroup> = [],
): NavNode[] {
  return enItems.map((item, i) => {
    const zhItem = zhItems[i];
    if (typeof item === 'string') {
      return {
        type: 'page',
        slug: item,
        titleEn: readPageTitle(repoRoot, 'en', item),
        titleZh: readPageTitle(repoRoot, 'zh', item),
        missing: isFileMissing(repoRoot, item),
      };
    }
    const zhGroup = typeof zhItem === 'object' && zhItem !== null ? zhItem : undefined;
    return {
      type: 'group',
      titleEn: item.group,
      titleZh: zhGroup?.group,
      children: walkPages(repoRoot, item.pages ?? [], zhGroup?.pages ?? []),
    };
  });
}

export function parseNavigation(repoRoot: string): NavNode[] {
  const docsPath = join(repoRoot, 'docs.json');
  const docs: DocsJson = JSON.parse(readFileSync(docsPath, 'utf8'));
  const enLang = findLanguageBlock(docs, 'en');
  const enTabs = aitableTabs(enLang);
  if (!enTabs.length) throw new Error('AI Table tab not found in docs.json (en)');
  const zhTabs = aitableTabs(findLanguageBlock(docs, 'zh'));

  return enTabs.map((enTab, i): NavNode => {
    const zhTab = zhTabs[i];
    return {
      type: 'group',
      titleEn: enTab.tab,
      titleZh: zhTab?.tab,
      children: walkPages(repoRoot, enTab.groups ?? [], zhTab?.groups ?? []),
    };
  });
}
