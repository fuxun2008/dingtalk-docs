import type { Block, BlockType } from '../shared/types';
import { isMediaBlock } from './media';

export interface BlockAlignment {
  leftToRight: Map<number, number>;
  rightToLeft: Map<number, number>;
}

const SKIP_FOR_ALIGN: Set<BlockType> = new Set(['frontmatter']);

interface IndexedBlock {
  index: number;
  block: Block;
}

interface HeadingEntry {
  index: number;
  depth: number;
}

function pickAlignable(blocks: Block[]): IndexedBlock[] {
  const result: IndexedBlock[] = [];
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    if (SKIP_FOR_ALIGN.has(b.type)) continue;
    if (isMediaBlock(b)) continue;
    result.push({ index: i, block: b });
  }
  return result;
}

function extractHeadings(items: IndexedBlock[]): HeadingEntry[] {
  const out: HeadingEntry[] = [];
  for (const it of items) {
    if (it.block.type === 'heading') {
      out.push({ index: it.index, depth: it.block.depth ?? 0 });
    }
  }
  return out;
}

function depthsEqual(a: HeadingEntry[], b: HeadingEntry[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i].depth !== b[i].depth) return false;
  return true;
}

// Standard LCS over depth equality; returns pairs of indices into the input arrays.
function lcsHeadingPairs(zh: HeadingEntry[], en: HeadingEntry[]): Array<[number, number]> {
  const m = zh.length;
  const n = en.length;
  if (m === 0 || n === 0) return [];
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = zh[i - 1].depth === en[j - 1].depth
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  const pairs: Array<[number, number]> = [];
  let i = m;
  let j = n;
  while (i > 0 && j > 0) {
    if (zh[i - 1].depth === en[j - 1].depth) {
      pairs.push([i - 1, j - 1]);
      i--; j--;
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      i--;
    } else {
      j--;
    }
  }
  return pairs.reverse();
}

function pairHeadings(zh: HeadingEntry[], en: HeadingEntry[]): Array<[HeadingEntry, HeadingEntry]> {
  if (depthsEqual(zh, en)) {
    return zh.map((z, i) => [z, en[i]] as [HeadingEntry, HeadingEntry]);
  }
  // When every heading has the same depth, depth-only LCS has no semantic
  // signal and may arbitrarily align the tail of one side with the head of the
  // other. Documentation translations normally preserve heading order, so a
  // stable prefix pairing is safer and keeps missing trailing sections local.
  const uniformDepth = zh.length > 0
    && en.length > 0
    && zh.every((entry) => entry.depth === zh[0].depth)
    && en.every((entry) => entry.depth === zh[0].depth);
  if (uniformDepth) {
    const length = Math.min(zh.length, en.length);
    return Array.from({ length }, (_, i) => [zh[i], en[i]] as [HeadingEntry, HeadingEntry]);
  }
  return lcsHeadingPairs(zh, en).map(([zi, ei]) => [zh[zi], en[ei]] as [HeadingEntry, HeadingEntry]);
}

// Pair non-heading items inside [zhStart, zhEnd) × [enStart, enEnd) by order; shorter side wins.
function pairSection(
  zhItems: IndexedBlock[],
  enItems: IndexedBlock[],
  zhStart: number,
  zhEnd: number,
  enStart: number,
  enEnd: number,
  out: Array<[number, number]>,
): void {
  const zhSlice: IndexedBlock[] = [];
  for (let i = zhStart; i < zhEnd; i++) {
    if (zhItems[i].block.type !== 'heading') zhSlice.push(zhItems[i]);
  }
  const enSlice: IndexedBlock[] = [];
  for (let j = enStart; j < enEnd; j++) {
    if (enItems[j].block.type !== 'heading') enSlice.push(enItems[j]);
  }
  const len = Math.min(zhSlice.length, enSlice.length);
  for (let k = 0; k < len; k++) {
    out.push([zhSlice[k].index, enSlice[k].index]);
  }
}

