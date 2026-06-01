import { useEffect, useLayoutEffect, useRef, useState } from 'react';

interface InlineEditorProps {
  initialValue: string;
  onCommit: (newValue: string) => void;
  onCancel: () => void;
  onDelete?: () => void;
}

interface WrapAction {
  label: string;
  prefix: string;
  suffix: string;
  placeholder: string;
  title: string;
}

const ACTIONS: WrapAction[] = [
  { label: 'B', prefix: '**', suffix: '**', placeholder: '加粗', title: '加粗（**…**）' },
  { label: 'I', prefix: '_', suffix: '_', placeholder: '斜体', title: '斜体（_…_）' },
  { label: 'Link', prefix: '[', suffix: '](https://)', placeholder: '链接文字', title: '链接（[文字](url)）' },
  { label: 'Code', prefix: '`', suffix: '`', placeholder: 'code', title: '行内代码（`…`）' },
];

function autosize(el: HTMLTextAreaElement): void {
  el.style.height = 'auto';
  el.style.height = `${el.scrollHeight}px`;
}

export function InlineEditor({ initialValue, onCommit, onCancel, onDelete }: InlineEditorProps) {
  const [value, setValue] = useState(initialValue);
  const ref = useRef<HTMLTextAreaElement>(null);
  const suppressBlurRef = useRef(false);
  const pendingSelectionRef = useRef<{ start: number; end: number } | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    autosize(el);
    if (pendingSelectionRef.current) {
      const { start, end } = pendingSelectionRef.current;
      pendingSelectionRef.current = null;
      el.focus();
      el.setSelectionRange(start, end);
    }
  }, [value]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
      return;
    }
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      onCommit(value);
    }
  };

  const onBlur = () => {
    if (suppressBlurRef.current) {
      suppressBlurRef.current = false;
      return;
    }
    if (value === initialValue) onCancel();
    else onCommit(value);
  };

  const handleDelete = () => {
    if (!onDelete) return;
    suppressBlurRef.current = true;
    onDelete();
  };

  const wrap = (action: WrapAction) => {
    const el = ref.current;
    if (!el) return;
    const start = el.selectionStart ?? 0;
    const end = el.selectionEnd ?? start;
    const selected = value.slice(start, end) || action.placeholder;
    const replacement = `${action.prefix}${selected}${action.suffix}`;
    const next = value.slice(0, start) + replacement + value.slice(end);
    const cursorStart = start + action.prefix.length;
    const cursorEnd = cursorStart + selected.length;
    pendingSelectionRef.current = { start: cursorStart, end: cursorEnd };
    setValue(next);
  };

  return (
    <div className="inline-editor">
      <div className="inline-editor-toolbar">
        {ACTIONS.map((a) => (
          <button
            key={a.label}
            type="button"
            className="inline-editor-tool"
            title={a.title}
            onMouseDown={(e) => {
              e.preventDefault();
              wrap(a);
            }}
          >
            {a.label}
          </button>
        ))}
        <span className="inline-editor-hint">ESC 取消 · ⌘/Ctrl+Enter 确认 · 失焦自动保留</span>
        {onDelete && (
          <button
            type="button"
            className="inline-editor-tool inline-editor-tool-danger"
            title="整块删除（标记后可撤销，保存才真正写回）"
            onMouseDown={(e) => {
              e.preventDefault();
              handleDelete();
            }}
          >
            删除整块
          </button>
        )}
      </div>
      <textarea
        ref={ref}
        className="inline-editor-textarea"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={onBlur}
        spellCheck={false}
      />
    </div>
  );
}
