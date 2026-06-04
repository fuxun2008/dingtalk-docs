# 培训 PPT 大纲（30 页 · v3 实装版）

> 本文件与 `/tmp/gen-dingtalk-pptx.js` 同步。每页讲解 1.5–3 分钟，总时长 ~80 分钟（不含 Q&A 与 demo 互动）。
>
> v3 设计约定：
>
> - 配色：Midnight Executive（PRIMARY `#1E2761` 60-70% 主导）+ Coral accent `#FF6B35`
> - 字体：英文 / 数字 = Cambria；中文 = PingFang SC；代码 = Menlo
> - **0 emoji**：icon 全部 react-icons heroicons + colored circle 包裹
> - **9 阶段 demo 单页布局**：命令 + 验证 + 一个坑 + **6 字段 Prompt 块**（前置 / 参数 / 任务 / 预期 / 出错 / 验收）
> - "复制下面这段，喂给 Claude CLI" 为 6 字段 prompt 块统一标题

## 用法

```bash
# 生成命令
NODE_PATH=$(npm root -g) node /tmp/gen-dingtalk-pptx.js
# → ~/Downloads/dingtalk-onboard-training.pptx

# PPTX → PDF（Keynote AppleScript，本机无 LibreOffice）
osascript /tmp/pptx-to-pdf.applescript ~/Downloads/dingtalk-onboard-training.pptx /tmp/dingtalk-onboard-training.pdf

# PDF → JPG（视觉 QA）
pdftoppm -jpeg -r 110 /tmp/dingtalk-onboard-training.pdf /tmp/slides/slide
```

---

## 封面 · 1 页

### 1. 封面（Cambria 大数字版式 · INK 深底）

- 标题：DingTalk 国际版帮助中心 · 子产品接入培训
- 副标题：1.5 天复现 onboard 流水线
- 大数字 Cambria：`10` 个子产品 · `1.5d` × 人 · `9` 阶段
- 演讲人：砚心；受众：10 个子产品负责人

## Part 1 · 全局视图（3 页）

### 2. 我们要做什么（数据 statCallout 版）

- 三个大数字：`210×3` AI Table / `349×3` DingTalk Docs / `12` 三语 tab
- 时间窗口：1.5 天 / 人 churn 完一个产品

### 3. 流水线全景 — G2 三泳道时序

- 横向：阶段 0–9 时间轴（每段 iconCircle 标注）
- 纵向三泳道：你 / Claude CLI / 砚心
- 责任主体着色（你 = PRIMARY；CLI = PRIMARY_LT；砚心 = CORAL）

### 4. Prompt 工作模式架构 — G1

- 三层数据流：你 → 复制 6 字段 Prompt → Claude CLI → 调 docs-* skill → 仓库变更
- 强调"你只动 prompt，命令由 CLI 跑；你不背 CLI 的报错，只复制粘贴 + 验收"

## Part 2 · 环境准备（4 页）

### 5. 必备工具表

- mac / brew / node / python3.11+ / git / mint / claude / playwright
- 8 张 iconCircle 卡片，各列版本下限

### 6. 仓库 & SSH 配置

- git clone gitlab + ssh key 上传截图占位
- 邮箱必须 `*.fx@alibaba-inc.com` 域

### 7. Claude CLI 装机 + settings.json

- `npm i -g @anthropic-ai/claude-cli` / `claude -p 'hi'` 三步验
- API key 占位 `XXXXXXXX` + 链接 `https://aistudio.alibaba-inc.com/#/aistudio/manage/accountManage`
- ⚠️ 阿里 MO 网关不支持 prompt caching；脚本里禁用 cache_control

### 8. 三语镜像目录树（G3）

- 真 SVG-like tree：`<slug>/` `zh/<slug>/` `ja/<slug>/` 三镜像
- docs.json 三处 navigation 入口对应关系
- mint dev 验证：三语切换 + 12 个产品 tab 状态

## Part 3 · Git 工作流（4 页）

### 9. 远端拓扑

- `git remote -v` 输出图：origin（gitlab） / github
- 强调：你只动 origin；github 由砚心同步

### 10. 分支命名 & 启动序列

- `feat/<slug>` 命名（贴产品分配对照表片段）
- 5 命令启动序列（fetch / checkout -b / push -u）

### 11. commit 规范

- `<type>: <说明>。to #82317048`
- 9 个阶段 commit 模板
- 反例：不要 `git add .` / 不要 commit `storage_state.json` / `endpoint.json` / `manifest.json`

### 12. MR 提交流程

- gitlab Web 步骤图：feat 分支 → New MR → target main → assignee 砚心
- 标题 + 描述模板

## Part 4 · Skill 速查（2 页）

### 13. 12 skill 时序图

- 横轴时间，纵轴 skill 名，箭头表示串联
- 主入口 `/docs-dingtalk-onboard` 加 CORAL 描边发光

### 14. 12 skill 一句话表

- 12 行表格（含 iconCircle 列）
- 第 12 行 = `/docs-translate-polish` 本轮新增

## Part 5 · 实战 demo（10 页 · 每阶段 1 页）

> 每页布局：阶段大数字 + 标题 + 命令块 + 验证 / 一个坑 双栏 + **6 字段 Prompt 块**

