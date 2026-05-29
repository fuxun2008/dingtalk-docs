import { useEffect, useRef } from 'react';

interface InlineEditorProps {
  initialValue: string;
  onCommit: (newValue: string) => void;
  onCancel: () => void;
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

export function InlineEditor({ initialValue, onCommit, onCancel }: InlineEditorProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    autosize(el);
    el.focus();
    el.setSelectionRange(el.value.length, el.value.length);
  }, []);

  const onInput = () => {
    if (ref.current) autosize(ref.current);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      onCancel();
      return;
    }
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      onCommit(ref.current?.value ?? '');
    }
  };

  const onBlur = () => {
    if (!ref.current) return;
    const next = ref.current.value;
    if (next === initialValue) onCancel();
    else onCommit(next);
  };

  const wrap = (action: WrapAction) => {
    const el = ref.current;
    if (!el) return;
    const start = el.selectionStart ?? 0;
    const end = el.selectionEnd ?? start;
    const selected = el.value.slice(start, end) || action.placeholder;
    const replacement = `${action.prefix}${selected}${action.suffix}`;
    const next = el.value.slice(0, start) + replacement + el.value.slice(end);
    el.value = next;
    const cursorStart = start + action.prefix.length;
    const cursorEnd = cursorStart + selected.length;
    el.setSelectionRange(cursorStart, cursorEnd);
    autosize(el);
    el.focus();
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
      </div>
      <textarea
        ref={ref}
        className="inline-editor-textarea"
        defaultValue={initialValue}
        onInput={onInput}
        onKeyDown={onKeyDown}
        onBlur={onBlur}
        spellCheck={false}
      />
    </div>
  );
}
