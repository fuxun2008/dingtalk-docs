import { useEffect, useState } from 'react';

interface DeletePageDialogProps {
  open: boolean;
  slug: string;
  onConfirm: () => Promise<void> | void;
  onCancel: () => void;
}

export function DeletePageDialog({ open, slug, onConfirm, onCancel }: DeletePageDialogProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setBusy(false);
      setError(null);
    }
  }, [open]);

  if (!open) return null;

  const confirm = async () => {
    setBusy(true);
    setError(null);
    try {
      await onConfirm();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'delete failed');
      setBusy(false);
    }
  };

  return (
    <div className="dialog-mask" onClick={busy ? undefined : onCancel}>
      <div className="dialog" role="alertdialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="dialog-title">删除整篇文章</h3>
        <p className="dialog-message">
          即将永久删除 <code>{slug}</code> 的<b>三语 mdx 文件</b>，并从 <code>docs.json</code> 移除
          <b>三处导航条目</b>，同时清理仅被本文引用的<b>孤儿图片</b>。此操作不可撤销。
        </p>
        <p className="dialog-message dialog-message-hint">
          删除后请在仓库根运行 <code>mint broken-links</code> 复核，并用 <code>git diff</code> 自查。
        </p>
        {error && <p className="dialog-error">删除失败：{error}</p>}
        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button type="button" className="btn btn-danger" onClick={confirm} disabled={busy}>
            {busy ? '删除中…' : '确认删除'}
          </button>
        </div>
      </div>
    </div>
  );
}
