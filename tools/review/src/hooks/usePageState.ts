import { useCallback, useEffect, useState } from 'react';
import type { PageBundle } from '../shared/types';
import { applyEdits } from '../lib/apply-edits';

interface PageState {
  slug: string | null;
  bundle: PageBundle | null;
  loading: boolean;
  error: string | null;
  dirty: Map<string, string>;
  isDirty: boolean;
  pendingTarget: string | null;
  saving: boolean;
  saveError: string | null;
  navigate: (target: string) => void;
  markDirty: (blockId: string, newRaw: string) => void;
  clearDirty: () => void;
  confirmDiscard: () => void;
  confirmSave: () => Promise<void>;
  cancelNavigate: () => void;
  reload: () => Promise<void>;
  save: () => Promise<boolean>;
}

function readHashSlug(): string | null {
  const h = window.location.hash;
  if (!h.startsWith('#/')) return null;
  const slug = h.slice(2);
  return slug || null;
}

function writeHashSlug(slug: string): void {
  const next = `#/${slug}`;
  if (window.location.hash !== next) window.location.hash = next;
}

async function fetchPage(slug: string): Promise<PageBundle> {
  const r = await fetch(`/api/page?slug=${encodeURIComponent(slug)}`);
  const data = await r.json();
  if (!r.ok || data.error) throw new Error(data.error ?? `HTTP ${r.status}`);
  return data as PageBundle;
}

export function usePageState(): PageState {
  const [slug, setSlug] = useState<string | null>(() => readHashSlug());
  const [bundle, setBundle] = useState<PageBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState<Map<string, string>>(new Map());
  const [pendingTarget, setPendingTarget] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const loadPage = useCallback(async (target: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPage(target);
      setBundle(data);
      setSlug(target);
      setDirty(new Map());
      writeHashSlug(target);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'load failed');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (slug) loadPage(slug);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onHashChange = () => {
      const next = readHashSlug();
      if (next && next !== slug) {
        if (dirty.size > 0) {
          setPendingTarget(next);
          writeHashSlug(slug ?? '');
        } else {
          loadPage(next);
        }
      }
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, [slug, dirty.size, loadPage]);

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (dirty.size > 0) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [dirty.size]);

  const navigate = useCallback(
    (target: string) => {
      if (target === slug) return;
      if (dirty.size === 0) {
        loadPage(target);
      } else {
        setPendingTarget(target);
      }
    },
    [slug, dirty.size, loadPage],
  );

  const markDirty = useCallback((blockId: string, newRaw: string) => {
    setDirty((prev) => {
      const next = new Map(prev);
      next.set(blockId, newRaw);
      return next;
    });
  }, []);

  const clearDirty = useCallback(() => setDirty(new Map()), []);

  const confirmDiscard = useCallback(() => {
    if (!pendingTarget) return;
    const target = pendingTarget;
    setPendingTarget(null);
    setDirty(new Map());
    loadPage(target);
  }, [pendingTarget, loadPage]);

  const save = useCallback(async (): Promise<boolean> => {
    if (!slug || !bundle || dirty.size === 0) return true;
    setSaving(true);
    setSaveError(null);
    try {
      const en = bundle.en;
      const { content, skipped } = applyEdits({
        content: en.content,
        blocks: en.blocks,
        frontmatter: en.frontmatter,
        dirty,
      });
      if (skipped.length > 0) throw new Error(`无法定位的修改：${skipped.join(', ')}`);
      const r = await fetch('/api/page', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slug, lang: 'en', content }),
      });
      const data = await r.json();
      if (!r.ok || data.error) throw new Error(data.error ?? `HTTP ${r.status}`);
      const fresh = await fetchPage(slug);
      setBundle(fresh);
      setDirty(new Map());
      return true;
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'save failed');
      return false;
    } finally {
      setSaving(false);
    }
  }, [slug, bundle, dirty]);

  const confirmSave = useCallback(async () => {
    if (!pendingTarget) return;
    const target = pendingTarget;
    const ok = await save();
    if (!ok) return;
    setPendingTarget(null);
    loadPage(target);
  }, [pendingTarget, save, loadPage]);

  const cancelNavigate = useCallback(() => setPendingTarget(null), []);

  const reload = useCallback(async () => {
    if (slug) await loadPage(slug);
  }, [slug, loadPage]);

  return {
    slug,
    bundle,
    loading,
    error,
    dirty,
    isDirty: dirty.size > 0,
    pendingTarget,
    saving,
    saveError,
    navigate,
    markDirty,
    clearDirty,
    confirmDiscard,
    confirmSave,
    cancelNavigate,
    reload,
    save,
  };
}
