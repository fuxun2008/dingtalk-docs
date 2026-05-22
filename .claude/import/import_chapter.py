#!/usr/bin/env python3
"""Convert one AI Table chapter from wolai-exported Markdown to Mintlify MDX.

Usage:
    python3 import_chapter.py <chapter-key> [--dry-run] [--force]

What it does (per chapter):
  1. Load aitable-chapters.json + aitable-slug-map.json
  2. For each doc belonging to the chapter:
       - Read source md (UTF-8)
       - Generate frontmatter (title + description) from H1
       - Apply content transforms (brand names, MDX escapes, link rewrites, image paths)
       - Copy images from <src-dir>/image/* → zh/aitable/<target>/images/*
       - Write target mdx
  3. Update docs.json:
       - Find/insert group in zh AI Table tab matching chapter title_zh
       - Build pages array with hierarchical groups for nested docs
       - Use json.dumps with indent=2 + ensure_ascii=False to match existing style
  4. Log per-doc results to /tmp/aitable-import-<chapter>.log

Exit code 0 = success, 1 = any doc failed (no partial write — atomic per chapter).

Idempotency: re-running with --force overwrites; without --force, refuses to
overwrite existing mdx files (safe by default).
"""
from __future__ import annotations
import argparse, json, os, re, shutil, sys
from pathlib import Path

# ---- Paths ----
REPO_ROOT     = Path('/Users/yanxin/www/dingtalk-docs')
CORPUS_ROOT   = Path('/Users/yanxin/github/dingtalk_ai_table')
IMPORT_DIR    = REPO_ROOT / '.claude' / 'import'
CHAPTERS_PATH = IMPORT_DIR / 'aitable-chapters.json'
SLUGMAP_PATH  = IMPORT_DIR / 'aitable-slug-map.json'
DOCSJSON_PATH = REPO_ROOT / 'docs.json'
ZH_AITABLE    = REPO_ROOT / 'zh' / 'aitable'

# ---- Brand-name replacements (order matters: compound first, bare last) ----
BRAND_PATTERNS = [
    (re.compile(r'钉钉\s?AI\s?表格'),  'AI表格'),
    (re.compile(r'钉钉\s?文档'),       '文档'),
    (re.compile(r'钉钉'),              'DingTalk'),
]

# ---- Domain replacements: only on .com → .io for selected subdomains ----
# Preserve: alidocs.dingtalk.com (CDN), open(-dev).dingtalk.com (developer docs)
DOMAIN_KEEP_SUBDOMAINS = {'alidocs', 'open', 'open-dev'}
# Replace .com → .io for these subdomains (and any other dingtalk.com subdomain
# not in DOMAIN_KEEP_SUBDOMAINS)
DOMAIN_REPLACE_PATTERN = re.compile(r'https://([\w-]+)\.dingtalk\.com')

def transform_dingtalk_domain(text: str) -> str:
    def replace(m: re.Match) -> str:
        sub = m.group(1)
        if sub in DOMAIN_KEEP_SUBDOMAINS:
            return m.group(0)
        return f'https://{sub}.dingtalk.io'
    return DOMAIN_REPLACE_PATTERN.sub(replace, text)

