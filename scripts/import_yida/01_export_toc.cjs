#!/usr/bin/env node
/**
 * 01_export_toc.cjs — 宜搭用户手册 TOC 导出
 *
 * 读 yida-doc-gen/config/sidebars.js 的 yida_support 树，产出：
 *   output/toc.json       扁平文档清单（slug/label/groupPath/order/filePath）
 *   output/nav-tree.json  压平后的导航树（Mintlify group 嵌套 ≤3 层）
 *   output/group-map.json 19 个一级分类 zh→en slug 映射（人工检查点 1）
 *
 * 用法: node scripts/import_yida/01_export_toc.cjs
 */
const fs = require('fs');
const path = require('path');

const SIDEBARS = '/Users/yanxin/www/yida-doc-gen/config/sidebars.js';
const OUT_DIR = path.join(__dirname, 'output');

// 一级分类 zh label → 英文 group slug（决定 zh/yida/<slug>/ 目录名）
const GROUP_SLUGS = {
  宜搭简介: 'intro',
  快速开始: 'quickstart',
  表单管理: 'form',
  流程设计: 'process',
  '集成&自动化': 'integration',
  门户设计: 'portal',
  报表设计: 'report',
  聚合表设计: 'aggregate-table',
  大屏设计: 'dashboard',
  自定义页面: 'custom-page',
  酷应用: 'cool-app',
  平台管理: 'platform-admin',
  应用管理: 'app-admin',
  AI助理: 'ai',
  插件中心: 'plugin',
  国际化: 'i18n',
  专属宜搭: 'exclusive',
  联系我们: 'contact-us',
  '开发者功能（需有代码基础）': 'developer-features',
};

const MAX_GROUP_DEPTH = 3; // Mintlify group 最大嵌套层（tab 下）

// 国际版不适用的分类（整组排除，含其下全部文档）：
// - AI助理（含「AI 助理」「宜搭 AI」两子组）/ 联系我们 / 大屏设计 / 插件中心：顶层组
// - 产品计费：宜搭简介下子分类（国内售卖体系）
// 注意：专属宜搭下的「空间 AI 助理」不在排除范围，按完整 label 精确匹配
const EXCLUDE_GROUPS = new Set(['AI助理', '联系我们', '产品计费', '大屏设计', '插件中心']);

// 国际版不适用/无实质内容的单页排除（按末段 slug 匹配）：
// - 空页/占位页：portal 富文本、内嵌页面（敬请期待）；integration 消息节点、Webhook触发、分支节点（源站即空）
// - 纯目录页（无链接无正文）：应用分发概述、统一流程概述、流程高级设置概述
// - 内网 epaas 通道文档（s-api.alibaba-inc.com，国际版不可用）：编写更多语言 SDK、宜搭 Open API (旧)
// - 国内支付/签章功能（支付宝/网商银行/e签宝体系）：电子签章、在线收款、银企支付
const EXCLUDE_DOCS = new Set([
  'srsbc47fusf3cnu4', // portal 富文本（敬请期待）
  'cahqidwksuogo6bl', // portal 内嵌页面（敬请期待）
  'gilxm02v9uel919u', // integration 消息节点（空）
  'qfnu8wt7i9689ekk', // integration Webhook触发（敬请期待）
  'ybagk4dyzisgfkmb', // integration 分支节点（空）
  'ymt5eevh432paorp', // app-admin 应用分发概述（纯目录）
  'ea1o8cgypga0lh9t', // process 统一流程目录页
  'ef8e88',           // process 流程高级设置目录页
  'li2sf8',           // 编写更多语言 SDK（内网网关）
  'agb8im',           // 宜搭 Open API (旧)（内网 epaas）
  'poyf3h',           // 电子签章（e签宝）
  'ibwgqm8t76c3tsmp', // 在线收款（支付宝/银企支付）
  'nr00zrwzux7x7xai', // 银企支付
]);

// 分组名精简（侧边栏展示用，去冗余后缀/历史别名；匹配仍用语雀原 label）
const GROUP_RENAME = {
  '开发者功能（需有代码基础）': '开发者功能',
  '上下级组织分发应用（原关联组织）': '上下级组织分发应用',
  '宜搭 Open API 开放接口': '宜搭 Open API',
  'JS 动作面板 - 前端代码开发': 'JS 动作面板',
};
const rename = (label) => GROUP_RENAME[label] || label;

const raw = require(SIDEBARS);
const sidebar = (raw.default || raw)['yida_support'];
if (!sidebar) throw new Error('sidebars.js 中未找到 yida_support');

// 根节点是「用户手册」总分类，取其 items 作为 19 个一级分类
const root = sidebar[0];
if (root.label !== '用户手册') throw new Error('根节点不是 用户手册: ' + root.label);

const docs = []; // 扁平清单
const seen = new Set();
let order = 0;

