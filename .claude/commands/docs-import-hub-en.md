---
description: EN-direct 导入路线 — 钉钉文档英文 hub 一键导入帮助中心子产品（hub crawl → download → 仿模板 import → 注册 en tab，跳过翻译）
---

# /docs-import-hub-en `<product-slug>` `<hub-url>` [`<tab-display-name>`]

把钉钉文档（alidocs）上某个英文 hub 节点导入 dingtalk-docs 仓库，作为帮助中心第 N 个 en tab。

**适用前提**：源即英文母版（团队已备 EN 版）。不走 `/docs-dingtalk-onboard` 9 阶段中→英/日翻译流水线（那条线适合 zh 源）。

**历史实操**：mail（22 篇，2026-06-08）、im（18 篇，2026-06-12）、drive（6 篇，2026-06-15）三个产品已用本路线。

## 参数

| 参数 | 必填 | 示例 | 说明 |
|---|---|---|---|
| `<product-slug>` | 是 | `drive` | 顶层目录名 / docs.json 子目录前缀，全英文 kebab-case |
| `<hub-url>` | 是 | `https://alidocs.dingtalk.com/i/nodes/<uuid>` | 钉钉文档 hub 节点 URL |
| `<tab-display-name>` | 否 | `Drive`（默认大写化 slug） | docs.json en Help Center tab 显示名 |

## 9 步流程

### 1. 前置环境检查

```bash
cd /Users/yanxin/www/dingtalk-docs/.claude/import/dingtalk_downloader
stat -f '%Sm' storage_state.json    # 看登录态时间戳
```

**若 storage_state.json 距今 > 7 天**：在**独立 Terminal**（不在 Claude REPL 里，REPL 的 stdin 被关会 EOFError）跑 `python3 auth_bootstrap.py`，浏览器扫码登录后回到 Terminal 按 Enter 保存。

### 2. crawl_hub.py 抓 manifest

```bash
python3 crawl_hub.py \
    --hub-url '<hub-url>' \
    --lang en-US \
    --output-dir ~/Downloads/$(date +%F)_DingTalk_<Product>/
```

**已知坑 1 — CJK 阈值**：`crawl_hub.py:53` `MAX_CJK_RATIO = 0.10`（2026-06-15 Drive 实操后从 0.05 固化到 0.10）。帮助中心 hub 装饰元素（侧栏「目录」「新建」等本地化按钮）常 6-9%，0.05 太严会卡 EOFError。若仍超 0.10 → 临时调 0.15 跑完**恢复 0.10**（不入仓）。

**已知坑 2 — API 401 偶发**：第一次 fetch_children_api 可能 HTTP 401（cookie warm-up），再跑一次通常 200。若连续 2 次 401 → 用 `python3 /tmp/<product>_hub_diag.py` 一次性诊断脚本（仿 drive 实操，加载 storage_state 直接调 dentry/list API + DOM 抽链接 + 截图）。

**已知坑 3 — Catalog 视图**：若 hub 渲染为 React DnD Catalog（无 `<a>` 标签），DOM fallback 必败。**API 路径必须能跑通**（dentryUuid 即 URL 末段 ID）；若 API 也不通，停下排查权限。

**已知坑 7 — file+hasChildren=True 嵌套层级**：钉钉文档 dentry 模型是 `dentryType` + `hasChildren` 双字段，**不是简单 file/folder 二分**。`dentryType=file` 的节点也可能 `hasChildren=True`（既是文档自身，也是子文档父级）。crawl_hub.py 2026-06-15 已修 fetch_children_api 用 hasChildren 决定递归。**下次接新产品需预期可能存在嵌套层级**：抓到的 manifest 包含 N 个顶层 + 各 parent 自身 + 各 parent 子文档；下载会按 `<parent>.adoc/<child>.adoc.md` 嵌套到源目录。

### 3. download.py 拉 markdown

```bash
python3 download.py --headed --locale en-US
```

**已知坑 4 — 必须 --headed**：headless 下 Playwright `hover()` 不触发完整鼠标事件，子菜单消失，导出按钮点击无反应。**这是硬性要求，不可绕过**。

**已知坑 5 — DOWNLOAD_TIMEOUT_MS**：`download.py:45` `DOWNLOAD_TIMEOUT_MS = 30_000` 对部分子节点偏短。若 timeout → 临时调 `120_000`，跑完**恢复 30_000**（不入仓）。

**已知坑 6 — hub 节点本身失败**：manifest 第 1 条是 hub 节点自身，download 会失败（无导出菜单），退码 1 但 leaf 全 ✅ 即可继续；若退码 1 后还有真实 leaf failed（如 timeout）→ `python3 download.py --retry-failed --headed --locale en-US` 重跑 failed 子集（建议先临时调 DOWNLOAD_TIMEOUT_MS=120_000，retry 完恢复 30_000）。

