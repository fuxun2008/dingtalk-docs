# docs.json 三语 navigation 安全编辑器

> 子 skill：被 [[docs-add-page]] 调用做原子操作（`add-page`）；也作为新增 product / group / 三语注册的入口

把 `docs.json`（2612 行单文件 + 三语 navigation 严格同序）的编辑从"手工 Edit 易破坏顺序 / 误删兄弟 product"压成原子化命令。**强制只用 Edit 工具精确字符串替换，绝对禁止 Write 整份覆盖**（历史踩坑：Write 一次毁掉作者风格 + 误删 2 个产品 tab）。

## 适用场景

- 新接入产品 → `add-product`（三语同步插一个新 tab）
- 已有产品新增 group → `add-group`（三语同步插一个 group）
- 单页新增 → `add-page`（被 `/docs-add-page` 调用，也可手动调）
- 重排 group 内页面顺序 → `reorder`（按官方左侧菜单）
- 健康检查 → `verify`（三语 tabs[]/groups[] 同序性 + pages 路径前缀正确性）

## 参数

通用：
- `<action>`（必填）：`add-product` / `add-group` / `add-page` / `reorder` / `verify`

各 action 自有参数：

| action | 参数 |
|---|---|
| `add-product` | `<slug>` `--name-en "..."` `--name-zh "..."` `--name-ja "..."` |
| `add-group` | `<product> <group-zh-name>` `--name-en "..."` `--name-ja "..."` `[--after <existing-group-zh>]` |
| `add-page` | `<product> <group-zh> <page-slug>` |
| `reorder` | `<product> <group-zh>` `--official-menu <path>` |
| `verify` | （无参数）|

## 执行流程（按 action 分支）

### 通用前置（所有 action）

```bash
test -f docs.json
git status -s docs.json | head     # 注意如脏，提示用户先 stash 或 commit
python3 -c "import json; json.load(open('docs.json'))"  # JSON 合法基线
```

### action: `verify`（最常用，先跑这个看健康度）

```python
import json
d = json.load(open('docs.json'))
langs = d['navigation']['languages']
# 1. 三语 tabs 数量 + 顺序
counts = {l['language']: len(l['tabs']) for l in langs}
assert counts['en'] == counts['zh'] == counts['ja'], f'tabs 数量不同步：{counts}'
# 2. 每 tab 的 groups 数量
for i in range(counts['en']):
    g_counts = {l['language']: len(l['tabs'][i].get('groups', [])) for l in langs}
    assert len(set(g_counts.values())) == 1, f'tab[{i}] groups 数量不同步：{g_counts}'
# 3. pages 路径前缀
for lang_block in langs:
    prefix = '' if lang_block['language'] == 'en' else lang_block['language'] + '/'
    # 递归扫所有 pages 字符串，检查前缀
    ...
```

输出：

```
✓ 三语 navigation 健康度：
  - tabs: en=N, zh=N, ja=N（同步 ✓）
  - 每 tab groups 数量同步 ✓
  - pages 路径前缀正确 ✓
  - 任一不符 → 报具体 tab[i].groups[j] 位置 + 修复建议
```

### action: `add-product <slug>`

1. **检查冲突**：三语 tabs[] 任一已含 `<slug>` 对应 tab → 停下报告
2. **三语目录建立**：
   ```bash
   mkdir -p zh/<slug>/ <slug>/ ja/<slug>/
   ```
3. **建三语 index.mdx**（frontmatter only）：
   ```
   zh/<slug>/index.mdx  → title "<name-zh>" / description "..."
   <slug>/index.mdx     → title "<name-en>" / description "..."
   ja/<slug>/index.mdx  → title "<name-ja>" / description "..."
   ```
4. **Edit `docs.json` 三处**：在三语 `tabs[]` **末尾追加**（不要插中间）新 tab 对象：
   ```jsonc
   { "tab": "<name-{lang}>", "groups": [
       { "group": "Overview", "pages": ["<prefix><slug>/index"] }
   ]}
   ```
5. **验证**：`mint broken-links` + `verify` action

**关键陷阱**：
- product slug 永远英文，三语共享
- tab 显示名按语言译，但 AI Table 这种品牌词在三语都保持英文（参考 `register_ja_docs_navigation.py` 的 `TAB_NAME_MAP`）

### action: `add-group <product> <group-zh>`

1. **检查冲突**：三语对应 product tab 的 `groups[]` 任一已含同名 group → 停下报告
2. **翻译查表**：
   - en：从 `--name-en` 取，缺则停下问
   - ja：从 `--name-ja` 取；缺则查内置 `GROUP_NAME_MAP_JA`（见下）；都未命中停下问
3. **Edit `docs.json` 三处**：在三语对应 tab 的 `groups[]` **末尾追加**（除非 `--after <existing-group>` 指定插入位置）新 group 对象：
   ```jsonc
   { "group": "<name-{lang}>", "pages": [] }
   ```
4. **验证**：`mint broken-links` + `verify` action

### action: `add-page <product> <group-zh> <page-slug>`

被 `/docs-add-page` 调用为原子操作（在 docs.json 三处同步插入 page 路径）。**独立调用时也可用，但更推荐走 `/docs-add-page`**（后者会同时建 mdx）。

操作：
1. 三语对应 group 的 `pages[]` **同位置**追加 `"<prefix><product>/<group-slug>/<page-slug>"`
2. JSON 合法验证

### action: `reorder <product> <group-zh>`

1. 读 `--official-menu <path>` 给的"权威顺序"（如来自 `scripts/crawl_official_menu.py` 抓的钉钉官方左侧菜单 JSON）
2. 把三语 `pages[]` 按权威顺序重排（注意只改顺序、不增删）
3. **本 action 本质是 [[docs-reorder-by-official-menu]] 子 skill 的薄壳**——优先走那个独立 skill，本 action 仅作为整合入口

