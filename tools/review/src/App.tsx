import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigation } from './hooks/useNavigation';
import { usePageState } from './hooks/usePageState';
import { useScrollSync } from './hooks/useScrollSync';
import { NavTree } from './components/NavTree';
import { ConfirmDialog } from './components/ConfirmDialog';
import { BlockPane } from './components/BlockPane';
import { FrontmatterCard } from './components/FrontmatterCard';
import { SaveBar } from './components/SaveBar';
import { AlignmentPanel } from './components/AlignmentPanel';
import { InsertBlockDialog, type InsertKind } from './components/InsertBlockDialog';
import { computeAlignment, type BlockAlignment } from './lib/align-blocks';

interface InsertDialogState {
  kind: InsertKind;
  afterBlockId: string;
}

type Side = 'zh' | 'en';

interface HoverState {
  side: Side;
  index: number;
}

const EMPTY_ALIGNMENT: BlockAlignment = { zhToEn: new Map(), enToZh: new Map() };

function peerIndex(alignment: BlockAlignment, hovered: HoverState, side: Side): number | null {
  if (hovered.side === side) return hovered.index;
  const map = side === 'en' ? alignment.zhToEn : alignment.enToZh;
  return map.get(hovered.index) ?? null;
}

export default function App() {
  const nav = useNavigation();
  const page = usePageState();
  const [hovered, setHovered] = useState<HoverState | null>(null);
  const [insertDialog, setInsertDialog] = useState<InsertDialogState | null>(null);

  const alignment = useMemo<BlockAlignment>(() => {
    if (!page.bundle) return EMPTY_ALIGNMENT;
    return computeAlignment(page.bundle.zh.blocks, page.bundle.en.blocks);
  }, [page.bundle]);

  const zhHoverIndex = hovered ? peerIndex(alignment, hovered, 'zh') : null;
  const enHoverIndex = hovered ? peerIndex(alignment, hovered, 'en') : null;

  const onHoverZh = useCallback(
    (idx: number | null) => setHovered(idx === null ? null : { side: 'zh', index: idx }),
    [],
  );
  const onHoverEn = useCallback(
    (idx: number | null) => setHovered(idx === null ? null : { side: 'en', index: idx }),
    [],
  );

  const alignLeftToRight = useCallback(
    (i: number) => alignment.zhToEn.get(i) ?? null,
    [alignment],
  );
  const alignRightToLeft = useCallback(
    (i: number) => alignment.enToZh.get(i) ?? null,
    [alignment],
  );

  const openInsertDialog = (kind: InsertKind, afterBlockId: string) => {
    setInsertDialog({ kind, afterBlockId });
  };
  const handleInsertSubmit = (raw: string) => {
    if (!insertDialog) return;
    page.insertBlock(insertDialog.afterBlockId, raw);
    setInsertDialog(null);
  };
  const closeInsertDialog = () => setInsertDialog(null);

  const zhBodyRef = useRef<HTMLDivElement>(null);
  const enBodyRef = useRef<HTMLDivElement>(null);
  const zhRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const enRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  const { suspendSync } = useScrollSync({
    leftBody: zhBodyRef,
    rightBody: enBodyRef,
    leftBlocks: zhRefs,
    rightBlocks: enRefs,
    enabled: !!page.bundle,
    alignLeftToRight,
    alignRightToLeft,
  });

  useEffect(() => {
    if (!hovered) return;
    const handle = window.setTimeout(() => {
      const srcSide: Side = hovered.side;
      const peerSide: Side = srcSide === 'zh' ? 'en' : 'zh';
      const peerIdx = peerIndex(alignment, hovered, peerSide);
      if (peerIdx === null) return;
      const srcRefs = srcSide === 'zh' ? zhRefs : enRefs;
      const peerRefs = peerSide === 'zh' ? zhRefs : enRefs;
      const srcBody = srcSide === 'zh' ? zhBodyRef : enBodyRef;
      const peerBody = peerSide === 'zh' ? zhBodyRef : enBodyRef;
      const srcEl = srcRefs.current.get(hovered.index);
      const peerEl = peerRefs.current.get(peerIdx);
      const srcBodyEl = srcBody.current;
      const peerBodyEl = peerBody.current;
      if (!srcEl || !peerEl || !srcBodyEl || !peerBodyEl) return;
      const srcTop = srcEl.getBoundingClientRect().top - srcBodyEl.getBoundingClientRect().top;
      const peerTop = peerEl.getBoundingClientRect().top - peerBodyEl.getBoundingClientRect().top;
      const delta = peerTop - srcTop;
      if (Math.abs(delta) < 8) return;
      suspendSync(peerSide === 'zh' ? 'left' : 'right', 500);
      peerBodyEl.scrollTo({ top: peerBodyEl.scrollTop + delta, behavior: 'smooth' });
    }, 150);
    return () => window.clearTimeout(handle);
  }, [hovered, alignment, suspendSync]);

  useEffect(() => {
    zhRefs.current.clear();
    enRefs.current.clear();
    setHovered(null);
    if (zhBodyRef.current) zhBodyRef.current.scrollTop = 0;
    if (enBodyRef.current) enBodyRef.current.scrollTop = 0;
  }, [page.slug]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && (e.key === 's' || e.key === 'S')) {
        if (page.isDirty && !page.saving) {
          e.preventDefault();
          page.save();
        }
        return;
      }
      if (e.target instanceof HTMLElement && ['TEXTAREA', 'INPUT'].includes(e.target.tagName)) return;
      if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
      if (!page.slug) return;
      const idx = nav.flatPages.findIndex((p) => p.slug === page.slug);
      if (idx < 0) return;
      const nextIdx = e.key === 'ArrowDown' ? idx + 1 : idx - 1;
      const next = nav.flatPages[nextIdx];
      if (!next) return;
      e.preventDefault();
      page.navigate(next.slug);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [nav.flatPages, page]);

  const registerZhRef = (index: number, el: HTMLDivElement | null) => {
    if (el) zhRefs.current.set(index, el);
    else zhRefs.current.delete(index);
  };
  const registerEnRef = (index: number, el: HTMLDivElement | null) => {
    if (el) enRefs.current.set(index, el);
    else enRefs.current.delete(index);
  };

  return (
    <div className="app-shell">
      <aside className="nav-pane">
        <div className="nav-pane-toolbar">
          <AlignmentPanel currentSlug={page.slug} onNavigate={page.navigate} />
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
          label={`中文（zh）${page.bundle ? '· ' + page.bundle.zh.blocks.length + ' blocks' : ''}`}
          side="zh"
          bodyRef={zhBodyRef}
        >
          <PaneContent
            page={page}
            side="zh"
            hoveredIndex={zhHoverIndex}
            onHover={onHoverZh}
            registerRef={registerZhRef}
          />
        </PaneShell>
        <PaneShell
          label={`英文（en）${page.bundle ? '· ' + page.bundle.en.blocks.length + ' blocks' : ''}`}
          side="en"
          bodyRef={enBodyRef}
          headerExtra={
            <SaveBar
              dirtyCount={page.dirtyCount}
              saving={page.saving}
              error={page.saveError}
              onSave={() => { page.save(); }}
            />
          }
        >
          <PaneContent
            page={page}
            side="en"
            hoveredIndex={enHoverIndex}
            onHover={onHoverEn}
            registerRef={registerEnRef}
            onOpenInsertDialog={openInsertDialog}
          />
        </PaneShell>
      </main>

      <ConfirmDialog
        open={!!page.pendingTarget}
        title={`当前页有 ${page.dirtyCount} 处未保存修改`}
        message={`切换到「${page.pendingTarget ?? ''}」前，请选择如何处理这些修改。`}
        onSave={page.confirmSave}
        onDiscard={page.confirmDiscard}
        onCancel={page.cancelNavigate}
      />

      <InsertBlockDialog
        open={!!insertDialog}
        kind={insertDialog?.kind ?? 'image'}
        onSubmit={handleInsertSubmit}
        onCancel={closeInsertDialog}
      />
    </div>
  );
}

