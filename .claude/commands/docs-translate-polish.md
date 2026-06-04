# 翻译润色（en / ja 已译文件二次打磨）

> 子 skill：作为 [[docs-translate-batch]] 之后的可选润色环节，针对已译产出做"自动语言检测 + 语言质量优化"。也可独立跑。

把 `<root>/` 或 `ja/<root>/` 下已经存在的英 / 日译文做二次打磨：保留语义、链接、组件、frontmatter 不变，只改语言层面的术语一致性 / 句长 / 主动语态 / 标点 / 列表平行 / 时态等问题。**绝不改动语义，只改语言质量。**

## 适用场景

- `/docs-translate-batch` 跑完后，对译文做一轮"母语化"打磨
- 词库 `/docs-glossary-sync` 更新后，让旧译文按新术语对齐
- 收到人工 review 反馈后，先用 polish 跑一遍批量统一风格，再人工兜底
- 翻译批次里看到 LLM 偶发口语 / 长定语 / Chinglish，想批量纠

> 单文件级用 `/docs-translate <path>` 重译；本 skill 是**整个产品目录**级的语言层打磨。

## 参数

- `<root>`（必填）：产品根目录名（如 `docs` / `aitable`），不带前缀
- `--lang <en|ja>`（必填）：目标语言；input 路径自动推导为 `<root>/`（en）或 `ja/<root>/`（ja）
- `--concurrency <N>`（默认 `4`）：并发路数
- `--only <path-prefix>`（可选）：只润色指定路径前缀（如 `docs/dingtalk-docs`）
- `--limit <N>`（可选）：只润色前 N 篇
- `--force`（可选）：忽略 polish 状态标记，强制重新润色
- `--dry-run`（可选）：只列任务 + 评估字符量，不调 LLM 不写文件

## Review checklist（内嵌在 polish prompt 里作为强约束）

每篇打磨严格按以下 10 条 review 维度：

1. **术语一致性**：未在术语表中出现的同义词统一为词库首选译法（首选译法见 `scripts/glossary/zh-<lang>.json` value 字段）
2. **句长**：长复合句拆短；英文单句不超 30 词，日文不超 50 字
3. **语态**：英文优先 imperative / active；日文优先 です・ます調 + 体言止め混用避免单调
4. **链接锚文本**：`[text](/foo)` 中 text 与目标页 frontmatter title 风格一致；不留 `[这里](...)` 之类无意义锚文本
5. **列表平行**：同级 bullet 起首词性 / 时态 / 单复数对齐
6. **时态**：description / heading 多用现在时；release notes 行业表达规范化（New / Improved / Fixed / Deprecated 或 新機能 / 改善 / 修正 / 廃止）
7. **标点**：英文用 `. , ? ! "" ()`；日文用 `。、「」（）`；不混用全 / 半角
8. **大小写**：英文 heading 用 sentence case（首字母 + 专有名词），不用 Title Case
9. **代码块标题**：` ```bash title="..." ` 中 title 文本通顺、有意义，不直翻中文
10. **截图 alt**（如有保留）：`![alt](url)` 中 alt 是描述性短句，不是机翻碎片

## 执行流程（5 步）

### 步骤 1 — 前置检查（fail fast）

```bash
# 目标目录存在
test -d <lang_dir>/                                      # en: <root>/  / ja: ja/<root>/
# 词库就位（用于术语一致性约束）
test -f scripts/glossary/zh-en.json
test -f scripts/glossary/zh-ja.json
# CLI 可用
which claude
# 占位检测：polish 不接占位文件，必须先用 /docs-translate-batch 出译文
grep -rlE 'TODO translate|TODO 翻訳|TODO 翻译' <lang_dir>/ --include='*.mdx' | head
# 应为空，否则报"polish 前请先 /docs-translate-batch 把占位翻译完"
```

### 步骤 2 — 干跑预检

```bash
python3 scripts/translate_polish_batch.py --root <root> --lang <lang> --dry-run --limit 3
```

输出每篇字符数 + 命中术语数 + 待打磨估计。**按本次基准外推全量成本**：

| 指标 | docs en（349 篇预估）| 单篇均值 |
|---|---|---|
| 用时 | ~16 min | ~3s |
| input tokens | ~330k（译文+术语注入）| ~950 |
| output tokens | ~410k（同等长度回吐）| ~1.2k |
| cost | ~$17 | ~$0.05 |

> 实测以首次跑完为准；polish 比 translate 略便宜（同等输出但 input 已是目标语言，少了 zh→en 的 token 膨胀）。

向用户回显成本估算 + "OK 继续吗？"。

### 步骤 3 — 批量打磨

```bash
python3 scripts/translate_polish_batch.py \
  --root <root> --lang <lang> \
  --concurrency <N> \
  [--only ...] [--limit ...] [--force]
