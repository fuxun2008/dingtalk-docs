# DingTalk 国际版帮助中心 · 子产品接入培训手册

> 受众：10 个产品负责人，并行接入 help.dingtalk.io
> 目标：1.5 天内复现「下载 → 清洗 → MDX → 翻译 → 提交 → MR」全程
> 配套文件：[product-assignment.md](./product-assignment.md) · [checklist.md](./checklist.md) · [cheatsheet.md](./cheatsheet.md) · [slides-outline.md](./slides-outline.md)
> 单一真相源：仓库根 [`CLAUDE.md`](../../CLAUDE.md) + 11 个 [`.claude/commands/docs-*.md`](../commands/)

---

## 目录

- [模块 A — 角色分工与全局视图](#模块-a--角色分工与全局视图)
- [模块 B — 一次性环境准备](#模块-b--一次性环境准备)
- [模块 C — Git 工作流约定](#模块-c--git-工作流约定)
- [模块 D — 11 个 docs-* skill 速查](#模块-d--11-个-docs--skill-速查)
- [模块 E — 端到端实战（9 阶段）](#模块-e--端到端实战9-阶段)
- [模块 E-bis — 翻译后人工 review / 润色](#模块-e-bis--翻译后人工-review--润色)
- [模块 F — PR / CR / 上线](#模块-f--pr--cr--上线)
- [模块 G — 关键陷阱清单（10 大坑）](#模块-g--关键陷阱清单10-大坑)
- [模块 H — FAQ](#模块-h--faq)
- [模块 I — 交付前自检](#模块-i--交付前自检)
- [附录 A · 产品分配表](./product-assignment.md)
- [附录 B · 速查卡](./cheatsheet.md)
- [附录 C · 已读文献索引](#附录-c--已读文献索引)
- [附录 D · 翻译润色脚本接口设计草稿](#附录-d--翻译润色脚本接口设计草稿)

---

## 模块 A — 角色分工与全局视图

### A.1 你是谁、负责什么

打开 [product-assignment.md](./product-assignment.md) 找到你的名字一行。记下 4 个东西：

| 字段 | 用在哪里 |
|---|---|
| **slug** | 个人分支名 `feat/<slug>` / 三语目录 `<slug>/` `zh/<slug>/` `ja/<slug>/` / docs.json 三处 navigation 注册路径 |
| **中文文档源 URL** | 阶段 0 输入 |
| **篇数估算** | 阶段 7 翻译成本预算（每 100 篇 ~15min ~$15） |
| **上线域名** | merge 后视觉对一遍的目标 |

### A.2 我是谁（砚心）做什么

- **不做**：阶段 0-9 的执行本身（你来做）
- **做**：CR 你的 MR + merge 到 `origin/main` + 同步到 `github/main` 触发 mintlify 上线
- **额外维护**：词库 `scripts/glossary/zh-en.json` / `zh-ja.json`（你**只读不改**）+ 后续会提供翻译润色脚本（见 [E-bis](#模块-e-bis--翻译后人工-review--润色)）

### A.3 流水线全景

```
[阶段 0]                            [阶段 1-9]                       [上线]
钉钉文档站           你（负责人）                          砚心
─────────                ──────────                       ────
.url 包                                                   ┌─────────┐
   │                  ┌─→ 1. 导入归档（zh 建树）          │ origin/ │
   │  扫码 + 抓端点    │  2. 字符卫生                     │  main   │
   ▼                  │  3. 标题正规化                   │   ↓     │
~/Downloads/          │  4. 高亮块 JSX                  │ CR/merge│
dingtalk-docs-        │  5. 编辑器残留清理               │   ↓     │
archive-<slug>/  ────►│  6. MDX 审计                    │ github/ │
                      │  7. 翻译 en + ja  ──── E-bis 人工 review
                      │  8. 链接清扫                     │   ↓     │
                      │  9. docs.json nav 注册           │mintlify │
                      └─→ MR 到 origin/main             │ 自动构建│
                                                        │  ~5min  │
                                                        └────┬────┘
                                                             ▼
                                              https://help.dingtalk.io/<slug>
```

### A.4 三个关键事实（背下来）

1. **三语镜像**：英文母版在仓库根，`zh/` 与 `ja/` 完全镜像同名同结构。slug 路径段三语共享，前缀区分（`/im/foo` vs `/zh/im/foo` vs `/ja/im/foo`）。
2. **docs.json 单文件三处 navigation**：`navigation.languages[]` 数组按语言分块，en / zh / ja 三块 tabs 严格同序（位置匹配，en[0] = zh[0] = ja[0]）。每加一个产品要三语同步追加。**绝不用 Write 覆盖整份 docs.json**。
3. **origin 是主战场**：`origin`（gitlab 内网）是 PR 目标，`github`（公开镜像）由砚心同步。你**不需要 github 权限**。

---

## 模块 B — 一次性环境准备

> 每条命令跑过且验证通过，才能进 [模块 C](#模块-c--git-工作流约定)。

### B.1 macOS 必备工具

| 工具 | 版本下限 | 检查命令 |
|---|---|---|
| Homebrew | 4.x | `brew --version` |
| node | 18+ | `node -v` |
| python3 | 3.11+ | `python3 --version` |
| git | 2.40+ | `git --version` |

缺哪个装哪个，brew 一键：

```bash
brew install node python@3.11 git
```

### B.2 拉仓库 + 配置 SSH

```bash
# 1. 拉仓库（默认 clone 到当前目录）
cd ~/www                                  # 或你习惯的工作根
git clone git@gitlab.alibaba-inc.com:dingding/dingtalk-docs.git
cd dingtalk-docs

# 2. 验证 remote
git remote -v
# 期望见：
# origin  git@gitlab.alibaba-inc.com:dingding/dingtalk-docs.git (fetch/push)
# github  git@github.com:fuxun2008/dingtalk-docs.git (fetch/push)   ← 仅砚心可推
```

如果 clone 报 `Permission denied (publickey)` → 没配置 SSH key：

```bash
# 看本机有没有 ed25519 key
ls ~/.ssh/id_ed25519.pub 2>/dev/null || ssh-keygen -t ed25519 -C "<你的工号邮箱>"
cat ~/.ssh/id_ed25519.pub  # 复制
# 打开 https://gitlab.alibaba-inc.com → 头像 → Settings → SSH Keys → 粘贴 → Add
```

### B.3 装 Mintlify CLI

```bash
npm i -g mint                  # 一次性全局装
mint --version                 # 期望 ≥ v6
mint login                     # 一次性，开本地搜索（浏览器扫码授权）
```

### B.4 装 Claude Code CLI

参考公司内网指引装好 `claude` CLI，**必须用阿里内网网关地址**（不要直连 Anthropic 公网）：

```bash
claude --version               # 有输出
claude -p 'hi'                 # 应回一句话；如报 400 → 检查 ANTHROPIC_BASE_URL
```

### B.5 装 playwright（仅阶段 0 用）

```bash
cd .claude/import/dingtalk_downloader
pip install -r requirements.txt
playwright install chromium

# 验证
python3 -c "from playwright.sync_api import sync_playwright; sync_playwright().start()" 2>&1 | head -3
# 期望无报错
```

### B.6 起一次 mint dev 验环境

```bash
cd <仓库根>
mint dev                       # 默认 :3000
# 浏览器开 http://localhost:3000
# 期望：左上能切 EN / 中 / 日；顶部见 Overview / AI Table / DingTalk Docs 三个 tab
# Ctrl-C 结束
```

### B.7 环境就绪自检（5 yes 才能进模块 C）

- [ ] `git clone` + `git remote -v` 两条命令都成功，见 origin / github 两个 remote
- [ ] `mint --version` ≥ v6
- [ ] `claude -p 'hi'` 不报 400，能回话
- [ ] `python3 -c "import playwright"` 不报错（仅阶段 0 用，可推后到阶段 0 前装）
- [ ] `mint dev` 起到 :3000，浏览器看到三语切换 + 现有产品 tab

---

## 模块 C — Git 工作流约定

### C.1 远端拓扑

```bash
git remote -v
```

| Remote | URL | 你 push | 谁 push |
|---|---|---|---|
| `origin` | gitlab.alibaba-inc.com 内网 | ✓ 推 feat/<slug> | 所有人 |
| `github` | github.com/fuxun2008/dingtalk-docs | ✗ 不要推 | 仅砚心（合并后同步） |

### C.2 默认分支是 `origin/main`（**不是 master**）

```bash
git fetch origin
git log --oneline origin/main | head -3       # 看 main 最新 commit
# master 已废，不要从 master 拉分支
```

### C.3 个人分支命名

| 场景 | 分支名 | 例 |
|---|---|---|
| 接入新产品 | `feat/<slug>` | `feat/calendar` / `feat/im` / `feat/meeting` |
| 上线后修自己产品的 bug | `fix/<slug>-<简短描述>` | `fix/calendar-broken-link` |
| 跨产品改进 | `refactor/<简短描述>`（**慎用**，先问砚心） | `refactor/lint-script-paramize` |

**禁止**：用姓名作分支名（`feat/summer` 这种是早期遗留，新批次不要再加）。slug 与产品一一对应，便于 reviewer 一眼看出影响范围。

### C.4 标准启动序列（5 命令）

```bash
cd <仓库根>
git fetch origin                                    # 1. 拿最新远端引用
git checkout -b feat/<slug> origin/main             # 2. 从 origin/main 出新分支
git push -u origin feat/<slug>                      # 3. 推到 origin，建立 upstream
git pull --rebase origin main                       # 4. 每天开工前再 rebase
git status                                          # 5. 确认干净
```

### C.5 commit 规范

格式：

```
<type>: <说明>。to #82317048
```

- `<type>`：`feat` / `fix` / `refactor` / `docs` / `chore` / `perf` / `ci`
- `<说明>`：中文，简洁，一句话
- `to #82317048`：**必带**，砚心的 aoneId 用于代码统计（用 `/commit-flow` skill 会自动填）

### C.6 阶段 commit 模板（9 个阶段对应 7 个 commit）

抄到剪贴板，每完成一阶段就用对应模板：

```
docs: 阶段 1 — <slug> 导入归档 N 篇。to #82317048
docs: 阶段 2-3 — <slug> 字符卫生 + 标题层级正规化（X 文件）。to #82317048
docs: 阶段 4-5 — <slug> 高亮块 JSX + 钉钉编辑器残留清理（X 文件）。to #82317048
docs: 阶段 6 — <slug> MDX 语法审计修复（X 文件）。to #82317048
docs: 阶段 7 — <slug> N 篇 en/ja 全量翻译。to #82317048
docs: 阶段 8 — <slug> 链接清扫 + 死链清理（X 文件）。to #82317048
docs: 阶段 9 — <slug> 三语 navigation 注册。to #82317048
```

### C.7 推送

```bash
git add <精确路径>          # 不要用 git add . / git add -A
git commit                  # 走 hooks（pre-commit / commit-msg）
git push                    # 已 -u origin 后简写
```

**禁止** `--force` / `--force-with-lease`，要回滚先群里 @ 砚心，他来决策（rebase 出问题 99% 可以 reflog 救回）。

### C.8 每天开工前必跑

```bash
git pull --rebase origin main          # 拿别人合入的改动
git status                             # 看冲突 / 未提交
```

如果 rebase 出现 `docs.json` 冲突 → 见 [陷阱 D](#陷阱-d-多人改-docsjson-rebase-冲突)。

### C.9 提 MR（gitlab Web 操作）

1. 打开 https://gitlab.alibaba-inc.com/dingding/dingtalk-docs
2. 左侧 **Merge Requests** → **New merge request**
3. Source branch：`feat/<slug>`，Target branch：`main`
4. 标题：`[<slug>] 接入 N 篇文档（阶段 1-9）`
5. 描述：粘 [checklist.md](./checklist.md) 末尾的 MR 描述模板
6. Assignee：砚心

### C.10 反例（不要做）

- ❌ `git add .` / `git add -A` —— 容易把 `storage_state.json` / `endpoint.json` / `manifest.json` / `scripts/lint/*_<slug>.py` 等本地工具一并 commit（虽然 .gitignore 兜底，但精确 add 更安全）
- ❌ commit 含敏感信息（cookie / token / 工号 / 手机号）—— 见 [模块 G 陷阱清单](#模块-g--关键陷阱清单10-大坑)
- ❌ 直接改 `main` —— main 是发布分支，自动触发上线
- ❌ commit / push 不问就上 —— 单一原则：**远端动作前问砚心**

---

## 模块 D — 12 个 docs-* skill 速查

按"端到端时序"排序。完整定义在 `.claude/commands/docs-*.md`，本节只给"什么时候用"。

> **使用范式**：你不直接跑命令，而是**复制下方"Prompt"列文本喂给 Claude CLI**，由它去执行 skill。skill 内部会再调底层脚本。

| # | Skill | 阶段 | 一句话 | Prompt（喂给 Claude CLI） | 详见 |
|---|---|---|---|---|---|
| 1 | `/docs-import-archive` | 0 | 从钉钉文档站抓 zh 原始 mdx 归档（含 2 个人工动作） | `/docs-import-archive --input <你的 .url 包> --output ~/Downloads/dingtalk-docs-archive-<slug>/` | [docs-import-archive.md](../commands/docs-import-archive.md) |
| 2 | `/docs-dingtalk-onboard <slug>` | 1-9 编排 | 串完整流水线（**主入口**） | `/docs-dingtalk-onboard <slug> --archive ~/Downloads/dingtalk-docs-archive-<slug>/` | [docs-dingtalk-onboard.md](../commands/docs-dingtalk-onboard.md) |
| 3 | `/docs-audit-mdx` | 6 / 8d | MDX 语法审计 + 外链死链探针 | `/docs-audit-mdx --root <slug> --lang zh --skip-links` | [docs-audit-mdx.md](../commands/docs-audit-mdx.md) |
| 4 | `/docs-glossary-sync` | 7 前置 | 同步官方词库 → zh-en.json / zh-ja.json（**仅砚心跑**） | `/docs-glossary-sync`（10 人不跑） | [docs-glossary-sync.md](../commands/docs-glossary-sync.md) |
| 5 | `/docs-translate-batch <slug>` | 7 | zh → en + ja 整目录翻译 | `/docs-translate-batch <slug> --dry-run --limit 3` 先干跑，再去掉 `--dry-run` | [docs-translate-batch.md](../commands/docs-translate-batch.md) |
| 6 | `/docs-translate-polish <slug>` | 7-bis | en/ja 自动语言润色（**本轮新增**，translate 后跑） | `/docs-translate-polish <slug> --lang en --dry-run --limit 1`，然后 `--lang en` 再 `--lang ja` | [docs-translate-polish.md](../commands/docs-translate-polish.md) |
| 7 | `/docs-translate <path>` | 7 局部 | 单文件翻译（兜底） | `/docs-translate <path-to-en-mdx> --force` | [docs-translate.md](../commands/docs-translate.md) |
| 8 | `/docs-nav-edit <action> <slug>` | 9a | docs.json 三语 navigation 原子操作（**强制 Edit 禁 Write**） | `/docs-nav-edit add-product <slug>` 然后 `/docs-nav-edit verify <slug>` | [docs-nav-edit.md](../commands/docs-nav-edit.md) |
| 9 | `/docs-add-page <product> <slug> <group>` | 9 增量 | 三语建页 + nav 同步 | `/docs-add-page <slug> <page-slug> <group>` | [docs-add-page.md](../commands/docs-add-page.md) |
| 10 | `/docs-preview` | 9c | mint dev + broken-links + 三语首页截图 | `/docs-preview` | [docs-preview.md](../commands/docs-preview.md) |
| 11 | `/docs-prune-orphan-images` | 5/6 后 | 删孤儿本地图 | `/docs-prune-orphan-images zh/<slug>/` | [docs-prune-orphan-images.md](../commands/docs-prune-orphan-images.md) |
| 12 | `/docs-reorder-by-official-menu` | 9 后 | 按官方左侧菜单重排 docs.json 顺序 | `/docs-reorder-by-official-menu <slug>` | [docs-reorder-by-official-menu.md](../commands/docs-reorder-by-official-menu.md) |

**最重要的两个**：

- `/docs-dingtalk-onboard <slug>` —— 阶段 1-9 一次跑通的编排器。**你 90% 时间在跟这个 skill 打交道**。
- `/docs-import-archive` —— 阶段 0 的子流程。**只在你第一次接产品时跑一次**。

其余 skill 由 onboard 编排器自动调用，或者作为补救手段单独跑（如发现死链后 `/docs-audit-mdx`、新增单页用 `/docs-add-page`）。

---

## 模块 E — 端到端实战（9 阶段）

> 主体内容。按 [docs-dingtalk-onboard.md](../commands/docs-dingtalk-onboard.md) 9 阶段拆开。每阶段统一结构：**目标 / 前置 / 命令 / 验证 / commit / 常见坑**。
>
> 推荐用法：第一次跑用 `/docs-dingtalk-onboard <slug> --archive ...` 编排器一击全跑，遇到 dry-run 暂停时对照本文逐项确认。

### 阶段 0 — 钉钉文档归档下载

> 📋 **Prompt 喂给 Claude CLI**（6 字段结构，复制下面这段）：
>
> ```
> [前置]   cd .claude/import/dingtalk_downloader；钉钉文档源 url 包准备好；分支 = feat/<slug>
> [参数]   <slug>=你的产品 slug；<你的-url-包>=钉钉源目录名
> [任务]   调 /docs-import-archive 下到 ~/Downloads/dingtalk-docs-archive-<slug>/
> [预期]   manifest.json total > 0；verify.py 4 项 pass；抽 3 篇 md H1 与 manifest title 一致
> [出错]   扫码失败 / 端点 401 → 重新登录抓 storage_state.json，过程中我会配合
> [验收]   说一句"阶段 0 通过"，再喊我进阶段 1
> ```

**目标**：从 https://alidocs.dingtalk.com/... 把你产品的 N 篇文档全下到本地 `~/Downloads/dingtalk-docs-archive-<slug>/`，每篇一个 .md 文件（保留原 H1、列表、链接、图）。

**人工动作**：本阶段 6 步里有 **2 步人工**（扫码登录 / 抓导出 API），不能跳。

**前置**：

```bash
cd .claude/import/dingtalk_downloader
python3 -c "import playwright; from playwright.sync_api import sync_playwright; sync_playwright().start()" 2>&1 | head -3  # 不报错
test -d "<你的 .url 包路径>"  # 比如 ~/Downloads/2026_06_03_DingTalk_Docs/钉钉日历.url/
```

**命令（6 步）**：

```bash
# 步骤 0：先调用 skill 全编排（推荐）
/docs-import-archive --input <你的 .url 包路径> --output ~/Downloads/dingtalk-docs-archive-<slug>/

# 或者手工逐步跑：
# 步骤 1：扫 .url 生成 manifest（纯自动，< 5s）
python3 build_manifest.py

# 步骤 2：浏览器扫码登录（人工，~30s）—— 弹 chromium 窗口，钉钉扫码
python3 auth_bootstrap.py

# 步骤 3：抓导出 API 端点（人工，~1min）—— 弹 chromium 窗口，工具栏点"导出 → Markdown"
python3 discover_endpoint.py

# 步骤 4：批量下载（纯自动，~10min/300 篇，限速 1.5s/篇）
python3 download.py
# 想监控用：tail -f download.log | grep --line-buffered -E 'ok|failed|error'

# 步骤 5：校验产物（纯自动，< 10s）
python3 verify.py
```

**验证**：

```bash
# manifest 总数 / 实际下载数对得上
python3 -c "import json; m=json.load(open('manifest.json')); print(f'total: {len(m)}')"
find ~/Downloads/dingtalk-docs-archive-<slug>/ -name '*.md' | wc -l   # 应接近 manifest total

# 抽 3 篇看 H1 与文件名匹配
for f in $(find ~/Downloads/dingtalk-docs-archive-<slug>/ -name '*.md' | head -3); do
  echo "=== $f ==="; head -3 "$f"; echo
done
```

**通过条件**：verify.py 4 项全 pass（数量 / 无空 md / 无登录页污染 / H1 一致），或失败 ≤ 5%（少量手补）。

**常见坑**：

- 路径必须带 `-<slug>` 后缀（[新陷阱 A](#新陷阱-a-archive-路径多人覆盖)）
- 跑一段后报"登录页污染" → 登录态过期（cookie 7 天），回步骤 2 重做，**不要**重做步骤 3
- 端点是产品 specific —— 你第一次跑必须重做步骤 3
- `storage_state.json` / `endpoint.json` / `manifest.json` **绝不能 commit**（已 .gitignore 兜底）

**不出 commit**（产物在 `~/Downloads/` 不在仓库，无需 commit）。

---

### 阶段 1 — 导入归档（zh 建树）

> 📋 **Prompt 喂给 Claude CLI**（阶段 1 单跑版；推荐用 `/docs-dingtalk-onboard <slug> --archive ...` 一击全跑阶段 1-9，遇 dry-run 暂停对照本节验证）：
>
> ```
> [前置]   feat/<slug> 分支；阶段 0 已完成；archive 目录在 ~/Downloads/
> [参数]   <slug>=产品 slug；<source-name>=manifest.json 里的源名
> [任务]   scripts/import_archive.py 把归档导入到 zh/<slug>/，先 --dry-run 后 --apply
> [预期]   nav-fragment 路径正确；篇数 ≈ manifest 一致；frontmatter 含 title + description
> [出错]   slug-map 报警 → 别强 apply，截图给我；中文目录名建议先 ascii 化
> [验收]   git commit 后说一句 "阶段 1 通过"，等我 review 再进阶段 2
> ```

**目标**：把阶段 0 产出的 `~/Downloads/dingtalk-docs-archive-<slug>/` 里 N 篇 md 转成带 frontmatter 的 mdx，落到仓库 `zh/<slug>/<group>/<page>.mdx`。

**前置**：

```bash
cd <仓库根>
git status                                    # 干净
ls ~/Downloads/dingtalk-docs-archive-<slug>/   # 阶段 0 产物在
ls zh/<slug>/ 2>/dev/null && echo "目录已存在，跳过本阶段" || echo "需要建树"
```

**命令**：

```bash
# dry-run 看会建哪些文件
python3 scripts/import_archive.py \
  --archive ~/Downloads/dingtalk-docs-archive-<slug>/ \
  --only "<你的产品中文目录名，如 12. 钉钉日历>" \
  --dry-run

# 满意 → apply
python3 scripts/import_archive.py \
  --archive ~/Downloads/dingtalk-docs-archive-<slug>/ \
  --only "<你的产品中文目录名>"
```

**验证**：

```bash
git status -s zh/<slug>/ | head           # 应只见 zh/<slug>/ 新增
find zh/<slug> -name '*.mdx' | wc -l      # 文件数对得上归档
head -5 zh/<slug>/<group>/*.mdx | head -20  # 抽样看 frontmatter 有 title + description
```

**通过条件**：`zh/<slug>/` 存在 + 文件数与归档接近（差 ≤ 5%）。

**commit**：

```bash
git add zh/<slug>/
git commit -m "docs: 阶段 1 — <slug> 导入归档 N 篇。to #82317048"
```

**常见坑**：

- `import_archive.py` 当前 hardcode 了 `9. 钉钉文档` 这类目录名 → 第一次接新产品如果 `--only "<不一样的名字>"` 不灵，**手工改脚本对应行**跑完再改回（不要 commit 脚本改动）

---

### 阶段 2 — 字符卫生

> 📋 **Prompt 喂给 Claude CLI**（onboard 编排器自动跑此阶段；手工补救时复制下面 6 字段）：
>
> ```
> [前置]   阶段 1 已 commit；zh/<slug>/ 目录就位；分支 = feat/<slug>
> [参数]   <slug>=产品 slug；3 个 lint 脚本必须先复制为 *_<slug>.py，不入库
> [任务]   按阶段 2 顺序跑 fix_frontmatter_nbsp / clean_invisible_chars / fix_garbage_descriptions，全部 --apply
> [预期]   NBSP / 零宽 / 垃圾 description 三个 grep 全为空；改了多少文件 commit 信息说清
> [出错]   不要修原始 scripts/lint/*.py 里 hardcode 的 zh/docs/ 路径，永远复制副本
> [验收]   说 "阶段 2 通过"，再进阶段 3 标题正规化
> ```

**目标**：清掉钉钉文档导出常见的 3 类不可见字符：NBSP（`\xc2\xa0`）/ 零宽空格（`\xe2\x80\x8b`）/ 垃圾 description（`description: |` 或 `description: :::`）。

**前置 ⚠️**：本阶段 3 个脚本目前 **hardcode 扫 `zh/docs/`**。你必须**先复制脚本为 `*_<slug>.py`**，跑完不要 commit 脚本（[新陷阱 B](#新陷阱-b-lint-脚本-hardcode)）：

```bash
for s in fix_frontmatter_nbsp clean_invisible_chars fix_garbage_descriptions; do
  cp scripts/lint/${s}.py scripts/lint/${s}_<slug>.py
  sed -i '' "s|zh/docs/|zh/<slug>/|g" scripts/lint/${s}_<slug>.py
done
```

**命令**（dry-run → apply，3 个脚本顺序无关）：

```bash
python3 scripts/lint/fix_frontmatter_nbsp_<slug>.py                  # dry-run
python3 scripts/lint/fix_frontmatter_nbsp_<slug>.py --apply

python3 scripts/lint/clean_invisible_chars_<slug>.py
python3 scripts/lint/clean_invisible_chars_<slug>.py --apply

python3 scripts/lint/fix_garbage_descriptions_<slug>.py
python3 scripts/lint/fix_garbage_descriptions_<slug>.py --apply
```

**验证**：

```bash
grep -rP '\xc2\xa0' zh/<slug>/ --include='*.mdx' | head        # NBSP 应为 0
grep -rP '\xe2\x80\x8b' zh/<slug>/ --include='*.mdx' | head    # 零宽应为 0
grep -rE '^description: "?(:::|\||$)' zh/<slug>/ --include='*.mdx' | head    # 垃圾 description 应为 0
```

**commit**：和阶段 3 合并：`docs: 阶段 2-3 — <slug> 字符卫生 + 标题层级正规化（X 文件）。to #82317048`

---

### 阶段 3 — 标题层级正规化（**顺序锁死**）

> 📋 **Prompt 喂给 Claude CLI**（6 字段结构，复制下面这段）：
>
> ```
> [前置]   阶段 2 已 commit；3 个脚本都已复制为 *_<slug>.py
> [参数]   <slug>=产品 slug；脚本顺序锁死 strip → demote → normalize
> [任务]   按顺序跑 strip_duplicate_h1_<slug>.py → demote_all_h1_<slug>.py → normalize_headings_<slug>.py，每个都先 dry-run 看再 --apply
> [预期]   grep -rEn '^# [^!]' zh/<slug>/ 输出 0 行（正文 H1 全部降级）
> [出错]   顺序绝不能换；先 demote 会把"重复 H1"变成"重复 H2"绕过 strip 检测
> [验收]   说"阶段 3 通过"，进阶段 4 高亮块
> ```

**目标**：Mintlify 把 frontmatter.title 作为页面唯一 H1，正文里再有 H1 会重复显示。本阶段把所有正文 H1 降级 + 修跳级（h2 → h5 拉回 h2 → h3）。

**前置**：阶段 2 已通过。

**⚠️ 顺序锁死**：strip → demote → normalize，**不可换序**（先 demote 会把"重复 H1"变成"重复 H2"绕过 strip 检测）。

**命令**（同样复制 `_<slug>.py` 套路）：

```bash
# 1. 删/降重复 H1（最先）
python3 scripts/lint/strip_duplicate_h1_<slug>.py
python3 scripts/lint/strip_duplicate_h1_<slug>.py --apply

# 2. 全局 H1 降级
python3 scripts/lint/demote_all_h1_<slug>.py
python3 scripts/lint/demote_all_h1_<slug>.py --apply

# 3. 跳级修复
python3 scripts/lint/normalize_headings_<slug>.py
python3 scripts/lint/normalize_headings_<slug>.py --apply
```

**验证**：

```bash
grep -rEn '^# [^!]' zh/<slug>/ --include='*.mdx' | head    # 正文 H1 应为 0（排除 shebang）
```

**commit**：

```bash
git add zh/<slug>/
git commit -m "docs: 阶段 2-3 — <slug> 字符卫生 + 标题层级正规化（X 文件）。to #82317048"
```

---

### 阶段 4 — `:::` 高亮块 / `&lt;` 实体

> 📋 **Prompt 喂给 Claude CLI**（6 字段结构）：
>
> ```
> [前置]   阶段 3 已 commit；convert_admonitions_<slug>.py 副本已就位
> [参数]   <slug>=产品 slug
> [任务]   跑 convert_admonitions_<slug>.py，把 :::tip / :::warning / :::note / :::info 转成 Mintlify <Tip>/<Warning>/<Note>/<Info>，并还原 &lt; 实体
> [预期]   grep -rE '^:::' zh/<slug>/ 与 grep -rE '&lt;' zh/<slug>/ 都为空
> [出错]   遇到不识别的 ::: 关键字（如 :::caution）→ 把命中行贴回给我，再决定映射成哪个组件
> [验收]   说"阶段 4 通过"，进阶段 5 编辑器残留
> ```

**目标**：把钉钉文档导出的 `:::tip` / `:::warning` 等 Docusaurus 风格高亮块转成 Mintlify 的 `<Tip>` / `<Warning>` 组件；把转义实体 `&lt;` 还原。

**命令**：

```bash
python3 scripts/lint/convert_admonitions.py                  # dry-run
python3 scripts/lint/convert_admonitions.py --apply
```

> 注：`convert_admonitions.py` 不一定 hardcode 路径——先 `head -30 scripts/lint/convert_admonitions.py` 看是否要复制。

**映射规则**（用于人工 review 抽样）：

| `:::` 形式 | Mintlify 组件 |
|---|---|
| `:::` 裸 | `<Note>` |
| `:::tip` | `<Tip>` |
| `:::warning` | `<Warning>` |
| `:::caution` | `<Warning>` |
| `:::info` | `<Info>` |
| `:::note` | `<Note>` |
| `:::check` | `<Check>` |

**验证**：

```bash
grep -rE '^:::' zh/<slug>/ --include='*.mdx' | head     # 应为 0
grep -rE '&lt;' zh/<slug>/ --include='*.mdx' | head     # 应为 0
```

---

### 阶段 5 — 钉钉编辑器残留清理

> 📋 **Prompt 喂给 Claude CLI**（6 字段结构）：
>
> ```
> [前置]   阶段 4 已 commit；fix_emoji_tags_<slug>.py 副本就位
> [参数]   <slug>=产品 slug
> [任务]   先跑 fix_emoji_tags_<slug>.py 清伪 emoji；再扫 zh/<slug>/ grep '\[Priority|\[Flag\]|\[Tip [0-9]|▌|▍|▲|◆'，命中的逐文件 Edit 删掉（不要批量 sed，结合上下文判断）
> [预期]   两类 grep 命中数都为 0；告诉我清掉了多少处 / 多少文件
> [出错]   不要 sed -i 批量替换：占位符可能出现在合法标题里；逐文件 Edit 才安全
> [验收]   说"阶段 5 通过"，准备进阶段 6 MDX 审计
> ```

**目标**：钉钉文档编辑器导出会带一堆装饰性"伪标签"（`[Bulb]` / `[Notebook]` / `[Sparkles]` → Unicode emoji）和 widget marker（`[Priority: 1]` / `[Flag]` / `▍` / `▌`）。

**命令（5a：脚本能处理的）**：

```bash
python3 scripts/fix_emoji_tags.py --lang zh
python3 scripts/fix_emoji_tags.py --lang zh --apply
```

**命令（5b：手工 Edit 清残骸）**：

```bash
# 先看命中
grep -rEn '\[Priority[: ]+[0-9]+\]|\[Flag\]|\[Tip [0-9]+\]|\[Progress\]|▍|▌|▲|◆' \
  zh/<slug>/ --include='*.mdx' | head -40
```

逐个用 `Edit` 工具处理。映射参考：

| 命中 | 替换为 |
|---|---|
| `[Priority: 1]` / `[Priority 1]` | `1.`（列表序号） |
| `[Flag]` / `[Progress]` / `[Tip N]` | 直接删除（多余装饰） |
| `▍` `▌` `▲` `◆` | 直接删除（widget marker） |

**验证**：

```bash
grep -rE '\[Priority|\[Flag\]|\[Tip [0-9]|▌|▍|▲|◆' zh/<slug>/ --include='*.mdx' | wc -l   # 应为 0
```

**commit**：和阶段 4 合并：`docs: 阶段 4-5 — <slug> 高亮块 + 编辑器残留清理（X 文件）。to #82317048`

**历史基准**：docs/ 349 篇做完阶段 5 清掉 4019 处 / 128 文件（伪 emoji 555 处 / 45 文件）。你的产品规模如果只 100 篇，命中数大致按比例缩。

---

### 阶段 6 — MDX 语法审计

> 📋 **Prompt 喂给 Claude CLI**（6 字段结构）：
>
> ```
> [前置]   阶段 5 已 commit；分支 = feat/<slug>
> [参数]   <slug>=产品 slug
> [任务]   先跑 /docs-audit-mdx --root <slug> --lang zh --skip-links 出 dry-run 报告；A/B/C/E/F/G 类直接 --apply；D 类（URL-as-label）逐条给我看再决定 label 改成什么
> [预期]   报告里 A/B/C/E/F/G 命中清零；D 类列表 ≤ 30 条供人审
> [出错]   D 类绝不自动改 label：链接文案改坏会破语义；逐条问我或维护者
> [验收]   说"阶段 6 通过"，进阶段 7 翻译
> ```

**目标**：清 MDX 语法 7 类问题（`++text++` / 破碎粗体 `** X**` / `[label](https:xxx)` 缺斜杠 / URL-as-label / 空 `<Note>` / release-notes Note 标签行 / release-notes 4 空格缩进）。

**命令**：

```bash
/docs-audit-mdx --root <slug> --lang zh --skip-links
```

走子 skill。脚本前 3 类 + E/F/G auto-fix，**D 类（URL-as-label）需人审**——告诉脚本你想把 "https://...xxx.html" 那种当 label 用的链接改成什么文字标签。

**验证**：跟着 skill 输出的报告走，A/B/C/E/F/G 必须命中 0，D 类有命中要逐个决策。

**commit**：

```bash
git add zh/<slug>/
git commit -m "docs: 阶段 6 — <slug> MDX 语法审计修复（X 文件）。to #82317048"
```

---

### 阶段 7 — 翻译到 en + ja（**最大头**）

> 📋 **Prompt 喂给 Claude CLI**（6 字段结构）：
>
> ```
> [前置]   阶段 6 已 commit；scripts/glossary/zh-en.json + zh-ja.json 存在且最近 30 天有更新（否则先找砚心跑 /docs-glossary-sync）
> [参数]   <slug>=产品 slug；<lang>=en 或 ja；<limit>=干跑篇数（建议 3）
> [任务]   先 /docs-translate-batch <slug> --dry-run --limit 3 干跑确认词库装配 + 估成本；通过后 /docs-translate-batch <slug> 全量跑 zh→en+ja
> [预期]   scripts/output/translate_docs/{en,ja}/report.md 头部 failed=0；占位检测覆盖 TODO translate / TODO 翻訳 / TODO 翻译 三种
> [出错]   cost 飙升 → ctrl-c 改用 --limit 100 分批；失败篇数 > 0 → 把 report.md 头部贴回给我决定是否重跑该批
> [验收]   两个 report.md failed=0 + 三语前缀 grep 干净；说"阶段 7 通过"，进 7-bis polish
> ```
>
> 跑完接 [模块 E-bis](#模块-e-bis--翻译后润色--抽样-review) 跑 polish。

**目标**：把 `zh/<slug>/` 整目录翻译成英文（`<slug>/`，**写仓库根**）和日文（`ja/<slug>/`）。

**前置**：

```bash
test -f scripts/glossary/zh-en.json    # 词库就位
test -f scripts/glossary/zh-ja.json    # 词库就位
which claude && claude -p 'hi'         # CLI 可用且回话
```

如果词库不在 / 过期 → **找砚心**跑 `/docs-glossary-sync`。你**不要自己改词库**（[新陷阱 C](#新陷阱-c-词库单文件并发改)）。

**命令**：

```bash
# 干跑预检（看会翻多少篇 + 命中术语数 + 成本估算）
/docs-translate-batch <slug> --dry-run --limit 3

# 正式跑
/docs-translate-batch <slug>
# 等价于：python3 scripts/translate_mdx_batch.py --root <slug> --lang en --concurrency 4
#       + python3 scripts/translate_mdx_batch.py --root <slug> --lang ja --concurrency 4
```

skill 自动跑 7 步：词库前置检查 → 干跑预检 → 翻译 → 链接前缀修正 → 残留扫描 → mint broken-links → ja navigation 注册提示。

**成本预算表**（按 docs/ 基准 349 篇 = 55min / $51.63 外推）：

| 你的篇数 | en 用时 | ja 用时 | en + ja 合计成本 |
|---|---|---|---|
| 50 | ~4 min | ~5 min | ~$8 |
| 100 | ~7 min | ~9 min | ~$15 |
| 200 | ~13 min | ~18 min | ~$30 |
| 300 | ~20 min | ~28 min | ~$45 |
| 500 | ~33 min | ~46 min | ~$75 |

**验证**：

```bash
# 报告头
head -10 scripts/output/translate_docs/en/report.md
head -10 scripts/output/translate_docs/ja/report.md
# 期望：failed: 0
```

**commit**（**等阶段 8 链接清扫做完一起 commit**，避免 review 时还有死链）：先不 commit。

**常见坑**：

- **占位检测必须覆盖中/英/日**：跑前 `grep -rlE 'TODO translate|TODO 翻訳|TODO 翻译' <lang>/<slug>/ | head -3` 兜底确认有占位
- **阿里网关不支持 prompt caching**：input tokens 走原价，脚本已按原价模式工作，不要自作主张改 cache_control
- **不能直接调 Anthropic SDK**：阿里内网网关限制 opus 计划仅 Claude Code 内可用，脚本通过 `claude -p --bare` 子进程绕过
- **`--force` 慎用**：会覆盖人工已校对过的译文，只在中文母版大幅更新时用，并先做 git 备份分支

---

### 阶段 8 — 链接清扫（**最容易漏的收尾**）

> 📋 **Prompt 喂给 Claude CLI**（6 字段结构）：
>
> ```
> [前置]   阶段 7 + 7-bis 已通过；三语篇数对齐
> [参数]   <slug>=产品 slug
> [任务]   按 4 步严格顺序跑：(1) en/<slug>/ 链接补 /en/ 前缀 + ja/<slug>/ 沿用 /zh/；(2) alidocs 旧域换 spm + 中文锚 → 站内；(3) /docs-audit-mdx --root <slug> --skip-syntax 死链探针；(4) mint broken-links 兜底
> [预期]   grep 跨语言前缀污染 = 0；alidocs / spm 命中 = 0；mint broken-links 仅剩本产品外历史死链
> [出错]   绝不加 \?$ MULTILINE fixup（27 个 H3 问号事故）；死链信号是 og:title 空（SPA），不是 HTTP 状态码
> [验收]   说"阶段 8 通过"，准备进阶段 9 nav 注册
> ```

**目标**：修 4 类链接问题：跨语言前缀污染 / alidocs 旧域 + spm 跟踪参数 + 中文锚 / 外链死链。

> 阶段 7 的 `/docs-translate-batch` 第 4 步已经自动做了 8a 跨语言前缀，但仍要手工验一遍——脚本只修 `<slug>` 范围内的，全仓兜底要再跑一次。

#### 8a — 跨语言前缀污染（必修）

```bash
# 看 en 错链：[x](/en/<slug>/foo)
grep -rE '\]\(/en/<slug>/' <slug>/ --include='*.mdx' | wc -l
# 看 ja 错链：[x](/zh/<slug>/foo)
grep -rE '\]\(/zh/<slug>/' ja/<slug>/ --include='*.mdx' | wc -l

# 批量 sed（仅 macOS BSD sed 语法，带空字符串备份后缀 ''）
find <slug>/ -name '*.mdx' -exec sed -i '' 's|](/en/<slug>/|](/<slug>/|g' {} \;
find ja/<slug>/ -name '*.mdx' -exec sed -i '' 's|](/zh/<slug>/|](/ja/<slug>/|g' {} \;
```

**历史基准**：docs/ 实测 en 35 处 / ja 142 处。

#### 8b — 全仓跨语言兜底

```bash
python3 scripts/fix_cross_lang_links.py             # dry-run
python3 scripts/fix_cross_lang_links.py --apply
```

#### 8c — alidocs 旧域 + spm + 中文锚（钉钉文档 export 常见 3 件套）

```bash
# 看现状
grep -rE 'alidocs\.dingtalk\.com|\?spm=|#\s*「' zh/<slug>/ <slug>/ ja/<slug>/ --include='*.mdx' | wc -l
```

如果非 0 → 用 **4 步严格顺序 Python 替换**（参考 [陷阱 4](#陷阱-4-alidocs-4-步替换严格顺序)）：

```python
import re
from pathlib import Path

PATTERNS = [
    (r'#\?dontjump=true#',  '?dontjump=true'),    # 1. 修双井号 export bug（最先）
    (r'#\s*「[^」]*」',      ''),                   # 2. 删中文锚
    (r'\s+「[^」]*」',       ''),                   # 2b. 步骤 1 副产物：留下无 # 的「...」
    (r'[?&]spm=[^&)\s]+',   ''),                   # 3. 删跟踪参数
    (r'alidocs\.dingtalk\.com', 'docs.dingtalk.io'), # 4. 域名换（最后）
]
for f in Path('.').rglob('*.mdx'):
    if not any(str(f).startswith(p) for p in ('<slug>/', 'zh/<slug>/', 'ja/<slug>/')):
        continue
    s = f.read_text(encoding='utf-8')
    for pat, repl in PATTERNS:
        s = re.sub(pat, repl, s)
    f.write_text(s, encoding='utf-8')
```

⚠️ **绝不加 `\?$` MULTILINE fixup**（这是已踩过的事故：会把所有 H3 问句标题的尾 `?` 吃掉，27 个 H3 一夜变成断句）。如果 spm 删完留 `?)` 或 `?&`，**只能精确修** `r'\?\)' → ')'` 和 `r'\?&' → '?'`。

#### 8d — 外链死链探针

```bash
/docs-audit-mdx --root <slug> --skip-syntax
```

走子 skill。脚本用 `check_external_links.py` 探针，判定依据是 SSR 注入的 `<meta property="og:title">` 是否为空（[陷阱 5](#陷阱-5-死链信号是-ogtitle-空)）。

#### 8e — 死链总验

```bash
mint broken-links
```

只关心 `<slug>/**` / `zh/<slug>/**` / `ja/<slug>/**` 下的死链。其它路径的死链是历史遗留。

**commit**：

```bash
git add <slug>/ zh/<slug>/ ja/<slug>/
git commit -m "docs: 阶段 7 — <slug> N 篇 en/ja 全量翻译。to #82317048"
git commit -m "docs: 阶段 8 — <slug> 链接清扫 + 死链清理（X 文件）。to #82317048"
# 阶段 7 和 8 通常分两次 commit（翻译产物 vs 清扫产物）
```

---

### 阶段 9 — docs.json 三语 navigation 注册 + 视觉验收

> 📋 **Prompt 喂给 Claude CLI**（6 字段结构）：
>
> ```
> [前置]   阶段 8 已通过；先 git pull --rebase origin main 拿最新 docs.json（避免冲掉别人的 tab）
> [参数]   <slug>=产品 slug；ja 块 group 中→日翻译表已交砚心或参 register_ja_docs_navigation.py 模板
> [任务]   /docs-nav-edit add-product <slug> 三语 nav 原子注册 → /docs-nav-edit verify <slug> 校验 → /docs-preview 三语首页截图抽验
> [预期]   verify 通过：三语 tabs 同序 + groups 同序 + pages 路径前缀正确；三语首页截图都见 <slug> tab
> [出错]   绝对禁止"请帮我 Write 整份 docs.json"；rebase 冲突时保留别人已合的 tab 再 nav-edit；遇到 ja group 翻译拿不准 → 找砚心
> [验收]   说"阶段 9 通过，准备开 MR"，等我 review checklist 后再开 MR
> ```

**目标**：把你的 `<slug>` tab 注册到 `docs.json` 三语 navigation，让 mintlify 知道这个产品存在；起 mint dev 抽 5 篇做视觉冒烟。

#### 9a — docs.json 三语 navigation 同步

**⚠️ 绝不用 Write 整份覆盖**！必须用 `/docs-nav-edit` 子 skill 原子操作（[陷阱 6](#陷阱-6-docsjson-绝不能-write-覆盖)）。

```bash
# 1. 拉最新 docs.json，避免和别人冲突
git pull --rebase origin main

# 2. 用 skill 加 tab（自动处理三语同序）
/docs-nav-edit add-product <slug>

# 3. 验证
/docs-nav-edit verify <slug>
# 期望：三语 tabs 同序 + groups 同序 + pages 路径前缀正确
```

#### 9b — ja navigation 的 group 中→日翻译

ja 块的 group 显示名需要日文（不能用中文）。参考 `scripts/register_ja_docs_navigation.py` 模板（含 60+ 条中→日 group 名映射），但**每个产品的 group 名翻译是 product-specific 的**——

如果你的 group 名都是常见词（"快速上手" / "常见问题"），可以用模板里现成的映射；如果有产品 specific 的 group（如 "宫格视图" / "甘特图"），**先给砚心一份中→日翻译表**，由他生成 `scripts/register_ja_<slug>_navigation.py` 跑。

#### 9c — 视觉验收

```bash
/docs-preview
```

走子 skill。自动起 mint dev + 跑 broken-links + playwright 三语首页截图。

**抽样手测**：浏览器开 http://localhost:3000，顶部 tab 切到你的产品，抽 5 篇看：

- 首页（`<slug>/index.mdx`）
- 1 个 group 入口
- 2 篇深层（含组件如 `<Note>` / `<Steps>` / `<CardGroup>` 的）
- 1 篇含表格 / 代码块的

**commit**：

```bash
git add docs.json
git commit -m "docs: 阶段 9 — <slug> 三语 navigation 注册。to #82317048"
```

**通过条件**：`mint dev` 起得来 + 三语首页可切 + 抽 5 篇渲染正常 + `mint broken-links` 通过。

---

## 模块 E-bis — 翻译后润色 + 抽样 review

> 阶段 7 跑完到提 MR 之间的过渡环节。**先用 `/docs-translate-polish` skill 自动润色，再人工抽样 review 兜底**。polish skill 已上线（本轮新增，见 [docs-translate-polish.md](../commands/docs-translate-polish.md)）。

### 标准流程

> 📋 **Prompt 喂给 Claude CLI**（6 字段结构 · 阶段 7-bis polish）：
>
> ```
> [前置]   阶段 7 翻译已通过；en/<slug>/ + ja/<slug>/ 篇数与 zh/<slug>/ 对齐
> [参数]   <slug>=产品 slug；<lang>=en 或 ja
> [任务]   先 /docs-translate-polish <slug> --lang en --dry-run --limit 1 验装配 + 估成本；通过后全量 polish en + ja 两轮
> [预期]   scripts/output/polish_docs/{en,ja}/report.md 头部 failed=0；按 10 项 checklist 自动收敛术语 / 句长 / 主动语态 / 列表平行 / 时态 / 标点 / 大小写 / 链接 label
> [出错]   不要让 polish 改 url / Mintlify 组件 / frontmatter title-description / 截图路径；这些超出 polish 边界
> [验收]   两个 report.md failed=0 + 抽样英 5 / 日 3 通读后说"7-bis 通过"，进阶段 8 链接清扫
> ```

```bash
# 1) 先 dry-run 1 篇验证 prompt 装配 + 估成本
/docs-translate-polish <slug> --lang en --dry-run --limit 1

# 2) 全量 polish en
/docs-translate-polish <slug> --lang en

# 3) 全量 polish ja
/docs-translate-polish <slug> --lang ja

# 4) 看产物报告
cat scripts/output/polish_docs/en/report.md
cat scripts/output/polish_docs/ja/report.md
```

### 何时跑 review

polish 跑完后，**抽样 review 再进阶段 8**。每个产品至少：英文版抽 5 篇通读、日文版抽 3 篇请日语同学过一眼。这是兜底——polish 已自动按下面 10 项 checklist 约束，但语言敏感问题仍需人眼。

### Review checklist（10 项 · polish 已自动按这个清单约束 prompt）

下表是 polish skill 内嵌的 prompt 强约束。人工 review 时也按这个清单走，看 polish 漏过哪些。

| # | 检查项 | 通过判定 |
|---|---|---|
| 1 | **术语一致性** | 关键术语（产品名 / 功能名）在不同篇里译法一致；与 `scripts/glossary/zh-en.json` 一致 |
| 2 | **句长** | 长句拆短（英文 ≤ 25 词 / 日文 ≤ 60 假名）；避免连续 3 个长句 |
| 3 | **主动语态** | 英文优先主动语态（"You can..." 优于 "It can be..."） |
| 4 | **链接锚文本** | `[label](url)` 的 label 不是 "click here" / "ここをクリック"，而是有信息量的短语 |
| 5 | **列表平行** | 列表项语法平行（都用动词起 / 都用名词起，不混） |
| 6 | **时态** | 英文 description / 操作指引用一般现在时 |
| 7 | **标点** | 英文用 ASCII 标点（`.,;:`），不是中文全角；日文用全角句读（`。、`） |
| 8 | **大小写** | 英文标题用 Title Case 或 Sentence case（产品规范一致），不要随机 |
| 9 | **代码块标题** | ` ```bash title="x" ` 的 title 跟着语言走（中文标题不要塞到英文版） |
| 10 | **截图 alt** | `![alt](url)` 的 alt 不为空且与语言匹配 |

### 命中问题怎么处理

| 命中类型 | 处理方式 |
|---|---|
| 单篇 1-2 处小问题 | 直接 `Edit` 工具改 |
| 同类问题在 10+ 篇里反复 | **写一条 sed / 用 Edit replace_all**，但**先在 3 篇验证再批量** |
| 整篇质量不达标 | `/docs-translate <path> --force` 单文件重译；如反复重译仍差 → 找砚心 |
| 术语错（不在词库） | 给砚心报，加入 `scripts/glossary/local-supplements.md`，下次 sync 后再 review |

### 不做的事

- ❌ 不要为了"看起来更专业"加形容词 / 引入新概念（不忠实于中文原意）
- ❌ 不要改 frontmatter title 与中文母版差异过大（破坏 URL 段对应关系）
- ❌ 不要删英文 / 日文里的链接（即使你觉得这条链接对外不该出现）
- ❌ 不要顺手"美化"其他产品的页（[CLAUDE.md 编码原则 3 手术级变更](../../CLAUDE.md)）

### polish skill 与人工 review 的边界

- **polish 能改的**：术语统一 / 句长 / 主动语态 / 列表平行 / 时态 / 标点 / 大小写 / 链接 label 信息量
- **polish 不动的**：链接 url / Mintlify 组件 / frontmatter title / description / 截图路径
- **人工 review 重点看**：日文敬体一致 / 英文专业领域是否有 polish 误改 / 业务术语是否还需进词库
- **不达标怎么办**：单篇差 → `/docs-translate <path> --force` 重译；术语错 → 报告砚心加进 `local-supplements.md` 后下次 sync

---

## 模块 F — PR / CR / 上线

### F.1 PR 前自检

打开 [checklist.md](./checklist.md) 逐项打勾。**所有项 yes** 才能开 MR。

### F.2 提 MR

1. 浏览器开 https://gitlab.alibaba-inc.com/dingding/dingtalk-docs
2. 左侧 **Merge Requests** → **New merge request**
3. Source branch：`feat/<slug>`，Target branch：`main`
4. 标题：

   ```
   [<slug>] 接入 N 篇文档（阶段 1-9）
   ```

5. 描述（粘下面模板，替换 `<>` 占位）：

   ```markdown
   ## 阶段验收
   - [x] 阶段 1 导入归档 <N> 篇
   - [x] 阶段 2-3 字符卫生 + 标题正规化
   - [x] 阶段 4-5 高亮块 + 编辑器残留
   - [x] 阶段 6 MDX 语法审计
   - [x] 阶段 7 翻译 en + ja（cost ~$<XX>）
   - [x] 阶段 8 链接清扫（broken-links: 0）
   - [x] 阶段 9 docs.json 注册

   ## 关键数字
   - 三语篇数：<slug>/=<N>, zh/<slug>/=<N>, ja/<slug>/=<N>
   - 翻译报告：scripts/output/translate_docs/{en,ja}/report.md
   - 死链：0

   ## 给 reviewer
   - 重点看 docs.json diff（确保没误删其他 tab）
   - 抽 3 篇 ja review 日语自然度
   ```

6. **Assignee**：砚心
7. 提交后**钉钉群里 @ 砚心**说一声（gitlab 通知钉钉群不及时）

### F.3 砚心 CR 关注点（让你被 review 时心里有数）

| 砚心会查的 | 你能预先自查的 |
|---|---|
| 三语篇数对齐 | `for d in <slug> zh/<slug> ja/<slug>; do echo "$d: $(find $d -name '*.mdx' | wc -l)"; done` 三数相等 |
| 三语目录结构对齐 | `diff <(find <slug> -type d | sed 's|^<slug>/||' | sort) <(find zh/<slug> -type d | sed 's|^zh/<slug>/||' | sort)` 无输出 |
| docs.json 三处 nav 同序 + 没误删别的 tab | `/docs-nav-edit verify <slug>` 通过 |
| 翻译 report 没 failed | `grep failed scripts/output/translate_docs/{en,ja}/report.md` 看数 |
| mint broken-links 通过 | 自己跑一遍，存到 PR 描述 |
| 没 commit 敏感 / 临时文件 | `git log --stat origin/main..HEAD | grep -E 'storage_state|endpoint.json|manifest.json|_<slug>\.py'` 应为空 |

### F.4 merge 后上线

砚心流程（你不用管，了解即可）：

1. 在 gitlab 上 `Squash & merge` 你的 MR 到 `origin/main`
2. 本地 `git fetch origin && git checkout main && git pull --rebase origin main`
3. `git push github main` 同步到 github
4. github 推送触发 mintlify GitHub App 自动构建（~3-5 min）
5. 通知你"已上线"

**你侧的事**：上线通知到了 → 浏览器开 `https://help.dingtalk.io/<slug>` 视觉对一遍（如果是新产品，先在浏览器顶部 tab 切到你的产品）。

### F.5 上线后发现问题

**不要直接改 main**。开新分支走同样流程：

```bash
git checkout -b fix/<slug>-<简短描述> origin/main
# 改完
git push -u origin fix/<slug>-<简短描述>
# 提 MR，标题 [<slug>] fix: <简短描述>
```

---

## 模块 G — 关键陷阱清单（10 大坑）

### 陷阱 1 — 阶段 3 顺序锁死

`strip_duplicate_h1` → `demote_all_h1` → `normalize_headings`。先 demote 会把"重复 H1"变成"重复 H2"，绕过 strip 的去重检测（strip 只识别 H1）。

> 来源：[`docs-dingtalk-onboard.md` 陷阱 1](../commands/docs-dingtalk-onboard.md)

### 陷阱 2 — 阶段 7 占位检测必须覆盖中/英/日

`translate_mdx_batch.py` 的 `is_placeholder()` 必须识别 `TODO translate` / `TODO 翻訳` / `TODO 翻译` / `Translate from` / `から翻訳` / `翻译自`。脚本已修复，但跑前还是先 `grep -rlE 'TODO translate|TODO 翻訳|TODO 翻译' <lang>/<slug>/ | head -3` 兜底。

### 陷阱 3 — 阶段 8 跨语言前缀污染必修

LLM 系统性产出错误前缀（en 加 `/en/`、ja 沿用 `/zh/`）。docs/ 基准：en 35 处 / ja 142 处。**步骤 8a 是必跑收尾**，不修 = 大量内部死链。

### 陷阱 4 — alidocs 4 步替换严格顺序

```
1. 双井号 export bug fix
2. 删中文锚 (#「...」)
3. 删 spm 跟踪参数
4. 域名换 alidocs.dingtalk.com → docs.dingtalk.io
```

**绝不加 `\?$` MULTILINE fixup**——`feature-limits.mdx` 27 个 H3 问句标题的尾 `?` 全被吃掉，rollback 后才发现。如果 spm 删完留 `?)` 或 `?&`，只能精确修 `r'\?\)' → ')'` 和 `r'\?&' → '?'`。

### 陷阱 5 — 死链信号是 og:title 空

docs.dingtalk.io 是 SPA，body 是 JS 渲染壳，HTTP 探针只能拿到静态外壳。**真信号是 SSR 注入的 `<meta property="og:title" content="">` 是否空**：活公开文档有真实标题，死/受限/exception 页面均空。已封装在 `check_external_links.py`。

### 陷阱 6 — docs.json 绝不能 Write 覆盖

`docs.json` 必须用 `Edit` 工具精确插入（实际操作走 `/docs-nav-edit`）。一次性 Write 覆盖会破坏作者风格 + 误删其他 4-12 个产品 tab。三语块严格同序：product slug 全英文不译，tab 显示名按语言翻译（中文 `文档` / 日文 `ドキュメント`），group 标题各语言自然翻译。

### 新陷阱 A — archive 路径多人覆盖

`docs-import-archive` 默认输出 `~/Downloads/dingtalk-docs-archive/`，10 人并跑会**互相覆盖**。强制：

```bash
/docs-import-archive --input ... --output ~/Downloads/dingtalk-docs-archive-<slug>/
```

后续阶段 1 也用同样后缀的路径作为 `--archive` 参数。

### 新陷阱 B — lint 脚本 hardcode

`scripts/lint/fix_frontmatter_nbsp.py` / `clean_invisible_chars.py` / `fix_garbage_descriptions.py` / `strip_duplicate_h1.py` / `demote_all_h1.py` / `normalize_headings.py` 6 个脚本目前 hardcode `zh/docs/`。

**安全做法**（避免 10 人并行修同一脚本起 git 冲突）：

```bash
for s in fix_frontmatter_nbsp clean_invisible_chars fix_garbage_descriptions strip_duplicate_h1 demote_all_h1 normalize_headings; do
  cp scripts/lint/${s}.py scripts/lint/${s}_<slug>.py
  sed -i '' "s|zh/docs/|zh/<slug>/|g" scripts/lint/${s}_<slug>.py
done
```

跑完产物（mdx 改动）正常 commit，**但 `scripts/lint/*_<slug>.py` 不 commit**（属于本地工具）。可以在最终 commit 时显式排除：

```bash
git add zh/<slug>/ <slug>/ ja/<slug>/        # 精确 add 内容产物
# 不 git add scripts/lint/*_<slug>.py
```

> 长期解决方案：脚本参数化为 `--root zh/<slug>/`（属于工具改进，砚心后续会做，但本批次不强求）。

### 新陷阱 C — 词库单文件并发改

`scripts/glossary/zh-en.json` 与 `zh-ja.json` 是单文件，多人并发追加词条必撞。约定：

- **你只读不改**：阶段 7 前确认词库存在即可，不要 Edit
- 发现术语漏 / 错 → 报给砚心，由他追加到 `scripts/glossary/local-supplements.md` 然后 `/docs-glossary-sync` 重生 zh-en/zh-ja.json
- 词库刷新后**你重跑阶段 7** 让译文用上新词

### 新陷阱 D — 多人改 docs.json rebase 冲突

`docs.json` 2600 行单文件，10 人都要追加自己 tab → rebase 必撞。约定：

```bash
# 阶段 9 之前必跑
git pull --rebase origin main

# 如果 docs.json 冲突
git status        # 看到 both modified: docs.json
# 打开 docs.json 找 <<<<<<< 标记
# 解决原则：保留别人已合入的 tab，把你的 tab 接在他后面（不要 --theirs / --ours 全选）
# 用 /docs-nav-edit verify <slug> 验证修完
git add docs.json
git rebase --continue
```

不会改 conflict 标记 → **不要硬来**，群里 @ 持有冲突 tab 的负责人对齐，必要时让砚心帮你 rebase。

---

## 模块 H — FAQ

### Q1：mint dev 端口冲突

```bash
lsof -ti:3000 | head -1            # 看占用进程
# 优先换端口（不要随意 kill 别人的进程）
mint dev --port 3001
```

### Q2：登录态过期 / chromium 报"登录页污染"

```bash
cd .claude/import/dingtalk_downloader
rm storage_state.json
python3 auth_bootstrap.py          # 回阶段 0 步骤 2 重做扫码
# **不要**重做步骤 3（discover_endpoint），端点没变
python3 download.py                # 续传未完成的
```

### Q3：翻译 cost 超预算

```bash
# 分批跑：只翻指定 group / 前 N 篇
/docs-translate-batch <slug> --only <子目录>
/docs-translate-batch <slug> --limit 50
```

### Q4：broken-links 报 alidocs.dingtalk.com 域名死链

回阶段 8c，重跑 4 步替换（注意严格顺序 + 不加 `\?$` fixup）。

### Q5：claude CLI 报 400

```bash
echo $ANTHROPIC_BASE_URL           # 应为公司网关地址，不是 api.anthropic.com
# 看你的 claude 配置文件
cat ~/.config/claude/settings.json 2>/dev/null | head
# 仍不行 → 找砚心
```

### Q6：上线后看不到自己的 slug 出现

排查顺序：

1. **docs.json 注册了没**：`/docs-nav-edit verify <slug>` 通过？
2. **MR 合了没**：gitlab 上 MR 状态是 Merged 不是 Open
3. **github 同步了没**：砚心的事，群里问
4. **mintlify 构建完了没**：https://dashboard.mintlify.com 看最新构建状态

### Q7：rebase 时 docs.json 冲突怎么办

见 [新陷阱 D](#新陷阱-d-多人改-docsjson-rebase-冲突)。

### Q8：我手贱 commit 了 `storage_state.json` 怎么办

```bash
# 还没 push
git rm --cached .claude/import/dingtalk_downloader/storage_state.json
git commit --amend --no-edit

# 已 push（更严重，需要重写历史）→ 立刻告诉砚心，cookie 视为泄漏，重新扫码生成新 cookie
```

### Q9：翻译时报"glossary file not found"

```bash
ls scripts/glossary/zh-en.json scripts/glossary/zh-ja.json
# 不存在 → 找砚心跑 /docs-glossary-sync
# 存在但翻译还是报错 → 看具体报错，可能是格式问题
```

### Q10：我跑完 9 阶段 PR 提了，但 reviewer 让我重来

正常。第一次跑 reviewer 关注点细，按反馈改完再 push 即可（同一分支 push 自动更新 MR）。后续跑熟了 review 速度会快。

---

## 模块 I — 交付前自检

详见 [checklist.md](./checklist.md)。一句话：**所有项 yes 才能开 MR**。

---

## 附录 C — 已读文献索引

本手册的事实点全部来自下列文献，发生冲突以下列文件为准：

| 文件 | 作用 |
|---|---|
| [`/CLAUDE.md`](../../CLAUDE.md) | 项目规约（命名 / 工作流 / 安全） |
| [`.claude/commands/docs-dingtalk-onboard.md`](../commands/docs-dingtalk-onboard.md) | 9 阶段编排器主定义 |
| [`.claude/commands/docs-import-archive.md`](../commands/docs-import-archive.md) | 阶段 0 归档下载 |
| [`.claude/commands/docs-translate-batch.md`](../commands/docs-translate-batch.md) | 阶段 7 翻译批次 |
| [`.claude/commands/docs-audit-mdx.md`](../commands/docs-audit-mdx.md) | 阶段 6 / 8d 审计 |
| [`.claude/commands/docs-glossary-sync.md`](../commands/docs-glossary-sync.md) | 词库同步（砚心） |
| [`.claude/commands/docs-translate.md`](../commands/docs-translate.md) | 单文件翻译 |
| [`.claude/commands/docs-nav-edit.md`](../commands/docs-nav-edit.md) | docs.json 安全编辑 |
| [`.claude/commands/docs-add-page.md`](../commands/docs-add-page.md) | 单页三语建页 |
| [`.claude/commands/docs-preview.md`](../commands/docs-preview.md) | 本地预览验证 |
| [`.claude/commands/docs-prune-orphan-images.md`](../commands/docs-prune-orphan-images.md) | 孤儿图清理 |
| [`.claude/commands/docs-reorder-by-official-menu.md`](../commands/docs-reorder-by-official-menu.md) | 按官方菜单重排 |
| [`.claude/import/dingtalk_downloader/README.md`](../import/dingtalk_downloader/README.md) | 阶段 0 下载器细节 |

---

## 附录 D — 翻译润色脚本（已上线 · 本轮新增）

> ✅ 已上线：`scripts/translate_polish_batch.py` 与 `.claude/commands/docs-translate-polish.md`。日常使用见 [模块 E-bis](#模块-e-bis--翻译后润色--抽样-review)；本附录是底层接口参考。

### 命令形式

```bash
/docs-translate-polish <slug> --lang en|ja [--only path] [--dry-run] [--concurrency 4]
```

### I/O

| | |
|---|---|
| **输入** | `<slug>/` 或 `ja/<slug>/`（已 translate-batch 出的草稿） |
| **输出** | 同路径原地覆盖；每篇 polish 后写报告 `scripts/output/polish_docs/<lang>/report.{json,md}` |

### 内部机制

- 与 `translate_mdx_batch.py` 同款架构：`claude -p --bare` 子进程，绕过阿里网关 SDK 限制
- Prompt 强约束：
  - **保留链接结构**（`[label](url)` 中 url 不动）
  - **保留 Mintlify 组件**（`<Note>` / `<Steps>` 等不动）
  - **不改 frontmatter**（title / description 是 docs.json 主键不可破）
  - **短句优先**（英文 ≤ 25 词 / 日文 ≤ 60 假名拆句）
  - **主动语态优先**（英文）
  - **术语锚定**（与 `scripts/glossary/zh-en.json` / `zh-ja.json` 一致）

### 成本预估

按 docs/ 349 篇基准外推：~$0.05/篇（约为 translate-batch 的 70%）—— input tokens 更少（不用注入完整词库 prompt，只用术语片段），output tokens 与 translate 相当。

| 你的篇数 | en polish | ja polish | 合计 |
|---|---|---|---|
| 100 | ~$5 | ~$5 | $10 |
| 300 | ~$15 | ~$15 | $30 |
| 500 | ~$25 | ~$25 | $50 |

### 在流水线里的位置

```
阶段 7 翻译 → 阶段 7-bis /docs-translate-polish → 抽样人工 review → 阶段 8 链接清扫
```

polish 是 translate 之后、链接清扫之前的强制环节。人工 review 退为兜底（语言敏感问题）。

---

**END · 培训手册**

> 反馈通道：钉钉群 @砚心 / 在仓库提 issue（gitlab）。
> 本手册随仓库版本走，每批新产品上线后会更新一次。
