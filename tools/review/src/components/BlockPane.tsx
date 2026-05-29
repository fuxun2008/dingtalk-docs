import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Block, BlockType } from '../shared/types';
import { InlineEditor } from './InlineEditor';

type Side = 'zh' | 'en';

interface BlockPaneProps {
  blocks: Block[];
  side: Side;
  dirty: Map<string, string>;
  hoveredIndex: number | null;
  onHoverBlock: (index: number | null) => void;
  onCommitBlock?: (blockId: string, newRaw: string) => void;
  registerBlockRef?: (index: number, el: HTMLDivElement | null) => void;
}

const READONLY_LABEL: Partial<Record<BlockType, string>> = {
  frontmatter: 'Frontmatter',
  code: '代码块',
  mdxJsxFlow: 'MDX 组件',
  mdxEsm: 'MDX 语句',
  mdxExpression: 'MDX 表达式',
  table: '表格',
  thematicBreak: '分割线',
  unknown: '未识别块',
};

const SKIP_TYPES: Set<BlockType> = new Set(['frontmatter']);

export function BlockPane({
  blocks,
  side,
  dirty,
  hoveredIndex,
  onHoverBlock,
  onCommitBlock,
  registerBlockRef,
}: BlockPaneProps) {
  const [editingId, setEditingId] = useState<string | null>(null);

  return (
    <div className={`block-pane block-pane-${side}`}>
      {blocks.map((block, index) => {
        if (SKIP_TYPES.has(block.type)) return null;
        return (
          <BlockItem
            key={block.id}
            block={block}
            index={index}
            side={side}
            isDirty={dirty.has(block.id)}
            currentRaw={dirty.get(block.id) ?? block.raw}
            isHovered={hoveredIndex === index}
            isEditing={editingId === block.id}
            onHover={onHoverBlock}
            onEnterEdit={onCommitBlock ? (id) => setEditingId(id) : undefined}
            onCommit={(newRaw) => {
              setEditingId(null);
              if (newRaw !== block.raw) onCommitBlock?.(block.id, newRaw);
            }}
            onCancel={() => setEditingId(null)}
            registerBlockRef={registerBlockRef}
          />
        );
      })}
    </div>
  );
}

interface BlockItemProps {
  block: Block;
  index: number;
  side: Side;
  isDirty: boolean;
  currentRaw: string;
  isHovered: boolean;
  isEditing: boolean;
  onHover: (index: number | null) => void;
  onEnterEdit?: (blockId: string) => void;
  onCommit: (newRaw: string) => void;
  onCancel: () => void;
  registerBlockRef?: (index: number, el: HTMLDivElement | null) => void;
}

function BlockItem({
  block,
  index,
  side,
  isDirty,
  currentRaw,
  isHovered,
  isEditing,
  onHover,
  onEnterEdit,
  onCommit,
  onCancel,
  registerBlockRef,
}: BlockItemProps) {
  const editableHere = block.editable && side === 'en';
  const classes = [
    'block-item',
    `block-item-${side}`,
    isHovered ? 'is-hovered' : '',
    isDirty ? 'is-dirty' : '',
    isEditing ? 'is-editing' : '',
    block.editable ? 'is-editable' : 'is-locked',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      ref={(el) => registerBlockRef?.(index, el)}
      className={classes}
      data-block-index={index}
      data-block-id={block.id}
      onMouseEnter={() => onHover(index)}
      onMouseLeave={() => onHover(null)}
      onDoubleClick={editableHere && onEnterEdit && !isEditing ? () => onEnterEdit(block.id) : undefined}
      title={editableHere && !isEditing ? '双击编辑' : undefined}
    >
      {isEditing ? (
        <InlineEditor initialValue={currentRaw} onCommit={onCommit} onCancel={onCancel} />
      ) : block.editable ? (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{currentRaw}</ReactMarkdown>
      ) : (
        <ReadonlyContent block={block} />
      )}
    </div>
  );
}

function ReadonlyContent({ block }: { block: Block }) {
  const label = READONLY_LABEL[block.type] ?? block.type;
  const preview = block.raw.length > 400 ? block.raw.slice(0, 400) + '…' : block.raw;
  return (
    <div className="readonly-content">
      <div className="readonly-content-tag">{label}</div>
      <pre className="readonly-content-raw">{preview}</pre>
    </div>
  );
}
