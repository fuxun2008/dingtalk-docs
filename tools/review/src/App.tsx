import { useEffect, useRef, useState } from 'react';
import { useNavigation } from './hooks/useNavigation';
import { usePageState } from './hooks/usePageState';
import { useScrollSync } from './hooks/useScrollSync';
import { NavTree } from './components/NavTree';
import { ConfirmDialog } from './components/ConfirmDialog';
import { BlockPane } from './components/BlockPane';
import { FrontmatterCard } from './components/FrontmatterCard';
import { SaveBar } from './components/SaveBar';
import { AlignmentPanel } from './components/AlignmentPanel';

export default function App() {
  const nav = useNavigation();
  const page = usePageState();
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  const zhBodyRef = useRef<HTMLDivElement>(null);
  const enBodyRef = useRef<HTMLDivElement>(null);
  const zhRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const enRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  useScrollSync({
    leftBody: zhBodyRef,
    rightBody: enBodyRef,
    leftBlocks: zhRefs,
    rightBlocks: enRefs,
    enabled: !!page.bundle,
  });

  useEffect(() => {
    zhRefs.current.clear();
    enRefs.current.clear();
    setHoveredIndex(null);
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
            hoveredIndex={hoveredIndex}
            onHover={setHoveredIndex}
            registerRef={registerZhRef}
          />
        </PaneShell>
        <PaneShell
          label={`英文（en）${page.bundle ? '· ' + page.bundle.en.blocks.length + ' blocks' : ''}`}
          side="en"
          bodyRef={enBodyRef}
          headerExtra={
            <SaveBar
              dirtyCount={page.dirty.size}
              saving={page.saving}
              error={page.saveError}
              onSave={() => { page.save(); }}
            />
          }
        >
          <PaneContent
            page={page}
            side="en"
            hoveredIndex={hoveredIndex}
            onHover={setHoveredIndex}
            registerRef={registerEnRef}
          />
        </PaneShell>
      </main>

      <ConfirmDialog
        open={!!page.pendingTarget}
        title={`当前页有 ${page.dirty.size} 处未保存修改`}
        message={`切换到「${page.pendingTarget ?? ''}」前，请选择如何处理这些修改。`}
        onSave={page.confirmSave}
        onDiscard={page.confirmDiscard}
        onCancel={page.cancelNavigate}
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
}

function PaneContent({ page, side, hoveredIndex, onHover, registerRef }: PaneContentProps) {
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
        hoveredIndex={hoveredIndex}
        onHoverBlock={onHover}
        onCommitBlock={side === 'en' ? page.markDirty : undefined}
        registerBlockRef={registerRef}
      />
    </>
  );
}
