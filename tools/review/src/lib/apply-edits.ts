import type { Block, FrontmatterMeta } from '../shared/types';
import { buildFrontmatter } from '../shared/frontmatter';
import { FM_TITLE_KEY, FM_DESC_KEY } from '../components/FrontmatterCard';

export interface ApplyEditsInput {
  content: string;
  blocks: Block[];
  frontmatter: FrontmatterMeta | null;
  dirty: Map<string, string>;
}

export interface ApplyEditsResult {
  content: string;
  appliedBlockIds: string[];
  frontmatterChanged: boolean;
  skipped: string[];
}

interface Edit {
  start: number;
  end: number;
  replacement: string;
  key: string;
}

export function applyEdits({ content, blocks, frontmatter, dirty }: ApplyEditsInput): ApplyEditsResult {
  const edits: Edit[] = [];
  const skipped: string[] = [];
  const appliedBlockIds: string[] = [];
  let frontmatterChanged = false;

  const dirtyTitle = dirty.has(FM_TITLE_KEY) ? dirty.get(FM_TITLE_KEY) : undefined;
  const dirtyDesc = dirty.has(FM_DESC_KEY) ? dirty.get(FM_DESC_KEY) : undefined;
  if ((dirtyTitle !== undefined || dirtyDesc !== undefined) && frontmatter) {
    const nextTitle = dirtyTitle ?? frontmatter.title;
    const nextDesc = dirtyDesc ?? frontmatter.description;
    const replacement = buildFrontmatter({
      title: nextTitle,
      description: nextDesc,
      rest: frontmatter.rest,
    });
    edits.push({
      start: frontmatter.startOffset,
      end: frontmatter.endOffset,
      replacement,
      key: '__frontmatter__',
    });
    frontmatterChanged = true;
  } else if ((dirtyTitle !== undefined || dirtyDesc !== undefined) && !frontmatter) {
    skipped.push(FM_TITLE_KEY, FM_DESC_KEY);
  }

  const blockById = new Map(blocks.map((b) => [b.id, b]));
  for (const [key, value] of dirty.entries()) {
    if (key === FM_TITLE_KEY || key === FM_DESC_KEY) continue;
    const block = blockById.get(key);
    if (!block) {
      skipped.push(key);
      continue;
    }
    let end = block.endOffset;
    if (value === '') {
      // 整块删除：连同尾部所有空行一并吃掉，避免留下空行隔离
      while (end < content.length && content[end] === '\n') end++;
    }
    edits.push({ start: block.startOffset, end, replacement: value, key });
    appliedBlockIds.push(key);
  }

  edits.sort((a, b) => b.start - a.start);
  let next = content;
  for (const e of edits) {
    next = next.slice(0, e.start) + e.replacement + next.slice(e.end);
  }

  return { content: next, appliedBlockIds, frontmatterChanged, skipped };
}
