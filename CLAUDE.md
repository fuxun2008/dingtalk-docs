# CLAUDE.md — dingtalk-docs

> 本文件给 Claude Code Agent 阅读，定义本仓库的工作约定。每次会话自动加载。

## 项目概述

DingTalk 国际版帮助中心，对外域名 `help.dingtalk.io`，由 [Mintlify](https://mintlify.com) Hobby 版 SaaS 托管。三语文档站（英文 / 中文 / 日文），纯 MDX 内容 + 单文件 `docs.json` 配置，无本地 build pipeline。

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

项目级 skill（仅本目录可用）：

| Skill | 用途 |
|---|---|
| `/docs-add-page <slug> <group>` | 三语镜像建页 + 同步 `docs.json` 三处 navigation |
| `/docs-translate <english-mdx-path>` | 以英文母版生成 zh / ja 翻译占位（不机翻） |
| `/docs-preview` | 后台启 mint dev + 死链检查 + playwright 三语首页截图 |

全局 skill：`/commit-flow`（提交）、`/memory-scan`（记忆扫描）、`/pr`（创建 PR）等。

## 架构设计

- **托管**：Mintlify Hobby SaaS（免费版）。无自托管服务器，无 build 阶段。
- **触发构建**：push 到 GitHub default 分支（`main`）→ Mintlify GitHub App 监听 → 平台侧自动构建。
- **配置入口**：单文件 `docs.json`（[schema](https://mintlify.com/docs.json)），管 navigation / colors / appearance / SEO / 字体 / logo。
- **三语镜像**：英文在仓库根，`zh/` 与 `ja/` 完全镜像同名同结构。`docs.json` 的 `navigation.languages` 数组按语言分块。
- **自定义域名**：`help.dingtalk.io` 通过 DNS CNAME 指向 `cname.mintlify.builders`，TLS 由 Mintlify 自动签发。

## 目录结构

```
.
├── docs.json              站点配置（colors / languages / navigation / SEO）
├── index.mdx              英文首页
├── quickstart.mdx         英文快速开始
├── guides/                英文指南目录
│   └── overview.mdx
├── zh/                    中文镜像（结构同根）
│   ├── index.mdx
│   ├── quickstart.mdx
│   └── guides/overview.mdx
├── ja/                    日文镜像（结构同根）
│   ├── index.mdx
│   ├── quickstart.mdx
│   └── guides/overview.mdx
├── logo/
│   ├── light.svg          浅色模式 logo
│   └── dark.svg           深色模式 logo
├── favicon.svg
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
- **主题**：`theme: "maple"`，品牌色 `#007fff`，appearance 默认跟随系统
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
- **group 标题**：按各语言自然翻译（`Guides` / `指南` / `ガイド`）
- **文件名**：与 slug 末段一致
- **frontmatter title**：各语言版本是自然翻译（区别于 slug）

### 链接
- 内部链接用**相对路径**：`/guides/messaging`，不写 `https://help.dingtalk.io/guides/messaging`
- 跨语言不互链（让用户用顶部语言切换器）
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
- [ ] `docs.json` 三个 language 块 navigation 同步更新（groups 同序、pages 路径加对应前缀）
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
