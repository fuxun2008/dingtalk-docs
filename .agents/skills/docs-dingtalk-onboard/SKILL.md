---
name: docs-dingtalk-onboard
version: 1.0.0
description: "Nine-stage orchestration pipeline that turns a raw DingTalk zh MDX export into a push-ready, mint-renderable, trilingual (en/zh/ja) help-center sub-product. Use when onboarding a new DingTalk sub-product, re-importing a product wholesale, or refreshing a single group."
description_zh: "钉钉文档子产品导入流水线（9 阶段编排）：把钉钉原始 zh mdx 导出树做成可 push、可渲染、可三语切换的最终态。"
user-invocable: true
argument-hint: "<slug> [--only <group>] [--from-stage N]"
---
# 钉钉文档子产品导入流水线

把"一份从钉钉文档（alidocs.dingtalk.com）原始导出的 zh mdx 树"按 **9 个阶段**编排成"可 push、可 mint dev 渲染、可三语切换"的最终态。整套流水线复用既有 13 个主脚本 + 7 个 lint 子脚本 + 5 个相关 skill，本 skill 是**编排者**——不抄脚本细节，只串流程并把 6 类历史踩坑写死在 prompt 里。

## 适用场景

- 新增 DingTalk 子产品帮助文档（源是钉钉文档 zh 导出 mdx 包，下一批 10+ 子产品都走这条线）
- 已有产品大规模重导入（旧 mdx 已在仓，但要全量刷新母版）
- 单 group 局部刷新（用 `--only` 限定，只走相关阶段）

## 参数

- `<product-slug>`（必传）：产品 slug，全英文 kebab-case，如 `calendar` / `meeting` / `mind` / `whiteboard`；最终落到 `zh/<slug>/`、`<slug>/`、`ja/<slug>/`
- `--archive <path>`（可选，阶段 1 必需）：钉钉文档归档目录绝对路径，如 `/Users/yanxin/Downloads/dingtalk-docs-archive`
- `--source-name <名>`（可选，阶段 1）：归档内的中文产品目录名（如 `9. 钉钉文档` / `12. 钉钉日历`），不传时让用户从 archive 列表里挑
- `--only <path>`（可选）：限定单 group 子集，如 `--only calendar/api`
- `--skip-translate`（可选）：只做 zh 侧清理，不出 en/ja（如果只是补 zh 母版）
- `--from-stage <N>`（可选）：从第 N 阶段开始（断点续跑；前置已通过手动验证时用）
- `--to-stage <N>`（可选）：只跑到第 N 阶段就停

## 执行流程（9 阶段 · 每阶段 dry-run → 用户确认 → apply → 验证 → 决定是否进下一阶段）

> **总原则**：每阶段开头都先 grep 看现状；现状即"通过条件"时直接 skip，**不强制走满**。任何阶段 apply 前必须 `git status` 干净（或 `git stash`），否则脚本 `--apply` 无 backup 会污染未提交工作。

### 阶段 1 — 导入归档（zh 侧建模）

> 如果还没有归档目录（`--archive` 传不出来），**先跑 [[docs-import-archive]]** 拉钉钉文档原始 mdx，产物路径作为本阶段 `--archive` 参数。

只在 `--archive` 有传或 `zh/<slug>/` 不存在时跑；否则直接进阶段 2。

```bash
# dry-run 看会建哪些文件
python3 scripts/import_archive.py --archive <archive-path> --only "<source-name>" --dry-run

# 满意 → apply
python3 scripts/import_archive.py --archive <archive-path> --only "<source-name>"
```

**验证**：
```bash
git status -s zh/<slug>/ | head      # 应只见 zh/<slug>/ 下新增
ls zh/<slug>/ | wc -l                # 文件数对得上归档？
```

**通过条件**：`zh/<slug>/` 存在 + `find zh/<slug> -name '*.mdx' | wc -l > 0`。

### 阶段 2 — frontmatter / 字符卫生

```bash
python3 scripts/lint/fix_frontmatter_nbsp.py                  # dry-run（脚本默认）
python3 scripts/lint/fix_frontmatter_nbsp.py --apply

python3 scripts/lint/clean_invisible_chars.py
python3 scripts/lint/clean_invisible_chars.py --apply

python3 scripts/lint/fix_garbage_descriptions.py
python3 scripts/lint/fix_garbage_descriptions.py --apply
```

> ⚠️ 这 3 个脚本目前 hardcode 扫 `zh/docs/**`。**给新子产品复用时，先用 `SearchReplace` 把脚本里的 `zh/docs/` 改为 `zh/<slug>/`**，跑完再改回——或者复制一份脚本为 `*_<slug>.py`。改完不要提交脚本本身，只提交产物。