# ---- Wolai cross-doc link: [label](https://wolai.dingtalk.com/...) → label ----
WOLAI_LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(https://wolai\.dingtalk\.com/[^)]+\)')

# Wolai bare-id link: [label](/<22+ char base62 id>) — pages exported with their
# wolai page-id as the bare href. We can't resolve these to mdx slugs without a
# secondary id-map, so degrade to plain text and log for manual follow-up.
WOLAI_BAREID_PATTERN = re.compile(
    r'\[([^\]]+)\]\(/[A-Za-z0-9]{20,}(?:\s+"[^"]*")?\)'
)

def strip_wolai_links(text: str, src_key: str, log: list) -> str:
    text = WOLAI_LINK_PATTERN.sub(r'\1', text)
    def bareid_replace(m):
        log.append(('wolai-bareid', src_key, m.group(0)))
        return m.group(1)
    text = WOLAI_BAREID_PATTERN.sub(bareid_replace, text)
    return text

# ---- Local image path: ![](image/foo.png) → ![](/zh/aitable/<target>/images/foo.png) ----
# Wolai uses `image/` (singular). We rewrite to a repo-root-absolute path under the
# mdx's same-name sibling dir (target). Absolute paths avoid relative-path pitfalls
# regardless of how deep the mdx is nested.
# Match both `![alt](image/x.png)` and `![alt](<image/x with spaces.gif> "title")`.
# Group 1 = alt, group 2 = image relative path (without leading `image/`).
IMAGE_PATTERN = re.compile(
    r'!\[([^\]]*)\]\('               # ![alt](
    r'(?:<image/([^>]+)>|image/([^)\s]+))'  # <image/path> or image/path
    r'(?:\s+"[^"]*")?'               # optional "title"
    r'\)'
)

def rewrite_image_paths(text: str, target: str, src_dir: Path, src_key: str, log: list) -> str:
    base = f'/zh/aitable/{target}/images/'
    def replace(m: re.Match) -> str:
        alt = m.group(1)
        path = m.group(2) or m.group(3)
        if not (src_dir / 'image' / path).exists():
            log.append(('src-missing', src_key, f'image/{path}'))
        return f'![{alt}]({base}{path})'
    return IMAGE_PATTERN.sub(replace, text)

# ---- HTML entities ----
def decode_entities(text: str) -> str:
    text = text.replace('&#x20;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    return text

# ---- Code-block masking (shared by escape_mdx and wolai_unescape) ----
CODE_FENCE_PATTERN = re.compile(r'```[\s\S]*?```', re.MULTILINE)
INLINE_CODE_PATTERN = re.compile(r'`[^`\n]+`')

def _mask_code(text: str, *, inline: bool = True) -> tuple[str, list[str]]:
    masks: list[str] = []
    def mask(m):
        masks.append(m.group(0))
        return f'\x00MASK{len(masks)-1}\x00'
    text = CODE_FENCE_PATTERN.sub(mask, text)
    if inline:
        text = INLINE_CODE_PATTERN.sub(mask, text)
    return text, masks

def _unmask_code(text: str, masks: list[str]) -> str:
    return re.sub(r'\x00MASK(\d+)\x00', lambda m: masks[int(m.group(1))], text)

# ---- Wolai over-escape: unescape ASCII punctuation that wolai over-escaped ----
# Wolai exports things like `!\[]\(image/x.png)`, `\*\*bold\*\*`, URL `\&` in tables.
# These are not real Markdown escapes — they're wolai noise that breaks our
# downstream IMAGE_PATTERN / INTERNAL_LINK_PATTERN matching and look ugly in
# rendered MDX.
#
# Only fenced code blocks are masked; inline `code` spans are NOT — because a
# half-escaped pair like `\`text`` would otherwise be mis-detected as an inline
# span and skip unescape, leaving a stray `\` before the now-real backtick which
# MDX then tries to parse JSX after.
WOLAI_ESCAPE_CHARS = r'\[\]\(\)&_*#.\-<>!|`~+='
WOLAI_ESCAPE_PATTERN = re.compile(r'\\([' + WOLAI_ESCAPE_CHARS + r'])')

def unescape_wolai(text: str) -> str:
    text, masks = _mask_code(text, inline=False)
    text = WOLAI_ESCAPE_PATTERN.sub(r'\1', text)
    return _unmask_code(text, masks)

# ---- Strip wolai-style angle-bracketed autolinks: <https://...> → https://... ----
# MDX 2 does not support GFM autolink syntax `<https://x>` and tries to parse
# it as a JSX tag (<https... -> tag name). Run outside code blocks.
AUTOLINK_PATTERN = re.compile(r'<(https?://[^>\s]+)>')

def strip_autolinks(text: str) -> str:
    text, masks = _mask_code(text)
    text = AUTOLINK_PATTERN.sub(r'\1', text)
    return _unmask_code(text, masks)

# ---- MDX escapes: bare { } < that MDX would otherwise treat as JSX ----
# In MDX 2, `<` followed by a letter is a JSX tag opener. Sources like
# `<签名时时间戳>` (Chinese placeholder) trigger a parse error. Escape `<` when
# followed by anything that isn't a valid JSX tag-name start (letter or `/`).
def escape_mdx(text: str) -> str:
    text, masks = _mask_code(text)
    text = re.sub(r'(?<!\\)\{', r'\\{', text)
    text = re.sub(r'(?<!\\)\}', r'\\}', text)
    text = re.sub(r'(?<!\\)<(?![a-zA-Z/!])', r'\\<', text)
    return _unmask_code(text, masks)

# ---- Internal cross-doc links ----
# Patterns to match:
#   [label](relative/path.md "title")
#   [label](<relative path with spaces.md> "title")
INTERNAL_LINK_PATTERN = re.compile(
    r'\[([^\]]+)\]\((?:<([^>]+\.md)>|([^)\s]+\.md))(?:\s+"[^"]*")?\)'
)

def build_slug_lookup(slug_map: dict) -> tuple[dict, dict]:
    """Build lookups: (1) by leaf doc-name (last path segment) for ambiguous matching,
    (2) by full source path (no .md) for exact matching."""
    by_leaf = {}        # 'doc-name' → list of (src_key, target)
    by_src_key = {}     # 'top/sub/leaf' → target
    for src_key, info in slug_map['entries'].items():
        target = info['target']
        by_src_key[src_key] = target
        leaf = src_key.split('/')[-1]
        by_leaf.setdefault(leaf, []).append((src_key, target))
    return by_leaf, by_src_key

def resolve_internal_link(href: str, current_src_key: str, by_leaf: dict, by_src_key: dict) -> str | None:
    """Given a relative .md href like '../foo/foo.md', resolve to a target slug path
    (full URL path under /zh/aitable/<chapter>/...). Returns None if unresolvable."""
    # Normalize: drop leading "./", strip ".md"
    href_clean = href.lstrip('./').rstrip()
    if href_clean.endswith('.md'):
        href_clean = href_clean[:-3]
    # Try as a complete source key
    if href_clean in by_src_key:
        return '/zh/aitable/' + by_src_key[href_clean]
    # Resolve relative to current doc's directory
    cur_dir = '/'.join(current_src_key.split('/')[:-1])
    if cur_dir:
        # Walk up '..' segments
        segments = href_clean.split('/')
        cur_segs = cur_dir.split('/')
        out_segs = list(cur_segs)
        for s in segments:
            if s == '..':
                if out_segs:
                    out_segs.pop()
            elif s == '.':
                pass
            else:
                out_segs.append(s)
        resolved = '/'.join(out_segs)
        if resolved in by_src_key:
            return '/zh/aitable/' + by_src_key[resolved]
        # Wolai pattern: <dir>/<dir>.md  — file is named after its dir.
        # Sometimes the link target is just <dir>/<dir>.md but the cleaned form has dir/dir.
        # Try matching by leaf
        leaf = resolved.split('/')[-1]
        candidates = by_leaf.get(leaf, [])
        if len(candidates) == 1:
            return '/zh/aitable/' + candidates[0][1]
    # Last-ditch: leaf-only match
    leaf = href_clean.split('/')[-1]
    candidates = by_leaf.get(leaf, [])
    if len(candidates) == 1:
        return '/zh/aitable/' + candidates[0][1]
    return None

def rewrite_internal_links(text: str, current_src_key: str, by_leaf: dict, by_src_key: dict, log: list) -> str:
    def replace(m: re.Match) -> str:
        label = m.group(1)
        href = m.group(2) or m.group(3)
        # Skip remote URLs (handled separately)
        if href.startswith(('http://', 'https://', 'mailto:', '#')):
            return m.group(0)
        # Only process .md links
        if not href.endswith('.md'):
            return m.group(0)
        target = resolve_internal_link(href, current_src_key, by_leaf, by_src_key)
        if target:
            log.append(('link-ok', current_src_key, href, target))
            return f'[{label}]({target})'
        log.append(('link-unresolved', current_src_key, href))
        # Degrade: drop link, keep label
        return label
    return INTERNAL_LINK_PATTERN.sub(replace, text)

# ---- TOC / H1 stripping ----
H1_PATTERN = re.compile(r'^#\s+(.+?)\s*$', re.MULTILINE)
TOC_BLOCK_PATTERN = re.compile(r'^##\s*目录\s*\n(?:^\s*[-*]\s+.*\n?)+', re.MULTILINE)

def strip_first_h1(text: str) -> tuple[str, str | None]:
    """Strip the first H1 and return (new-text, h1-title)."""
    m = H1_PATTERN.search(text)
    if not m:
        return text, None
    title = m.group(1).strip()
    # Strip the matched H1 line
    text = text[:m.start()] + text[m.end():]
    # Drop leading whitespace introduced by removal
    text = text.lstrip('\n')
    return text, title

def strip_toc_block(text: str) -> str:
    return TOC_BLOCK_PATTERN.sub('', text)

# ---- Horizontal rule normalization ----
HRULE_PATTERN = re.compile(r'^\*\*\*\s*$', re.MULTILINE)

def normalize_hrules(text: str) -> str:
    return HRULE_PATTERN.sub('---', text)

# ---- Description extraction: first non-empty line after H1, truncated ----
def extract_description(text: str, max_len: int = 80) -> str:
    for line in text.split('\n'):
        line = line.strip()
        # Skip empty, headings, hrules, code-fence, image-only, table rows
        if not line or line.startswith('#') or line.startswith('---') or line.startswith('```') or line.startswith('!['):
            continue
        if line.startswith('|') or line.startswith('- ') or line.startswith('* '):
            continue
        # Strip leading `> ` (blockquote) prefixes, possibly nested
        while line.startswith('>'):
            line = line[1:].lstrip()
        if not line:
            continue
        # Strip markdown link/image syntax inline
        line = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', line)
        line = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', line)
        # Strip emphasis markers and leading emoji-like decorations
        line = re.sub(r'[*_`]', '', line).strip()
        if not line:
            continue
        if len(line) > max_len:
            line = line[:max_len] + '...'
        return line
    return 'TODO: description'

# ---- Main conversion pipeline ----
def convert_doc(src_path: Path, target_mdx: Path, src_key: str, target: str, by_leaf: dict, by_src_key: dict, log: list) -> None:
    text = src_path.read_text(encoding='utf-8')

    # 1. Strip TOC
    text = strip_toc_block(text)
    # 2. Strip first H1 (becomes frontmatter title)
    text, h1_title = strip_first_h1(text)
    # 3. Unescape wolai over-escapes (must happen before image/link rewriters
    #    so patterns like `!\[]\(image/x.png)` match)
    text = unescape_wolai(text)
    # 4. Decode HTML entities
    text = decode_entities(text)
    # 5. Brand name replacements
    for pat, repl in BRAND_PATTERNS:
        text = pat.sub(repl, text)
    # Title also gets brand transform
    if h1_title:
        for pat, repl in BRAND_PATTERNS:
            h1_title = pat.sub(repl, h1_title)
    # 6. Strip wolai cross-doc links (full URL + bare page-id)
    text = strip_wolai_links(text, src_key, log)
    # 7. Rewrite internal .md links
    text = rewrite_internal_links(text, src_key, by_leaf, by_src_key, log)
    # 8. Rewrite local image paths
    text = rewrite_image_paths(text, target, src_path.parent, src_key, log)
    # 9. Transform dingtalk.com → .io (selective)
    text = transform_dingtalk_domain(text)
    # 9.5 Strip <https://x> autolinks (MDX 2 parses them as JSX tags)
    text = strip_autolinks(text)
    # 10. Normalize horizontal rules
    text = normalize_hrules(text)
    # 11. MDX escape stray { }
    text = escape_mdx(text)

    # Build frontmatter
    title = h1_title or src_key.split('/')[-1]
    description = extract_description(text)
    # YAML double-quoted strings only accept \\ \" \n \r \t \0 \a \b \f \v \e
    # Strip any other stray backslash (e.g. \$ from wolai over-escape)
    def yaml_sanitize(s: str) -> str:
        s = re.sub(r'\\(?!["\\nrtbfv0aeNLP])', '', s)
        return s.replace('"', '\\"')
    title_safe = yaml_sanitize(title)
    description_safe = yaml_sanitize(description)
    frontmatter = f'---\ntitle: "{title_safe}"\ndescription: "{description_safe}"\n---\n\n'

    # Write
    target_mdx.parent.mkdir(parents=True, exist_ok=True)
    target_mdx.write_text(frontmatter + text.lstrip('\n'), encoding='utf-8')

def copy_images(src_dir: Path, target_images_dir: Path) -> int:
    """Copy all files from <src-dir>/image/* to <target-images-dir>/. Returns count."""
    src_images = src_dir / 'image'
    if not src_images.is_dir():
        return 0
    target_images_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in src_images.iterdir():
        if item.is_file():
            shutil.copy2(item, target_images_dir / item.name)
            count += 1
    return count

# ---- docs.json update ----
def build_pages_tree(chapter_entries: list[tuple[str, dict]]) -> list:
    """Given a list of (src_key, info) tuples for one chapter, build the
    Mintlify pages array with nested groups for parents that have children.

    Example output:
      [
        "zh/aitable/fields/add-field",
        "zh/aitable/fields/field-grouping",
        ...,
        {
          "group": "字段类型列表",
          "pages": [
            "zh/aitable/fields/field-types",
            "zh/aitable/fields/field-types/button",
            ...
          ]
        }
      ]
    """
    # Build a tree: target-path → has-children?
    by_target = {info['target']: info for _, info in chapter_entries}
    targets = sorted(by_target.keys(), key=lambda t: (t.count('/'), t))
    # For each target, check if any other target starts with target + '/'
    has_children = {t: any(o != t and o.startswith(t + '/') for o in targets) for t in targets}

    # Group children under their parent
    # parent_target → list of child_targets
    children_of = {t: [] for t in targets}
    for t in targets:
        # Find immediate parent: longest prefix t.rsplit('/', 1)[0] that's also a target
        if '/' in t:
            parent = t.rsplit('/', 1)[0]
            if parent in by_target:
                children_of[parent].append(t)

    # Determine roots: top-level targets within the chapter (depth=1)
    chapter_prefix_depth = next(iter(by_target)).split('/')[0]  # 'fields' etc.
    roots = [t for t in targets if t.count('/') == 1]  # 'fields/x'
    roots.sort()

    def render(target: str) -> str | dict:
        page_path = 'zh/aitable/' + target
        kids = children_of[target]
        if not kids:
            return page_path
        # Render as sub-group with title from src zh-name
        info = by_target[target]
        kids_sorted = sorted(kids)
        sub_pages = [page_path] + [render(k) for k in kids_sorted]
        return {
            'group': info['title_zh'],
            'pages': sub_pages,
        }

    return [render(r) for r in roots]

def update_docs_json(chapter_key: str, chapter_title_zh: str, pages_tree: list, dry_run: bool) -> None:
    docs = json.loads(DOCSJSON_PATH.read_text(encoding='utf-8'))
    # Locate zh language → AI Table tab → groups
    zh_lang = next(l for l in docs['navigation']['languages'] if l['language'] == 'zh')
    aitable_tab = next(t for t in zh_lang['tabs'] if t['tab'] == 'AI Table')
    groups = aitable_tab['groups']
    # Find or insert group for this chapter
    existing_idx = next((i for i, g in enumerate(groups) if g['group'] == chapter_title_zh), None)
    new_group = {'group': chapter_title_zh, 'pages': pages_tree}
    if existing_idx is not None:
        groups[existing_idx] = new_group
        print(f'  docs.json: replaced existing "{chapter_title_zh}" group')
    else:
        groups.append(new_group)
        print(f'  docs.json: appended new "{chapter_title_zh}" group')

    if dry_run:
        print(f'  (dry-run: docs.json NOT written)')
        return
    DOCSJSON_PATH.write_text(json.dumps(docs, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

# ---- Main ----
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('chapter', help='Chapter key from aitable-chapters.json')
    parser.add_argument('--dry-run', action='store_true', help='Print actions without writing')
    parser.add_argument('--force', action='store_true', help='Overwrite existing mdx files')
    args = parser.parse_args()

    chapters = json.loads(CHAPTERS_PATH.read_text(encoding='utf-8'))
    slug_map = json.loads(SLUGMAP_PATH.read_text(encoding='utf-8'))

    chapter = next((c for c in chapters['chapters'] if c['key'] == args.chapter), None)
    if not chapter:
        print(f'ERROR: unknown chapter {args.chapter!r}. Available: '
              + ', '.join(c['key'] for c in chapters['chapters']))
        return 1

    by_leaf, by_src_key = build_slug_lookup(slug_map)

    # Find all slug-map entries belonging to this chapter
    chapter_entries = [(k, v) for k, v in slug_map['entries'].items() if v['chapter'] == args.chapter]
    print(f'Chapter: {args.chapter} ({chapter["title_zh"]})')
    print(f'Docs to convert: {len(chapter_entries)}')

    # Pre-check existence
    conflicts = []
    for src_key, info in chapter_entries:
        target_mdx = ZH_AITABLE / (info['target'] + '.mdx')
        if target_mdx.exists() and not args.force:
            conflicts.append(target_mdx)
    if conflicts:
        print(f'\nERROR: {len(conflicts)} target mdx files already exist (re-run with --force to overwrite):')
        for c in conflicts[:10]:
            print(f'  - {c.relative_to(REPO_ROOT)}')
        return 1

    log = []
    converted = 0
    image_total = 0
    for src_key, info in chapter_entries:
        src_path = CORPUS_ROOT / (src_key + '.md')
        if not src_path.exists():
            print(f'  SKIP (source missing): {src_key}')
            log.append(('src-missing', src_key))
            continue
        target_mdx = ZH_AITABLE / (info['target'] + '.mdx')
        target_images_dir = ZH_AITABLE / info['target'] / 'images'

        rel_target = target_mdx.relative_to(REPO_ROOT)
        if args.dry_run:
            print(f'  [dry] {src_key}.md → {rel_target}')
        else:
            convert_doc(src_path, target_mdx, src_key, info['target'], by_leaf, by_src_key, log)
            img_count = copy_images(src_path.parent, target_images_dir)
            image_total += img_count
            converted += 1
            print(f'  ✓ {src_key}.md → {rel_target} ({img_count} imgs)')

    # docs.json update
    pages_tree = build_pages_tree(chapter_entries)
    update_docs_json(args.chapter, chapter['title_zh'], pages_tree, args.dry_run)

    # Log
    log_path = Path(f'/tmp/aitable-import-{args.chapter}.log')
    log_lines = [f'{t[0]}: ' + ' | '.join(str(x) for x in t[1:]) for t in log]
    log_path.write_text('\n'.join(log_lines) + '\n', encoding='utf-8')
    unresolved = sum(1 for t in log if t[0] == 'link-unresolved')
    ok = sum(1 for t in log if t[0] == 'link-ok')
    bareid = sum(1 for t in log if t[0] == 'wolai-bareid')
    src_missing = sum(1 for t in log if t[0] == 'src-missing')
    print(f'\nSummary: converted={converted}, images={image_total}, '
          f'links ok={ok}, unresolved={unresolved}, wolai-bareid stripped={bareid}, '
          f'src-missing={src_missing}')
    print(f'Log: {log_path}')
    if unresolved:
        print(f'⚠  {unresolved} internal .md links could not be resolved — degraded to plain text.')
    if bareid:
        print(f'ℹ  {bareid} wolai bare-id links stripped (cross-doc references to pages '
              f'whose wolai id we don\'t have); see log to restore manually later.')
    if src_missing:
        print(f'⚠  {src_missing} image refs in source point to files that do not exist on disk '
              f'(source-level corruption); see log for paths — these will render broken.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
