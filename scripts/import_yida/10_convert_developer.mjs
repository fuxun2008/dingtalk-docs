#!/usr/bin/env node
/**
 * 10_convert_developer.mjs — 宜搭开发者手册 md/mdx → Mintlify MDX
 *
 * 源: yida-doc-gen/developer-doc/docs/{guide,api,tutorial,components}
 * 产物: zh/open/yida/<relpath>.mdx + output/tab-yida-dev.json + output/dev-report.json
 *
 * 转换要点:
 *  - <Iframe url> → 原生 <iframe>（在线 demo 保留）
 *  - <AttrTable dataSource> → 求值后渲染为 markdown 表格（category=form 合并公共表单属性）
 *  - :::tip/info/caution/danger → <Tip>/<Note>/<Warning>
 *  - 独立图片段落 → <Frame>
 *  - 链接重写: /docs/* → /zh/open/yida/*；用户手册链接 → /zh/yida/*
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = '/Users/yanxin/www/yida-doc-gen/developer-doc/docs';
const REPO = path.join(__dirname, '..', '..');
const DEST_PREFIX = 'zh/open/yida';
const OUT_DIR = path.join(__dirname, 'output');

// 用户手册链接映射（末段 slug → 新站路径）
const toc = JSON.parse(fs.readFileSync(path.join(OUT_DIR, 'toc.json'), 'utf8'));
const LAST_MAP = Object.fromEntries(toc.map((e) => [e.slug.split('/').pop(), '/' + e.file]));

// AttrTable 公共表单属性
const formPropsSrc = fs.readFileSync(
  '/Users/yanxin/www/yida-doc-gen/developer-doc/src/components/AttrTable/formProps.ts',
  'utf8',
);
const FORM_PROPS = new Function('return ' + formPropsSrc.replace(/^export default/, ''))();

const report = { converted: [], warnings: [] };
const warn = (file, kind, detail) => report.warnings.push({ file, kind, detail: String(detail).slice(0, 160) });

// 标题精简覆盖（文档 id → 新标题）：中文 ≤15 字规范；
// 组件页「API 名 + 中文名」为标准命名专有名词，不精简
const TITLE_OVERRIDES = {
  'guide/FAQ/q2': '使用 Apache ECharts',
  'guide/FAQ/q4': '宜搭与三方系统数据打通',
};

// ---------- 侧边栏结构（复刻 developer-doc/config/sidebars.js + getDocsFromDir） ----------

function readFm(fp) {
  const src = fs.readFileSync(fp, 'utf8');
  const m = /^---\n([\s\S]*?)\n---\n?/.exec(src);
  const fm = {};
  if (m) {
    for (const line of m[1].split('\n')) {
      const kv = /^(\w+):\s*(.*)$/.exec(line.trim());
      if (kv) fm[kv[1]] = kv[2].replace(/^['"]|['"]$/g, '');
    }
  }
  return { fm, body: m ? src.slice(m[0].length) : src };
}

function docsFromDir(dir) {
  const abs = path.join(SRC, dir);
  return fs
    .readdirSync(abs)
    .filter((f) => /\.mdx?$/.test(f) && !/^index\.mdx?$/.test(f))
    .map((f) => path.join(dir, f))
    .sort((a, b) => {
      const oa = Number(readFm(path.join(SRC, a)).fm.order || 100);
      const ob = Number(readFm(path.join(SRC, b)).fm.order || 100);
      return oa - ob;
    })
    .map((f) => f.replace(/\.mdx?$/, ''));
}

const sidebar = [
  {
    group: '开发指南',
    ids: [
      'guide/about',
      'guide/start',
      'guide/keywords',
      'guide/designer',
      { group: '核心概念', ids: docsFromDir('guide/concept') },
      { group: '自定义组件', ids: docsFromDir('guide/customComponent') },
      { group: 'FAQ', ids: docsFromDir('guide/FAQ') },
      'guide/contributing',
    ],
  },
  { group: 'API', ids: docsFromDir('api') },
  { group: '教程', ids: docsFromDir('tutorial') },
  {
    group: '组件',
    ids: [
      ...docsFromDir('components'),
      { group: '布局组件', ids: docsFromDir('components/layout') },
      { group: '基础组件', ids: docsFromDir('components/basic') },
      { group: '表单组件', ids: docsFromDir('components/form') },
      { group: '高级组件', ids: docsFromDir('components/advanced') },
    ],
  },
];

// ---------- 内容转换 ----------

function rewriteLink(url, file) {
  // 开发者手册站内链接（原站 /docs/<dir>/... 或构建后 /docs/developer/...）
  let m = /^\/docs\/developer\/(.+?)(#.*)?$/.exec(url) || /^\/docs\/((?:guide|api|tutorial|components)\/.+?)(#.*)?$/.exec(url);
  if (m) return `/${DEST_PREFIX}/${m[1].replace(/\.mdx?$/, '')}${m[2] || ''}`;
  // 用户手册
  m = /^https:\/\/(?:docs\.aliwork\.com\/docs\/yida_support|www\.yuque\.com\/yida\/support)\/([\w/]+?)\/?(#.*)?$/.exec(url);
  if (m) {
    const last = m[1].split('/').pop();
    if (LAST_MAP[last]) return LAST_MAP[last] + (m[2] || '');
    warn(file, 'user-manual-miss', url);
    return `https://docs.aliwork.com/docs/yida_support/${m[1]}`;
  }
  if (/alibaba-inc\.com/.test(url)) {
    warn(file, 'intranet-link', url);
    return null; // 去链接
  }
  if (/^https?:\/\/oa\.dingtalk\.com/.test(url)) return url.replace('oa.dingtalk.com', 'oa.dingtalk.io');
  if (/dingtalk\.com/.test(url)) warn(file, 'dingtalk-keep', url);
  return url;
}

function rewriteLinks(text, file) {
  // label 允许一层嵌套方括号（如 [SearchDataSource[]](...)）
  return text.replace(/(!?)\[((?:[^\[\]]|\[[^\]]*\])*)\]\(([^)\s]+)\)/g, (whole, bang, label, url) => {
    if (bang) return whole; // 图片不动
    const nu = rewriteLink(url, file);
    if (nu === null) return label;
    return `[${label}](${nu})`;
  });
}

const CALLOUT_MAP = { tip: 'Tip', info: 'Note', note: 'Note', caution: 'Warning', warning: 'Warning', danger: 'Warning' };

function convertCallouts(body, file) {
  const lines = body.split('\n');
  const out = [];
  const stack = [];
  for (const line of lines) {
    const open = /^:::(\w+)\s*(.*)$/.exec(line.trim());
    if (open && CALLOUT_MAP[open[1]]) {
      const comp = CALLOUT_MAP[open[1]];
      stack.push(comp);
      out.push(`<${comp}>`);
      if (open[2]) out.push(`**${open[2]}**`);
      continue;
    }
    if (/^:::\s*$/.test(line.trim())) {
      const comp = stack.pop();
      if (comp) {
        out.push(`</${comp}>`);
      } else {
        warn(file, 'callout-unbalanced', line);
        out.push(line);
      }
      continue;
    }
    if (open) warn(file, 'callout-unknown', line);
    out.push(line);
  }
  return out.join('\n');
}

function mdCell(v) {
  const s = String(v ?? '-')
    .replace(/\|/g, '\\|')
    .replace(/\n/g, '<br />')
    .trim();
  if (!s) return '-';
  // code span 外的 { 和 <（<br /> 除外）需转义，避免 MDX 当作 JSX 解析
  return s
    .split(/(`[^`]*`)/)
    .map((seg, i) => (i % 2 === 1 ? seg : seg.replace(/\{/g, '\\{').replace(/<(?!br\s*\/?>)/g, '\\<')))
    .join('');
}

function codeSpan(s) {
  const fence = s.includes('`') ? '``' : '`';
  return `${fence}${s}${fence}`;
}

function fmtType(v, file) {
  const s = String(v ?? '-').trim();
  if (!s || s === '-') return '-';
  // 含 markdown 链接的类型保留链接并重写，否则包 code span
  if (s.includes('](')) return mdCell(rewriteLinks(s, file));
  return mdCell(codeSpan(s));
}

function fmtDefault(v) {
  let s = String(v ?? '-').trim();
  if (!s || s === '-') return '-';
  // fenced 代码块（```/~~~，源数据存在未闭合 fence）压成单行 code span
  s = s.replace(/^(?:```|~~~)\w*\s*/, '').replace(/(?:```|~~~)\s*$/, '');
  s = s.replace(/\s+/g, ' ').trim();
  if (!s) return '-';
  return mdCell(codeSpan(s));
}

function attrTableToMd(expr, category, file) {
  let data;
  try {
    data = new Function('return ' + expr)();
  } catch (e) {
    warn(file, 'attrtable-eval-fail', e.message);
    return null;
  }
  if (category === 'form') data = [...FORM_PROPS, ...(data || [])];
  data = [...(data || [])].sort((a, b) => (a.code < b.code ? -1 : 1));
  if (!data.length) return null;
  const rows = data.map(
    (r) => `| \`${r.code}\` | ${mdCell(rewriteLinks(r.desc ?? '-', file))} | ${fmtType(r.type, file)} | ${fmtDefault(r.default)} |`,
  );
  return ['| 属性 | 说明 | 类型 | 默认值 |', '|---|---|---|---|', ...rows].join('\n');
}

