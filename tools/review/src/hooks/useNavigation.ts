import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { NavNode, NavPage, ProductTab } from '../shared/types';
import type { ReviewContext } from './usePageState';

interface NavState {
  tree: NavNode[];
  flatPages: NavPage[];
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
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

/** Navigation tree for the selected product tab + left/right languages. */
export function useNavigation(ctx: ReviewContext): NavState {
  const [tree, setTree] = useState<NavNode[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const cancelledRef = useRef(false);

  const { product, leftLang, rightLang } = ctx;

  const loadNav = useCallback(async () => {
    if (!product) {
      setTree([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const params = new URLSearchParams({ product, left: leftLang, right: rightLang });
      const r = await fetch(`/api/nav?${params.toString()}`);
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
    }
  }, [product, leftLang, rightLang]);

  useEffect(() => {
    cancelledRef.current = false;
    loadNav();
    return () => {
      cancelledRef.current = true;
    };
  }, [loadNav]);

  const flatPages = useMemo(() => flattenPages(tree), [tree]);
  return { tree, flatPages, loading, error, reload: loadNav };
}

interface ProductsState {
  products: ProductTab[];
  loading: boolean;
  error: string | null;
}

/** The list of selectable product tabs (one proofreading unit each). */
export function useProducts(): ProductsState {
  const [products, setProducts] = useState<ProductTab[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch('/api/products');
        const data: { products?: ProductTab[]; error?: string } = await r.json();
        if (cancelled) return;
        if (data.error) setError(data.error);
        else setProducts(data.products ?? []);
      } catch (err: unknown) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'fetch products failed');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { products, loading, error };
}
