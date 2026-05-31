import { useEffect, useRef, useState } from 'react';

export type InsertKind = 'image' | 'video';

interface InsertBlockDialogProps {
  open: boolean;
  kind: InsertKind;
  onSubmit: (raw: string) => void;
  onCancel: () => void;
}

const URL_HINT = '仅支持 http:// 或 https:// 开头的 CDN 链接';

function isSafeUrl(url: string): boolean {
  const trimmed = url.trim();
  return /^https?:\/\/\S+$/i.test(trimmed);
}

function escapeAlt(s: string): string {
  return s.replace(/[\[\]]/g, '');
}

function buildRaw(kind: InsertKind, url: string, alt: string): string {
  const u = url.trim();
  if (kind === 'image') {
    return `![${escapeAlt(alt.trim())}](${u})`;
  }
  return `<video src="${u}" controls width="100%"/>`;
}

export function InsertBlockDialog({ open, kind, onSubmit, onCancel }: InsertBlockDialogProps) {
  const [url, setUrl] = useState('');
  const [alt, setAlt] = useState('');
  const urlRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setUrl('');
      setAlt('');
      queueMicrotask(() => urlRef.current?.focus());
    }
  }, [open, kind]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onCancel]);

  if (!open) return null;

  const canSubmit = isSafeUrl(url);
  const label = kind === 'image' ? '插入图片' : '插入视频';

  const submit = () => {
    if (!canSubmit) return;
    onSubmit(buildRaw(kind, url, alt));
  };

  return (
    <div className="dialog-mask" onClick={onCancel}>
      <div className="dialog" role="dialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="dialog-title">{label}</h3>
        <div className="insert-dialog-body">
          <label className="insert-dialog-field">
            <span className="insert-dialog-field-label">
              {kind === 'image' ? '图片 URL' : '视频 URL'}
              <span className="insert-dialog-required">*</span>
            </span>
            <input
              ref={urlRef}
              type="text"
              className="insert-dialog-input"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && canSubmit) {
                  e.preventDefault();
                  submit();
                }
              }}
              placeholder={kind === 'image' ? 'https://img.alicdn.com/...' : 'https://cloud.video.taobao.com/...'}
              spellCheck={false}
            />
            <span className="insert-dialog-hint">{URL_HINT}</span>
          </label>
          {kind === 'image' && (
            <label className="insert-dialog-field">
              <span className="insert-dialog-field-label">替代文字 alt（选填）</span>
              <input
                type="text"
                className="insert-dialog-input"
                value={alt}
                onChange={(e) => setAlt(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && canSubmit) {
                    e.preventDefault();
                    submit();
                  }
                }}
                placeholder="简短描述图片内容，便于无障碍与 SEO"
                spellCheck={false}
              />
            </label>
          )}
          <div className="insert-dialog-preview-label">将插入</div>
          <pre className="insert-dialog-preview">
            {url.trim() ? buildRaw(kind, url, alt) : '（填入 URL 后预览）'}
          </pre>
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            取消
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={submit}
            disabled={!canSubmit}
            title={canSubmit ? '插入（Enter）' : URL_HINT}
          >
            插入
          </button>
        </div>
      </div>
    </div>
  );
}
