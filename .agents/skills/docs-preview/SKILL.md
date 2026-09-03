---
name: docs-preview
version: 1.0.0
description: "Local visual smoke test: start mint dev, run mint broken-links to catch newly introduced dead links, and screenshot the three language homepages. Use after a batch translation, a bulk cleanup, or a docs.json navigation change."
description_zh: "本地预览 + 死链验证 + 三语首页截图：mint dev 起服务、mint broken-links 查死链、三语首页视觉冒烟。"
user-invocable: true
argument-hint: "[--port 3333] [--pages <path>]"
---
# 本地预览 + 死链验证 + 三语首页截图

> 子 skill：作为 [[docs-dingtalk-onboard]] 阶段 9c 视觉验收时调用；也可独立跑作为日常改动后的"视觉冒烟"

把大批改完后的三件事——`mint dev` 起没起来、`mint broken-links` 是否新增死链、三语首页视觉是否正常——压成一条命令。

## 适用场景

- 批量翻译完（`/docs-translate-batch`）后视觉验收
- 大批清理完（`/docs-audit-mdx --apply` / `/docs-dingtalk-onboard` 阶段 2-8）后冒烟
- 改 `docs.json` navigation 后看左侧菜单是否乱位
- 日常单页 / 三五页改动后的快速验

## 参数

- `--port <N>`（默认 `3000`）：mint dev 端口
- `--no-screenshots`（可选）：只跑 dev 起 + broken-links，不出截图（适合 CI / 远程无显示器）
- `--langs <en,zh,ja>`（默认 `en,zh,ja`）：要截图的语言，逗号分隔
- `--baseline <path>`（可选）：上轮的 `broken-links.txt`，本轮 diff 出"新增"死链；不传则只显示当前死链总数
- `--keep-dev`（可选）：跑完不杀 dev server（便于用户在浏览器继续手动验证）

## 执行流程（6 步）

### 步骤 0 — 前置检查

```bash
which mint                                              # mint CLI 可用
test -f docs.json
lsof -ti:<port> 2>/dev/null | head -1                   # 端口有无被占（非 0 → 报告让用户停掉）
```

端口被占 → 停下报告占用进程，让用户决定 kill 或换端口。

### 步骤 1 — 后台启 `mint dev`

```bash
# 用 Bash run_in_background=true
mint dev --port <port>
```

记下 task_id 供步骤 5 杀进程用。

### 步骤 2 — 等 ready

用 `Monitor` until-loop 探活，每 1s 探一次：

```bash
until curl -fsS http://localhost:<port>/ > /dev/null 2>&1; do sleep 1; done
echo "READY"
```

设 `timeout_ms: 60000`（一般 5-15s 起得来；超 60s 报告失败让用户排查）。

### 步骤 3 — 跑 broken-links + diff

```bash
mint broken-links 2>&1 | tee /tmp/broken-links-$(date +%s).txt
```

如传了 `--baseline`：

```bash
diff <(sort <baseline>) <(sort /tmp/broken-links-<now>.txt) | grep '^>' | head -50
echo "新增死链：$(diff <(sort <baseline>) <(sort /tmp/broken-links-<now>.txt) | grep -c '^>')"
```

否则报告：

```
当前死链总数：N
全文：/tmp/broken-links-<now>.txt
```

### 步骤 4 — playwright 三语首页截图（除非 `--no-screenshots`）

```bash
mkdir -p .screenshots                                   # 已 gitignore
```

对 `--langs` 每个语言：

```
en  → http://localhost:<port>/
zh  → http://localhost:<port>/zh
ja  → http://localhost:<port>/ja
```

用 `mcp__playwright__browser_navigate` + `mcp__playwright__browser_take_screenshot`：

```
.screenshots/preview-en-<YYYY-MM-DD>.png
.screenshots/preview-zh-<YYYY-MM-DD>.png
.screenshots/preview-ja-<YYYY-MM-DD>.png
```

`fullPage: true`（看到底部 footer 是否三语都正常）。

### 步骤 5 — 杀 dev server（除非 `--keep-dev`）

用 `TaskStop` 杀步骤 1 的 background task。

`--keep-dev` 时打印：

```
mint dev 仍在 http://localhost:<port> 运行
手动杀：lsof -ti:<port> | xargs kill
```

### 步骤 6 — 报告

```
✓ 预览验证完成：
  - mint dev：起在 :<port>（耗时 Xs）
  - broken-links：N 条死链 / 新增 M 条（vs baseline）
  - 截图：.screenshots/preview-{en,zh,ja}-<date>.png

下一步：
- 看截图排查视觉问题（左侧 nav 顺序 / footer 三语链接 / hero 图）
- 死链新增 > 0：检查最近改动的 mdx 内部链接
- 提交：/commit-flow（如改动已就绪）
```

**不自动 commit / push**（按 user memory `feedback_commit_authorization.md`）。

## 关键陷阱

### 陷阱 1：`.screenshots/` 已 gitignore

不要担心截图被误提交。**也不要**手工 `git add .screenshots/`——历史已决定本地预览图不入库（避免仓库膨胀）。

### 陷阱 2：mint dev 端口冲突

3000 是 React/Next.js 通用端口，常被其他项目占。**优先用 `--port` 换 3001/3002**，不要随意 kill 其他进程（可能是用户在另一个项目跑 dev）。

### 陷阱 3：broken-links baseline 由用户自己 cache

本 skill 不维护"上次的死链快照"。**用户改前自己跑一次 `mint broken-links > /tmp/baseline.txt`**，改后传 `--baseline /tmp/baseline.txt` 才能 diff。不传就只看绝对数。

### 陷阱 4：playwright headless 时 hero 图可能未加载

默认 headless 模式下 lazy-load 图片可能跳过截图时机。截图前 `mcp__playwright__browser_wait_for` 等首屏关键文本出现，再截。

### 陷阱 5：`--keep-dev` 用户记得自己杀

留 dev 跑很方便手动验，但忘了杀下次再跑 skill 会报端口占。报告里**明确提示杀法**。

## 与其他 skill 的协作

- `/docs-dingtalk-onboard` 阶段 9c — 主要调用方
- `/docs-translate-batch` — 翻译完用本 skill 视觉冒烟
- `/docs-audit-mdx --apply` — 大批清理后跑本 skill 验证渲染不破坏
- `/docs-add-page` / `/docs-nav-edit` — 改完 navigation 用本 skill 看左侧菜单
- `/commit-flow` — 通过后用户授权提交（aoneId `82317048`）
