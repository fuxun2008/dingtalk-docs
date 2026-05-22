---
description: 从本地语料按章节导入 AI Table 中文文档到 zh/aitable/，自动转换 mdx + 拷贝图片 + 重写链接 + 注入 docs.json
---

# Docs Import AI Table Chapter — 按章节导入 AI 表格中文文档

把 `/Users/yanxin/github/dingtalk_ai_table` 下 wolai 导出的某一章节 Markdown 批量转换为 Mintlify MDX，落到 `zh/aitable/<chapter>/` 下，并同步注入 `docs.json`。

底层调用 `.claude/import/import_chapter.py`，由本 skill 提供工作流编排。

## 参数

- `chapter-key`：章节键，必须存在于 `.claude/import/aitable-chapters.json` 中。可选值：
  - `getting-started`（从这里开始）
  - `basic-operations`（AI 表格基础操作）
  - `fields`（使用字段）
  - `forms`（使用表单）
  - `views`（使用视图）
  - `dashboards`（使用仪表盘）
  - `ai-assistant`（使用 AI 表格助理）
  - `automation`（自动化工作流）
  - `more`（更多）
  - `application-mode`（应用模式）
  - `formulas`（公式函数）
  - `permissions`（高级权限）
  - `data-connectors`（数据连接中心）
  - `plugins`（插件中心）
  - `admin-console`（AI 表格管理后台）
  - `scenarios`（场景实践）
  - `pricing-and-rights`（付费权益）
  - `announcements`（公告）

调用示例：
- `/docs-import-aitable-chapter getting-started`
- `/docs-import-aitable-chapter automation`

## 步骤

1. **校验参数**
   - 缺 `chapter-key` → 停下询问
   - 用 jq/python 读 `.claude/import/aitable-chapters.json` 确认 key 存在，否则列出可选值

2. **Dry-run 预览**
   ```bash
   python3 .claude/import/import_chapter.py <chapter-key> --dry-run
   ```
   - 列出该章节会生成的 mdx 路径清单 + 图片数量 + 内部链接重写数量
   - 输出 docs.json 改动位置（替换已有 group / 追加新 group）
   - **不要写盘**

3. **请用户确认**
   读出 dry-run 摘要给用户。明确说"会写入 <N> 个 mdx + 拷贝 <M> 张图 + 改 docs.json，确认后执行"。
   用户 ack 后再继续。

4. **执行转换**
   ```bash
   python3 .claude/import/import_chapter.py <chapter-key>
   ```
   - 已存在 mdx 默认拒绝覆盖；用户要求覆盖时加 `--force`
   - 失败立刻停下报错，保持仓库未污染

5. **检查日志**
   读 `/tmp/aitable-import-<chapter-key>.log`：
   - `link-unresolved` 条目 → 列出来给用户（这些链接已降级为纯文本，需要人工补 slug-map 后重导）
   - `src-missing` 条目 → 报警（语料缺文件）

6. **跑死链检查**
   ```bash
   mint broken-links
   ```
   - 与 `.claude/import/broken-links-allowlist.txt` 做差集
   - 非白名单死链 → 报给用户决定：修复 / 加白名单 / 跳过
   - 内部链接（站内 `/zh/aitable/...`）死链不允许进白名单

7. **本地预览（按需）**
   首次或大改动时建议：
   ```bash
   mint dev
   ```
   抽看 1-2 篇刚导入的页面：
   - 标题/正文/图片渲染正常
   - 内部链接可点
   - 品牌名替换正确（无遗留「钉钉AI表格」/「钉钉文档」）
   - 顶部 tab 切到 AI Table，左侧导航该章节 group 正常展示

8. **报告产物**
   - 新增 mdx 数量
   - 新增图片数量（MB）
   - docs.json 改动摘要
   - 链接日志路径
   - 提示用户可以进入下一章节

## 错误处理

| 场景 | 处理 |
|---|---|
| `chapter-key` 不在 chapters.json | 列出可选值让用户选 |
| 目标 mdx 已存在 | 默认拒绝覆盖；询问用户是否 `--force` 重导 |
| 源 .md 缺失 | 跳过并记录到日志，章节其他文件继续处理 |
| slug-map 缺条目 | 报错并停下（应先补 slug-map.json 再重导） |
| 内部链接 unresolved | 降级为纯文本 + 记录日志，**不阻断**（事后人工补） |
| MDX 编译失败 | `mint dev` 会报具体行号；定位修复后重导 |
| 死链命中非白名单 | 列出来让用户决定 |

## 约定

- 转换规则细节见 `.claude/import/import_chapter.py` 顶部的 docstring 与 [[plan-https-help-dingtalk-io-dark-light-breezy-piglet]] 的 C 节
- slug 映射稳定后**不要随意改**（会破坏内部链接）
- 每章节是一个原子单位：要么整章节落入，要么不落
- 本 skill 只处理**中文**（`zh/aitable/`）；en / ja 由后续 `/docs-translate` 处理，不在本期范围
- 跨章节去重已在 `aitable-chapters.json` 的 `$note` 中定档（如「用AI 表格一表一助理发消息」只在 automation 落一份）

## 配套文件

| 路径 | 用途 |
|---|---|
| `.claude/import/aitable-chapters.json` | 18 章节定义 + docs 列表 |
| `.claude/import/aitable-slug-map.json` | 215 篇中文 → 英文 slug 稳定映射 |
| `.claude/import/import_chapter.py` | Python 转换器（本 skill 底层） |
| `.claude/import/broken-links-allowlist.txt` | 死链白名单（按需追加） |
| `/tmp/aitable-import-<chapter>.log` | 每次导入日志（链接重写 / 缺失 / 错误） |

## 完成标志

- 17 章节全部导入完毕
- `mint broken-links` 通过（差集为 0）
- 浏览器抽查每章节 1-2 页视觉正确
- `docs.json` zh AI Table tab 下 18 个 group（1 已有 index + 17 章节）
- 提交：每章节一个 commit（`feat: 导入 AI 表格<章节名>章节中文文档。to #82317048`）
