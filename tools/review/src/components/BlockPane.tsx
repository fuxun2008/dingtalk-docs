import { Fragment, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Block, BlockType } from '../shared/types';
import { INSERT_AT_START, type PendingInsert } from '../lib/apply-edits';
import { InlineEditor } from './InlineEditor';
import type { InsertKind } from './InsertBlockDialog';

type Side = 'left' | 'right';

interface BlockPaneProps {
  blocks: Block[];
  side: Side;
  editable: boolean;
  dirty: Map<string, string>;
  inserts?: Map<string, PendingInsert>;
  hoveredIndex: number | null;
  onHoverBlock: (index: number | null) => void;
  onCommitBlock?: (blockId: string, newRaw: string) => void;
  onRestoreBlock?: (blockId: string) => void;
  onOpenInsertDialog?: (kind: InsertKind, afterBlockId: string) => void;
  onOpenReplaceDialog?: (blockId: string, raw: string) => void;
  onRemoveInsert?: (insertId: string) => void;
  registerBlockRef?: (index: number, el: HTMLDivElement | null) => void;
}

interface IndexedInsert {
  id: string;
  raw: string;
  seq: number;
}

function groupInsertsByAnchor(inserts: Map<string, PendingInsert> | undefined): Map<string, IndexedInsert[]> {
  const map = new Map<string, IndexedInsert[]>();
  if (!inserts) return map;
  for (const [id, { afterBlockId, raw, seq }] of inserts.entries()) {
    const list = map.get(afterBlockId) ?? [];
    list.push({ id, raw, seq });
    map.set(afterBlockId, list);
  }
  for (const list of map.values()) list.sort((a, b) => a.seq - b.seq);
  return map;
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

const IMAGE_ONLY_RE = /^!\[[^\]]*\]\([^)]+\)\s*$/;
const VIDEO_TAG_RE = /^<video\s+([^>]*?)\/?\s*>(?:\s*<\/video>)?\s*$/i;
const IMG_TAG_RE = /^<img\s+([^>]*?)\/?\s*>\s*$/i;

function isMediaBlock(block: Block): boolean {
  const trimmed = block.raw.trim();
  if (block.type === 'paragraph') return IMAGE_ONLY_RE.test(trimmed);
  if (block.type === 'mdxJsxFlow') return VIDEO_TAG_RE.test(trimmed) || IMG_TAG_RE.test(trimmed);
  return false;
}

export function BlockPane({
  blocks,
  side,
  editable,
  dirty,
  inserts,
  hoveredIndex,
  onHoverBlock,
  onCommitBlock,
  onRestoreBlock,
  onOpenInsertDialog,
  onOpenReplaceDialog,
  onRemoveInsert,
  registerBlockRef,
}: BlockPaneProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const insertsByAnchor = useMemo(() => groupInsertsByAnchor(inserts), [inserts]);
  const showInsertUI = editable && !!onOpenInsertDialog;
  const topInserts = insertsByAnchor.get(INSERT_AT_START) ?? [];

  return (
    <div className={`block-pane block-pane-${side}`}>
      {showInsertUI && (
        <InsertGap onPick={(kind) => onOpenInsertDialog!(kind, INSERT_AT_START)} />
      )}
      {topInserts.map((ins) => (
        <PendingInsertPreview key={ins.id} insert={ins} onRemove={onRemoveInsert} />
      ))}
      {blocks.map((block, index) => {
        if (SKIP_TYPES.has(block.type)) return null;
        const blockInserts = insertsByAnchor.get(block.id) ?? [];
        return (
          <Fragment key={block.id}>
            <BlockItem
              block={block}
              index={index}
              side={side}
              editable={editable}
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
              onDelete={onCommitBlock ? () => {
                setEditingId(null);
                onCommitBlock(block.id, '');
              } : undefined}
              onReplace={onOpenReplaceDialog ? () => onOpenReplaceDialog(block.id, block.raw) : undefined}
              onRestore={onRestoreBlock ? () => onRestoreBlock(block.id) : undefined}
              registerBlockRef={registerBlockRef}
            />
            {blockInserts.map((ins) => (
              <PendingInsertPreview key={ins.id} insert={ins} onRemove={onRemoveInsert} />
            ))}
            {showInsertUI && (
              <InsertGap onPick={(kind) => onOpenInsertDialog!(kind, block.id)} />
            )}
          </Fragment>
        );
      })}
    </div>
  );
}

