# 三语镜像建页 + docs.json 三处 navigation 同步

> 子 skill：作为 [[docs-dingtalk-onboard]] 阶段 9 单页增量补充时调用；也作为日常单页新增的入口

把"新增一篇文档"从 7 步手工操作（建 3 mdx + 改 docs.json 3 处 + 跑死链）压成一条命令。最容易漏的是 `docs.json` 某个 language 块的 `pages[]` 没追加，或三语路径前缀写错（en `/<product>/...` / zh `/zh/<product>/...` / ja `/ja/<product>/...`）。

## 适用场景

- 给已有 product tab + group 加一篇新文档（最常见）
- 临时补一篇专题文档（如新功能上线公告）
- 不适用：批量翻译走 `/docs-translate-batch`；新增 group / product tab 走 `/docs-nav-edit`

## 参数

- `<product>`（必填）：产品 slug，全英文 kebab-case（如 `docs` / `aitable` / `overview`）
- `<slug>`（必填）：页面 kebab-case 名，与文件名一致（如 `voice-input` / `formula-vlookup`）
- `<group>`（必填）：所属 group 中文名（如 `常见问题` / `编辑`），脚本会按中文名匹配 zh 块的 `group` 字段
- `--title-zh "<中文标题>"`（可选）：默认用 slug 反推；新页非纯英文标题时传入
- `--title-en "<English Title>"`（可选）：同上
- `--title-ja "<日本語タイトル>"`（可选）：同上
- `--skip-broken-links`（可选）：跳过最后的 `mint broken-links`（适合临时建多页时连跑，最后一次再总验）

## 执行流程（5 步）

### 步骤 1 — 前置检查

```bash
test -f docs.json
test -d zh/<product>/ && test -d <product>/ && test -d ja/<product>/    # 三语 product 目录存在
git status -s | grep -v '??' | head                                      # worktree 干净（避免脏 add）
```

读 `docs.json` 解析三语 navigation：
- 找到 product tab（按 zh 块的 tab 显示名映射到 en/ja 同位置 tab）
- 找到 group（按 zh 块的中文 `group` 字段 → 同序匹配 en/ja 的 `group` 字段）
- 抽出该 group 的 `pages[]` 三语版本

**fail fast**：
- product 三语目录有任一缺失 → 提示用户先建 product（用 `/docs-nav-edit add-product`）
- group 在 zh / en / ja 任一不存在 → 提示用户先建 group（用 `/docs-nav-edit add-group`）

### 步骤 2 — 同名冲突检查

```bash
test -f zh/<product>/<group-slug>/<slug>.mdx && echo "[err] zh 已存在同名"
test -f <product>/<group-slug>/<slug>.mdx && echo "[err] en 已存在同名"
test -f ja/<product>/<slug>/<slug>.mdx && echo "[err] ja 已存在同名"
```

任一存在 → 停下问用户：覆盖 / 改 slug / 取消。

### 步骤 3 — 建 3 个 mdx

**目标路径**（group-slug 由 group 中文名 kebab-case 化得到，**优先**从已有兄弟页路径反推）：

```
en:  <product>/<group-slug>/<slug>.mdx
zh:  zh/<product>/<group-slug>/<slug>.mdx
ja:  ja/<product>/<group-slug>/<slug>.mdx
```

frontmatter 模板：

```mdx
---
title: "<title-{lang}>"
description: "<one-line description in target lang>"
---

## <H2 占位>

<!-- TODO: 正文 -->
```

**关键**：
- `title` 三语自然翻译
- `description` 三语自然翻译，单句 ≤ 80 字，Mintlify SEO 用
- body 留 H2 + TODO 占位，**不擅自编内容**

### 步骤 4 — Edit 三处 docs.json（绝不 Write）

用 `Edit` 工具精确字符串替换，三个 language 块 `pages[]` 同序追加新条目：

```jsonc
// en 块
{
  "group": "Frequently Asked Questions",
  "pages": [
    "<product>/<group-slug>/existing-page",
    "<product>/<group-slug>/<slug>"     // ← 新增
  ]
}

// zh 块
{
  "group": "常见问题",
  "pages": [
    "zh/<product>/<group-slug>/existing-page",
    "zh/<product>/<group-slug>/<slug>"  // ← 新增
  ]
}

// ja 块
{
  "group": "よくある質問",
  "pages": [
    "ja/<product>/<group-slug>/existing-page",
    "ja/<product>/<group-slug>/<slug>"  // ← 新增
  ]
}
```

**字符串替换技巧**：用"最后一条已有 page + 闭合 `]`"作 `old_string`，加新行做 `new_string`：

```
old: "<product>/<group-slug>/last-existing"
        ]
new: "<product>/<group-slug>/last-existing",
        "<product>/<group-slug>/<slug>"
        ]
```

每个 language 块单独 Edit（共 3 次 Edit 调用），避免一次性大段替换风险。

### 步骤 5 — 验证

```bash
# JSON 合法
python3 -c "import json; json.load(open('docs.json'))"

# 死链（除非 --skip-broken-links）
mint broken-links
```

报告：

```
✓ 三语建页完成：
  - en: <product>/<group-slug>/<slug>.mdx
  - zh: zh/<product>/<group-slug>/<slug>.mdx
  - ja: ja/<product>/<group-slug>/<slug>.mdx
  - docs.json 三处 pages 已同步追加
  - mint broken-links：通过 / 见输出

下一步：
- 填正文：Edit 3 个 mdx 把 TODO 替换为正文
- 提交：/commit-flow
  建议 commit message：docs: 新增 <product>/<slug> 三语页。to #82317048
```

**不自动 commit / push**（按 user memory `feedback_commit_authorization.md`）。

## 关键陷阱

### 陷阱 1：tab 显示名按语言译，但 slug 永远英文

- en tab 名 `Docs` / zh tab 名 `文档` / ja tab 名 `ドキュメント`，但 product slug 永远是 `docs`（路径不变）
- 不要为日文版改 slug（如 `ja/dokyumento/...`），保持 `ja/docs/...`

### 陷阱 2：三语 pages 必须同位置追加

- 一个 group 的 en `pages[]` 第 N 个 = zh 第 N 个 = ja 第 N 个，反映同一篇文档
- 追加新页必须在三语 `pages[]` 的**同一位置**插入（一般是末尾），否则下次重排会乱位
- group 不存在时不擅自建——回到 `/docs-nav-edit add-group`

### 陷阱 3：`docs.json` 绝不 Write 整份

历史踩坑：用 Write 整份覆盖一次，毁掉作者风格 + 误删 2 个产品 tab，回滚后才发现。**只用 Edit 工具精确字符串替换**。

### 陷阱 4：group-slug 优先从已有兄弟页反推

中文 group 名 → 路径段没有机器映射（如 `常见问题` 可能是 `faq` / `common-issues` / `frequently-asked-questions`）。**先 ls 已有 group 目录拿到准确 slug**，不要凭想象命名。

## 与其他 skill 的协作

- `/docs-nav-edit add-group` — 新 group 时先用本 skill 建 group，再用 add-page 加页
- `/docs-translate <single-path>` — 单页建好后用此 skill 把 zh 翻译同步到 en/ja（如初稿是 zh）
- `/docs-preview` — 建多页后视觉验证
- `/commit-flow` — 用户授权提交（aoneId `82317048`）