### 4. verify.py 验语言

```bash
python3 verify.py --expect-lang en
```

`EN_MAX_CJK_RATIO = 0.20`（独立常量，不与 crawl_hub.py 的阈值耦合）。leaf 正文 CJK > 20% → 源未切英文，**停下排查**，不要进入下一步。

### 5. 抽 GROUPS 表（手工）

扫源目录 `~/Downloads/<date>_DingTalk_<Product>/*.adoc.md`：

- **若含 `README.adoc.md`**（IM 模式）：用 README 内的层级列表为 GROUPS 来源，README 自身不入仓
- **若无 README**（Mail/Drive 模式）：按文件名前缀语义 + 实际正文标题手工划 3-6 个 group

GROUPS 表三种形态（看源文件名特征选）：

```python
# 形态 A: 文件名 == slug（im 风格，二元组）
GROUPS = [('<group>', [('<slug>', '<expected_title>'), ...]), ...]

# 形态 B: 文件名带数字编号前缀（mail 风格，二元组 + find_source 按编号查）
GROUPS = [('<group>', [('<slug>', '<expected_title>'), ...]), ...]

# 形态 C: 文件名是 Title Case + 空格/标点（drive 风格，三元组 + find_source 按 basename 拼路径）
# source_basename 支持嵌套形式 '<Parent>.adoc/<Child>.adoc.md'（应对 file+hasChildren=True 嵌套层级）
GROUPS = [('<group>', [('<slug>', '<source_basename>', '<expected_title>'), ...]), ...]
```

**嵌套层级的 group 编排**（hasChildren 父级文档的处理）：把 parent overview 作为 group 第一个 page、子文档紧随其后，对应钉钉文档 hub 折叠菜单"目录文档"的语义。Drive 实例 4 group：Getting Started(3 平铺) + Employee User Guide(1 overview + 13 子) + Administrator Guide(1 overview + 4 子) + FAQ(1 overview + 1 子)。

### 6. 写 `scripts/import_<slug>_en.py`

**从既有任一模板复制**（推荐挑形态最接近的）：

```bash
cp scripts/import_drive_en.py scripts/import_<slug>_en.py   # 文件名形态 C
cp scripts/import_im_en.py    scripts/import_<slug>_en.py   # 文件名形态 A
cp scripts/import_mail_en.py  scripts/import_<slug>_en.py   # 文件名形态 B
```

**必改 4 处**（无论选哪个模板）：

| 改动 | 原值（举 drive） | 改为 |
|---|---|---|
| `DEFAULT_SOURCE` | `~/Downloads/2026-06-15_DingTalk_Drive` | 当前下载日期目录 |
| `<SLUG>_DIR` | `REPO_ROOT / 'drive'` | `REPO_ROOT / '<slug>'` |
| `OUTPUT_DIR` | `... / 'drive_en'` | `... / '<slug>_en'` |
| `GROUPS` 表 | drive 6 篇 3 group | 第 5 步抽出的当前产品 GROUPS |
| `'tab': 'Drive'` | `Drive` | `<tab-display-name>` |

**条件性差异点**（按下载下来的文件实测决定，不要照抄模板）：

- **line-1 H1 形态**：im 是 `# <kebab-slug>` 噪声 → `LEADING_FILENAME_H1_RE`；mail 是 `# NN - <Title>` 编号噪声 → `LEADING_NUMBERED_H1_RE`；drive 是 `# <Title>` 真 H1 → **不剥 H1**，让 `parse_frontmatter_data` 自动抽 + 剥；可能有 `---` 分隔线残留 → `LEADING_HR_RE` 剥
- **find_source 入参**：mail 按编号、im 按 slug（直接拼 `<slug>.adoc.md`）、drive 按 source_basename（直接拼 `<basename>`）

**绝不动**的部分（无论选哪个模板）：`clean_invisible` / `extract_clean_description` / `process_one` 主体 / `build_nav_fragment` / `main` 主循环 / 复用的 `escape_mdx` / `parse_frontmatter_data` / `yaml_escape`。

### 7. dry-run + 实写

```bash
python3 scripts/import_<slug>_en.py --dry-run
```

**验收 3 信号**（全绿才进下一步）：
- 成功 == GROUPS 表 expected_total（无 missing）
- mdx 残留 NBSP == 0
- title 不一致 == 0（若 > 0：检查是 GROUPS 表 expected_title 写错还是源 H1 + parse_frontmatter_data 流程不对）

