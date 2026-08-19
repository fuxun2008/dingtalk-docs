import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigation, useProducts } from './hooks/useNavigation';
import { usePageState } from './hooks/usePageState';
import { useScrollSync } from './hooks/useScrollSync';
import type { SideEditor } from './hooks/useSideEditor';
import { NavTree } from './components/NavTree';
import { ConfirmDialog } from './components/ConfirmDialog';
import { BlockPane } from './components/BlockPane';
import { FrontmatterCard } from './components/FrontmatterCard';
import { SaveBar } from './components/SaveBar';
import { TopBar } from './components/TopBar';
import { AlignmentPanel } from './components/AlignmentPanel';
import { DeletePageDialog } from './components/DeletePageDialog';
import { ImageLocalizationDialog } from './components/ImageLocalizationDialog';
import { BatchImagePanel } from './components/BatchImagePanel';
import {
  InsertBlockDialog,
  type InsertKind,
  type InsertMode,
} from './components/InsertBlockDialog';
import { LANG_LABEL } from './shared/types';
import { computeAlignment, resolveMediaTarget, type BlockAlignment } from './lib/align-blocks';
import { INSERT_AT_START } from './lib/apply-edits';
import { parseMediaRaw } from './lib/media';

type Side = 'left' | 'right';

type MediaDialogState =
  | { mode: 'insert'; side: Side; kind: InsertKind; afterBlockId: string; url?: undefined; alt?: undefined }
  | { mode: 'replace'; side: Side; kind: InsertKind; blockId: string; url: string; alt: string; raw: string };

type LocalizationDialogState = {
  targetSide: Side;
  sourceUrl: string;
  sourceAlt: string;
  initialCdnUrl: string;
  initialEnglishAlt: string;
  templateRaw: string;
} & (
  | { mode: 'replace'; blockId: string }
  | { mode: 'insert'; afterBlockId: string }
);

interface HoverState {
  side: Side;
  index: number;
}

const EMPTY_ALIGNMENT: BlockAlignment = { leftToRight: new Map(), rightToLeft: new Map() };

function peerIndex(alignment: BlockAlignment, hovered: HoverState, side: Side): number | null {
  if (hovered.side === side) return hovered.index;
  const map = side === 'right' ? alignment.leftToRight : alignment.rightToLeft;
  return map.get(hovered.index) ?? null;
}

