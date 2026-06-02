# 产品目录级批量翻译（zh → en + ja）

> 子 skill：作为 [[docs-dingtalk-onboard]] 流水线第 7 阶段调用（也可独立跑）

把 `zh/<root>/` 下整个产品目录批量翻成英文（写入 `<root>/`）与日文（写入 `ja/<root>/`），自动跑词库强约束 + 图视频剥离 + 链接前缀修正 + 死链验证。

## 适用场景

- 新接入一个产品（如 `aitable` / 新产品 slug），中文母版已就位，要一次性产出三语
- 已有产品的中文母版大幅更新，需要 `--force` 重译全部
- 单 group / 单 page 子集快速验证（用 `--only` / `--limit`）

> 单文件级翻译用 `/docs-translate <source-path>`；本 skill 是**整个产品目录**级。

## 参数

- `<root>`（必填）：zh 下的根目录名（如 `docs` / `aitable`）
- `--langs <en,ja>`（默认 `en,ja`）：目标语言，逗号分隔
- `--concurrency <N>`（默认 `4`）：并发路数；阿里网关实测 4 路稳定
- `--only <path-prefix>`（可选）：只翻指定路径前缀（如 `aitable/dashboard`）
- `--limit <N>`（可选）：只翻前 N 篇
- `--force`（可选）：覆盖非占位的已译文件
- `--dry-run`（可选）：只列任务 + 命中术语，不调 LLM、不写文件
- `--skip-pilot`（可选）：跳过 3 篇干跑预检

## 执行流程（7 步）

### 步骤 1 — 前置检查（fail fast）

```bash
test -d zh/<root>/                                          # 源目录存在
test -f scripts/glossary/zh-en.json                         # 词库就位
test -f scripts/glossary/zh-ja.json
which claude                                                # CLI 可用（脚本依赖 claude -p --bare 子进程）
```

报告每个目标语言下 `<lang>/<root>/` 现状：

```bash
# 占位 mdx 数（待翻）
grep -rlE 'TODO translate|TODO 翻訳|TODO 翻译' <lang>/<root>/ --include='*.mdx' | wc -l
# 已译 mdx 数（总数 - 占位）
find <lang>/<root>/ -name '*.mdx' | wc -l
```

任何检查失败 → 停下来报具体怎么修，不冒进。

### 步骤 2 — 干跑预检（默认跑，可 `--skip-pilot` 跳）

```bash
python3 scripts/translate_mdx_batch.py --root <root> --lang <langs[0]> --dry-run --limit 3
```

输出每篇命中术语数 + 源字符数。**按本次基准外推全量成本**：

| 指标 | docs 实测（349 篇） | 单篇均值 |
|---|---|---|
| 用时 | en 23min / ja 32min | ~4s / ~5.5s |
| input tokens | en 237k / ja 285k | ~680 / ~820 |
| output tokens | en 444k / ja 573k | ~1.3k / ~1.6k |
| cost | en $24.25 / ja $27.38 | ~$0.07 / ~$0.08 |

向用户回显成本估算 + 问"OK 继续吗？"（除非 `--dry-run`）。

### 步骤 3 — 批量翻译（按 `--langs` 顺序串行）

```bash
python3 scripts/translate_mdx_batch.py \
  --root <root> --lang <lang> \
  --concurrency <N> \
  [--only ...] [--limit ...] [--force]
```

脚本会自动：
- 跳过非占位的已译文件（除非 `--force`）
- 单篇失败重试 3 次（指数退避 3/6/12s）
- 写报告到 `scripts/output/translate_docs/<lang>/{report.json,report.md}`

每个 lang 跑完后**读 report.md 头部回显**：

```
总：N / ok / skipped / failed
input / output tokens
cost
```

**有 failed → 停下来让用户决策**（重试 / 跳过 / 终止），不冒进。

### 步骤 4 — 修 LLM 错链前缀（**这步必跑**，最容易漏的收尾）

LLM 经常给内部相对链接加错语言前缀。**先 `grep -c` 报告将改多少处**：

```bash
# en：英文站是根，错链形如 [x](/en/<root>/foo)
grep -rE '\]\(/en/<root>/' <root>/ --include='*.mdx' | wc -l
# ja：LLM 容易沿用源里的 /zh/，错链形如 [x](/zh/<root>/foo)
grep -rE '\]\(/zh/<root>/' ja/<root>/ --include='*.mdx' | wc -l
```

然后批量替换：

```bash
find <root> -name '*.mdx' -exec sed -i '' 's|](/en/<root>/|](/<root>/|g' {} \;
find ja/<root> -name '*.mdx' -exec sed -i '' 's|](/zh/<root>/|](/ja/<root>/|g' {} \;
```

本次 docs 实测：en 改 35 处 / ja 改 142 处。

### 步骤 5 — 残留扫描

```bash
# TODO 占位残留
grep -rE 'TODO translate|TODO 翻訳|TODO 翻译|TODO: Translate|から翻訳|翻译自' <root>/ ja/<root>/ --include='*.mdx' | head

# 图 / 视频 / iframe 标签残留（应全部被脚本剥离）
grep -rE '<img |<video |<iframe ' <root>/ ja/<root>/ --include='*.mdx' | head
grep -rE '^!\[' <root>/ ja/<root>/ --include='*.mdx' | head
```

任何输出非空 → 列出问题文件让用户决定。**已知误报**：mdx 内代码块里展示"不支持的 Markdown 语法"时，`![ab]]()` 等会被 grep 命中，但这是代码块内容、mintlify 按代码渲染，可忽略。