**验证**：
```bash
grep -rP '\xc2\xa0' zh/<slug>/ --include='*.mdx' | head     # NBSP 应为 0
grep -rP '\xe2\x80\x8b' zh/<slug>/ --include='*.mdx' | head # 零宽应为 0
grep -rE '^description: "?(:::|\\||$)' zh/<slug>/ --include='*.mdx' | head  # 垃圾 description 应为 0
```

### 阶段 3 — 标题层级正规化（**顺序锁死**）

```bash
# 1) 删/降重复 H1（必须最先，否则 demote 把它变成"重复 H2"绕过本步检测）
python3 scripts/lint/strip_duplicate_h1.py
python3 scripts/lint/strip_duplicate_h1.py --apply

# 2) 全局 H1 降级（Mintlify 把 frontmatter.title 作为页面唯一 H1）
python3 scripts/lint/demote_all_h1.py
python3 scripts/lint/demote_all_h1.py --apply

# 3) 跳级修复（h2→h5 拉回 h2→h3）
python3 scripts/lint/normalize_headings.py
python3 scripts/lint/normalize_headings.py --apply
```

**验证**：
```bash
grep -rEn '^# [^!]' zh/<slug>/ --include='*.mdx' | head  # 正文 H1 应为 0（排除 shebang）
```

### 阶段 4 — `:::` 高亮块 / `&lt;` 实体

```bash
python3 scripts/lint/convert_admonitions.py
python3 scripts/lint/convert_admonitions.py --apply
```

映射：`:::` 裸 → `<Note>`、`:::tip` → `<Tip>`、`:::warning` → `<Warning>`、`:::info` → `<Info>`、`:::caution` → `<Warning>`、`:::note` → `<Note>`、`:::check` → `<Check>`。

**验证**：
```bash
grep -rE '^:::' zh/<slug>/ --include='*.mdx' | head      # 应为 0
grep -rE '&lt;' zh/<slug>/ --include='*.mdx' | head      # 实体应为 0
```

### 阶段 5 — 钉钉编辑器残留清理

```bash
# 5a. 伪 emoji 标签（[Bulb] [Notebook] [Sparkles] ...）→ Unicode
python3 scripts/fix_emoji_tags.py --lang zh
python3 scripts/fix_emoji_tags.py --lang zh --apply
```

**5b. 手工 SearchReplace 清剩余残骸**（脚本未覆盖的）：

```bash
# 看哪些命中
grep -rEn '\[Priority[: ]+[0-9]+\]|\[Flag\]|\[Tip [0-9]+\]|\[Progress\]|▍|▌|▲|◆' \
  zh/<slug>/ --include='*.mdx' | head -40
```

逐个用 `SearchReplace` 处理，参考既有产物 commit `66bc60e` 的 sed 模式：

- `[Priority: 1]` → `1.`（列表序号）
- `[Priority 1]` → 同上
- `[Flag]` / `[Progress]` / `[Tip N]` → 删除（多余装饰）
- `▍` / `▌` / `▲` / `◆` → 删除（widget marker）

**验证**：
```bash
grep -rE '\[Priority|\[Flag\]|\[Tip [0-9]|▌|▍' zh/<slug>/ --include='*.mdx' | wc -l   # 应为 0
```

### 阶段 6 — MDX 语法审计

```bash
/docs-audit-mdx --root <slug> --lang zh --skip-links
```

走子 skill。脚本检测 7 类（A. `++text++` / B. `** X**` / C. `[label](https:xxx)` / D. URL-as-label / E. 空 `<Note>` / F. release-notes Note 标签行 / G. release-notes 4 空格缩进），前 3 类 + E/F/G auto-fix，D 类报告人审。

**通过条件**：A/B/C/E/F/G 命中 0；D 类有命中时**停下来让用户审 label 改成什么**，不擅自决策。

### 阶段 7 — 翻译到 en + ja

除非 `--skip-translate`。走子 skill：

```bash
/docs-translate-batch <slug>
```

子 skill 内部会跑 7 步：词库前置检查 → 干跑预检 → 翻译 → 链接前缀修正 → 残留扫描 → mint broken-links → ja navigation 注册提示。

**成本预估**（按 docs/ 349 篇基准外推）：

| 篇数 | en 用时 | ja 用时 | 合计成本 |
|---|---|---|---|
| 100 | ~7 min | ~9 min | ~$15 |
| 200 | ~13 min | ~18 min | ~$30 |
| 349（基准） | 23 min | 32 min | $51.63 |

**通过条件**：en + ja report 的 failed = 0；skipped 仅为已存在的非占位文件。

### 阶段 8 — 链接清扫（**最容易漏的收尾**）