// `left`/`right` are the two compared panes; the algorithm is symmetric so the
// internal zh/en labels are just historical names for the two sides.
export function computeAlignment(leftBlocks: Block[], rightBlocks: Block[]): BlockAlignment {
  const leftToRight = new Map<number, number>();
  const rightToLeft = new Map<number, number>();

  const zhItems = pickAlignable(leftBlocks);
  const enItems = pickAlignable(rightBlocks);
  if (zhItems.length === 0 || enItems.length === 0) return { leftToRight, rightToLeft };

  const zhHeadings = extractHeadings(zhItems);
  const enHeadings = extractHeadings(enItems);
  const headingPairs = pairHeadings(zhHeadings, enHeadings);

  const pairs: Array<[number, number]> = [];

  // Build section ranges over the items arrays using matched headings as anchors.
  // Anchor positions are item-array indices.
  const findItemIdx = (items: IndexedBlock[], originalIndex: number): number => {
    for (let i = 0; i < items.length; i++) if (items[i].index === originalIndex) return i;
    return -1;
  };

  let prevZhAnchor = -1;
  let prevEnAnchor = -1;
  for (const [zh, en] of headingPairs) {
    const zhAnchorIdx = findItemIdx(zhItems, zh.index);
    const enAnchorIdx = findItemIdx(enItems, en.index);
    if (zhAnchorIdx < 0 || enAnchorIdx < 0) continue;

    // Section before this anchor pair.
    pairSection(zhItems, enItems, prevZhAnchor + 1, zhAnchorIdx, prevEnAnchor + 1, enAnchorIdx, pairs);
    // The heading itself.
    pairs.push([zh.index, en.index]);

    prevZhAnchor = zhAnchorIdx;
    prevEnAnchor = enAnchorIdx;
  }

  // Tail section after the last matched pair.
  pairSection(zhItems, enItems, prevZhAnchor + 1, zhItems.length, prevEnAnchor + 1, enItems.length, pairs);

  for (const [zi, ei] of pairs) {
    leftToRight.set(zi, ei);
    rightToLeft.set(ei, zi);
  }
  return { leftToRight, rightToLeft };
}

export type MediaTarget =
  | { mode: 'replace'; blockIndex: number }
  | { mode: 'insert'; afterBlockIndex: number | null };

/**
 * Resolve a media block to the same structural interval on the other language.
 * Text/heading alignment supplies the boundaries; media order within that interval
 * decides whether to replace an existing peer or insert a missing one.
 */
export function resolveMediaTarget(
  sourceIndex: number,
  sourceBlocks: Block[],
  targetBlocks: Block[],
  sourceToTarget: Map<number, number>,
): MediaTarget {
  let previousSource = -1;
  let previousTarget = -1;
  for (let i = sourceIndex - 1; i >= 0; i--) {
    const peer = sourceToTarget.get(i);
    if (peer !== undefined) {
      previousSource = i;
      previousTarget = peer;
      break;
    }
  }

  let nextSource = sourceBlocks.length;
  let nextTarget = targetBlocks.length;
  for (let i = sourceIndex + 1; i < sourceBlocks.length; i++) {
    const peer = sourceToTarget.get(i);
    if (peer !== undefined) {
      nextSource = i;
      nextTarget = peer;
      break;
    }
  }

  const sourceMedia = sourceBlocks
    .map((block, index) => ({ block, index }))
    .filter(({ block, index }) => index > previousSource && index < nextSource && isMediaBlock(block));
  const ordinal = Math.max(0, sourceMedia.findIndex(({ index }) => index === sourceIndex));
  const targetMedia = targetBlocks
    .map((block, index) => ({ block, index }))
    .filter(({ block, index }) => index > previousTarget && index < nextTarget && isMediaBlock(block));

  const existing = targetMedia[ordinal];
  if (existing) return { mode: 'replace', blockIndex: existing.index };

  const precedingMedia = targetMedia[Math.min(ordinal, targetMedia.length) - 1];
  return {
    mode: 'insert',
    afterBlockIndex: precedingMedia?.index ?? (previousTarget >= 0 ? previousTarget : null),
  };
}
