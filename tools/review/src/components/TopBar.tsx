import { useMemo } from 'react';
import { ALL_LANGS, LANG_LABEL, type Lang, type ProductTab } from '../shared/types';
import type { ReviewContext } from '../hooks/usePageState';

interface TopBarProps {
  products: ProductTab[];
  productsLoading: boolean;
  ctx: ReviewContext;
  onChange: (partial: Partial<ReviewContext>) => void;
  canDelete: boolean;
  onDeletePage: () => void;
  onOpenImageBatch: () => void;
}

interface ProductGroup {
  product: string;
  tabs: ProductTab[];
}

function groupByProduct(products: ProductTab[]): ProductGroup[] {
  const out: ProductGroup[] = [];
  for (const p of products) {
    const last = out[out.length - 1];
    if (last && last.product === p.product) last.tabs.push(p);
    else out.push({ product: p.product, tabs: [p] });
  }
  return out;
}

export function TopBar({ products, productsLoading, ctx, onChange, canDelete, onDeletePage, onOpenImageBatch }: TopBarProps) {
  const groups = useMemo(() => groupByProduct(products), [products]);

  return (
    <header className="topbar">
      <div className="topbar-brand">钉钉文档校对</div>

      <label className="topbar-field">
        <span className="topbar-field-label">产品模块</span>
        <select
          className="topbar-select"
          value={ctx.product}
          disabled={productsLoading || products.length === 0}
          onChange={(e) => onChange({ product: e.target.value })}
        >
          {groups.map((g) => (
            <optgroup key={g.product} label={g.product}>
              {g.tabs.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.tab}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
      </label>

      <LangPicker
        label="左侧语言"
        value={ctx.leftLang}
        onChange={(leftLang) => onChange({ leftLang })}
      />
      <span className="topbar-vs">对照</span>
      <LangPicker
        label="右侧语言"
        value={ctx.rightLang}
        onChange={(rightLang) => onChange({ rightLang })}
      />

      <div className="topbar-spacer" />

      <button type="button" className="btn btn-primary topbar-batch" onClick={onOpenImageBatch}>
        图片批处理
      </button>

      <button
        type="button"
        className="btn btn-danger topbar-delete"
        disabled={!canDelete}
        onClick={onDeletePage}
        title="删除当前文章（三语 mdx + docs.json 导航 + 孤儿图）"
      >
        删除整篇
      </button>
    </header>
  );
}

interface LangPickerProps {
  label: string;
  value: Lang;
  onChange: (lang: Lang) => void;
}

function LangPicker({ label, value, onChange }: LangPickerProps) {
  return (
    <label className="topbar-field">
      <span className="topbar-field-label">{label}</span>
      <select className="topbar-select" value={value} onChange={(e) => onChange(e.target.value as Lang)}>
        {ALL_LANGS.map((l) => (
          <option key={l} value={l}>
            {LANG_LABEL[l]}
          </option>
        ))}
      </select>
    </label>
  );
}