interface PaneShellProps {
  label: string;
  side: 'zh' | 'en';
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
  side: 'zh' | 'en';
  hoveredIndex: number | null;
  onHover: (index: number | null) => void;
  registerRef: (index: number, el: HTMLDivElement | null) => void;
  onOpenInsertDialog?: (kind: InsertKind, afterBlockId: string) => void;
}

function PaneContent({ page, side, hoveredIndex, onHover, registerRef, onOpenInsertDialog }: PaneContentProps) {
  if (page.loading) return <div className="pane-placeholder">加载中…</div>;
  if (page.error) return <div className="pane-placeholder error">{page.error}</div>;
  if (!page.slug || !page.bundle) return <div className="pane-placeholder">从左侧选择文件开始校对</div>;
  const content = page.bundle[side];
  return (
    <>
      <FrontmatterCard
        meta={content.frontmatter}
        side={side}
        dirty={page.dirty}
        onChange={side === 'en' ? page.markDirty : undefined}
      />
      <BlockPane
        blocks={content.blocks}
        side={side}
        dirty={page.dirty}
        inserts={side === 'en' ? page.inserts : undefined}
        hoveredIndex={hoveredIndex}
        onHoverBlock={onHover}
        onCommitBlock={side === 'en' ? page.markDirty : undefined}
        onRestoreBlock={side === 'en' ? page.unmarkDirty : undefined}
        onOpenInsertDialog={side === 'en' ? onOpenInsertDialog : undefined}
        onRemoveInsert={side === 'en' ? page.removeInsert : undefined}
        registerBlockRef={registerRef}
      />
    </>
  );
}
