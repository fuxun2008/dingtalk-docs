const FRONTMATTER_RE = /^---\n([\s\S]*?)\n---/;

export interface ParsedFrontmatter {
  title?: string;
  description?: string;
  rest: Record<string, string>;
  raw: string;
  bodyOffset: number;
}

function unquote(value: string): string {
  const trimmed = value.trim();
  if (trimmed.length >= 2 && trimmed.startsWith('"') && trimmed.endsWith('"')) {
    return trimmed.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, '\\');
  }
  if (trimmed.length >= 2 && trimmed.startsWith("'") && trimmed.endsWith("'")) {
    return trimmed.slice(1, -1).replace(/''/g, "'");
  }
  return trimmed;
}

function quoteForYaml(value: string): string {
  if (value === '') return "''";
  if (/[:\-#?{}[\],&*!|>'"%@`\n]/.test(value) || value !== value.trim()) {
    return `'${value.replace(/'/g, "''")}'`;
  }
  return value;
}

/** title/description follow the corpus convention of always double-quoting. */
function doubleQuote(value: string): string {
  return `"${value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
}

export function parseFrontmatter(content: string): ParsedFrontmatter | null {
  const m = FRONTMATTER_RE.exec(content);
  if (!m) return null;
  const body = m[1];
  const raw = m[0];
  const lines = body.split('\n');
  const result: ParsedFrontmatter = {
    rest: {},
    raw,
    bodyOffset: raw.length,
  };
  for (const line of lines) {
    const idx = line.indexOf(':');
    if (idx < 0) continue;
    const key = line.slice(0, idx).trim();
    const val = unquote(line.slice(idx + 1));
    if (key === 'title') result.title = val;
    else if (key === 'description') result.description = val;
    else result.rest[key] = val;
  }
  return result;
}

export function readTitle(content: string): string | undefined {
  return parseFrontmatter(content)?.title;
}

export function buildFrontmatter(fm: { title?: string; description?: string; rest: Record<string, string> }): string {
  const lines: string[] = ['---'];
  if (fm.title !== undefined) lines.push(`title: ${doubleQuote(fm.title)}`);
  if (fm.description !== undefined) lines.push(`description: ${doubleQuote(fm.description)}`);
  for (const [k, v] of Object.entries(fm.rest)) {
    lines.push(`${k}: ${quoteForYaml(v)}`);
  }
  lines.push('---');
  return lines.join('\n');
}