8a. 跨语言前缀污染（LLM 翻译时保留了 zh 原链 `/zh/<slug>/`）：

```bash
# 先 -c 看会改多少
grep -rE '\]\(/en/<slug>/|\]\(/zh/<slug>/' <slug>/ ja/<slug>/ --include='*.mdx' | wc -l

# 批量 sed
find <slug>/ -name '*.mdx' -exec sed -i '' 's|](/en/<slug>/|](/<slug>/|g' {} \;
find ja/<slug>/ -name '*.mdx' -exec sed -i '' 's|](/zh/<slug>/|](/ja/<slug>/|g' {} \;
```

8b. 全仓跨语言污染兜底（脚本扫得更宽）：

```bash
python3 scripts/fix_cross_lang_links.py
python3 scripts/fix_cross_lang_links.py --apply
```

8c. 钉钉旧域名 + spm 跟踪参数 + 中文锚（钉钉文档 export 常见 3 件套）：

```bash
# 看现状
grep -rE 'alidocs\.dingtalk\.com|\?spm=|#\s*「' zh/<slug>/ <slug>/ ja/<slug>/ --include='*.mdx' | wc -l
```

如果非 0，参考本会话 commit `64df707` 的 Python 4-步替换（**注意 6 号陷阱，绝不加 `\?$` MULTILINE fixup**）。

8d. 外链死链探针（SPA og:title 判定）：

```bash
/docs-audit-mdx --root <slug> --skip-syntax
```

8e. 死链总验：

```bash
mint broken-links
```

**通过条件**：`mint broken-links` 输出 0 死链（或只剩"超纲"的非本产品路径死链）。

### 阶段 9 — navigation 注册 + 视觉验收

9a. `docs.json` 三语 navigation 同步（**绝不用 Write 覆盖**，必须 SearchReplace 精确插入）：

读 zh / en / ja 三个 language 块，确认：
- 三块 `tabs[]` 同序追加 `<slug>` 对应 tab（slug 全英文，tab 显示名按语言翻译）
- 三块 `groups[]` 同序，groups 内 `pages[]` 路径分别带前缀 `/zh/<slug>/...` / `/<slug>/...` / `/ja/<slug>/...`

9b. ja navigation 注册可参考 `scripts/register_ja_docs_navigation.py` 模板（含 60+ 条中→日 group 名映射），但**每个产品的 group 名翻译是 product-specific 的**——本 skill 不机器做，提示用户给 group 中→日翻译表。

9c. 视觉验收：调用 [[docs-preview]] 子 skill：

```bash
/docs-preview
```

抽 5 篇各产品页（首页 / 1 个 group 入口 / 2 篇深层 / 1 篇含组件的）打开看可读。

**通过条件**：`mint dev` 起得来 + 三语首页可切 + 抽 5 篇渲染正常。

---

## 关键陷阱（已踩过 6 类）

### 陷阱 1：阶段 3 顺序锁死

`strip_duplicate_h1` → `demote_all_h1` → `normalize_headings`。先 demote 会把"重复 H1"变成"重复 H2"，绕过 strip 的去重检测（strip 只识别 H1）。

### 陷阱 2：阶段 7 占位检测必须覆盖中/英/日

`translate_mdx_batch.py` 的 `is_placeholder()` 已修复（commit `bb15cd3`，识别 `TODO translate` / `TODO 翻訳` / `TODO 翻译` / `Translate from` / `から翻訳` / `翻译自`），但跑前还是 `grep -rlE 'TODO translate|TODO 翻訳|TODO 翻译' <lang>/<slug>/ | head -3` 兜底确认有占位再跑。

### 陷阱 3：阶段 8 跨语言前缀污染必修

LLM 系统性产出错误前缀（en 加 `/en/`、ja 沿用 `/zh/`）。docs/ 基准：en 35 处 / ja 142 处。**步骤 8a 是必跑收尾**，不修 = 大量内部死链。

### 陷阱 4：阶段 8 alidocs 旧域 4 步替换严格顺序

```python
r'#\?dontjump=true#'  → '?dontjump=true'     # 1. 修双井号 export bug（最先）
r'#\s*「[^」]*」'      → ''                    # 2. 删中文锚
r'\s+「[^」]*」'       → ''                    # 2b. 步骤 1 副产物：留下无 # 的「...」
r'[?&]spm=[^&)\s]+'   → ''                    # 3. 删跟踪参数
r'alidocs\.dingtalk\.com' → 'docs.dingtalk.io' # 4. 域名换（最后做）
```

