import { useCallback, useEffect, useRef, useState } from 'react';
import type { Lang, PageBundle } from '../shared/types';
import { ALL_LANGS } from '../shared/types';
import { useSideEditor, type SideEditor } from './useSideEditor';

export interface ReviewContext {
  product: string;
  leftLang: Lang;
  rightLang: Lang;
}

type PendingNav =
  | { kind: 'slug'; slug: string }
  | { kind: 'ctx'; ctx: ReviewContext; slug: string | null };

export interface DeleteResult {
  slug: string;
  deletedFiles: string[];
  removedNavLines: string[];
  deletedImages: string[];
}

export interface PageState {
  ctx: ReviewContext;
  slug: string | null;
  bundle: PageBundle | null;
  loading: boolean;
  error: string | null;
  left: SideEditor;
  right: SideEditor;
  isDirty: boolean;
  dirtyCount: number;
  pendingNav: PendingNav | null;
  setContext: (partial: Partial<ReviewContext>) => void;
  navigate: (slug: string) => void;
  confirmDiscard: () => void;
  confirmSave: () => Promise<void>;
  cancelNavigate: () => void;
  reload: () => Promise<void>;
  saveAll: () => Promise<boolean>;
  deleteCurrent: () => Promise<DeleteResult>;
}

const DEFAULT_CTX: ReviewContext = { product: '', leftLang: 'zh', rightLang: 'en' };

function parseHash(): { ctx: ReviewContext; slug: string | null } {
  const h = window.location.hash;
  if (!h.startsWith('#/')) return { ctx: { ...DEFAULT_CTX }, slug: null };
  const [pathPart, queryPart] = h.slice(2).split('?');
  const params = new URLSearchParams(queryPart ?? '');
  const lang = (v: string | null, fb: Lang): Lang => (v && ALL_LANGS.includes(v as Lang) ? (v as Lang) : fb);
  return {
    ctx: {
      product: pathPart || '',
      leftLang: lang(params.get('left'), 'zh'),
      rightLang: lang(params.get('right'), 'en'),
    },
    slug: params.get('slug') || null,
  };
}

function writeHash(ctx: ReviewContext, slug: string | null): void {
  const params = new URLSearchParams();
  params.set('left', ctx.leftLang);
  params.set('right', ctx.rightLang);
  if (slug) params.set('slug', slug);
  const next = `#/${ctx.product}?${params.toString()}`;
  if (window.location.hash !== next) {
    history.replaceState(null, '', next);
  }
}

async function fetchBundle(slug: string, ctx: ReviewContext): Promise<PageBundle> {
  const params = new URLSearchParams({ slug, left: ctx.leftLang, right: ctx.rightLang });
  const r = await fetch(`/api/page?${params.toString()}`);
  const data = await r.json();
  if (!r.ok || data.error) throw new Error(data.error ?? `HTTP ${r.status}`);
  return data as PageBundle;
}

