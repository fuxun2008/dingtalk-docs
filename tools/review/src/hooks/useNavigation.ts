import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { NavNode, NavPage } from '../shared/types';

interface NavState {
  tree: NavNode[];
  flatPages: NavPage[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
}

const FOCUS_THROTTLE_MS = 2000;

function flattenPages(nodes: NavNode[]): NavPage[] {
  const out: NavPage[] = [];
  const walk = (list: NavNode[]) => {
    for (const n of list) {
      if (n.type === 'page') out.push(n);
      else walk(n.children);
    }
  };
  walk(nodes);
  return out;
}

export function useNavigation(): NavState {
  const [tree, setTree] = useState<NavNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const lastReloadAtRef = useRef(0);
  const cancelledRef = useRef(false);

  const loadNav = useCallback(async () => {
    try {
      const r = await fetch('/api/nav');
      const data: { tree?: NavNode[]; error?: string } = await r.json();
      if (cancelledRef.current) return;
      if (data.error) {
        setError(data.error);
      } else {
        setError(null);
        setTree(data.tree ?? []);
      }
    } catch (err: unknown) {
      if (cancelledRef.current) return;
      setError(err instanceof Error ? err.message : 'fetch nav failed');
    } finally {
      if (!cancelledRef.current) setLoading(false);
      lastReloadAtRef.current = Date.now();
    }
  }, []);

  useEffect(() => {
    cancelledRef.current = false;
    loadNav();
    return () => {
      cancelledRef.current = true;
    };
  }, [loadNav]);

  useEffect(() => {
    const onFocus = () => {
      if (Date.now() - lastReloadAtRef.current < FOCUS_THROTTLE_MS) return;
      loadNav();
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [loadNav]);

  const flatPages = useMemo(() => flattenPages(tree), [tree]);
  return { tree, flatPages, loading, error, reload: loadNav };
}
