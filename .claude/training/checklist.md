# 交付前自检清单（9 阶段 × 通过条件）

> 开 MR 之前，对照本表逐项打勾。任一未勾 → 不要开 MR；任一拿不准 → 找砚心。源：`.claude/commands/docs-dingtalk-onboard.md` 每阶段「通过条件」段。

把 `<slug>` 替换为你的产品 slug（见 `product-assignment.md`）。

---

## 环境就绪（一次性）

- [ ] `which mint` 有输出 + `mint --version` ≥ v6
- [ ] `which claude` 有输出 + `claude -p 'hi'` 不报 400
- [ ] `git remote -v` 见 `origin` 指向 gitlab、`github` 指向 GitHub（github 仅砚心同步）
- [ ] `git branch --show-current` 是 `feat/<slug>`（不是 `main` / `master`）
- [ ] `mint dev` 能起到 :3000 + 三语切换可见

## Git 卫生（任何 commit 前）

- [ ] `git status` 干净，或已 `git stash` 暂存
- [ ] 没暂存 `storage_state.json` / `endpoint.json` / `manifest.json`（应被 .gitignore 拦下）
- [ ] 没暂存 `scripts/lint/*_<slug>.py` 复制脚本（属于本地工具，不入库）
- [ ] commit message 格式 `<type>: <说明>。to #82317048`，aoneId 已带

---

## 阶段 0 — 钉钉文档归档下载

- [ ] `~/Downloads/dingtalk-docs-archive-<slug>/` 存在（**用 `-<slug>` 后缀隔离**，避免与他人覆盖）
- [ ] `manifest.json` 的 total > 0，groups 数对得上输入目录
- [ ] `verify.py` 4 项校验全 pass，或失败 ≤ 5%
- [ ] 抽 3 篇 md 打开看 H1 与 manifest title 一致

## 阶段 1 — 导入归档（建 zh 树）

- [ ] `zh/<slug>/` 目录存在
- [ ] `find zh/<slug> -name '*.mdx' | wc -l` 与 manifest total 接近（差 ≤ 5%）
- [ ] 抽 3 篇 mdx 检查 frontmatter 有 `title` + `description`
- [ ] **commit**：`docs: 阶段 1 — <slug> 导入归档 N 篇。to #82317048`

## 阶段 2 — 字符卫生

- [ ] `grep -rP '\xc2\xa0' zh/<slug>/ --include='*.mdx' | head` 为空（NBSP=0）
- [ ] `grep -rP '\xe2\x80\x8b' zh/<slug>/ --include='*.mdx' | head` 为空（零宽=0）
- [ ] `grep -rE '^description: "?(:::|\\||$)' zh/<slug>/ --include='*.mdx' | head` 为空（垃圾 description=0）

## 阶段 3 — 标题正规化（顺序锁死）

- [ ] 跑过 `strip_duplicate_h1.py --apply`（必须**最先**）
- [ ] 跑过 `demote_all_h1.py --apply`
- [ ] 跑过 `normalize_headings.py --apply`
- [ ] `grep -rEn '^# [^!]' zh/<slug>/ --include='*.mdx' | head` 为空（正文 H1=0）
- [ ] **commit**：`docs: 阶段 2-3 — <slug> 字符卫生 + 标题层级正规化（X 文件）。to #82317048`

## 阶段 4 — `:::` 高亮块 / `&lt;` 实体

- [ ] `grep -rE '^:::' zh/<slug>/ --include='*.mdx' | head` 为空
- [ ] `grep -rE '&lt;' zh/<slug>/ --include='*.mdx' | head` 为空

## 阶段 5 — 钉钉编辑器残留

- [ ] `grep -rE '\[Priority|\[Flag\]|\[Tip [0-9]|▌|▍|▲|◆' zh/<slug>/ --include='*.mdx' | wc -l` = 0
- [ ] 伪 emoji 已清（命中 0）
- [ ] **commit**：`docs: 阶段 4-5 — <slug> 高亮块 JSX + 钉钉编辑器残留清理（X 文件）。to #82317048`

## 阶段 6 — MDX 语法审计

