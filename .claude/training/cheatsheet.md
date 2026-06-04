# 速查卡 · A4 单面打印

## Git 启动序列

```bash
git fetch origin
git checkout -b feat/<slug> origin/main      # 从 origin/main 出（不是 master）
git push -u origin feat/<slug>
```

每天开工先 rebase：`git pull --rebase origin main`

## 12 个 docs-* skill 速查

| Skill | 一句话 |
|---|---|
| `/docs-import-archive` | 阶段 0：从钉钉文档站抓 zh 归档（扫码 + 抓端点 2 人工） |
| `/docs-dingtalk-onboard <slug>` | 阶段 1-9 编排器（**主入口**） |
| `/docs-audit-mdx --root <slug>` | 阶段 6 / 8d：MDX 审计 + 外链死链探针 |
| `/docs-glossary-sync` | 阶段 7 前：合并官方词库 csv → zh-en/zh-ja.json（**仅砚心跑**） |
| `/docs-translate-batch <slug>` | 阶段 7：zh → en+ja 整目录翻译 |
| `/docs-translate-polish <slug>` | 阶段 7-bis：en/ja 自动语言润色（**本轮新增**，translate 后跑） |
| `/docs-translate <path>` | 单文件翻译（兜底） |
| `/docs-nav-edit add-product <slug>` | 阶段 9a：docs.json 三语 nav 原子操作（**禁 Write**） |
| `/docs-add-page <product> <slug> <group>` | 单页三语建页 |
| `/docs-preview` | mint dev + broken-links + 三语首页截图 |
| `/docs-prune-orphan-images` | 删完章节后清孤儿图 |
| `/docs-reorder-by-official-menu` | 按官方左侧菜单重排 pages |

## Prompt 6 字段结构（喂给 Claude CLI 的统一格式）

> 你不直接跑命令，是把下面这段**复制到 Claude CLI**，由它去调 skill。每段 prompt 必须含 6 字段，缺一都会卡壳——它会反问你而不是干活。

```
[前置]   先 cd ~/www/dingtalk-docs；分支 = feat/<slug>；上一阶段 commit 已落
[参数]   <slug>=你的产品 slug；<source>=钉钉源目录名
[任务]   清晰的一句话动词开头：导入 / 翻译 / 润色 / 注册 ...
[预期]   你期待 CLI 看到的产物：报告 X 行；某 grep 为空；某文件存在
[出错]   遇到这俩信号怎么办（命令 stdout / 阻塞点）
[验收]   通过后让你说一句什么话再放它走（类似口令）
```

每个产品从头到尾 9 段 prompt（详见 `dingtalk-onboard-guide.md` 模块 D 各阶段「📋 Prompt 喂给 Claude CLI」）。本卡只列每阶段的**关键命令**，6 字段全文去 guide 抄。

```
# 阶段 0 — 下载（人工：扫码 + 抓端点）
/docs-import-archive --input <你的 .url 包> --output ~/Downloads/dingtalk-docs-archive-<slug>/

# 阶段 1-6 — 编排器一击全跑
/docs-dingtalk-onboard <slug> --archive ~/Downloads/dingtalk-docs-archive-<slug>/

# 阶段 7 + 7-bis — 翻译 + 润色
/docs-translate-batch <slug> --dry-run --limit 3   # 必须先干跑
/docs-translate-batch <slug>                        # 全量 zh→en+ja
/docs-translate-polish <slug> --lang en --dry-run --limit 1
/docs-translate-polish <slug> --lang en
/docs-translate-polish <slug> --lang ja

# 阶段 8 — 链接清扫（编排器内嵌，手工补救才单独喂）
"按阶段 8 的 4 步严格顺序跑：跨语言前缀 → alidocs 替换 → /docs-audit-mdx 死链探针 → mint broken-links"

# 阶段 9 — nav 注册 + 验收
/docs-nav-edit add-product <slug>
/docs-nav-edit verify <slug>
/docs-preview
```

## 9 阶段顺序

```
0 下载   → 1 导入   → 2 字符卫生 → 3 标题层级 → 4 高亮块 →
5 编辑器残留 → 6 MDX 审计 → 7 翻译 en+ja → 8 链接清扫 → 9 nav 注册
                                              ↓
                                          MR → 砚心 CR → 上线
```

## 每阶段 commit 模板