export function usePageState(): PageState {
  const initialRef = useRef(parseHash());
  const initial = initialRef.current;
  const [ctx, setCtx] = useState<ReviewContext>(initial.ctx);
  const [slug, setSlug] = useState<string | null>(initial.slug);
  const [bundle, setBundle] = useState<PageBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingNav, setPendingNav] = useState<PendingNav | null>(null);

  // Refs mirror latest state so fetch callbacks stay stable across renders.
  const ctxRef = useRef(ctx);
  ctxRef.current = ctx;
  const slugRef = useRef(slug);
  slugRef.current = slug;

  const loadPage = useCallback(async (target: string, nextCtx: ReviewContext) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchBundle(target, nextCtx);
      setBundle(data);
      setSlug(target);
      writeHash(nextCtx, target);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'load failed');
    } finally {
      setLoading(false);
    }
  }, []);

  /** Re-read one side from disk and patch only that side (keeps the other side's edits stable). */
  const refreshSide = useCallback(async (side: 'left' | 'right') => {
    const s = slugRef.current;
    if (!s) return;
    const fresh = await fetchBundle(s, ctxRef.current);
    setBundle((prev) => {
      if (!prev) return fresh;
      return side === 'left' ? { ...prev, left: fresh.left } : { ...prev, right: fresh.right };
    });
  }, []);

  const refreshLeft = useCallback(() => refreshSide('left'), [refreshSide]);
  const refreshRight = useCallback(() => refreshSide('right'), [refreshSide]);

  const left = useSideEditor({ side: 'left', lang: ctx.leftLang, slug, content: bundle?.left ?? null, refresh: refreshLeft });
  const right = useSideEditor({ side: 'right', lang: ctx.rightLang, slug, content: bundle?.right ?? null, refresh: refreshRight });

  const dirtyCount = left.dirtyCount + right.dirtyCount;
  const dirtyCountRef = useRef(dirtyCount);
  dirtyCountRef.current = dirtyCount;

  // Initial load if the hash already points at a page.
  useEffect(() => {
    if (initial.slug && initial.ctx.product) loadPage(initial.slug, initial.ctx);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (dirtyCount > 0) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirtyCount]);

  const applyContext = useCallback(
    (next: ReviewContext, targetSlug: string | null) => {
      setCtx(next);
      ctxRef.current = next;
      if (targetSlug) {
        loadPage(targetSlug, next);
      } else {
        setSlug(null);
        setBundle(null);
        writeHash(next, null);
      }
    },
    [loadPage],
  );

  // Follow external hash changes (browser back/forward, manual URL edits). Our own
  // navigation uses history.replaceState, which does not fire hashchange — so any event
  // here is external. When the page is dirty, revert the URL and surface the confirm dialog.
  const syncFromHash = useCallback(() => {
    const parsed = parseHash();
    if (!parsed.ctx.product) return;
    const sameCtx =
      parsed.ctx.product === ctxRef.current.product &&
      parsed.ctx.leftLang === ctxRef.current.leftLang &&
      parsed.ctx.rightLang === ctxRef.current.rightLang;
    const sameSlug = (parsed.slug ?? null) === slugRef.current;
    if (sameCtx && sameSlug) return;
    if (dirtyCountRef.current > 0) {
      writeHash(ctxRef.current, slugRef.current);
      setPendingNav({ kind: 'ctx', ctx: parsed.ctx, slug: parsed.slug });
      return;
    }
    applyContext(parsed.ctx, parsed.slug);
  }, [applyContext]);

  useEffect(() => {
    window.addEventListener('hashchange', syncFromHash);
    return () => window.removeEventListener('hashchange', syncFromHash);
  }, [syncFromHash]);

  const setContext = useCallback(
    (partial: Partial<ReviewContext>) => {
      const next = { ...ctxRef.current, ...partial };
      // Switching product invalidates the current slug; lang changes keep it.
      const keepSlug = partial.product === undefined || partial.product === ctxRef.current.product;
      const targetSlug = keepSlug ? slugRef.current : null;
      if (dirtyCount > 0) {
        setPendingNav({ kind: 'ctx', ctx: next, slug: targetSlug });
        return;
      }
      applyContext(next, targetSlug);
    },
    [dirtyCount, applyContext],
  );

  const navigate = useCallback(
    (target: string) => {
      if (target === slugRef.current) return;
      if (dirtyCount > 0) {
        setPendingNav({ kind: 'slug', slug: target });
        return;
      }
      loadPage(target, ctxRef.current);
    },
    [dirtyCount, loadPage],
  );

  const saveAll = useCallback(async (): Promise<boolean> => {
    const a = await left.save();
    const b = await right.save();
    return a && b;
  }, [left, right]);

  const runPending = useCallback(
    (nav: PendingNav) => {
      if (nav.kind === 'slug') loadPage(nav.slug, ctxRef.current);
      else applyContext(nav.ctx, nav.slug);
    },
    [loadPage, applyContext],
  );

  const confirmDiscard = useCallback(() => {
    if (!pendingNav) return;
    const nav = pendingNav;
    setPendingNav(null);
    left.clear();
    right.clear();
    runPending(nav);
  }, [pendingNav, left, right, runPending]);

  const confirmSave = useCallback(async () => {
    if (!pendingNav) return;
    const nav = pendingNav;
    const ok = await saveAll();
    if (!ok) return;
    setPendingNav(null);
    runPending(nav);
  }, [pendingNav, saveAll, runPending]);

  const cancelNavigate = useCallback(() => setPendingNav(null), []);

  const reload = useCallback(async () => {
    if (slugRef.current) await loadPage(slugRef.current, ctxRef.current);
  }, [loadPage]);

  const deleteCurrent = useCallback(async (): Promise<DeleteResult> => {
    const s = slugRef.current;
    if (!s) throw new Error('no page selected');
    const r = await fetch('/api/page', {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slug: s }),
    });
    const data = await r.json();
    if (!r.ok || data.error) throw new Error(data.error ?? `HTTP ${r.status}`);
    left.clear();
    right.clear();
    setSlug(null);
    setBundle(null);
    writeHash(ctxRef.current, null);
    return data as DeleteResult;
  }, [left, right]);

  return {
    ctx,
    slug,
    bundle,
    loading,
    error,
    left,
    right,
    isDirty: dirtyCount > 0,
    dirtyCount,
    pendingNav,
    setContext,
    navigate,
    confirmDiscard,
    confirmSave,
    cancelNavigate,
    reload,
    saveAll,
    deleteCurrent,
  };
}