- [ ] `/docs-audit-mdx --root <slug> --lang zh --skip-links` 报告 A/B/C/E/F/G 命中 0
- [ ] D 类（URL-as-label）若有命中 → **已找人审 label 应改成什么**，不自作主张
- [ ] **commit**：`docs: 阶段 6 — <slug> MDX 语法审计修复（X 文件）。to #82317048`

## 阶段 7 — 翻译 en + ja

- [ ] `scripts/glossary/zh-en.json` 与 `zh-ja.json` 存在 + 最近 30 天有更新（否则先找砚心跑 `/docs-glossary-sync`）
- [ ] `--dry-run --limit 3` 干跑无错
- [ ] en `report.md` 头：`failed = 0`，skipped 仅为非占位已存在文件
- [ ] ja `report.md` 头：`failed = 0`
- [ ] **人工 review 抽样**：英文版抽 5 篇通读，日文版抽 3 篇请日语同学过一眼（可在评审时进行）
- [ ] **commit**：`docs: 阶段 7 — <slug> N 篇 en/ja 全量翻译。to #82317048`

## 阶段 7-bis — 自动润色（本轮新增）

- [ ] `/docs-translate-polish <slug> --lang en --dry-run --limit 1` 干跑无错（验证 prompt 装配 + 估成本合理）
- [ ] `/docs-translate-polish <slug> --lang en` 全量跑完，`scripts/output/polish_docs/en/report.md` 头 `failed = 0`
- [ ] `/docs-translate-polish <slug> --lang ja` 全量跑完，`scripts/output/polish_docs/ja/report.md` 头 `failed = 0`
- [ ] 抽样 review：英文 5 篇通读 + 日文 3 篇请日语同学过一眼（兜底 polish 漏过的问题）
- [ ] **commit**：`docs: 阶段 7-bis — <slug> en/ja 自动润色。to #82317048`

## 阶段 8 — 链接清扫

- [ ] `grep -rE '\]\(/en/<slug>/' <slug>/ --include='*.mdx' | wc -l` = 0
- [ ] `grep -rE '\]\(/zh/<slug>/' ja/<slug>/ --include='*.mdx' | wc -l` = 0
- [ ] `grep -rE 'alidocs\.dingtalk\.com|\?spm=|#\s*「' zh/<slug>/ <slug>/ ja/<slug>/ --include='*.mdx' | wc -l` = 0
- [ ] `/docs-audit-mdx --root <slug> --skip-syntax` 死链探针通过
- [ ] `mint broken-links` 通过（或仅剩本产品外的历史死链）
- [ ] **commit**：`docs: 阶段 8 — <slug> 链接清扫 + 死链清理（X 文件）。to #82317048`

## 阶段 9 — docs.json 三语 navigation 注册

- [ ] **用 `/docs-nav-edit add-product <slug>`**（绝不 Write 整份 docs.json）
- [ ] `/docs-nav-edit verify <slug>` 通过：三语 tabs 同序 + groups 同序 + pages 路径前缀正确
- [ ] ja 块的 group 中→日翻译表已交给砚心（或自行参照 `register_ja_docs_navigation.py` 模板生成）
- [ ] `/docs-preview` 三语首页截图均见自己产品 tab
- [ ] 抽 5 篇页（首页 / 1 个 group 入口 / 2 篇深层 / 1 篇含组件）渲染正常
- [ ] **commit**：`docs: 阶段 9 — <slug> 三语 navigation 注册。to #82317048`

---

## 三语对齐检查（开 MR 前最后一道）

- [ ] 三语篇数对齐：`for d in <slug> zh/<slug> ja/<slug>; do echo "$d: $(find $d -name '*.mdx' | wc -l)"; done` 三数相等
- [ ] 三语目录结构对齐：`diff <(find <slug> -type d | sed 's|^<slug>/||' | sort) <(find zh/<slug> -type d | sed 's|^zh/<slug>/||' | sort)` 无输出
- [ ] `docs.json` 三处 navigation 都改了（en / zh / ja 都有 `<slug>` 对应 tab）

## MR 提交