export default function App() {
  const page = usePageState();
  const nav = useNavigation(page.ctx);
  const products = useProducts();
  const [hovered, setHovered] = useState<HoverState | null>(null);
  const [mediaDialog, setMediaDialog] = useState<MediaDialogState | null>(null);
  const [localizationDialog, setLocalizationDialog] = useState<LocalizationDialogState | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const { setContext } = page;

  // Default to the first product once the list arrives (unless the hash already set one).
  useEffect(() => {
    if (!page.ctx.product && products.products.length > 0) {
      setContext({ product: products.products[0].key });
    }
  }, [products.products, page.ctx.product, setContext]);

  const leftBlocks = page.left.content?.blocks;
  const rightBlocks = page.right.content?.blocks;
  const alignment = useMemo<BlockAlignment>(() => {
    if (!leftBlocks || !rightBlocks) return EMPTY_ALIGNMENT;
    return computeAlignment(leftBlocks, rightBlocks);
  }, [leftBlocks, rightBlocks]);

  const leftHoverIndex = hovered ? peerIndex(alignment, hovered, 'left') : null;
  const rightHoverIndex = hovered ? peerIndex(alignment, hovered, 'right') : null;

  const onHoverLeft = useCallback(
    (idx: number | null) => setHovered(idx === null ? null : { side: 'left', index: idx }),
    [],
  );
  const onHoverRight = useCallback(
    (idx: number | null) => setHovered(idx === null ? null : { side: 'right', index: idx }),
    [],
  );

  const alignLeftToRight = useCallback((i: number) => alignment.leftToRight.get(i) ?? null, [alignment]);
  const alignRightToLeft = useCallback((i: number) => alignment.rightToLeft.get(i) ?? null, [alignment]);

  const openInsertDialog = (side: Side) => (kind: InsertKind, afterBlockId: string) =>
    setMediaDialog({ mode: 'insert', side, kind, afterBlockId });

  const openReplaceDialog = (side: Side) => (blockId: string, raw: string) => {
    const parsed = parseMediaRaw(raw);
    if (!parsed) return;
    setMediaDialog({ mode: 'replace', side, kind: parsed.kind, blockId, url: parsed.url, alt: parsed.alt, raw });
  };

  const handleMediaSubmit = (raw: string) => {
    if (!mediaDialog) return;
    const editor = mediaDialog.side === 'left' ? page.left : page.right;
    if (mediaDialog.mode === 'insert') editor.insertBlock(mediaDialog.afterBlockId, raw);
    else editor.markDirty(mediaDialog.blockId, raw);
    setMediaDialog(null);
  };

  const openLocalizationDialog = (sourceSide: Side) => (sourceIndex: number, raw: string) => {
    const sourceEditor = sourceSide === 'left' ? page.left : page.right;
    const targetSide: Side = sourceSide === 'left' ? 'right' : 'left';
    const targetEditor = targetSide === 'left' ? page.left : page.right;
    const sourceBlocks = sourceEditor.content?.blocks;
    const targetBlocks = targetEditor.content?.blocks;
    const sourceMedia = parseMediaRaw(raw);
    if (!sourceBlocks || !targetBlocks || !sourceMedia || sourceMedia.kind !== 'image') return;
    if (sourceEditor.lang === 'en' || targetEditor.lang !== 'en') {
      setNotice('图片本地化需要将非英文文档放在一侧、英文（en）文档放在另一侧。');
      return;
    }

    const sourceToTarget = sourceSide === 'left' ? alignment.leftToRight : alignment.rightToLeft;
    const target = resolveMediaTarget(sourceIndex, sourceBlocks, targetBlocks, sourceToTarget);
    if (target.mode === 'replace') {
      const targetBlock = targetBlocks[target.blockIndex];
      const targetMedia = parseMediaRaw(targetBlock.raw);
      setLocalizationDialog({
        mode: 'replace',
        targetSide,
        blockId: targetBlock.id,
        sourceUrl: sourceMedia.url,
        sourceAlt: sourceMedia.alt,
        initialCdnUrl: targetMedia?.kind === 'image' ? targetMedia.url : '',
        initialEnglishAlt: targetMedia?.kind === 'image' ? targetMedia.alt : '',
        templateRaw: targetBlock.raw,
      });
      return;
    }

    const anchor = target.afterBlockIndex === null ? INSERT_AT_START : targetBlocks[target.afterBlockIndex]?.id;
    if (!anchor) {
      setNotice('无法定位英文插入位置，请先检查中英文段落对齐。');
      return;
    }
    setLocalizationDialog({
      mode: 'insert',
      targetSide,
      afterBlockId: anchor,
      sourceUrl: sourceMedia.url,
      sourceAlt: sourceMedia.alt,
      initialCdnUrl: '',
      initialEnglishAlt: '',
      templateRaw: raw,
    });
  };

  const handleLocalizationSubmit = (raw: string) => {
    if (!localizationDialog) return;
    const targetEditor = localizationDialog.targetSide === 'left' ? page.left : page.right;
    if (localizationDialog.mode === 'replace') {
      const existing = targetEditor.content?.blocks.find((block) => block.id === localizationDialog.blockId);
      if (existing?.raw === raw) {
        setNotice('英文文档已使用该 CDN 图片，无需重复写入。');
        setLocalizationDialog(null);
        return;
      }
      targetEditor.markDirty(localizationDialog.blockId, raw);
    } else {
      targetEditor.insertBlock(localizationDialog.afterBlockId, raw);
    }
    setLocalizationDialog(null);
    setNotice('英文图片已加入待保存修改，请在英文侧点击“保存”写回 MDX。');
  };

  const leftBodyRef = useRef<HTMLDivElement>(null);
  const rightBodyRef = useRef<HTMLDivElement>(null);
  const leftRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const rightRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  const { suspendSync } = useScrollSync({
    leftBody: leftBodyRef,
    rightBody: rightBodyRef,
    leftBlocks: leftRefs,
    rightBlocks: rightRefs,
    enabled: !!page.bundle,
    alignLeftToRight,
    alignRightToLeft,
  });

  useEffect(() => {
    if (!hovered) return;
    const handle = window.setTimeout(() => {
      const srcSide: Side = hovered.side;
      const peerSide: Side = srcSide === 'left' ? 'right' : 'left';
      const peerIdx = peerIndex(alignment, hovered, peerSide);
      if (peerIdx === null) return;
      const srcRefs = srcSide === 'left' ? leftRefs : rightRefs;
      const peerRefs = peerSide === 'left' ? leftRefs : rightRefs;
      const srcBody = srcSide === 'left' ? leftBodyRef : rightBodyRef;
      const peerBody = peerSide === 'left' ? leftBodyRef : rightBodyRef;
      const srcEl = srcRefs.current.get(hovered.index);
      const peerEl = peerRefs.current.get(peerIdx);
      const srcBodyEl = srcBody.current;
      const peerBodyEl = peerBody.current;
      if (!srcEl || !peerEl || !srcBodyEl || !peerBodyEl) return;
      const srcTop = srcEl.getBoundingClientRect().top - srcBodyEl.getBoundingClientRect().top;
      const peerTop = peerEl.getBoundingClientRect().top - peerBodyEl.getBoundingClientRect().top;
      const delta = peerTop - srcTop;
      if (Math.abs(delta) < 8) return;
      suspendSync(peerSide, 500);
      peerBodyEl.scrollTo({ top: peerBodyEl.scrollTop + delta, behavior: 'smooth' });
    }, 150);
    return () => window.clearTimeout(handle);
  }, [hovered, alignment, suspendSync]);

  useEffect(() => {
    leftRefs.current.clear();
    rightRefs.current.clear();
    setHovered(null);
    if (leftBodyRef.current) leftBodyRef.current.scrollTop = 0;
    if (rightBodyRef.current) rightBodyRef.current.scrollTop = 0;
  }, [page.slug]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && (e.key === 's' || e.key === 'S')) {
        if (page.isDirty) {
          e.preventDefault();
          page.saveAll();
        }
        return;
      }
      if (e.target instanceof HTMLElement && ['TEXTAREA', 'INPUT', 'SELECT'].includes(e.target.tagName)) return;
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      if (!page.slug) return;
      const idx = nav.flatPages.findIndex((p) => p.slug === page.slug);
      if (idx < 0) return;
      const nextIdx = e.key === 'ArrowDown' ? idx + 1 : idx - 1;
      const next = nav.flatPages[nextIdx];
      if (!next || next.missing) return;
      e.preventDefault();
      page.navigate(next.slug);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [nav.flatPages, page]);

  const handleDelete = useCallback(async () => {
    const idx = nav.flatPages.findIndex((p) => p.slug === page.slug);
    const result = await page.deleteCurrent();
    setDeleteOpen(false);
    setNotice(
      `已删除「${result.slug}」：${result.deletedFiles.length} 个 mdx、` +
        `${result.removedNavLines.length} 处导航、${result.deletedImages.length} 张孤儿图。`,
    );
    await nav.reload();
    const next = nav.flatPages[idx + 1] ?? nav.flatPages[idx - 1];
    if (next && next.slug !== result.slug && !next.missing) page.navigate(next.slug);
  }, [nav, page]);

  return (
    <div className="app-shell">
      <TopBar
        products={products.products}
        productsLoading={products.loading}
        ctx={page.ctx}
        onChange={page.setContext}
        canDelete={!!page.slug}
        onDeletePage={() => setDeleteOpen(true)}
        onOpenImageBatch={() => setBatchOpen(true)}
      />

      {notice && (
        <div className="app-notice" role="status">
          {notice}
          <button type="button" className="app-notice-close" onClick={() => setNotice(null)}>
            ×
          </button>
        </div>
      )}

      <div className="app-main">
        <aside className="nav-pane">
          <div className="nav-pane-toolbar">
            <AlignmentPanel ctx={page.ctx} currentSlug={page.slug} onNavigate={page.navigate} />
            <button
              type="button"
              className="nav-reload-button"
              onClick={() => { nav.reload(); }}
              disabled={nav.loading}
              title="重新读取磁盘上的 docs.json 与 mdx（切分支或拉取后用）"
            >
              <span aria-hidden="true">↻</span>
              <span>刷新</span>
            </button>
          </div>
          {nav.loading && <div className="nav-pane-placeholder">加载导航中…</div>}
          {nav.error && <div className="nav-pane-placeholder error">{nav.error}</div>}
          {!nav.loading && !nav.error && (
            <NavTree
              tree={nav.tree}
              currentSlug={page.slug}
              dirtySlug={page.isDirty ? page.slug : null}
              onSelect={page.navigate}
            />
          )}
        </aside>

        <main className="dual-pane">
          <PaneShell
            label={`左 · ${LANG_LABEL[page.ctx.leftLang]}${page.left.content ? ' · ' + page.left.content.blocks.length + ' blocks' : ''}`}
            side="left"
            bodyRef={leftBodyRef}
            headerExtra={
              <SaveBar
                dirtyCount={page.left.dirtyCount}
                saving={page.left.saving}
                error={page.left.saveError}
                onSave={() => { page.left.save(); }}
              />
            }
          >
            <PaneContent
              page={page}
              editor={page.left}
              side="left"
              hoveredIndex={leftHoverIndex}
              onHover={onHoverLeft}
              registerRef={(i, el) => setRef(leftRefs, i, el)}
              onOpenInsertDialog={openInsertDialog('left')}
              onOpenReplaceDialog={openReplaceDialog('left')}
              onLocalizeMedia={page.left.lang !== 'en' && page.right.lang === 'en' ? openLocalizationDialog('left') : undefined}
            />
          </PaneShell>
          <PaneShell
            label={`右 · ${LANG_LABEL[page.ctx.rightLang]}${page.right.content ? ' · ' + page.right.content.blocks.length + ' blocks' : ''}`}
            side="right"
            bodyRef={rightBodyRef}
            headerExtra={
              <SaveBar
                dirtyCount={page.right.dirtyCount}
                saving={page.right.saving}
                error={page.right.saveError}
                onSave={() => { page.right.save(); }}
              />
            }
          >
            <PaneContent
              page={page}
              editor={page.right}
              side="right"
              hoveredIndex={rightHoverIndex}
              onHover={onHoverRight}
              registerRef={(i, el) => setRef(rightRefs, i, el)}
              onOpenInsertDialog={openInsertDialog('right')}
              onOpenReplaceDialog={openReplaceDialog('right')}
              onLocalizeMedia={page.right.lang !== 'en' && page.left.lang === 'en' ? openLocalizationDialog('right') : undefined}
            />
          </PaneShell>
        </main>
      </div>

      <ConfirmDialog
        open={!!page.pendingNav}
        title={`当前页有 ${page.dirtyCount} 处未保存修改`}
        message="切换前请选择如何处理这些修改。"
        onSave={page.confirmSave}
        onDiscard={page.confirmDiscard}
        onCancel={page.cancelNavigate}
      />

      <DeletePageDialog
        open={deleteOpen}
        slug={page.slug ?? ''}
        onConfirm={handleDelete}
        onCancel={() => setDeleteOpen(false)}
      />

      <InsertBlockDialog
        open={!!mediaDialog}
        kind={mediaDialog?.kind ?? 'image'}
        mode={(mediaDialog?.mode ?? 'insert') as InsertMode}
        initialUrl={mediaDialog?.mode === 'replace' ? mediaDialog.url : ''}
        initialAlt={mediaDialog?.mode === 'replace' ? mediaDialog.alt : ''}
        initialRaw={mediaDialog?.mode === 'replace' ? mediaDialog.raw : ''}
        onSubmit={handleMediaSubmit}
        onCancel={() => setMediaDialog(null)}
      />

      <ImageLocalizationDialog
        open={!!localizationDialog}
        sourceUrl={localizationDialog?.sourceUrl ?? ''}
        sourceAlt={localizationDialog?.sourceAlt ?? ''}
        initialCdnUrl={localizationDialog?.initialCdnUrl ?? ''}
        initialEnglishAlt={localizationDialog?.initialEnglishAlt ?? ''}
        templateRaw={localizationDialog?.templateRaw ?? ''}
        targetExists={localizationDialog?.mode === 'replace'}
        onSubmit={handleLocalizationSubmit}
        onCancel={() => setLocalizationDialog(null)}
      />

      <BatchImagePanel
        open={batchOpen}
        defaultScope={page.slug?.includes('/') ? page.slug.slice(0, page.slug.lastIndexOf('/')) : 'yida/intro'}
        onClose={() => setBatchOpen(false)}
        onApplied={(result) => {
          setNotice(`批处理已回写 ${result.appliedIds.length} 个媒体，修改 ${result.changedFiles.length} 个英文 MDX；请刷新当前页面查看。`);
          void nav.reload();
        }}
      />
    </div>
  );
}

