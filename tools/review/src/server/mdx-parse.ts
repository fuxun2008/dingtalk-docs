import { unified } from 'unified';
import remarkParse from 'remark-parse';
import remarkFrontmatter from 'remark-frontmatter';
import remarkGfm from 'remark-gfm';
import remarkMdx from 'remark-mdx';
import { nanoid } from 'nanoid';
import type { Block, BlockType } from '../shared/types';

const EDITABLE_TYPES = new Set<BlockType>(['heading', 'paragraph', 'list', 'blockquote']);

const TYPE_MAP: Record<string, BlockType> = {
  yaml: 'frontmatter',
  heading: 'heading',
  paragraph: 'paragraph',
  list: 'list',
  blockquote: 'blockquote',
  code: 'code',
  thematicBreak: 'thematicBreak',
  mdxJsxFlowElement: 'mdxJsxFlow',
  mdxjsEsm: 'mdxEsm',
  mdxFlowExpression: 'mdxExpression',
  table: 'table',
};

function mapType(astType: string): BlockType {
  return TYPE_MAP[astType] ?? 'unknown';
}

interface AstNode {
  type: string;
  depth?: number;
  position?: { start: { offset?: number }; end: { offset?: number } };
}

interface AstRoot {
  children: AstNode[];
}

export function parseMdxBlocks(content: string): Block[] {
  const processor = unified()
    .use(remarkParse)
    .use(remarkFrontmatter, ['yaml'])
    .use(remarkGfm)
    .use(remarkMdx);

  const tree = processor.parse(content) as unknown as AstRoot;
  const blocks: Block[] = [];

  for (const node of tree.children) {
    const start = node.position?.start?.offset;
    const end = node.position?.end?.offset;
    if (start === undefined || end === undefined) continue;
    const type = mapType(node.type);
    blocks.push({
      id: nanoid(8),
      type,
      raw: content.slice(start, end),
      startOffset: start,
      endOffset: end,
      editable: EDITABLE_TYPES.has(type),
      depth: type === 'heading' ? node.depth : undefined,
    });
  }
  return blocks;
}

export function validateMdxSyntax(content: string): { ok: true } | { ok: false; error: string; line?: number; column?: number } {
  try {
    const processor = unified()
      .use(remarkParse)
      .use(remarkFrontmatter, ['yaml'])
      .use(remarkGfm)
      .use(remarkMdx);
    processor.parse(content);
    return { ok: true };
  } catch (err) {
    const e = err as { message?: string; line?: number; column?: number };
    return { ok: false, error: e.message ?? 'parse error', line: e.line, column: e.column };
  }
}