interface BlockItemProps {
  block: Block;
  index: number;
  side: Side;
  editable: boolean;
  isDirty: boolean;
  currentRaw: string;
  isHovered: boolean;
  isEditing: boolean;
  onHover: (index: number | null) => void;
  onEnterEdit?: (blockId: string) => void;
  onCommit: (newRaw: string) => void;
  onCancel: () => void;
  onDelete?: () => void;
  onReplace?: () => void;
  onRestore?: () => void;
  registerBlockRef?: (index: number, el: HTMLDivElement | null) => void;
}

function BlockItem({
  block,
  index,
  side,
  editable,
  isDirty,
  currentRaw,
  isHovered,
  isEditing,
  onHover,
  onEnterEdit,
  onCommit,
  onCancel,
  onDelete,
  onReplace,
  onRestore,
  registerBlockRef,
}: BlockItemProps) {
  const editableHere = block.editable && editable;
  const isMedia = isMediaBlock(block);
  const mediaActionable = editable && !block.editable && isMedia;
  const isDeleted = (editableHere || mediaActionable) && isDirty && currentRaw === '';
  const classes = [
    'block-item',
    `block-item-${side}`,
    isHovered ? 'is-hovered' : '',
    isDirty ? 'is-dirty' : '',
    isEditing ? 'is-editing' : '',
    isDeleted ? 'is-deleted' : '',
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
      onDoubleClick={editableHere && onEnterEdit && !isEditing && !isDeleted ? () => onEnterEdit(block.id) : undefined}
      title={editableHere && !isEditing && !isDeleted ? '双击编辑' : undefined}
    >
      {isEditing ? (
        <InlineEditor initialValue={currentRaw} onCommit={onCommit} onCancel={onCancel} onDelete={onDelete} />
      ) : isDeleted ? (
        <DeletedPlaceholder block={block} onRestore={onRestore} />
      ) : block.editable ? (
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{currentRaw}</ReactMarkdown>
      ) : (
        <ReadonlyContent
          block={block}
          onDelete={mediaActionable ? onDelete : undefined}
          onReplace={mediaActionable ? onReplace : undefined}
        />
      )}
    </div>
  );
}

function DeletedPlaceholder({ block, onRestore }: { block: Block; onRestore?: () => void }) {
  const preview = block.raw.split('\n')[0].slice(0, 80);
  return (
    <div className="deleted-placeholder">
      <div className="deleted-placeholder-tag">已标记删除 · 保存后写回</div>
      <div className="deleted-placeholder-preview" title={block.raw}>{preview}</div>
      {onRestore && (
        <button type="button" className="deleted-placeholder-restore" onClick={onRestore}>
          撤销
        </button>
      )}
    </div>
  );
}

function MediaActions({ onDelete, onReplace, replaceLabel, deleteLabel }: {
  onDelete?: () => void;
  onReplace?: () => void;
  replaceLabel: string;
  deleteLabel: string;
}) {
  return (
    <div className="readonly-content-actions">
      {onReplace && (
        <button
          type="button"
          className="readonly-content-replace"
          onClick={onReplace}
          title={replaceLabel}
          aria-label={replaceLabel}
        >
          替换
        </button>
      )}
      {onDelete && (
        <button
          type="button"
          className="readonly-content-delete"
          onClick={onDelete}
          title={deleteLabel}
          aria-label={deleteLabel}
        >
          删除
        </button>
      )}
    </div>
  );
}