- [ ] 标题：`[<slug>] 接入 N 篇文档（阶段 1-9）`
- [ ] 描述模板：
  ```
  ## 阶段验收
  - [x] 阶段 1 导入归档 N 篇
  - [x] 阶段 2-3 字符卫生 + 标题正规化
  - [x] 阶段 4-5 高亮块 + 编辑器残留
  - [x] 阶段 6 MDX 语法审计
  - [x] 阶段 7 翻译 en + ja（cost ~$XX）
  - [x] 阶段 8 链接清扫（broken-links: 0）
  - [x] 阶段 9 docs.json 注册

  ## 关键数字
  - 三语篇数：<slug>/=N, zh/<slug>/=N, ja/<slug>/=N
  - 翻译报告：scripts/output/translate_docs/{en,ja}/report.md
  - 死链：0

  ## 给 reviewer
  - 重点看 docs.json diff（确保没误删其他 tab）
  - 抽 3 篇 ja review 日语自然度
  ```
- [ ] Assignee：砚心

---

## 全部 yes 才能开 MR。任何一项 no 或拿不准 → 回头修，或在群里 @砚心。

---

## 提交流程（每个产品做完一次）

1. 把本文件**勾选完整**版本另存为 `.claude/training/checklist-<slug>.md`（或在 MR 描述里粘贴勾选状态）
2. MR 描述顶部贴检查清单（套用 [模块 F.2 模板](./dingtalk-onboard-guide.md#f2-提-mr)）
3. assignee 填砚心，群里 `@砚心` 附 stage / log 截图 + prompt 原文
4. 砚心 30 min 内回复（CR 通过 → squash merge → 同步 github → mintlify 自动构建 ~5 min 上线）
5. 上线后视觉验收 `https://help.dingtalk.io/<slug>/`，发现问题开 `fix/<slug>-<issue>` 新分支走同流程

---

## 卡壳追问模板（Claude CLI 不前进时直接复制）

> 目标：让 CLI 说人话、说出关键信号；你不要替它猜。

| # | 卡壳类型 | 标准追问 prompt（直接复制喂回 CLI） | 验收口令 |
|---|---|---|---|
| 1 | CLI 反问"你想干什么？" | "我重新喂一份 6 字段 prompt 给你，请按 [前置]/[参数]/[任务]/[预期]/[出错]/[验收] 严格执行；任务 = <一句话动词开头>" | "明白，开跑" |
| 2 | CLI 报错跑路 | "把刚才命令的完整 stdout + stderr 原样贴回给我；不要尝试自己修；不要省略任何 traceback" | 看到完整错误堆栈 |
| 3 | 跑了一半停住 | "你停在第几步？需要哪个参数 / 哪个文件？说明缺什么再继续" | CLI 列出缺的输入 |
| 4 | 改完没效果 | "git diff <相关文件> 给我看；列出你实际改了什么 + 没改什么" | diff 输出可见 |
| 5 | skill 名字找不到 | "ls .claude/commands/docs-*.md 给我看；确认 skill 文件存在再调" | skill 列表可见 |
| 6 | docs.json 冲突 | "**绝不 Write 整份 docs.json**；只用 /docs-nav-edit add-product / verify；冲突先 git pull --rebase origin main 看完整冲突标记" | rebase 后 nav-edit 通过 |
| 7 | 翻译 cost 超预算 | "立刻 ctrl-c；按 100 篇分批跑，先 /docs-translate-batch <slug> --dry-run --limit 100 给我看预估 cost；不要全量盲跑" | dry-run cost ≤ 阈值 |
| 8 | mint broken-links 一堆死链 | "只列 <slug>/ + zh/<slug>/ + ja/<slug>/ 三目录下的死链；其他产品的历史死链先忽略" | 输出仅本产品死链 |

### 找砚心的边界

- 自查 1-8 仍卡 30 min → 群里 @ 砚心 附：1. CLI 完整输出 2. 你喂的 prompt 原文 3. 你已经试过哪一行追问
- 不要在没附以上 3 项前直接 @；砚心收到信息不全会反问，浪费两边时间
