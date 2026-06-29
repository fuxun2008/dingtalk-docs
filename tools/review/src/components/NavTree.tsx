import { useState } from 'react';
import type { NavGroup, NavNode } from '../shared/types';

interface NavTreeProps {
  tree: NavNode[];
  currentSlug: string | null;
  dirtySlug: string | null;
  onSelect: (slug: string) => void;
}

export function NavTree({ tree, currentSlug, dirtySlug, onSelect }: NavTreeProps) {
  return (
    <nav className="navtree">
      {tree.map((node, i) => (
        <NavItem
          key={i}
          node={node}
          depth={0}
          currentSlug={currentSlug}
          dirtySlug={dirtySlug}
          onSelect={onSelect}
        />
      ))}
    </nav>
  );
}

interface NavItemProps {
  node: NavNode;
  depth: number;
  currentSlug: string | null;
  dirtySlug: string | null;
  onSelect: (slug: string) => void;
}

function NavItem({ node, depth, currentSlug, dirtySlug, onSelect }: NavItemProps) {
  if (node.type === 'page') {
    const isCurrent = node.slug === currentSlug;
    const isDirty = node.slug === dirtySlug;
    const fallback = node.slug.split('/').pop() ?? node.slug;
    const label = node.titleLeft ?? node.titleRight ?? fallback;
    return (
      <button
        type="button"
        className={`navtree-page ${isCurrent ? 'is-current' : ''} ${node.missing ? 'is-missing' : ''}`}
        style={{ paddingLeft: 12 + depth * 14 }}
        onClick={() => onSelect(node.slug)}
        title={`${node.slug}${node.missing ? '（文件缺失）' : ''}`}
        disabled={node.missing}
      >
        <span className="navtree-page-label">{label}</span>
        {isDirty && <span className="navtree-dirty-dot" aria-label="未保存" />}
      </button>
    );
  }
  return <GroupItem node={node} depth={depth} currentSlug={currentSlug} dirtySlug={dirtySlug} onSelect={onSelect} />;
}

interface GroupItemProps {
  node: NavGroup;
  depth: number;
  currentSlug: string | null;
  dirtySlug: string | null;
  onSelect: (slug: string) => void;
}

function GroupItem({ node, depth, currentSlug, dirtySlug, onSelect }: GroupItemProps) {
  const [open, setOpen] = useState(true);
  const title = node.titleLeft ?? node.titleRight;
  return (
    <div className="navtree-group">
      <button
        type="button"
        className="navtree-group-head"
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={() => setOpen((v) => !v)}
      >
        <span className={`navtree-caret ${open ? 'is-open' : ''}`}>▸</span>
        <span className="navtree-group-title">{title}</span>
      </button>
      {open && (
        <div className="navtree-group-body">
          {node.children.map((child, i) => (
            <NavItem
              key={i}
              node={child}
              depth={depth + 1}
              currentSlug={currentSlug}
              dirtySlug={dirtySlug}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}