function setRef(refs: React.MutableRefObject<Map<number, HTMLDivElement>>, index: number, el: HTMLDivElement | null) {
  if (el) refs.current.set(index, el);
  else refs.current.delete(index);
}

interface PaneShellProps {
  label: string;
  side: Side;
  bodyRef: React.RefObject<HTMLDivElement>;
  children: React.ReactNode;
  headerExtra?: React.ReactNode;
}

function PaneShell({ label, side, bodyRef, children, headerExtra }: PaneShellProps) {
  return (
    <section className={`pane pane-${side}`}>
      <div className="pane-header">
        <span className="pane-header-label">{label}</span>
        {headerExtra && <span className="pane-header-extra">{headerExtra}</span>}
      </div>
      <div className="pane-body" ref={bodyRef}>
        {children}
      </div>
    </section>
  );
}

interface PaneContentProps {
  page: ReturnType<typeof usePageState>;
  editor: SideEditor;
  side: Side;
  hoveredIndex: number | null;
  onHover: (index: number | null) => void;
  registerRef: (index: number, el: HTMLDivElement | null) => void;
  onOpenInsertDialog: (kind: InsertKind, afterBlockId: string) => void;
  onOpenReplaceDialog: (blockId: string, raw: string) => void;
  onLocalizeMedia?: (index: number, raw: string) => void;
}

