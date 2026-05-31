import { useCallback, useEffect, useRef, type RefObject } from 'react';

type RefMap = Map<number, HTMLDivElement>;

interface UseScrollSyncOptions {
  leftBody: RefObject<HTMLDivElement>;
  rightBody: RefObject<HTMLDivElement>;
  leftBlocks: RefObject<RefMap>;
  rightBlocks: RefObject<RefMap>;
  enabled: boolean;
  alignLeftToRight?: (leftIndex: number) => number | null;
  alignRightToLeft?: (rightIndex: number) => number | null;
}

export interface ScrollSyncControls {
  suspendSync: (side: 'left' | 'right', ms?: number) => void;
}

function findTopVisibleIndex(container: HTMLDivElement, blocks: RefMap): { index: number; offset: number } | null {
  const containerTop = container.getBoundingClientRect().top;
  let best: { index: number; offset: number } | null = null;
  for (const [index, el] of blocks) {
    const top = el.getBoundingClientRect().top - containerTop;
    if (top > container.clientHeight) continue;
    if (top + el.offsetHeight < 0) continue;
    if (best === null || Math.abs(top) < Math.abs(best.offset)) {
      best = { index, offset: top };
    }
  }
  return best;
}

export function useScrollSync({
  leftBody,
  rightBody,
  leftBlocks,
  rightBlocks,
  enabled,
  alignLeftToRight,
  alignRightToLeft,
}: UseScrollSyncOptions): ScrollSyncControls {
  const lock = useRef<'left' | 'right' | null>(null);
  const releaseTimer = useRef<number | null>(null);
  const alignerRef = useRef<{
    l2r?: (i: number) => number | null;
    r2l?: (i: number) => number | null;
  }>({});
  alignerRef.current.l2r = alignLeftToRight;
  alignerRef.current.r2l = alignRightToLeft;

  const suspendSync = useCallback((side: 'left' | 'right', ms: number = 500) => {
    lock.current = side;
    if (releaseTimer.current !== null) window.clearTimeout(releaseTimer.current);
    releaseTimer.current = window.setTimeout(() => {
      lock.current = null;
      releaseTimer.current = null;
    }, ms);
  }, []);

  useEffect(() => {
    if (!enabled) return;
    const left = leftBody.current;
    const right = rightBody.current;
    if (!left || !right) return;

    const release = () => {
      if (releaseTimer.current !== null) window.clearTimeout(releaseTimer.current);
      releaseTimer.current = window.setTimeout(() => {
        lock.current = null;
        releaseTimer.current = null;
      }, 120);
    };

    const sync = (from: 'left' | 'right') => {
      const source = from === 'left' ? left : right;
      const target = from === 'left' ? right : left;
      const sourceBlocks = from === 'left' ? leftBlocks.current : rightBlocks.current;
      const targetBlocks = from === 'left' ? rightBlocks.current : leftBlocks.current;
      if (!source || !target || !sourceBlocks || !targetBlocks) return;

      const top = findTopVisibleIndex(source, sourceBlocks);
      if (!top) return;
      const aligner = from === 'left' ? alignerRef.current.l2r : alignerRef.current.r2l;
      const targetIdx = aligner ? aligner(top.index) : top.index;
      if (targetIdx === null) return;
      const targetEl = targetBlocks.get(targetIdx);
      if (!targetEl) return;

      const targetCurrentTop = targetEl.getBoundingClientRect().top - target.getBoundingClientRect().top;
      const delta = targetCurrentTop - top.offset;
      if (Math.abs(delta) < 1) return;

      lock.current = from === 'left' ? 'right' : 'left';
      target.scrollTop += delta;
      release();
    };

    const onLeftScroll = () => {
      if (lock.current === 'left') return;
      sync('left');
    };
    const onRightScroll = () => {
      if (lock.current === 'right') return;
      sync('right');
    };

    left.addEventListener('scroll', onLeftScroll, { passive: true });
    right.addEventListener('scroll', onRightScroll, { passive: true });
    return () => {
      left.removeEventListener('scroll', onLeftScroll);
      right.removeEventListener('scroll', onRightScroll);
      if (releaseTimer.current !== null) window.clearTimeout(releaseTimer.current);
    };
  }, [enabled, leftBody, rightBody, leftBlocks, rightBlocks]);

  return { suspendSync };
}
