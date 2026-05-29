import { useEffect, useMemo, useState } from 'react';
import type { NavNode, NavPage } from '../shared/types';

interface NavState {
  tree: NavNode[];
  flatPages: NavPage[];
  loading: boolean;
  error: string | null;
}

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

  useEffect(() => {
    let cancelled = false;
    fetch('/api/nav')
      .then((r) => r.json())
      .then((data: { tree?: NavNode[]; error?: string }) => {
        if (cancelled) return;
        if (data.error) {
          setError(data.error);
        } else {
          setTree(data.tree ?? []);
        }
        setLoading(false);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'fetch nav failed');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const flatPages = useMemo(() => flattenPages(tree), [tree]);
  return { tree, flatPages, loading, error };
}
