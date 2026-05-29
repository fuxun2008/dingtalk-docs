import { useEffect, useRef } from 'react';
import type { FrontmatterMeta } from '../shared/types';

export const FM_TITLE_KEY = '__fm_title__';
export const FM_DESC_KEY = '__fm_description__';

type Side = 'zh' | 'en';

interface FrontmatterCardProps {
  meta: FrontmatterMeta | null;
  side: Side;
  dirty: Map<string, string>;
  onChange?: (key: string, value: string) => void;
}

export function FrontmatterCard({ meta, side, dirty, onChange }: FrontmatterCardProps) {
  if (!meta) return null;
  const titleValue = dirty.get(FM_TITLE_KEY) ?? meta.title ?? '';
  const descValue = dirty.get(FM_DESC_KEY) ?? meta.description ?? '';
  const isDirtyTitle = dirty.has(FM_TITLE_KEY);
  const isDirtyDesc = dirty.has(FM_DESC_KEY);

  return (
    <div className={`fm-card fm-card-${side}`}>
      <div className="fm-card-tag">Frontmatter（元信息）</div>
      <FmField
        label="标题"
        value={titleValue}
        editable={side === 'en'}
        isDirty={isDirtyTitle}
        onChange={onChange ? (v) => onChange(FM_TITLE_KEY, v) : undefined}
      />
      <FmField
        label="描述"
        value={descValue}
        editable={side === 'en'}
        isDirty={isDirtyDesc}
        multiline
        onChange={onChange ? (v) => onChange(FM_DESC_KEY, v) : undefined}
      />
    </div>
  );
}

interface FmFieldProps {
  label: string;
  value: string;
  editable: boolean;
  isDirty: boolean;
  multiline?: boolean;
  onChange?: (value: string) => void;
}

function FmField({ label, value, editable, isDirty, multiline, onChange }: FmFieldProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (!multiline) return;
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value, multiline]);

  const className = `fm-field ${isDirty ? 'is-dirty' : ''}`;
  if (!editable) {
    return (
      <div className={className}>
        <span className="fm-field-label">{label}</span>
        <div className="fm-field-value-readonly">{value || <em className="fm-empty">（空）</em>}</div>
      </div>
    );
  }
  if (multiline) {
    return (
      <div className={className}>
        <span className="fm-field-label">{label}</span>
        <textarea
          ref={ref}
          className="fm-field-input fm-field-textarea"
          value={value}
          rows={2}
          onChange={(e) => onChange?.(e.target.value)}
        />
      </div>
    );
  }
  return (
    <div className={className}>
      <span className="fm-field-label">{label}</span>
      <input
        className="fm-field-input"
        type="text"
        value={value}
        onChange={(e) => onChange?.(e.target.value)}
      />
    </div>
  );
}
