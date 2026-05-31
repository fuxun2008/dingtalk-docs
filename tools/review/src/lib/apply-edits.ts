import type { Block, FrontmatterMeta } from '../shared/types';
import { buildFrontmatter } from '../shared/frontmatter';
import { FM_TITLE_KEY, FM_DESC_KEY } from '../components/FrontmatterCard';

export const INSERT_AT_START = '__start__';

export interface PendingInsert {
  afterBlockId: string;
  raw: string;
  seq: number;
}

export interface ApplyEditsInput {
  content: string;
  blocks: Block[];
  frontmatter: FrontmatterMeta | null;
  dirty: Map<string, string>;
  inserts?: Map<string, PendingInsert>;
}

export interface ApplyEditsResult {
  content: string;
  appliedBlockIds: string[];
  appliedInsertIds: string[];
  frontmatterChanged: boolean;
  skipped: string[];
}

interface Edit {
  start: number;
  end: number;
  replacement: string;
  key: string;
  insertSeq?: number;
}

export function applyEdits({ content, blocks, frontmatter, dirty, inserts }: ApplyEditsInput): ApplyEditsResult {
  const edits: Edit[] = [];
  const skipped: string[] = [];
  const appliedBlockIds: string[] = [];
  const appliedInsertIds: string[] = [];
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

  if (inserts) {
    for (const [key, { afterBlockId, raw, seq }] of inserts.entries()) {
      let anchorEnd: number;
      if (afterBlockId === INSERT_AT_START) {
        anchorEnd = frontmatter?.endOffset ?? 0;
      } else {
        const anchor = blockById.get(afterBlockId);
        if (!anchor) {
          skipped.push(key);
          continue;
        }
        anchorEnd = anchor.endOffset;
      }
      // 在 anchor 末尾处零宽插入；前后各补一个空行，确保 mdx 块级分隔
      edits.push({
        start: anchorEnd,
        end: anchorEnd,
        replacement: `\n\n${raw}\n`,
        key,
        insertSeq: seq,
      });
      appliedInsertIds.push(key);
    }
  }

  // 按 start 倒序应用；相同 anchor 的多个插入按 seq 倒序，保证最早插入的最先出现
  edits.sort((a, b) => {
    if (b.start !== a.start) return b.start - a.start;
    const aSeq = a.insertSeq ?? -1;
    const bSeq = b.insertSeq ?? -1;
    return bSeq - aSeq;
  });
  let next = content;
  for (const e of edits) {
    next = next.slice(0, e.start) + e.replacement + next.slice(e.end);
  }

  return { content: next, appliedBlockIds, appliedInsertIds, frontmatterChanged, skipped };
}
