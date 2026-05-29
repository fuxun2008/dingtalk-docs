interface SaveBarProps {
  dirtyCount: number;
  saving: boolean;
  error: string | null;
  onSave: () => void;
}

export function SaveBar({ dirtyCount, saving, error, onSave }: SaveBarProps) {
  const disabled = saving || dirtyCount === 0;
  return (
    <div className="savebar">
      {error && <span className="savebar-error" title={error}>保存失败：{error}</span>}
      <span className="savebar-count">
        {dirtyCount > 0 ? `${dirtyCount} 处未保存` : '已保存'}
      </span>
      <button
        type="button"
        className="btn btn-primary savebar-btn"
        disabled={disabled}
        onClick={onSave}
        title="ALT+S"
      >
        {saving ? '保存中…' : '保存 (ALT+S)'}
      </button>
    </div>
  );
}