function convertAttrTables(body, file) {
  let out = '';
  let i = 0;
  while (i < body.length) {
    const start = body.indexOf('<AttrTable', i);
    if (start < 0) {
      out += body.slice(i);
      break;
    }
    out += body.slice(i, start);
    const end = body.indexOf('/>', start);
    if (end < 0) {
      warn(file, 'attrtable-unclosed', '');
      out += body.slice(start);
      break;
    }
    const tag = body.slice(start, end + 2);
    const catM = /category=["'](\w+)["']/.exec(tag);
    const dsIdx = tag.indexOf('dataSource={');
    let md = null;
    if (dsIdx >= 0) {
      // 花括号配平提取表达式
      let depth = 0;
      let j = dsIdx + 'dataSource={'.length - 1; // 指向起始 {
      let exprEnd = -1;
      for (; j < tag.length; j++) {
        if (tag[j] === '{') depth++;
        else if (tag[j] === '}') {
          depth--;
          if (depth === 0) {
            exprEnd = j;
            break;
          }
        }
      }
      if (exprEnd > 0) {
        md = attrTableToMd(tag.slice(dsIdx + 'dataSource={'.length, exprEnd), catM?.[1], file);
      }
    } else if (catM) {
      md = attrTableToMd('[]', catM[1], file);
    }
    out += md ?? '';
    if (md === null) warn(file, 'attrtable-dropped', tag.slice(0, 80));
    i = end + 2;
  }
  return out;
}

// 加粗尾部标点 + 闭合 ** 后紧跟文字 → CommonMark 不闭合（页面裸显 **）：标点移出加粗
const BOLD_PUNCT_RE = /\*\*([^*\n]*[^\s*：:；;，,、。．.！!？?])([：:；;，,、。．.！!？?]+)\*\*(?=[\w\u4e00-\u9fff])/g;

function fixBoldPunct(body) {
  return body
    .split(/(```[\s\S]*?```)/)
    .map((seg, i) => (i % 2 ? seg : seg.replace(BOLD_PUNCT_RE, '**$1**$2')))
    .join('');
}

// ---- www.aliwork.com → www.yidaapps.com 域名国际化 ----
// 不可替换路径（国际版无对应服务，实测会坏）：/o/* 样例应用、/developer* demo/设计器、
// /bench* 工作台实例、/alibaba/* 国内专有路径；其余（裸域、/fileHandle、/APP_* 模板等）已实测同构，替换。
const ALIWORK_KEEP = ['/o', '/developer', '/bench', '/alibaba'];
const keepAliworkPath = (path) =>
  ALIWORK_KEEP.some((p) => path === p || path.startsWith(p + '/') || path.startsWith(p + '?') || path.startsWith(p + '-'));

function fixAliworkDomains(body) {
  const stash = [];
  // 1) href 指向不可替换路径的 md 链接整段保护（label 也不动，保持 label/href 一致）
  body = body.replace(/\[([^\]]*)\]\((https?:\/\/www\.aliwork\.com(\/[^)]*)?)\)/g, (whole, label, href, path) => {
    if (keepAliworkPath(path || '/')) {
      stash.push(whole);
      return `\x00KEEP${stash.length - 1}\x00`;
    }
    return whole;
  });
  // 2) 通用 URL 替换（iframe demo src 的 /developer* 命中 keep 规则自动保留）
  body = body.replace(/(https?:\/\/)www\.aliwork\.com(\/[^\s)"'`\\<>\]]*)?/g, (whole, proto, path) =>
    keepAliworkPath(path || '/') && path ? whole : proto + 'www.yidaapps.com' + (path || ''));
  // 3) 无协议裸域名
  body = body.replace(/(?<![/.\w])www\.aliwork\.com(?![\w.])/g, 'www.yidaapps.com');
  return body.replace(/\x00KEEP(\d+)\x00/g, (_, i) => stash[+i]);
}

