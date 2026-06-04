# CLAUDE.md — dingtalk-docs

> 本文件给 Claude Code Agent 阅读，定义本仓库的工作约定。每次会话自动加载。

## 项目概述

DingTalk 国际版帮助中心，对外域名 `help.dingtalk.io`，由 [Mintlify](https://mintlify.com) Hobby 版 SaaS 托管。三语文档站（英文 / 中文 / 日文），纯 MDX 内容 + 单文件 `docs.json` 配置，无本地 build pipeline。

**多产品架构**：每个语言下用顶部水平 tabs 切换产品（Overview / AI Table / DingTalk Docs / ...），URL 形如 `/<product>/<slug>`（en）或 `/zh/<product>/<slug>`、`/ja/<product>/<slug>`。

## 常用命令

```bash
# 本地预览（默认 http://localhost:3000）
mint dev

# 死链检查（提交前必跑）
mint broken-links

# 启用本地搜索（一次性，CLI 登录后才有搜索）
mint login

# 触发线上部署：push 到 main → Mintlify GitHub App 自动构建
git push origin main
```

文档专用 skill（12 个，按流水线顺序）：

| # | Skill | 用途 |
|---|---|---|
| 1 | `/docs-dingtalk-onboard <product-slug> [--archive <path>]` | **主入口**：9 阶段钉钉文档子产品导入流水线（编排者，串 13 主脚本 + 7 lint + 5 子 skill） |
| 2 | `/docs-import-archive [--input <path>]` | 阶段 0：钉钉文档归档自动下载（5 脚本编排，含人工扫码 / 抓端点提示），产物供 onboard 阶段 1 消费 |
| 3 | `/docs-add-page <product> <slug> <group>` | 三语镜像建页 + 同步 `docs.json` 三处 navigation；`<product>` 为产品 slug（`overview` / `aitable` / `docs` 等） |
| 4 | `/docs-translate <english-mdx-path>` | 单文件翻译：以英文母版生成 zh / ja，自动注入项目词库作为术语强约束 |
| 5 | `/docs-translate-batch <root>` | 阶段 7：产品目录 zh → en/ja 批量翻译（词库强约束 + 图视频剥离 + 链接前缀修正 + 死链验证 + ja nav 提示）；349 篇基准 ~$25/lang/30min |
| 6 | `/docs-translate-polish <slug> --lang <en\|ja>` | 阶段 7-bis：en/ja 翻译润色（10 项 review checklist 强约束 + 词库注入 + 断点续跑） |
| 7 | `/docs-glossary-sync` | 翻译词库同步：把语言同学维护的官方词库 csv 合并进项目（`import/*.csv` → `official/*.json` → 最终 `zh-en.json` / `zh-ja.json`） |
| 8 | `/docs-audit-mdx` | 阶段 6 / 8d：MDX 语法审计（`++text++` / 破碎粗体 / 废占位 URL）+ 钉钉外链死链探针（og:title SSR 检测）；两阶段 dry-run → `--apply` |
| 9 | `/docs-nav-edit <action> <product>` | 阶段 9：`docs.json` 三语 navigation 安全编辑（`add-product` / `add-group` / `add-page` / `reorder` / `verify`），强制 Edit 禁 Write |
| 10 | `/docs-preview` | 阶段 9 验收：后台启 mint dev + 死链检查 + playwright 三语首页截图 |
| 11 | `/docs-prune-orphan-images` | 删除不再被任何 mdx 引用的本地图片 |
| 12 | `/docs-reorder-by-official-menu` | 按官方左侧菜单重排 `docs.json` 顺序 |

通用 skill（8 个，项目级，与 docs-* 同目录，**无需依赖个人 `~/.claude/commands/`**）：

| # | Skill | 用途 |
|---|---|---|
| 1 | `/commit-flow` | 标准提交流程（lint → 分析 diff → 自动带 aoneId → commit） |
| 2 | `/code-review` | 本地变更或 GitHub PR 代码审查 |
| 3 | `/pr` | 从当前分支创建 GitHub PR（含 summary + test plan 模板） |
| 4 | `/plan` | 实现前先出方案（等用户确认再 code） |
| 5 | `/build-fix` | 增量检测 + 修复 build / type 错误 |
| 6 | `/refactor-clean` | 安全清除死代码 |
| 7 | `/security-scan` | 扫密钥 / 漏洞 / 不安全模式 |
| 8 | `/memory-scan` | 主动扫一遍可入 memory 的事实并询问 |

## 架构设计

- **托管**：Mintlify Hobby SaaS（免费版）。无自托管服务器，无 build 阶段。
- **触发构建**：push 到 GitHub default 分支（`main`）→ Mintlify GitHub App 监听 → 平台侧自动构建。
- **配置入口**：单文件 `docs.json`（[schema](https://mintlify.com/docs.json)），管 navigation / colors / appearance / SEO / 字体 / logo。
- **三语镜像**：英文在仓库根，`zh/` 与 `ja/` 完全镜像同名同结构。`docs.json` 的 `navigation.languages` 数组按语言分块。
- **多产品 tabs**：每个语言块下 `tabs[]` 数组按位置匹配（en[0] = zh[0] = ja[0] = Overview，依此类推）；新增产品要三语同步追加。
- **按语言 navbar / footer**：`navbar` 按当前语言指向对应地区官网（en→.io / zh→.com / ja→.co.jp）；`footer` 三语均列全 3 个地区作为兜底。
- **自定义域名**：`help.dingtalk.io` 通过 DNS CNAME 指向 `cname.mintlify.builders`，TLS 由 Mintlify 自动签发。

## 目录结构

```
.
├── docs.json              站点配置（colors / languages / navigation / SEO）
├── favicon.ico            站点 favicon（品牌资产）
├── index.mdx              Overview tab — 英文首页
├── quickstart.mdx         Overview tab — 英文快速开始
├── guides/                Overview tab — 英文指南目录
│   └── overview.mdx
├── aitable/               AI Table tab — 英文产品文档
│   └── index.mdx
├── docs/                  Docs tab — 英文产品文档（15 个 group：getting-started / quickstart /
│   │                      release-notes / admin-guide / doc-ai / customer-stories / best-practices /
│   │                      advanced / dingtalk-docs / sheets / mind / whiteboard / knowledge-base /
│   │                      knowledge-group / templates）
│   └── ...                每 group 下含 index.mdx + N 篇 mdx；部分含 3 层嵌套 group（doc-ai / sheets / mind 等）
├── zh/                    中文镜像（结构同根，zh/docs/* 实文）
│   ├── index.mdx
│   ├── quickstart.mdx
│   ├── guides/overview.mdx
│   ├── aitable/...
│   └── docs/...           15 个 group 同 en，路径完全镜像
├── ja/                    日文镜像（结构同根，ja/docs/* 为占位 mdx，待翻译）
│   ├── index.mdx
│   ├── quickstart.mdx
│   ├── guides/overview.mdx
│   ├── aitable/...
│   └── docs/...           15 个 group 同 en（2026-06-02 已全量翻译；docs.json 已注册 ja `ドキュメント` tab）
├── scripts/               导入 / 翻译 / 词库 / 一次性工具脚本
│   ├── import_archive.py            历史归档 docx 批量导入
│   ├── translate_chapter_api.py     单篇 mdx 翻译（早期版，按章节）
│   ├── translate_mdx_batch.py       【批量翻译核心】zh/<root>/ → <root>/(en) 或 ja/<root>/(ja)；走 `claude -p --bare` 子进程，词库强约束 + 图视频剥离 + 断点续跑；详见 memory `project_docs_translation_batch1`
│   ├── register_ja_docs_navigation.py  一次性脚本：把 zh `文档` tab 镜像为 ja `ドキュメント` tab 注入 docs.json（含 60+ 条中→日 group 名映射表）
│   ├── glossary_sync.py             词库合并器（official + local-supplements → zh-en.json / zh-ja.json）
│   ├── glossary/                    翻译词库分层
│   │   ├── import/                  语言同学的官方词库 csv 源（.numbers 已 gitignore）
│   │   ├── official/                规范化后的 zh-en / zh-ja / conflicts json
│   │   ├── local-supplements.md     官方未覆盖的 AI Table / DingTalk Docs 专项术语 + 风格指南
│   │   ├── zh-en.json               最终消费产物（official + 本地补充合并）
│   │   ├── zh-ja.json
│   │   └── merge-report.md
│   └── output/
│       ├── import/                  导入产物：slug-map / link-map / nav-fragment-{group}.json / report-{group}.md
│       └── translate_docs/<lang>/   翻译批次产物：report.json / report.md（每篇 elapsed / token / cost / hit_terms）
├── logo/                  本地 logo 兜底目录（当前用远程 alicdn SVG）
├── .claude/commands/      项目级 skill 定义
├── .gitignore
├── README.md              面向贡献者的说明
└── CLAUDE.md              本文件
```

## 技术栈与约定

- **Mintlify Hobby ≥ v6**，CLI 命令 `mint`
- **MDX**：Markdown + React 组件混写，文件扩展名 `.mdx`，必须带 frontmatter（`title` + `description`）
- **JSON 配置**：`docs.json` 必带 `$schema` 字段（编辑器自动校验）
- **字体**：PingFang SC（中日韩友好）
- **主题**：`theme: "mint"`，品牌色 `#0066ff`（与 logo `#06F` 一致），appearance 默认跟随系统
- **LLM 投喂入口**：docs.json 顶层 `contextual.options` 已开 8 个（copy / view / chatgpt / claude / perplexity / mcp / cursor / vscode），每页右上区会出现 contextual 按钮组
- **包管理 / build 工具**：**无**（不依赖 Node 项目结构；mint CLI 自带运行时）

### 可用 MDX 组件（Mintlify 内置）

写文档时优先用以下组件，不要从外部引入：

| 组件 | 用途 | 关键 props |
|---|---|---|
| `<Card>` / `<CardGroup cols={N}>` | 卡片 / 卡片网格 | `title`、`icon`、`href` |
| `<Note>` / `<Tip>` / `<Warning>` / `<Info>` / `<Check>` | 提示框（不同语义色） | — |
| `<Steps>` + `<Step>` | 编号步骤流程 | Step `title` |
| `<Tabs>` + `<Tab>` | 选项卡切换 | Tab `title` |
| `<Accordion>` / `<AccordionGroup>` | 折叠面板 | `title`、`defaultOpen` |
| `<CodeGroup>` | 多语言代码块切换 | 子元素加 ` ```lang title="x" ` |
| `<Frame>` | 截图 / 图片框 | `caption` |
| `<Icon>` | Font Awesome 图标 | `icon`（如 `"rocket"`）|
| `<Update>` | 更新日志条目 | `label`、`description` |

完整组件参考：https://mintlify.com/docs/components

## 编码原则（Karpathy 四原则，文档场景版）

### 1. Think Before Coding — 写之前先看
- 改 `docs.json` 前先看 navigation 现状，确认目标 group 存在
- 新增页前 `ls` 三语目录确认无重名
- 跑 `mint broken-links` 拿到改动前的基线

### 2. Simplicity First — 简单至上
- 段落优先于复杂组件；能用 `<Note>` 就别套 `<Card>` 嵌 `<CardGroup>`
- 不引入新依赖（Mintlify 已内置足够多组件）
- 描述用一句话讲清，不堆砌形容词

### 3. Surgical Changes — 手术级变更
- 只改要求的页；不顺手"美化"其他页
- 改 `docs.json` 用 Edit 工具精确插入，**绝不 Write 覆盖整个 JSON**
- 翻译时只动 zh / ja 文件，不修改英文母版

### 4. Goal-Driven Execution — 目标驱动
- 改完后 `mint broken-links` 必须通过
- 重要改动用 `/docs-preview` 本地视觉确认
- 三语改动要交叉对照（en / zh / ja 路径与 group 数组同序）

## 编码风格（文档写作风格）

### 核心原则
- **KISS**：句子短，结构扁；能链接就不要重复整段说明
- **DRY**：同一概念不要在三处页里重写——抽到独立页，其他页 `<Card href="...">` 引用
- **YAGNI**：不要为"以后可能用得到"建空 group / 空页

### 不可变性
- 编辑 `docs.json` 用 Edit 工具的精确字符串替换
- 不重写整份 JSON / MDX，避免破坏作者风格与已有链接

### 文件组织
- 一个主题 = 一个 mdx 文件
- 单文件 > 800 行时考虑拆分为 group
- 截图存 `images/<slug>/<name>.png`（首次出现时按需创建目录）

### 命名约定
- **slug 路径段**：`kebab-case`，**保持英文**（三语共享同一路径，前缀靠 `/zh/...` `/ja/...`）
- **product slug**：`aitable` / `docs` 等，全英文 kebab-case；与 tab 显示名解耦（tab 名可按语言翻译，slug 永远英文）
- **group 标题**：按各语言自然翻译（`Guides` / `指南` / `ガイド`）
- **tab 标题**：产品名保持英文（`AI Table` / `DingTalk Docs` 品牌名不译）；通用名按语言翻译（`Overview` / `总览` / `概要`）
- **文件名**：与 slug 末段一致
- **frontmatter title**：各语言版本是自然翻译（区别于 slug）

### 链接
- 内部链接用**相对路径**：`/guides/messaging`，不写 `https://help.dingtalk.io/guides/messaging`
- 跨语言不互链（让用户用顶部语言切换器）
- **跨产品不互链**：尊重产品边界，让用户用顶部 tab 切换；产品间共用概念抽到 Overview tab
- 外链加 `target="_blank"`：MDX 默认 `[label](url)` 即可

### 死链
- 提交前必跑 `mint broken-links`，不允许带死链入库

## 安全准则

- **严禁硬编码**：API key / token / 内部域名 / 工号 / 手机号绝不进 mdx 或 docs.json
- **截图脱敏**：手机号、邮箱、token、二维码、UID 一律打码
- **外链审核**：不指向已下线 / 钓鱼站点；引用第三方时优先官方域名
- **`.gitignore` 已配置** `.env` / `.env.local` / `credentials*`，但提交前再 `git diff` 自查一遍
- **不暴露内部信息**：内网域名 / 私有仓库地址 / 内部工具截图不入库

## 代码质量检查清单

提交前每条逐项 check：

- [ ] 三语都有同名同结构的 mdx（en 根 / zh/ / ja/）
- [ ] `docs.json` 三个 language 块 navigation 同步更新（tabs 按位置匹配、groups 同序、pages 路径加对应前缀）
- [ ] 新页落在正确的 product tab 下（slug 路径段第一级与 `<product>` 一致）
- [ ] `mint broken-links` 通过
- [ ] 无硬编码敏感信息
- [ ] 外链可访问且为正式 URL
- [ ] MDX 组件标签闭合、必填属性齐全
- [ ] frontmatter 含 `title` + `description`
- [ ] 单文件 ≤ 800 行

## Git 规范

- **commit 格式**：`<type>: <description>。to #82317048`
- **type**：`feat` | `fix` | `refactor` | `docs` | `chore` | `perf`
- **description**：中文，简洁
- **末尾必带** `to #82317048`（aoneId，用于代码统计；可被 `/commit-flow` skill 自动填充）
- 暂存用精确 add，**不用** `git add .` / `git add -A`
- 不提交 `.env` / `credentials` 等敏感文件
- `main` 是发布分支，push 即触发自动构建
- **commit / push / 创建 PR 前需用户明确授权**（不要"顺手"提交）
- 完整流程见 `/commit-flow` skill

## 相关资源

| 资源 | 地址 |
|---|---|
| Mintlify Dashboard | https://dashboard.mintlify.com |
| Mintlify Docs | https://mintlify.com/docs |
| Mintlify 组件库 | https://mintlify.com/docs/components |
| CNAME 目标 | `cname.mintlify.builders` |
| 仓库 | `git@github.com:fuxun2008/dingtalk-docs.git` |
| 线上站点 | https://help.dingtalk.io |
