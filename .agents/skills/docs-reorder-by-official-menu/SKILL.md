---
name: docs-reorder-by-official-menu
version: 1.0.0
description: "Reorder the pages array of one or more docs.json groups to match the official alidocs left-side menu order, synced across languages. Handles deeply nested groups and flat leaf pages."
description_zh: "按官方左侧菜单重排 docs.json 顺序：指定 group 的 pages 数组按 alidocs 官方菜单顺序重排，三语同步。"
user-invocable: true
argument-hint: "<group-title> [<group-title> ...]"
---
# 按官方左侧菜单重排 docs.json 顺序

把指定 group（一个或多个）的 `pages` 数组按 alidocs 官方左侧菜单（钉钉文档项目）顺序重排，三语同步（en + zh，ja 暂跳）。

## 适用场景

- 新接入的 group 顺序与官方不一致
- 官方菜单调整后需要重新对齐
- 三/四级嵌套 group + 平铺叶子页面通吃（已验证 13 个 group / 7+ 级深度）

## 参数

- `<group_slug>...`（可选，可传多个）：要新增/重排的 docs.json group slug（如 `doc-ai sheets`）
  - 省略 → 用 `TARGET_GROUPS` 当前清单跑全部（幂等，已对齐的不变）
  - 传 group_slug → 自动定位它在 official menu 的标题前缀并加入 `TARGET_GROUPS`

## 前置资产（仓库已就绪）

| 资产 | 路径 | 来源 |
|---|---|---|
| 官方菜单快照 | `scripts/output/fix/official-menu-full.json` | `scripts/crawl_official_menu.py`（Playwright 爬虫）|
| 重排引擎 | `scripts/fix_post_import.py` 的 `pages` 子命令 | title-based resolver（见 Pitfalls）|

**只在以下情况才重爬**：官方菜单结构变化（标题改名 / 节点增删 / 顺序调整）。重爬命令：

```bash
python3 scripts/crawl_official_menu.py        # 默认 headless
python3 scripts/crawl_official_menu.py --headed  # 调试时显示浏览器
```

## 执行步骤

### 1. 定位目标 group 在 official menu 的标题前缀

```bash
python3 -c "
import json
m = json.load(open('scripts/output/fix/official-menu-full.json'))
for i,it in enumerate(m):
    if it['depth']==1: print(f'{i:3d} {it[\"title\"]}')
"
```

输出形如 `158 d1 9. 钉钉文档` — 前缀就是 `9.`。

### 2. 编辑 `scripts/fix_post_import.py` 的 TARGET_GROUPS

```python
TARGET_GROUPS: list[tuple[str, str]] = [
    # (menu_title_prefix, docs_json_slug)
    ("9.", "dingtalk-docs"),
    ...
    ("5.", "doc-ai"),    # ← 新增行
]
```

顺序无所谓（处理时按 list 顺序），但建议按 menu 前缀排序便于阅读。

### 3. dry-run 检查覆盖率

```bash
python3 scripts/fix_post_import.py pages --dry-run
```

**必须每个 group-lang 行都是 `0 missing, 0 appended-orphan`**。出现非零：

- `missing`：菜单项在 mdx frontmatter 找不到匹配 → 检查 mdx title 是否被改过或缺失
- `appended-orphan`：docs.json 已有的 slug 在新菜单里没出现 → 可能 official-menu 漏爬，或菜单结构变了，需重爬

### 4. 写盘 + 验证

```bash
python3 scripts/fix_post_import.py pages                 # 落盘
python3 -c "import json; json.load(open('docs.json'))"   # JSON 合法
mint broken-links                                         # 死链 0（aitable 预存的不算）
git diff docs.json | grep -oE '"docs/[a-z-]+/' | sort -u  # 仅目标 group 被动
```

**Level 5 浏览器验**（视觉对照）：

```bash
mint dev
# 访问 http://localhost:3000/zh/docs/<group_slug> 与
# https://alidocs.dingtalk.com/i/p/Y7kmbokZp3pgGLq2 左侧菜单对照
```

## 关键陷阱（已踩过的坑）

### Pitfall 1: 别用 docKey-based resolver

`scripts/output/import/link-map-*.json` 是 import 阶段从 MD 内 cross-reference 提取的，**不是 page roster**。某些 group 只能覆盖 9/67，会产生大量 orphan。

✅ 用 title-based resolver（已实现）：扫 `zh/docs/<group>/**/*.mdx` 的 frontmatter `title`，与 official menu 的 `title` 字段匹配。

### Pitfall 2: Unicode 空白

frontmatter title 可能含 NBSP (U+00A0)、ZWSP (U+200B)、全角空格 (U+3000)，菜单用普通空格 → 直接 string 比较会全部 miss（曾在 release-notes 出现 44/45 orphan）。

✅ `_norm_title()` 已统一 normalize 为 `\x20`（已实现）。

### Pitfall 3: 数字前缀

menu 一级标题是 `"10. 钉钉表格"`，但之前 `titles` 子命令把 mdx title 改成了 `"钉钉表格"`（去前缀）。

✅ resolver 有 fallback：精确匹配失败 → 去掉 `^\d+\.\s*` 再匹配（已实现）。

### Pitfall 4: ja 块暂时跳过

CLAUDE.md 约定本期不在 docs.json 加 ja 块。`cmd_pages` 内部 `if lang == "ja": continue`，不要去掉。

### Pitfall 5: 不要 Write 覆盖 docs.json

虽然 `cmd_pages` 内部用 `json.dump`（已是规则的合规例外，因为整文件结构化重写），但**永远不要在 skill 流程外用 Write 整个改 docs.json**。手工微调用 SearchReplace 精确替换。

## 失败回滚

```bash
git checkout -- docs.json
git checkout -- scripts/fix_post_import.py  # 撤销 TARGET_GROUPS 改动
```

## 与 commit-flow 协作

重排完不要自动 commit。让用户后续 `/commit-flow` 一并提交（commit message 例：`docs: <group> 按官方左侧菜单重排子页面顺序。to #82317048`）。