```bash
python3 scripts/import_<slug>_en.py   # 实写
```

产物：`<slug>/*.mdx` × N + `scripts/output/<slug>_en/{nav-fragment.json, slug-map.json, report.md}`

### 8. docs.json 注册 en tab（Edit 工具精确插入）

定位 IM tab（或最后一个 en Help Center tab）的闭合 `}` 位置：

```bash
grep -n '"tab":' docs.json | head -10    # 看 en 块 tabs 序列
```

**用 Edit 工具**精确字符串替换，**绝不 Write 覆盖整个 docs.json**（项目硬规则）。锚点形态：

```
                  ]
                }            ← 最后一个 tab 闭合
              ]
            },               ← Help Center product 闭合
            {
              "product": "Open Platform",
```

改为：

```
                  ]
                }            ← 最后一个 tab 闭合
              },             ← 加逗号
              {              ← 插新 tab
                "tab": "<tab-display-name>",
                "groups": [
                  ... (从 scripts/output/<slug>_en/nav-fragment.json 复制 groups 数组)
                ]
              }
            ]
            },
            {
              "product": "Open Platform",
```

**Edit 后立刻验**：
```bash
python3 -c "import json; json.load(open('docs.json')); print('OK')"
grep -c '"<slug>/' docs.json   # 应 == N
```

**绝不动**：zh 块 / ja 块（对齐 mail/im/drive 现状，仅 en）。

### 9. 验收：mint broken-links + mint dev 视觉抽样

```bash
mint broken-links 2>&1 | grep -i <slug>    # drive 相关死链应为空
mint dev                                    # 启 :3000（被占则跳 :3001）
```

浏览器抽样 3 篇（含一篇长文 / 一篇带表/带图 / 一篇 FAQ 风格），确认：
- 顶部 tab 数 = 既有 + 1（按 Drive 后是 6 个）
- 左侧 nav group / page 数与 GROUPS 表一致
- H1 与 frontmatter.title 一致、不重复

## 跑完恢复 checklist

- [ ] `crawl_hub.py:53` `MAX_CJK_RATIO = 0.10`（默认值，若临时调到 0.15 要恢复）
- [ ] `download.py:45` `DOWNLOAD_TIMEOUT_MS = 30_000`（默认值，若临时调到 120_000 要恢复）
- [ ] `git diff .claude/import/dingtalk_downloader/` 应仅含 storage_state.json / manifest.json（这两个在 .gitignore），无 .py 改动

## 提交策略

按 mail/im/drive 历史风格，每阶段独立 commit，**等用户明确授权后才执行**：

1. `feat: 接入 <Product> EN N 篇 + scripts/import_<slug>_en.py + scripts/output/<slug>_en/。to #82317048`
2. `feat: docs.json en Help Center 注册 <Product> tab（第 N tab）。to #82317048`

push / PR 待用户明确发话。

## 命名约定

- **product slug**：全英文 kebab-case，与 docs.json `"<slug>/<page>"` 前缀一致
- **tab 显示名**：与钉钉国际版官网产品名一致（mail/im/drive 都用单词，简洁优先）
- **mdx slug**：源文件 stem 去 `.adoc` 或语义化 kebab-case（drive 把 `What Is DingTalk Drive?` 缩为 `what-is-dingtalk-drive`）
- **不动 zh/ja**：本流程只做 en；反向翻译（en → zh/ja）是未解决问题，需要新 skill `/docs-translate-batch-reverse` 或在原 skill 加 `--source-lang en` 参数

## 相关 memory

- `en-direct-import-route` — 5 步路线总纲
- `dingtalk-doc-export-automation` — 4 个非显然自动化事实（含 CJK 阈值 / DOWNLOAD_TIMEOUT_MS 临时调参经验）
- `alidocs-dentry-list-api` — dentry/list API 调用方式
- `dingtalk-mail-capture-state-20260607` / `dingtalk-im-capture-state-20260612` — mail/im 历史实操状态

## 反模式

- ❌ 用 9 阶段 `/docs-dingtalk-onboard`：那条线假设 zh 源需翻译，重译 en 反损质量
- ❌ 把临时调参（MAX_CJK_RATIO 0.15 / DOWNLOAD_TIMEOUT_MS 120_000）commit 入仓：脚本是给所有产品复用的
- ❌ 在 Claude REPL 里 `! python3 auth_bootstrap.py`：REPL 关 stdin → EOFError
- ❌ `Write` 覆盖整个 docs.json：用 `Edit` 工具精确插入
- ❌ 改 zh/ja 块的 Help Center products：对齐 mail/im/drive 现状仅做 en