function docSlug(id) {
  return id.replace(/^yida_support\//, '');
}

// 语雀 slug 可能是层级路径（如 wtwabe/uezmum/og76m2），末段已验证全局唯一，文件名取末段
function lastSeg(slug) {
  return slug.split('/').pop();
}

function addDoc(id, label, topGroup, groupPath) {
  const slug = docSlug(id);
  if (EXCLUDE_DOCS.has(lastSeg(slug))) {
    console.log('[exclude] 跳过单页:', lastSeg(slug), label);
    return null;
  }
  if (seen.has(slug)) {
    console.warn('  [dup] 重复 slug 跳过:', slug, label);
    return null;
  }
  seen.add(slug);
  const groupDir = GROUP_SLUGS[topGroup];
  const entry = {
    order: order++,
    slug,
    id,
    label,
    topGroup,
    groupPath, // zh label 路径（不含根）
    file: `zh/yida/${groupDir}/${lastSeg(slug)}`, // 不带扩展名，即 Mintlify page 路径
  };
  docs.push(entry);
  return entry.file;
}

/**
 * 递归构建 Mintlify 导航节点。
 * depth 为当前 group 层级（一级分类 = 1）。
 * 返回 pages 数组元素（字符串 page 路径 或 {group, pages}）。
 */
function buildNav(items, topGroup, groupPath, depth) {
  const pages = [];
  for (const it of items) {
    if (it.type === 'doc') {
      const f = addDoc(it.id, it.label, topGroup, groupPath);
      if (f) pages.push(f);
    } else if (it.type === 'category') {
      if (EXCLUDE_GROUPS.has(it.label)) {
        console.log('[exclude] 跳过分类:', groupPath.concat(it.label).join(' > '));
        continue;
      }
      const childPath = [...groupPath, it.label];
      const childPages = [];
      // 分类自带落地文档 → 作为该组第一页
      if (it.link && it.link.id) {
        const f = addDoc(it.link.id, it.label, topGroup, childPath);
        if (f) childPages.push(f);
      }
      const kids = buildNav(it.items || [], topGroup, childPath, depth + 1);
      childPages.push(...kids);
      if (childPages.length === 0) continue;
      if (depth >= MAX_GROUP_DEPTH) {
        // 压平：深层分类不再生成 group，页面平铺到上层
        pages.push(...childPages);
      } else {
        pages.push({ group: rename(it.label), pages: childPages });
      }
    }
  }
  return pages;
}

const navTree = [];
const groupMap = [];
for (const cat of root.items) {
  if (cat.type !== 'category') {
    console.warn('[warn] 一级出现非分类节点:', cat.label || cat.id);
    continue;
  }
  if (EXCLUDE_GROUPS.has(cat.label)) {
    console.log('[exclude] 跳过一级分类:', cat.label);
    continue;
  }
  const gslug = GROUP_SLUGS[cat.label];
  if (!gslug) throw new Error('缺少一级分类 slug 映射: ' + cat.label);
  const before = docs.length;
  const pages = [];
  if (cat.link && cat.link.id) {
    const f = addDoc(cat.link.id, cat.label, cat.label, [cat.label]);
    if (f) pages.push(f);
  }
  pages.push(...buildNav(cat.items || [], cat.label, [cat.label], 1));
  navTree.push({ group: rename(cat.label), pages });
  groupMap.push({ label: cat.label, slug: gslug, docCount: docs.length - before });
}

// 根分类自身的 link（用户手册总入口页）
if (root.link && root.link.id) {
  console.log('[info] 根「用户手册」自带 link:', root.link.id, '→ 归入 intro 组首位');
  const slug = docSlug(root.link.id);
  if (!seen.has(slug)) {
    const entry = {
      order: -1,
      slug,
      id: root.link.id,
      label: root.label,
      topGroup: '宜搭简介',
      groupPath: ['宜搭简介'],
      file: `zh/yida/intro/${lastSeg(slug)}`,
    };
    docs.unshift(entry);
    navTree[0].pages.unshift(entry.file);
    groupMap[0].docCount++;
  }
}

// 统计压平情况
function maxNavDepth(pages, d) {
  let m = d;
  for (const p of pages) {
    if (typeof p === 'object') m = Math.max(m, maxNavDepth(p.pages, d + 1));
  }
  return m;
}

fs.mkdirSync(OUT_DIR, { recursive: true });
fs.writeFileSync(path.join(OUT_DIR, 'toc.json'), JSON.stringify(docs, null, 2));
fs.writeFileSync(path.join(OUT_DIR, 'nav-tree.json'), JSON.stringify(navTree, null, 2));
fs.writeFileSync(path.join(OUT_DIR, 'group-map.json'), JSON.stringify(groupMap, null, 2));

console.log('总文档数:', docs.length);
console.log('nav group 最大深度:', maxNavDepth(navTree.map((g) => ({ pages: g.pages, group: g.group })), 1));
console.table(groupMap);
