interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  onSave: () => void;
  onDiscard: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({ open, title, message, onSave, onDiscard, onCancel }: ConfirmDialogProps) {
  if (!open) return null;
  return (
    <div className="dialog-mask" onClick={onCancel}>
      <div className="dialog" role="alertdialog" onClick={(e) => e.stopPropagation()}>
        <h3 className="dialog-title">{title}</h3>
        <p className="dialog-message">{message}</p>
        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            取消
          </button>
          <button type="button" className="btn btn-danger" onClick={onDiscard}>
            放弃修改
          </button>
          <button type="button" className="btn btn-primary" onClick={onSave}>
            保存并切换
          </button>
        </div>
      </div>
    </div>
  );
}
