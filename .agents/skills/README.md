# Qoder 技能索引（dingtalk-docs）

本目录是 dingtalk-docs 的 Qoder 技能库，由原 Claude Code 的 `.claude/commands/` 迁移而来。
Qoder 默认自动发现 `.agents/skills/`，每个子目录一个技能，入口 `SKILL.md`（含 `name` / `description` frontmatter）。

调用方式：斜杠命令 `/docs-release`，或让代理按 description 自动匹配触发。

## 流水线主线

| 技能 | 作用 |
| --- | --- |
| `docs-dingtalk-onboard` | **编排者**：9 阶段把钉钉 zh mdx 导出树做成可发布的三语子产品 |
| `docs-import-archive` | 阶段 0：5 脚本下载一个产品的全部原始 mdx 到本地归档 |
| `docs-import-hub-en` | EN-direct 路线：英文 hub 一键导入，跳过翻译 |

## 建页与导航

| 技能 | 作用 |
| --- | --- |
| `docs-add-page` | 三语镜像建页 + docs.json 三处 navigation 同步 |
| `docs-nav-edit` | docs.json 三语 navigation 原子编辑器（add-product / add-group / add-page / reorder / verify） |
| `docs-reorder-by-official-menu` | 按 alidocs 官方左侧菜单重排 group 内页面顺序 |

## 翻译

| 技能 | 作用 |
| --- | --- |
| `docs-translate` | 单篇翻译（词库强约束） |
| `docs-translate-batch` | 产品目录级批量翻译（zh → en + ja） |
| `docs-translate-polish` | 已译 en / ja 二次润色，只改语言质量不改语义 |
| `docs-glossary-sync` | 官方 csv 词库合并进 `scripts/glossary/*.json` |

## 质量与发布

| 技能 | 作用 |
| --- | --- |
| `docs-audit-mdx` | MDX 质量审计 + 钉钉外链死链探针 |
| `docs-open-platform-cleanup` | 开放平台 API 文档 8 类特异瑕疵批量清洗 |
| `docs-prune-orphan-images` | 删除不再被任何 mdx 引用的孤儿图 |
| `docs-preview` | mint dev + broken-links + 三语首页截图视觉冒烟 |
| `security-scan-docs` | 文档站隐私扫描（corpId / 手机号 / 内网域名 / 二维码） |
| `commit-flow` | 本仓库提交流程（带 `to #<aone-id>`，绝不自动 push） |
| `docs-release` | 合并进 main + 双远端推送，触发 Mintlify 线上发布 |

## 运行依赖

技能正文里的命令依赖以下本地环境，缺失时先补齐再跑：

- **`mint`**（Mintlify CLI）— `docs-preview` / `docs-audit-mdx` 等依赖。由 nvm 管理，
  **非交互 shell 可能取不到**；代理执行时若报 `mint: command not found`，用登录 shell
  （`zsh -lic 'mint broken-links'`）或写全路径。
- **`claude` CLI** — `docs-translate-batch` / `docs-translate-polish` 通过
  `claude -p --bare` 子进程调用 opus 完成翻译。这是阿里内网网关的限制（opus 计划仅在
  Claude Code 内可用），**不能改成直接 SDK 调用**，因此该 CLI 必须保留安装。
- **`python3`** — 全部 `scripts/*.py` 流水线脚本。
- `.claude/import/dingtalk_downloader/` — `docs-import-archive` / `docs-import-hub-en` 的
  下载脚本仍在原路径，未迁移（含 `.gitignore` 白名单 fail-closed 规则，移动会破坏脱敏保护）。

## 迁移说明

- 迁移脚本：`.agents/tools/migrate-claude-commands.py`（幂等，可重跑）
- 平台适配：Claude 的 `Edit` 工具 → Qoder 的 `SearchReplace` 工具（共 37 处）。
  这一步是功能性的：Qoder 无 `Edit` 工具，不改写会导致代理退化成用 `Write` 整份覆盖
  `docs.json` —— 正是 `docs-nav-edit` / `docs-add-page` 反复警告的灾难性操作。
- 另有 2 处 Claude 私有路径改为 Qoder 等价机制（user memory 路径 → `SearchMemory`；
  Claude rules 路径 → 直述 prompt caching 约定）。
- 其余正文与 `.claude/commands/` **逐字节一致**，历史踩坑与硬规则原样保留。
- `.claude/commands/` 下另有 8 个通用命令（`build-fix` / `code-review` / `plan` / `pr` /
  `refactor-clean` / `security-scan` / `memory-scan` / `commit-flow`）与 `~/.claude/commands/`
  同源，Qoder 已通过 `source-command-*` 暴露，未重复迁移；其中 `commit-flow` 因本仓库额外
  加了「双远端 + 禁止自动 push」约束，已作为项目技能单独迁移。