```

脚本行为：
- 默认跳过已被标记为已 polish 的文件（frontmatter 私有字段 `polished: true`，或 sidecar `<file>.polished` 文件二选一）
- 单篇失败重试 3 次（指数退避 3/6/12s）
- 报告写到 `scripts/output/polish_docs/<lang>/{report.json,report.md}`

跑完读 report.md 头部回显：

```
总：N / ok / skipped / failed
input / output tokens / cost
```

**有 failed → 停下来让用户决策**（重试 / 跳过 / 终止）。

### 步骤 4 — 残留扫描（与 translate-batch 同步）

```bash
# 图 / 视频 / iframe 不应被 polish 重新生成
grep -rE '<img |<video |<iframe ' <lang_dir>/ --include='*.mdx' | head
# 内部链接前缀正确（不应被 polish 改坏）
grep -rE '\]\(/zh/' <lang_dir>/ --include='*.mdx' | head    # ja 不应有 /zh/
grep -rE '\]\(/en/' <lang_dir>/ --include='*.mdx' | head    # en 不应有 /en/ 前缀
```

任何输出非空 → 列出问题文件让用户决定（未通过则 polish 不算成功）。

### 步骤 5 — 死链验证

```bash
mint broken-links
```

只关心 `<lang_dir>/**` 路径下的死链。增量数应为 0（polish 不应引入新死链）。

## 与 translate-batch 的差异

| 维度 | translate-batch | translate-polish |
|---|---|---|
| 输入 | `zh/<root>/*.mdx` | `<root>/*.mdx`（en）/ `ja/<root>/*.mdx` |
| 输出 | `<root>/*.mdx` 或 `ja/<root>/*.mdx`（新建） | 同路径覆盖 |
| 任务 | 跨语言翻译 | 同语言润色 |
| 词库角色 | 强约束首译 | 强约束术语对齐（更新旧译文） |
| 占位处理 | 检测到占位才跑 | 检测到占位**拒绝跑**（先 translate） |
| 图视频处理 | 强制剥离 | 不剥离（已在 translate 阶段剥离）|
| 系统 prompt | `SYSTEM_RULES + STYLE_<LANG>` | `POLISH_RULES + REVIEW_CHECKLIST + STYLE_<LANG>` |
| 单篇 input | 中文长 | 英 / 日译文长（更短）|
| 单篇成本 | ~$0.07-0.08 | ~$0.05 |

## 关键陷阱

### Pitfall 1: polish 不能改语义

约束 prompt 必须明确"只改语言层面 — 术语 / 句长 / 标点 / 时态；**绝不增删信息、绝不改链接、绝不改 frontmatter 字段名、绝不改组件 props**"。脚本同时跑后置正则双保险，对比前后链接数 / 组件标签数差异 > 0 时拒绝写入。

### Pitfall 2: polish 不接占位

源文件还是 `TODO translate` 占位时跑 polish 等于让 LLM 生成内容，是错误。脚本前置 `is_placeholder()` 检测，命中即 skipped + 报"先跑 translate-batch"。

### Pitfall 3: 不重复 polish

不加状态记录会被反复打磨，每跑一次成本叠加。脚本默认在 frontmatter 添加 `polished: true` 字段标记；读到该字段即 skip（除非 `--force`）。

### Pitfall 4: 词库强约束不能 over-fit

word-by-word 替换会把术语表中已译过的英文词重复套上。脚本只在 hit 时把术语表 inject 到 user message 让 LLM 自己判断，**不做正则替换**。

### Pitfall 5: 阿里网关无 prompt caching

input 走原价。**不要**改成 `cache_control`，详见 [[docs-translate-batch]] Pitfall 3。

## 与其他 skill 的协作

- `/docs-translate-batch` — 必须先跑完，产出非占位译文后再 polish
- `/docs-glossary-sync` — 词库更新后跑 polish，让旧译文对齐新术语
- `/docs-translate <path>` — 单文件级；本 skill 是产品目录级
- `/commit-flow` — polish 完成后用户授权提交（aoneId `82317048`）
- `/docs-preview` — 跑完做视觉验证（重点看 heading 大小写、列表平行、句长）

## 报告

```
✓ <root> polish 完成（<lang>）：
  - N ok / N skipped / N failed
  - 用时 Xmin  成本 $Y
  - 残留扫描：clean / 见列表
  - mint broken-links：通过 / X 条新死链（应为 0）

下一步：
- 提交：/commit-flow
  建议 commit message：docs: <root> en/ja 译文 polish（X 文件，术语 + 句长 + 时态对齐）。to #82317048
- 视觉对比：mint dev → 切对应语言 → 抽样进入对应 tab
- 全量人工 review 兜底（推荐对 release-notes / quickstart 这种核心页保留人工把关）
```

**不自动 commit / push**（按 user memory `feedback_commit_authorization.md`）。
