import { useEffect, useRef, type RefObject } from 'react';

type RefMap = Map<number, HTMLDivElement>;

interface UseScrollSyncOptions {
  leftBody: RefObject<HTMLDivElement>;
  rightBody: RefObject<HTMLDivElement>;
  leftBlocks: RefObject<RefMap>;
  rightBlocks: RefObject<RefMap>;
  enabled: boolean;
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

export function useScrollSync({ leftBody, rightBody, leftBlocks, rightBlocks, enabled }: UseScrollSyncOptions) {
  const lock = useRef<'left' | 'right' | null>(null);
  const releaseTimer = useRef<number | null>(null);

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
      const targetEl = targetBlocks.get(top.index);
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
}