function ReadonlyContent({ block, onDelete, onReplace }: { block: Block; onDelete?: () => void; onReplace?: () => void }) {
  const trimmed = block.raw.trim();

  if (block.type === 'paragraph' && IMAGE_ONLY_RE.test(trimmed)) {
    return (
      <div className="readonly-content readonly-content-media">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.raw}</ReactMarkdown>
        <MediaActions onDelete={onDelete} onReplace={onReplace} replaceLabel="替换此图片" deleteLabel="删除此图片" />
      </div>
    );
  }

  if (block.type === 'mdxJsxFlow') {
    const videoMatch = trimmed.match(VIDEO_TAG_RE);
    if (videoMatch) {
      return (
        <div className="readonly-content readonly-content-media">
          <div dangerouslySetInnerHTML={{ __html: `<video ${videoMatch[1]}></video>` }} />
          <MediaActions onDelete={onDelete} onReplace={onReplace} replaceLabel="替换此视频" deleteLabel="删除此视频" />
        </div>
      );
    }
    const imgMatch = trimmed.match(IMG_TAG_RE);
    if (imgMatch) {
      return (
        <div className="readonly-content readonly-content-media">
          <div dangerouslySetInnerHTML={{ __html: `<img ${imgMatch[1]}/>` }} />
          <MediaActions onDelete={onDelete} onReplace={onReplace} replaceLabel="替换此图片" deleteLabel="删除此图片" />
        </div>
      );
    }
  }

  const label = READONLY_LABEL[block.type] ?? block.type;
  const preview = block.raw.length > 400 ? block.raw.slice(0, 400) + '…' : block.raw;
  return (
    <div className="readonly-content">
      <div className="readonly-content-tag">{label}</div>
      <pre className="readonly-content-raw">{preview}</pre>
    </div>
  );
}

interface InsertGapProps {
  onPick: (kind: InsertKind) => void;
}

function InsertGap({ onPick }: InsertGapProps) {
  return (
    <div className="insert-gap" role="presentation">
      <div className="insert-gap-chips">
        <button
          type="button"
          className="insert-gap-chip"
          onClick={() => onPick('image')}
          title="在此处插入图片"
        >
          + 图片
        </button>
        <button
          type="button"
          className="insert-gap-chip"
          onClick={() => onPick('video')}
          title="在此处插入视频"
        >
          + 视频
        </button>
      </div>
    </div>
  );
}

interface PendingInsertPreviewProps {
  insert: IndexedInsert;
  onRemove?: (insertId: string) => void;
}

function PendingInsertPreview({ insert, onRemove }: PendingInsertPreviewProps) {
  const trimmed = insert.raw.trim();
  const videoMatch = trimmed.match(VIDEO_TAG_RE);
  const imgMatch = !videoMatch ? trimmed.match(IMG_TAG_RE) : null;
  const isImageMarkdown = !videoMatch && !imgMatch && IMAGE_ONLY_RE.test(trimmed);

  return (
    <div className="pending-insert-preview">
      <div className="pending-insert-preview-tag">
        <span>新增 · 保存后写回</span>
        {onRemove && (
          <button
            type="button"
            className="pending-insert-preview-remove"
            onClick={() => onRemove(insert.id)}
            title="撤销此插入"
          >
            撤销
          </button>
        )}
      </div>
      <div className="pending-insert-preview-body">
        {videoMatch ? (
          <div dangerouslySetInnerHTML={{ __html: `<video ${videoMatch[1]}></video>` }} />
        ) : imgMatch ? (
          <div dangerouslySetInnerHTML={{ __html: `<img ${imgMatch[1]}/>` }} />
        ) : isImageMarkdown ? (
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{insert.raw}</ReactMarkdown>
        ) : (
          <pre className="pending-insert-preview-raw">{insert.raw}</pre>
        )}
      </div>
    </div>
  );
}