function PaneContent({
  page,
  editor,
  side,
  hoveredIndex,
  onHover,
  registerRef,
  onOpenInsertDialog,
  onOpenReplaceDialog,
  onLocalizeMedia,
}: PaneContentProps) {
  if (page.loading) return <div className="pane-placeholder">加载中…</div>;
  if (page.error) return <div className="pane-placeholder error">{page.error}</div>;
  if (!page.slug || !page.bundle) return <div className="pane-placeholder">从左侧选择文件开始校对</div>;
  if (!editor.content) {
    return <div className="pane-placeholder">该语言（{LANG_LABEL[editor.lang]}）暂无对应文件</div>;
  }
  return (
    <>
      <FrontmatterCard
        meta={editor.content.frontmatter}
        side={side}
        editable
        dirty={editor.dirty}
        onChange={editor.markDirty}
      />
      <BlockPane
        blocks={editor.content.blocks}
        side={side}
        editable
        dirty={editor.dirty}
        inserts={editor.inserts}
        hoveredIndex={hoveredIndex}
        onHoverBlock={onHover}
        onCommitBlock={editor.markDirty}
        onRestoreBlock={editor.unmarkDirty}
        onOpenInsertDialog={onOpenInsertDialog}
        onOpenReplaceDialog={onOpenReplaceDialog}
        onLocalizeMedia={onLocalizeMedia}
        onRemoveInsert={editor.removeInsert}
        registerBlockRef={registerRef}
      />
    </>
  );
}
