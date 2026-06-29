import { useCallback, useEffect, useRef, useState } from 'react';
import { nanoid } from 'nanoid';
import type { Lang, PageContent } from '../shared/types';
import { applyEdits, type PendingInsert } from '../lib/apply-edits';

export type Side = 'left' | 'right';

export interface SideEditor {
  side: Side;
  lang: Lang;
  content: PageContent | null;
  dirty: Map<string, string>;
  inserts: Map<string, PendingInsert>;
  dirtyCount: number;
  saving: boolean;
  saveError: string | null;
  markDirty: (blockId: string, newRaw: string) => void;
  unmarkDirty: (blockId: string) => void;
  insertBlock: (afterBlockId: string, raw: string) => string;
  removeInsert: (insertId: string) => void;
  clear: () => void;
  save: () => Promise<boolean>;
}

interface UseSideEditorArgs {
  side: Side;
  lang: Lang;
  slug: string | null;
  content: PageContent | null;
  /** Re-read this side from disk after a successful write (keeps the other side stable). */
  refresh: () => Promise<void>;
}

/** Owns the editing state (dirty blocks + pending inserts) for a single pane. */
export function useSideEditor({ side, lang, slug, content, refresh }: UseSideEditorArgs): SideEditor {
  const [dirty, setDirty] = useState<Map<string, string>>(new Map());
  const [inserts, setInserts] = useState<Map<string, PendingInsert>>(new Map());
  const insertSeqRef = useRef(0);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Reset edits whenever the page or this side's language changes.
  useEffect(() => {
    setDirty(new Map());
    setInserts(new Map());
    setSaveError(null);
  }, [slug, lang]);

  const dirtyCount = dirty.size + inserts.size;

  const markDirty = useCallback((blockId: string, newRaw: string) => {
    setDirty((prev) => {
      const next = new Map(prev);
      next.set(blockId, newRaw);
      return next;
    });
  }, []);

  const unmarkDirty = useCallback((blockId: string) => {
    setDirty((prev) => {
      if (!prev.has(blockId)) return prev;
      const next = new Map(prev);
      next.delete(blockId);
      return next;
    });
  }, []);

  const insertBlock = useCallback((afterBlockId: string, raw: string): string => {
    const id = `__insert_${nanoid(8)}`;
    insertSeqRef.current += 1;
    const seq = insertSeqRef.current;
    setInserts((prev) => {
      const next = new Map(prev);
      next.set(id, { afterBlockId, raw, seq });
      return next;
    });
    return id;
  }, []);

  const removeInsert = useCallback((insertId: string) => {
    setInserts((prev) => {
      if (!prev.has(insertId)) return prev;
      const next = new Map(prev);
      next.delete(insertId);
      return next;
    });
  }, []);

  const clear = useCallback(() => {
    setDirty(new Map());
    setInserts(new Map());
    setSaveError(null);
  }, []);

  const save = useCallback(async (): Promise<boolean> => {
    if (!slug || !content || dirtyCount === 0) return true;
    setSaving(true);
    setSaveError(null);
    try {
      const { content: nextContent, skipped } = applyEdits({
        content: content.content,
        blocks: content.blocks,
        frontmatter: content.frontmatter,
        dirty,
        inserts,
      });
      if (skipped.length > 0) throw new Error(`无法定位的修改：${skipped.join(', ')}`);
      const r = await fetch('/api/page', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slug, lang, content: nextContent }),
      });
      const data = await r.json();
      if (!r.ok || data.error) throw new Error(data.error ?? `HTTP ${r.status}`);
      await refresh();
      setDirty(new Map());
      setInserts(new Map());
      return true;
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : 'save failed');
      return false;
    } finally {
      setSaving(false);
    }
  }, [slug, lang, content, dirty, inserts, dirtyCount, refresh]);

  return {
    side,
    lang,
    content,
    dirty,
    inserts,
    dirtyCount,
    saving,
    saveError,
    markDirty,
    unmarkDirty,
    insertBlock,
    removeInsert,
    clear,
    save,
  };
}
