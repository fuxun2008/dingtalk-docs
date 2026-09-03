# AGENTS.md

## 项目

DingTalk 国际版帮助中心（help.dingtalk.io），Mintlify Hobby SaaS 托管，纯 MDX + 单文件 `docs.json` 配置，无本地 build pipeline，三语（en / zh / ja）镜像站点。

## Skills（可执行经验库）

`.agents/skills/` 是本仓库的 Qoder 技能库（Qoder 默认自动发现），17 个技能覆盖导入、建页、导航、翻译、质量、发布全流程。索引见 `.agents/skills/README.md`。

- **执行任务前先扫一遍技能索引**：任务命中某个技能的 description 时，**严格按该 `SKILL.md` 的步骤执行**，不要自行发挥——正文里写死了大量历史踩坑（顺序锁、正则禁忌、`docs.json` 覆盖事故）。
- 改 `docs.json` 一律走 `docs-nav-edit` / `docs-add-page`，**只用 `SearchReplace` 精确替换，禁止 `Write` 整份覆盖**。
- 发布走 `docs-release`（推 main 到 github 会触发 Mintlify 线上发布，须先取得用户授权）。
- 原 `.claude/commands/` 保留作为上游出处，**修改请改 `.agents/skills/`**，勿改旧副本。

## 常用命令

```bash
mint dev
mint broken-links
mint login
python3 -c "import json; json.load(open('docs.json'))" && echo OK
```

## 目录速览

- 英文母版在仓库根：`index.mdx`、`docs/`、`aitable/` 等
- `zh/`、`ja/` 完整镜像同名同结构
- `docs.json` 是唯一配置入口，管理 navigation、colors、SEO
- 三语 language 块下 tabs 按数组位置一一匹配
- `scripts/` 放导入、翻译、词库工具
- `scripts/glossary/zh-en.json`、`zh-ja.json` 是翻译术语单一真相源

## 内容规范

- 每篇 `.mdx` 必须有 frontmatter：`title` + `description`
- 内部链接用相对路径，例如 `/guides/xxx`
- 不跨语言互链，不跨产品互链，靠站点顶部切换器
- slug 路径段全英文 kebab-case，三语共享同一路径段
- 注册进 `docs.json` 后不要改 slug
- 单文件超过 800 行时拆分为 group
- 外链加 `target="_blank"`
- 优先复用 Mintlify 内置组件：`Card`、`Note`、`Steps`、`Tabs`、`Accordion`、`CodeGroup`、`Frame`、`Icon`、`Update`
- 不引入外部依赖

## 禁止事项

- 不硬编码 API key、token、内部域名、工号、手机号
- 截图必须脱敏：手机号、邮箱、token、二维码、UID 打码
- `docs.json` 禁止整份覆盖，只能精确编辑目标片段
- `scripts/glossary/zh-en.json`、`zh-ja.json` 对个人贡献者只读，改动走统一词库同步流程
- 不提交 `.env`、`credentials*`、`storage_state.json`、`endpoint.json`、`manifest.json` 等中间产物
- 不改动本次任务范围外的文件、产品、语言

## Git 规范

- 分支：`feat/<slug>`，从 `origin/main` 切出
- 每天开工先 `git pull --rebase origin main`
- Commit：`<type>: <说明>。to #82317048`
- type 可用：`feat`、`fix`、`refactor`、`docs`、`chore`、`perf`
- 暂存用精确 `git add <file>`，不用 `git add .` 或 `git add -A`
- commit、push、创建 PR 前必须获得用户明确授权

## 提交前检查

- `mint broken-links` 通过
- 三语目录结构与文件数对齐
- `docs.json` 三个 language 块同步更新
- tabs 位置匹配、groups 同序、pages 路径前缀正确
- 无硬编码敏感信息
- MDX 组件标签闭合、必填属性齐全，frontmatter 齐全

## 关键工作流

- 新增文档页：先确认三语目录无重名，再建 en / zh / ja 三个同结构文件，并同步 `docs.json`
- 批量翻译：先 dry-run 看成本和范围，再执行；报告里必须确认 failed = 0
- Navigation 编辑：先验证三语 tabs / groups / pages 顺序，再精确编辑，禁止整份写回
- 视觉验收：重要改动用本地预览检查三语首页和目标页面
- 删除 mdx 后：检查并清理不再被引用的本地图片
- 大范围修改后：做隐私/安全扫描，避免内部链接、token、手机号、二维码等进入公开文档