### 步骤 6 — 死链验证

```bash
mint broken-links
```

只关心 `<root>/**` 和 `ja/<root>/**` 路径下的死链。其它路径的死链是历史遗留（如 `zh/aitable` CJK URL 编码不对称，详见 memory `project_mdx_image_batch_pitfalls`），不在本批次责任范围内。

### 步骤 7 — ja navigation 注册（仅 `--langs` 含 ja 时）

读 `docs.json` 的 ja navigation，看有没有指向 `ja/<root>` 的 tab：

```bash
python3 -c "
import json
d = json.load(open('docs.json'))
ja_lang = next((x for x in d['navigation']['languages'] if x['language']=='ja'), None)
if not ja_lang:
    print('NO_JA_LANG_BLOCK')
else:
    found = any(any(g['pages'][0].startswith(f'ja/<root>/') if g.get('pages') else False for g in t.get('groups', []) if g.get('pages')) for t in ja_lang.get('tabs', []))
    print('TAB_EXISTS' if found else 'NEED_REGISTER')
"
```

- **TAB_EXISTS** → skip
- **NEED_REGISTER** → 提示用户：

  > 检测到 docs.json 缺 ja `<root>` 对应 tab。按 `scripts/register_ja_docs_navigation.py` 模板手动加：
  >
  > 1. `cp scripts/register_ja_docs_navigation.py scripts/register_ja_<root>_navigation.py`
  > 2. 改 `SOURCE_TAB_NAME`（在 zh 块里找显示名）、`TARGET_TAB_NAME`（日文 tab 显示名）、`GROUP_NAME_MAP`（产品的 group 中→日名翻译表，需人工提供）
  > 3. `python3 scripts/register_ja_<root>_navigation.py`（预演）→ 满意后加 `--write` 落盘
  >
  > **为什么不在 skill 里自动做**：每个产品的 group 名翻译是 product-specific 的，没人能机器做对。

### 步骤 8 — 报告与引导

按本次模板回显：

```
✓ <root> 翻译完成：
  - en: N ok / N skipped / N failed  用时 Xmin  成本 $Y
  - ja: N ok / N skipped / N failed  用时 Xmin  成本 $Y
  - 链接前缀修正：en X 处 / ja Y 处
  - 残留扫描：clean / 见上面列表
  - mint broken-links：通过 / X 条死链
  - docs.json ja <root> tab：已注册 / 需手动 register

下一步：
- 如要提交：/commit-flow
  建议 commit message：docs: <root> N 篇 en/ja 全量翻译 + 链接前缀修正 + ja navigation 注册。to #82317048
- 如要本地预览：mint dev → 切 EN/JA → 进入对应 tab
```

**不自动 commit / push**（按 user memory `feedback_commit_authorization.md`）。

## 关键陷阱（已踩过的坑）

### Pitfall 1: 占位检测必须覆盖多语言

`translate_mdx_batch.py` 的 `is_placeholder()` 正则必须同时识别 en / ja / zh 三种 TODO 标记（`TODO translate` / `TODO 翻訳` / `TODO 翻译` / `Translate from` / `から翻訳` / `翻译自`），否则像本次第一轮日文那样会 349 篇全 skip。脚本已修复（见 commit `bb15cd3`），但 skill 跑前还是先确认目标目录确有占位：

```bash
grep -rlE 'TODO translate|TODO 翻訳|TODO 翻译' <lang>/<root>/ --include='*.mdx' | head -3
```

### Pitfall 2: 链接前缀必修

LLM 系统性产出错误前缀（en 加 `/en/`、ja 沿用 `/zh/`）。本次 docs 实测：en 35 处 / ja 142 处。**步骤 4 是收尾必跑步**，不修会导致大量内部死链。

### Pitfall 3: 阿里网关不支持 prompt caching

input tokens 走原价，不要试图缓存 system prompt。脚本已按原价模式工作，实测成本仍可接受（349 篇 ~$25/lang）。不要自作主张改成 `cache_control`。

### Pitfall 4: 直接调 anthropic SDK 会被网关 400

阿里内网网关限制 opus 计划仅 Claude Code 内可用。脚本通过 `claude -p --bare` 子进程绕过；**不能**改成直接 SDK 调用。详见 memory `project_docs_translation_batch1`。

### Pitfall 5: 别用 `--force` 顺手重译

`--force` 会覆盖所有已译文件（包括人工已校对过的）。只在中文母版大幅更新时用，并且**先做 git 备份分支**。

## 与其他 skill 的协作

- `/docs-glossary-sync` — 词库更新后再跑本 skill，让翻译用上最新术语
- `/docs-translate <single-path>` — 单文件级翻译（本 skill 不适用的场景）
- `/commit-flow` — 翻译完成后用户授权提交（aoneId `82317048`）
- `/docs-preview` — 跑完批量翻译后用此 skill 做视觉验证

## 历史基准（docs/ 首批 2026-06-02）

| 语向 | 文件数 | 用时 | input tokens | output tokens | cost |
|---|---|---|---|---|---|
| zh→en | 349 (348 ok + 1 skip) | 23.3 min | 237k | 444k | $24.25 |
| zh→ja | 349 (349 ok) | 32.3 min | 285k | 573k | $27.38 |
| **合计** | **698** | **~55 min** | **522k** | **1.02M** | **$51.63** |

完整记录：memory `project_docs_translation_batch1`。