```
docs: 阶段 1 — <slug> 导入归档 N 篇。to #82317048
docs: 阶段 2-3 — <slug> 字符卫生 + 标题正规化（X 文件）。to #82317048
docs: 阶段 4-5 — <slug> 高亮块 + 编辑器残留清理（X 文件）。to #82317048
docs: 阶段 6 — <slug> MDX 语法审计修复（X 文件）。to #82317048
docs: 阶段 7 — <slug> N 篇 en/ja 全量翻译。to #82317048
docs: 阶段 8 — <slug> 链接清扫 + 死链清理（X 文件）。to #82317048
docs: 阶段 9 — <slug> 三语 navigation 注册。to #82317048
```

## 10 大陷阱速记

1. **阶段 3 顺序锁死**：strip_duplicate_h1 → demote_all_h1 → normalize_headings
2. **阶段 7 占位检测覆盖多语言**：跑前 `grep -rlE 'TODO translate|TODO 翻訳|TODO 翻译' <lang>/<slug>/`
3. **阶段 8 跨语言前缀必修**：en 加 `/en/`、ja 沿 `/zh/`，sed 批量修
4. **阶段 8 alidocs 4 步替换严格顺序**：双井号 → 中文锚 → spm → 域名换；**绝不加 `\?$` MULTILINE fixup**（会吃 H3 问号）
5. **阶段 8 死链信号是 og:title 空**（SPA），不是 HTTP 状态码
6. **阶段 9 docs.json 绝不 Write 整份覆盖**：必须 Edit 精确插入
7. **新陷阱 A**：archive 路径要带后缀 `~/Downloads/dingtalk-docs-archive-<slug>/`，否则多人覆盖
8. **新陷阱 B**：`scripts/lint/*.py` hardcode `zh/docs/`，复制为 `*_<slug>.py` 跑，**不入库**
9. **新陷阱 C**：词库 `zh-en.json` 单文件并发改会冲突，**只读不改**
10. **新陷阱 D**：阶段 9 前先 `git pull --rebase origin main` 拿最新 docs.json，冲突时**保留别人已合的 tab**

## 救命命令

```bash
# 端口被占
lsof -ti:3000 | xargs kill

# 想暂存改动跑命令
git stash && <跑你的命令> && git stash pop

# 看死链报告
mint broken-links 2>&1 | tee /tmp/broken-links-$(date +%s).txt

# 看自己改了哪些 mdx
git status -s '*.mdx' | head -40

# 三语篇数对齐校验
for d in <slug> zh/<slug> ja/<slug>; do echo "$d: $(find $d -name '*.mdx' | wc -l)"; done

# docs.json 没被破坏
python3 -c "import json; json.load(open('docs.json'))" && echo OK
```

## 我该找谁

- 词库更新 / glossary-sync → 砚心
- 想改 `scripts/lint/*.py` hardcode → **不改，复制为 `*_<slug>.py`**
- docs.json 有别人的改动 rebase 冲突 → 先群里 @ 持有冲突 tab 的负责人
- mintlify 上线后页面不见 / 显示异常 → 砚心
- 翻译 cost 超预算 → 自己 `--limit N` 分批跑，仍超报告砚心

## 卡壳手册（Claude CLI 不动 / 答非所问怎么办）

8 类典型卡壳 → 标准追问 prompt（直接复制粘贴）：

| 卡壳信号 | 标准追问 |
|---|---|
| CLI 反问"你想干什么？" | 你 prompt 缺 [任务] 字段。补上动词开头一句话 |
| CLI 报错跑路 | "把刚才的命令完整 stdout/stderr 贴回给我，不要尝试自己修" |
| 跑了一半停住 | "你停在哪一步？还需要我提供什么参数？" |
| 改完没效果 | "diff 给我看你改了哪些文件、改前改后" |
| skill 没找到 | `ls .claude/commands/docs-*` 自查名字；不在就找砚心 |
| docs.json 冲突 | **绝不 Write 整份**；说"用 /docs-nav-edit add-product，不要手动 Edit" |
| 翻译 cost 超预算 | "停下来，按 100 篇分批跑，先 --limit 100 给我看 cost" |
| mint broken-links 一堆死链 | "只列我本产品 <slug>/ 下的死链，不要管别人的历史死链" |

兜底口令：拿不准就群里 `@砚心` 附 prompt 原文 + CLI 完整输出。

## 配色 / 字体备注（PPTX + 手册视觉约定）

- 主色：`#1E2761`（Midnight Executive 深海军蓝）+ accent `#FF6B35`（Coral）
- 字体：英文 / 数字 = Cambria；中文 = PingFang SC；代码 = Menlo
- emoji 政策：**0 emoji**（icon 用 react-icons heroicons + colored circle 包裹）
- 6 字段 prompt 块永远用主色深底 + WHITE 等宽字
