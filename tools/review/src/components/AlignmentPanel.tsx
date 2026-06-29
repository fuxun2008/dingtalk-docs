import { useCallback, useEffect, useState } from 'react';
import type { ReviewContext } from '../hooks/usePageState';

interface AlignmentItem {
  slug: string;
  titleLeft?: string;
  titleRight?: string;
  leftCount: number;
  rightCount: number;
  diff: number;
  error?: string;
}

interface AlignmentResponse {
  total: number;
  mismatchCount: number;
  mismatches: AlignmentItem[];
}

interface AlignmentPanelProps {
  ctx: ReviewContext;
  currentSlug: string | null;
  onNavigate: (slug: string) => void;
}

export function AlignmentPanel({ ctx, currentSlug, onNavigate }: AlignmentPanelProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AlignmentResponse | null>(null);

  const runScan = useCallback(async () => {
    if (!ctx.product) {
      setError('请先选择产品模块');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ product: ctx.product, left: ctx.leftLang, right: ctx.rightLang });
      const r = await fetch(`/api/alignment?${params.toString()}`);
      const json = await r.json();
      if (!r.ok || json.error) throw new Error(json.error ?? `HTTP ${r.status}`);
      setData(json as AlignmentResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'scan failed');
    } finally {
      setLoading(false);
    }
  }, [ctx.product, ctx.leftLang, ctx.rightLang]);

  // Invalidate cached results when the product / languages change (re-scan on next open).
  useEffect(() => {
    setData(null);
    setError(null);
  }, [ctx.product, ctx.leftLang, ctx.rightLang]);

  const onClick = () => {
    setOpen(true);
    if (!data && !loading) runScan();
  };

  return (
    <>
      <button
        type="button"
        className="alignment-trigger"
        onClick={onClick}
        title="扫描所有页面，对比中英 block 数量"
      >
        <span>对齐扫描</span>
        {data && data.mismatchCount > 0 && (
          <span className="alignment-trigger-badge">{data.mismatchCount}</span>
        )}
      </button>

      {open && (
        <div className="dialog-mask" onClick={() => setOpen(false)}>
          <div className="alignment-dialog" onClick={(e) => e.stopPropagation()}>
            <div className="alignment-dialog-head">
              <div>
                <div className="alignment-dialog-title">中英 block 对齐扫描</div>
                <div className="alignment-dialog-sub">
                  {loading && '扫描中…'}
                  {error && <span className="alignment-error">{error}</span>}
                  {data && !loading && (
                    <>
                      共 {data.total} 页 · 不对齐 <b>{data.mismatchCount}</b> 页
                    </>
                  )}
                </div>
              </div>
              <div className="alignment-dialog-actions">
                <button className="btn btn-ghost" onClick={runScan} disabled={loading}>
                  {loading ? '扫描中…' : '重新扫描'}
                </button>
                <button className="btn btn-ghost" onClick={() => setOpen(false)}>
                  关闭
                </button>
              </div>
            </div>
            <div className="alignment-list">
              {data && data.mismatches.length === 0 && !loading && (
                <div className="alignment-empty">所有页面 block 数量一致 ✓</div>
              )}
              {data?.mismatches.map((m) => (
                <button
                  key={m.slug}
                  type="button"
                  className={'alignment-row' + (m.slug === currentSlug ? ' is-current' : '')}
                  onClick={() => {
                    onNavigate(m.slug);
                    setOpen(false);
                  }}
                >
                  <span className="alignment-row-title">
                    {m.titleLeft ?? m.titleRight ?? m.slug}
                  </span>
                  <span className="alignment-row-slug">{m.slug}</span>
                  {m.error ? (
                    <span className="alignment-row-error">{m.error}</span>
                  ) : (
                    <span className="alignment-row-counts">
                      左 <b>{m.leftCount}</b> · 右 <b>{m.rightCount}</b>
                      <span className={'alignment-row-diff' + (m.diff > 0 ? ' is-pos' : ' is-neg')}>
                        {m.diff > 0 ? `+${m.diff}` : m.diff}
                      </span>
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
