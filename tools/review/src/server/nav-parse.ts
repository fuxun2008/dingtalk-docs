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

const AITABLE_TAB_NAMES = ['AI Table', 'AI 表格', 'AI テーブル'];

function findAITableTab(docs: DocsJson, lang: string): DocsJsonTab | null {
  const langBlock = docs.navigation?.languages?.find((l) => l.language === lang);
  if (!langBlock?.tabs) return null;
  return langBlock.tabs.find((t) => AITABLE_TAB_NAMES.includes(t.tab)) ?? null;
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

export function parseAITableNav(repoRoot: string): NavNode[] {
  const docsPath = join(repoRoot, 'docs.json');
  const docs: DocsJson = JSON.parse(readFileSync(docsPath, 'utf8'));
  const enTab = findAITableTab(docs, 'en');
  if (!enTab) throw new Error('AI Table tab not found in docs.json (en)');
  const zhTab = findAITableTab(docs, 'zh');
  return walkPages(repoRoot, enTab.groups ?? [], zhTab?.groups ?? []);
}