function frameImages(body) {
  // 独立成段的图片包 Frame（跳过代码块）
  const parts = body.split(/(```[\s\S]*?```)/);
  return parts
    .map((seg, idx) => {
      if (idx % 2 === 1) return seg;
      return seg.replace(/^(!\[[^\]]*\]\([^)]+\))[ \t]*$/gm, '<Frame>\n  $1\n</Frame>\n');
    })
    .join('');
}

function firstParagraph(body) {
  for (const block of body.split(/\n\s*\n/)) {
    const t = block.trim();
    if (!t || t.startsWith('#') || t.startsWith('import ') || t.startsWith('<') || t.startsWith('!') || t.startsWith(':::') || t.startsWith('```')) continue;
    const plain = t
      .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
      .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
      .replace(/[*`>#]/g, '')
      .replace(/\s+/g, ' ')
      .trim();
    if (plain.length >= 10) return plain.slice(0, 110);
  }
  return '';
}

function convertFile(id) {
  const srcPath = fs.existsSync(path.join(SRC, id + '.md')) ? path.join(SRC, id + '.md') : path.join(SRC, id + '.mdx');
  const { fm, body: rawBody } = readFm(srcPath);
  let body = rawBody;
  // 去掉 docusaurus 组件 import
  body = body.replace(/^import\s+(Iframe|AttrTable)\s+from\s+['"]components\/(Iframe|AttrTable)['"];?\s*$/gm, '');
  // Iframe → 原生 iframe
  body = body.replace(/<Iframe\s+url=["']([^"']+)["'][^/>]*\/>/g, '<iframe src="$1" width="100%" height="480" frameBorder="0"></iframe>');
  body = convertAttrTables(body, id);
  body = convertCallouts(body, id);
  body = rewriteLinks(body, id);
  body = fixAliworkDomains(body);
  body = fixBoldPunct(body);
  body = frameImages(body);
  body = body.replace(/\n{3,}/g, '\n\n').trim();

  // 正文首行 H1：无 frontmatter title 时提取为 title，并从正文移除避免双标题
  let title = fm.title || '';
  const h1m = /^#\s+(.+)\n?/.exec(body);
  if (h1m) {
    if (!title) title = h1m[1].trim();
    body = body.slice(h1m[0].length).trim();
  }
  if (!title) title = path.basename(id);
  title = TITLE_OVERRIDES[id] || title;
  const desc = firstParagraph(body);
  const fmLines = ['---', `title: "${title.replace(/"/g, '\\"')}"`];
  if (desc) fmLines.push(`description: "${desc.replace(/"/g, '\\"')}"`);
  fmLines.push('---');

  const dest = path.join(REPO, DEST_PREFIX, id + '.mdx');
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.writeFileSync(dest, fmLines.join('\n') + '\n\n' + body + '\n');
  report.converted.push(id);
}

// ---------- 执行 ----------

function walkIds(items, fn) {
  for (const it of items) {
    if (typeof it === 'string') fn(it);
    else walkIds(it.ids, fn);
  }
}

for (const g of sidebar) walkIds(g.ids, convertFile);

// nav 片段（landing 页 index 由人工创建，置于「开发指南」组之前的 tab 首页）
function toNav(items) {
  return items.map((it) =>
    typeof it === 'string' ? `${DEST_PREFIX}/${it}` : { group: it.group, pages: toNav(it.ids) },
  );
}
const tab = {
  tab: '宜搭开发',
  icon: 'cubes',
  groups: [
    { group: '开始使用', pages: [`${DEST_PREFIX}/index`] },
    ...sidebar.map((g) => ({ group: g.group, pages: toNav(g.ids) })),
  ],
};
fs.writeFileSync(path.join(OUT_DIR, 'tab-yida-dev.json'), JSON.stringify(tab, null, 2));

const kinds = {};
for (const w of report.warnings) kinds[w.kind] = (kinds[w.kind] || 0) + 1;
fs.writeFileSync(path.join(OUT_DIR, 'dev-report.json'), JSON.stringify(report, null, 2));
console.log('converted:', report.converted.length);
console.log('warnings:', kinds);