**绝不加 `\?$` MULTILINE fixup**——本会话 `feature-limits.mdx` 27 个 H3 问句标题的尾 `?` 全被吃掉，rollback 后才发现。如果 spm 删完留 `?)` 或 `?&`，只能精确修 `r'\?\)' → ')'` 和 `r'\?&' → '?'`。

### 陷阱 5：阶段 8 docs.dingtalk.io 死链信号是 og:title 空

docs.dingtalk.io 是 SPA，body 是 JS 渲染壳，HTTP 探针只能拿到静态外壳。**真信号是 SSR 注入的 `<meta property="og:title" content="">` 是否空**：活公开文档有真实标题，死/受限/exception 页面均空。已封装在 `check_external_links.py`。

### 陷阱 6：阶段 9 `docs.json` 绝不能 Write 整份覆盖

`docs.json` 必须用 `SearchReplace` 工具精确插入。一次性 Write 覆盖会破坏作者风格 + 误删其他 4-12 个产品 tab。三语块严格同序：product slug 全英文不译，tab 显示名按语言翻译（中文 `文档` / 日文 `ドキュメント`），group 标题各语言自然翻译。

---

## 与其他 skill 的协作

- `/docs-import-archive` — 阶段 1 上游：从钉钉文档站拉原始 mdx 归档
- `/docs-audit-mdx` — 阶段 6（syntax）+ 阶段 8d（死链探针）的子 skill
- `/docs-translate-batch` — 阶段 7 的子 skill
- `/docs-glossary-sync` — 阶段 7 之前如果有词库更新，先跑本 skill 让翻译用上最新术语
- `/docs-prune-orphan-images` — 阶段 5/6 大规模删章节后，清孤儿本地图（如有本地图引用）
- `/docs-nav-edit` — 阶段 9a `docs.json` 三语 navigation 注册的实际工具（add-product / add-group / verify）
- `/docs-preview` — 阶段 9c 视觉验收
- `/commit-flow` — 每阶段通过后用户授权提交（aoneId `82317048`）

**不自动 commit / push**（按 user memory `feedback_commit_authorization.md`）。每个阶段通过后停下来等用户确认是否提交。

## 提交建议（每阶段对应一个 commit）

```
docs: 阶段 1 — <slug> 导入归档 N 篇。to #82317048
docs: 阶段 2-3 — <slug> 字符卫生 + 标题层级正规化（X 文件）。to #82317048
docs: 阶段 4-5 — <slug> 高亮块 JSX + 钉钉编辑器残留清理（X 文件）。to #82317048
docs: 阶段 6 — <slug> MDX 语法审计修复（X 文件）。to #82317048
docs: 阶段 7 — <slug> N 篇 en/ja 全量翻译。to #82317048
docs: 阶段 8 — <slug> 链接清扫 + 死链清理（X 文件）。to #82317048
docs: 阶段 9 — <slug> 三语 navigation 注册。to #82317048
```

## 历史基准（docs/ 首批 2026-06）

| 阶段 | docs/ 349 篇实测 |
|---|---|
| 2 — 字符卫生 | NBSP 数千处一次清完 |
| 3 — 标题正规化 | 32 文件重复 H1 处理（strip）；批次 2-3 commit `4dabae3` |
| 5 — 钉钉编辑器残留 | 4019 处 / 128 文件（commit `868d6e8`） |
| 5a — 伪 emoji | 555 处 / 45 文件（commit `b60a116`） |
| 7 — 翻译 | en 23min/$24.25 + ja 32min/$27.38 = ~55min/$51.63 |
| 8a — 跨语言前缀 | en 35 处 / ja 142 处（commit `894d6aa` 修 EN 跨语言污染 309 处） |
| 8d — 外链死链 | 93 URL / 420 占位 / 168 文件（commit `e44c0e5`） |
| 总耗时 | ~1.5 天单人（含人审、commit、push） |

完整事件记录：memory `project_docs_translation_batch1` + `reference_dingtalk_export_quirks`。

---

## 已知限制

- **`import_archive.py` 当前 hardcode 了 `9. 钉钉文档` 这类 zh 归档目录名**：下次发现新产品归档命名不一致时，需要在脚本里加 `--source-name` 参数（本 skill 暂不做，按需手动改脚本）
- **阶段 2 的 3 个 lint 脚本路径 hardcode `zh/docs/`**：复用时手动改脚本路径，跑完改回（**不要 commit 脚本修改**）
- **小产品（≤30 篇）走 9 阶段可能 overshoot**：阶段 5 可能 0 命中、阶段 8 可能没死链；按通过条件直接跳就行
- **本 skill 不处理"删图后遗症"**（如 EN/JA 删图后语义断裂）：那是 docs/ 早期一次性决策，新子产品默认保留所有图，不会出现该问题