### 内置 GROUP_NAME_MAP_JA（中→日翻译表）

继承自 `scripts/register_ja_docs_navigation.py`（一次性脚本）的 60+ 条积累。**未命中时停下问用户**，不擅自机器译。

```python
GROUP_NAME_MAP_JA = {
    # 文档 tab — 一级
    "新手指南": "はじめに", "快速上手": "クイックスタート", "功能更新": "リリースノート",
    "管理员指引": "管理者ガイド", "文档 AI": "ドキュメント AI", "客户案例": "導入事例",
    "最佳实践": "ベストプラクティス", "进阶玩法": "高度な使い方",
    "钉钉文档": "DingTalk Docs", "钉钉表格": "DingTalk Spreadsheet",
    "钉钉脑图": "DingTalk Mind", "钉钉白板": "DingTalk Whiteboard",
    "知识库": "ナレッジベース", "知识小组": "ナレッジグループ", "模板中心": "テンプレートセンター",
    # 文档 AI 子组
    "入门必读": "入門ガイド", "知识库问答助理": "ナレッジベース QA アシスタント",
    "进阶使用": "高度な使い方", "场景实践": "ユースケース", "更多智能应用": "その他のスマート機能",
    # 最佳实践 子组
    "客户实践": "お客様事例", "行业实践": "業界別事例", "角色实践": "職種別事例",
    # 钉钉文档 子组
    "插入内容": "コンテンツの挿入", "插入 OKR": "OKR を挿入", "协作互动": "コラボレーション",
    "关联钉钉": "DingTalk 連携", "样式排版": "スタイルとレイアウト",
    "快捷键输入": "ショートカット入力", "打印和导出": "印刷とエクスポート",
    "使用设置": "設定", "常见问题": "よくある質問",
    # 钉钉表格 子组
    "编辑": "編集", "格式": "書式", "公式与函数": "数式と関数", "视图": "ビュー",
    "智能工具": "スマートツール", "导出和另存为模板": "エクスポートとテンプレート保存",
    # 钉钉脑图 子组
    "基础功能": "基本機能", "插入附件": "添付ファイルの挿入",
    "协作与分享": "コラボレーションと共有", "其他功能": "その他の機能",
    # AI 表格 tab — 一级
    "从这里开始": "はじめに", "AI 表格基础操作": "AI Table 基本操作",
    "使用字段": "フィールドの使い方", "使用表单": "フォームの使い方",
    "使用视图": "ビューの使い方", "使用仪表盘": "ダッシュボードの使い方",
    "自动化工作流": "自動化ワークフロー", "更多": "その他",
    "应用模式": "利用モード", "公式函数": "数式と関数",
    "高级权限": "高度な権限", "插件中心": "プラグインセンター",
    # AI 表格 子组
    "字段类型列表": "フィールドタイプ一覧", "仪表盘组件": "ダッシュボードコンポーネント",
    "使用函数": "関数の使い方", "函数实践": "関数の活用例",
    "AI表格插件中心-使用指南": "AI Table プラグインセンター — 使い方ガイド",
    "网页采集助手-插件介绍和安装指南": "ウェブクリッパー — プラグインの紹介とインストールガイド",
}

TAB_NAME_MAP_JA = {
    "文档": "ドキュメント",
    "AI 表格": "AI Table",
}
```

**新产品扩展**：第一次给新产品（如 `calendar` / `meeting`）跑 `add-group` 时，要求用户提供完整中→日翻译表（一次性整理），跑完更新本 skill 文件的 `GROUP_NAME_MAP_JA`。

## 关键陷阱（已踩过）

### 陷阱 1：绝不 Write 整份 `docs.json`

**最严重历史踩坑**：用 Write 整份覆盖一次，毁掉作者风格 + 误删 2 个产品 tab，回滚后才发现。**本 skill 强制只用 Edit 工具精确字符串替换**，每个 language 块单独 Edit，三个 Edit 调用串联。

### 陷阱 2：三语严格同位置

- tabs[0]_en = tabs[0]_zh = tabs[0]_ja，同位置必须指向同一产品
- 一个 product tab 内的 groups[i] 三语对齐
- 一个 group 内的 pages[j] 三语对齐
- 任何插入都要"三语同位置"，不可错位
- `verify` action 会扫这三层同步性

### 陷阱 3：tab 显示名 vs slug 解耦

- product slug：永远英文 kebab-case（`docs` / `aitable`），路径 `/<slug>` 三语共用
- tab 显示名：按语言译（`Docs` / `文档` / `ドキュメント`）
- 不要给日文版改 slug

### 陷阱 4：未命中翻译表停下问

`GROUP_NAME_MAP_JA` 未覆盖的 group 名 → **停下让用户给翻译**，不擅自机器译。一旦机器译错入库，后续要修三语 + 文件路径全套，代价高。

### 陷阱 5：`reorder` action 是薄壳

真正的重排逻辑在 [[docs-reorder-by-official-menu]] skill。本 action 仅作为整合入口（统一 `/docs-nav-edit` 命令面），实际执行还是走那个独立 skill。

## 与其他 skill 的协作

- `/docs-add-page` — 调用本 skill 的 `add-page` 做 docs.json 三处同步
- `/docs-reorder-by-official-menu` — `reorder` action 转发到它
- `/docs-dingtalk-onboard` 阶段 9a — 新产品三语 navigation 注册的实际工具
- `/docs-preview` — nav 改完用本 skill 视觉验证左侧菜单
- `/commit-flow` — 通过后用户授权提交（aoneId `82317048`）

**不自动 commit / push**（按 user memory `feedback_commit_authorization.md`）。