### 15. 阶段 0 — 归档下载

- 命令：5 步（manifest → 扫码 → 抓端点 → 下载 → 校验）
- 一个坑：archive 路径加 `-<slug>` 后缀避免多人覆盖
- 6 字段 Prompt：含 [前置] cd `.claude/import/dingtalk_downloader` + [出错] 扫码失败回退

### 16. 阶段 1 — 导入

- 命令：`python3 scripts/import_archive.py --archive ... --only "<source-name>" --dry-run`
- 一个坑：`--apply` 之前必先 `--dry-run` 看 nav-fragment 路径

### 17. 阶段 2 — 字符卫生

- 命令：3 个 lint 脚本顺序跑
- 一个坑：脚本 hardcode `zh/docs/` → 复制为 `*_<slug>.py` 跑，**不入库**

### 18. 阶段 3 — 标题正规化

- 命令：strip → demote → normalize **顺序锁死**
- 一个坑：先 demote 会绕过 strip 的去重

### 19. 阶段 4-5 — 高亮块 + 编辑器残留

- 命令：`convert_admonitions.py` + `fix_emoji_tags.py`
- 一个坑：手工 Edit 清 `[Priority:N]` `▍` `▌` 残留

### 20. 阶段 6 — MDX 审计

- 命令：`/docs-audit-mdx --root <slug> --lang zh --skip-links`
- 一个坑：D 类（URL-as-label）需人审，不要自作主张

### 21. 阶段 7 — 翻译 · A（流程）

- 命令：`/docs-translate-batch <slug> --dry-run --limit 3` → 全量
- 一个坑：占位检测必须覆盖中/英/日（grep `TODO translate|TODO 翻訳|TODO 翻译`）

### 22. 阶段 7 — 翻译 · B（成本 + 4 大坑）

- 成本预算表：100 / 200 / 300 / 500 篇 × en/ja
- 4 大坑：占位检测覆盖三语 / 前缀必修 / 不能 cache（阿里 MO 网关）/ 不能直调 SDK
- 提示：跑完接 `/docs-translate-polish` 自动润色（本轮新增）

### 23. 阶段 8 — 链接清扫

- 命令：4 步严格顺序（跨语言前缀 → alidocs → 死链探针 → broken-links）
- 一个坑（CORAL 大字）：**绝不加 `\?$` MULTILINE fixup**（27 个 H3 问号事故）

### 24. 阶段 9 — docs.json 三语 nav 注册

- 命令：`/docs-nav-edit add-product <slug>` + `verify` + `/docs-preview`
- 一个坑：禁 Write 整份；禁手动 Edit 整份；只用 nav-edit

## Part 6 · 关键陷阱（3 页）

### 25. 已踩 6 大坑

- 6 条 bullet（来自 onboard skill），每条 iconCircle CORAL motif

### 26. 多人并跑新增 4 坑

- archive 路径冲突 / lint 脚本 hardcode / 词库单文件 / docs.json rebase

### 27. 出错排序优先级（决策树）

- mint broken-links 失败 → 自查
- 翻译 cost 超 → 自查
- docs.json 注册不对 → 找砚心
- 上线后页面异常 → 找砚心
- 含"卡壳手册" mini 版（8 类 + 标准追问）

## Part 7 · CR / 上线（2 页）

### 28. PR checklist + 砚心关注点

- 三语篇数对齐 / docs.json verify / 翻译 report 无 failed / broken-links 0
- 砚心 review 重点：docs.json diff（确保没误删别人的 tab）

### 29. 上线后回环

- merge → 砚心同步 github → mintlify 自动构建 ~5 分钟
- 上线后视觉对一遍：`https://help.dingtalk.io/<slug>`
- 出问题 → `fix/<slug>-<issue>` 新分支走同样流程，**不直接改 main**

## 结尾 · Q&A + 资料索引（1 页）

### 30. Q&A + 资料索引

- 主手册：`.claude/training/dingtalk-onboard-guide.md`
- 速查卡：`.claude/training/cheatsheet.md`（A4 打印贴墙）
- 验收清单：`.claude/training/checklist.md`
- 产品分配：`.claude/training/product-assignment.md`
- 工程资料：`CLAUDE.md` 项目规约 / `.claude/commands/docs-*.md` 12 个 skill 完整定义
- 沟通：钉钉群 `<群名>`，遇阻先群里 @砚心，附 prompt 原文 + CLI 完整输出

---

## v3 与 v2 的差异（合并备查）

| 维度 | v2 | v3（本版本） |
|---|---|---|
| 配色 | BRAND 蓝 + 紫 + 绿 + 橙混搭 | Midnight Executive 主色 + Coral 单 accent |
| Icon | react-icons + 8 处文字 emoji 混用 | 全 react-icons heroicons + colored circle，0 emoji |
| Stage demo 布局 | 单页：命令 + 验证 + 短 prompt（2 行） | 单页：命令 + 验证 + 一个坑 + **6 字段 Prompt 块** |
| Prompt 字段 | 自由 1-2 行 | 强制 6 字段：前置 / 参数 / 任务 / 预期 / 出错 / 验收 |
| 页数 | 30 | 30（v3 plan 原拟 43，落地保 30 lite） |
| 主色覆盖 | < 30% | ≥ 60% |
