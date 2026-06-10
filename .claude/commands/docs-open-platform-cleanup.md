# 开放平台开发者文档批量清洗

> 子 skill：开放平台（zh/open/）开发者文档导入后特异性瑕疵批量修复。与 [[docs-audit-mdx]] 互补——后者侧重通用 MDX 渲染瑕疵（`++text++` / 破碎粗体 / 死链），本 skill 专治钉钉开放平台 API 文档形态的 7 类残留。

已在 zh/open/ 416 篇上沉淀验证（2026-06-10，6 commit / 382 篇 / 7 类全清）。

## 适用场景

- 新批"开放平台"文档（API 接口 / SDK 文档 / 概述 / FAQ）从 open.dingtalk.io 迁入 zh/open/ 后
- 周期性体检（API 文档批量更新后扫一遍）
- 通过 [[docs-dingtalk-onboard]] 阶段 6 之后插入运行（开放平台 product 专用）

## 参数

- `--root <name>`（默认 `zh/open`）：根目录限定
- `--lang zh|en|ja`（默认 `zh`）：开放平台目前只 zh 有内容，en/ja 暂不动
- `--apply`（可选）：实际写盘修复（默认 dry-run，先报告再问）
- `--only <类号>`：限定单类，如 `--only E`、`--only A,B,C`
- `--skip <类号>`：跳过某类，如 `--skip H`（H 误报多，可手工后做）

## 7 类瑕疵速查 + 治理策略

### A —"支持与帮助"段 + 钉钉社区二维码外站图（必删）

钉钉文档结尾常自带运营尾巴：

```markdown
## 支持与帮助

如果你在开发过程中遇到了任何问题，可通过扫描下方二维码加入"钉钉开发者社区（互助群）"寻求帮助：

![支持与帮助](https://help-static-aliyun-doc.aliyuncs.com/.../p1071955.png)
```

国际版不该有钉钉国内运营信息，整段删。

```bash
grep -rln "## 支持与帮助" zh/open/
```

### B — URL 内 `&#123;param&#125;` HTML 实体（**包反引号**后还原）

```bash
grep -rln "&#123;\|&#125;" zh/open/
```

钉钉导出 HTTP URL 把路径参数 `{corpId}` `{userId}` `{spaceId}` 的花括号实体化，渲染时显示字面 `&#123;corpId&#125;`。

**⚠️ MDX 陷阱**：直接 `replace_all '&#123;' → '{'` 会让表格 cell 里的裸 `{xxx}` 被 mintlify 当 JSX 表达式解析 →
`Unexpected end of file in expression, expected a corresponding closing brace for {`。

**正确做法**：

```
旧：| HTTP URL | https://api.dingtalk.io/v1.0/oauth2/&#123;corpId&#125;/token |
新：| HTTP URL | `https://api.dingtalk.io/v1.0/oauth2/{corpId}/token` |
```

整 URL 包反引号变 inline code，再还原实体。inline code 内 mintlify 不解析 JSX。

JSON 示例 cell 同理：`{"errcode":0}` 必须包反引号。

### C — `Map&lt;String, Any>` Java SDK 泛型实体（**包反引号**还原）

```bash
grep -rln "&lt;\|&gt;\|&amp;\|&quot;" zh/open/
```

```
旧：| criteria | Map&lt;String, Object> | ...
新：| criteria | `Map<String, Object>` | ...
```

文件名规则段里的特殊字符列表 `&lt;、>、|` 也需包反引号：

```
新：- 不能包含特殊字符，包括：制表符、`*`、`"`、`<`、`>`、`|`
```

### D — `\_` 反斜杠转义（**直接** `replace_all`）

```bash
grep -rln '\\_' zh/open/
```

钉钉对单下划线过度转义（如 `access\_token` / `dept\_id` / `qyapi\_get\_member`）。Markdown 单 `_` 不会触发斜体（需 `_x_` 配对），转义纯属导出器残留。

**安全做法**：每篇 Read 后 `Edit replace_all '\_' → '_'`（zh/open 168 篇验证零边界例外）。

### E — 代码块语言后缀 ` lines`（**白名单脚本批量**）

```bash
grep -rEln '^```[a-z]+ lines' zh/open/
```

钉钉导出代码块语言名后追加字面 ` lines`（如 ` ```java lines` / ` ```python lines`），mintlify highlighter 不识别 → 高亮失效。

**12 种语言白名单**：`java/python/text/go/http/json/php/cpp/curl/bash/javascript/xml/csharp/typescript/html`

**先 P0 阶段逐篇 review 验证无例外，再脚本批量**：

```bash
find zh/open/ -name "*.mdx" -exec perl -i -pe \
  's/^```(java|python|text|go|http|json|php|cpp|curl|bash|javascript|xml|csharp|typescript|html) lines\b/```$1/g' \
  {} \;
```

### F — 段标题语言错配（手工修）

钉钉导出的多语言代码示例段每段段标题下代码块语言名常错配：

| 段标题 | 实际原标 | 应改为 |
|---|---|---|
| `PHP` | ` ```java lines` | ` ```php` |
| `Node.js` | ` ```text lines` | ` ```javascript` |
| `C#` | ` ```java lines` | ` ```csharp` |
| `Go` | ` ```text lines` | ` ```go` |
| `Java` | ` ```text lines` | ` ```java` |
| `HTTP` 响应 | ` ```text lines` | ` ```http` |

每篇 Read 后逐个 Edit 改正。E 类脚本只清后缀，F 类的错配必须手工。

### G — 表格"空表头三明治"

```bash
grep -rEln '^\|( *\|)+ *$' zh/open/
```

钉钉导出器误产空表头行：

```
| | | |          ← 空表头（误产）
| --- | --- | --- |
| 错误码 | 错误码描述 | 解决方案 |   ← 真表头沦为第一数据行
```

**修复**（真表头提前 + 删空头）：

```
| 错误码 | 错误码描述 | 解决方案 |
| --- | --- | --- |
```

**最常见**：错误码表（51/53 篇是 "错误码 / 错误码描述 / 解决方案" 三列）。

### H — 段中无效空粗体 `**。**` / `**，**` / `**.**`

```bash
grep -rEn '\*\*[。，、：；！？\.\,\!\?]+\*\*' zh/open/
```

钉钉编辑器对标点的过度加粗（如 `获取免登授权码**。**` 渲染时显示字面 `**`，因为前面非粗体内容找不到配对 `**` 开始）。

**⚠️ 误报陷阱**：grep 会把 `**类型一**：**用户**` 中的 `**：**` 当命中（实际是两个合法粗体边界），用 PCRE 加 negative lookbehind/lookahead 仍不能完全排除。**必须肉眼判断后再 Edit**。

## 执行流程（5 步）

### 步骤 1 — 全库扫描，给出 7 类命中数报告

```bash
echo "A 支持与帮助: $(grep -rl '## 支持与帮助' zh/open/ | wc -l)"
echo "B &#123;/&#125;: $(grep -rl '&#123;\|&#125;' zh/open/ | wc -l)"
echo "C &lt;/&gt;/&amp;: $(grep -rl '&lt;\|&gt;\|&amp;\|&quot;' zh/open/ | wc -l)"
echo "D \\_: $(grep -rl '\\\\_' zh/open/ | wc -l)"
echo "E lines: $(grep -rEl '^\`\`\`[a-z]+ lines' zh/open/ | wc -l)"
echo "G 空表头: $(grep -rEl '^\|( *\|)+ *\$' zh/open/ | wc -l)"
echo "H 空粗体: $(grep -rEln '\*\*[。，、：；！？.,!?]+\*\*' zh/open/ | wc -l) (含误报)"
```

不传 `--apply` 时停在此步出报告。

### 步骤 2 — P0 样本逐篇 review 验证（5-10 篇）

挑高命中文件先逐篇 Edit，验证模式无边界例外，再决定哪些类可脚本化。

### 步骤 3 — 分批处理（按风险分层）

| 类 | 风险 | 工具 | 节奏 |
|---|---|---|---|
| A | 单点删除 | Edit 删整段 | 一波做完 |
| B | **MDX JSX 陷阱** | 每篇 Edit 包反引号 + 还原 | 分批 15-30 篇一波 |
| C | **MDX 标签陷阱** | 每篇 Edit 包反引号 | 分批一波 |
| D | 安全 | 每篇 `Edit replace_all '\_' → '_'` | 30 篇一波 |
| E | 机械（已 P0 验证） | 脚本批量 perl 一行 | 一次性 |
| F | 上下文判断 | 每篇 Edit 改语言名 | 一篇篇 |
| G | 单点重排 | 每篇 Edit 删空头 + 调换顺序 | 分批 10-15 一波 |
| H | 误报多 | 每篇 Read 肉眼判断 + Edit | 慢做 |

### 步骤 4 — 每批 commit

每批一个 commit，格式（按项目约定带 aoneId）：

```
fix: 开放平台开发者文档 Batch X{类} — N 篇逐篇 review 修复{瑕疵描述}。to #82317048
```

参考已 commit 风格：见 6 个历史 commit（`67c8964` / `05203cf` / `c555afd` / `d8b45ee` / `b436e3e` / `522b3b1`）。

### 步骤 5 — 收尾验收（必跑）

```bash
# 7 类全清验证（应全为 0）
grep -rln "## 支持与帮助" zh/open/ | wc -l
grep -rln "&#123;\|&#125;" zh/open/ | wc -l
grep -rln "&lt;\|&gt;\|&amp;\|&quot;" zh/open/ | wc -l
grep -rln '\\_' zh/open/ | wc -l
grep -rEln '^```[a-z]+ lines' zh/open/ | wc -l
grep -rEln '^\|( *\|)+ *$' zh/open/ | wc -l

# mintlify MDX 解析无错（关键，B/C 阶段最易引入）
mint broken-links 2>&1 | grep -E "Syntax error|Unable to parse"

# 不引入新 broken-links
mint broken-links 2>&1 | grep -E "^zh/open/"
```

任何一条非空 → 回到对应类别继续修。

## 不做

- 不动 en/open/ 和 ja/open/（开放平台英文仅 1 占位 / 日文未注册）
- 不动 docs.json navigation
- 不顺手翻译 / 重排 / 加新页
- 不重写已修过的批次（按 git log 看进度）
- 不跳过 P0 样本验证直接脚本（即使是机械模式，**先 review 再脚本**）

## 与现有 skill 关系

- 与 [[docs-audit-mdx]] **互补不重叠**：audit-mdx 治 `++text++` / 破碎粗体 / 废占位 URL / 死外链；本 skill 治开放平台特有 7 类
- 通用瑕疵清单见 [[reference_dingtalk_export_quirks]]（25+ 类）；本 skill 是其中开放平台子集的实操指南
- 可作为 [[docs-dingtalk-onboard]] 9 阶段流水线在阶段 6（MDX 审计）之后插入运行

## 历史战果（基准）

- **2026-06-10 zh/open 批次 1**：6 commit / 382 篇独立修复 / 7 类全清
  - Batch 1 P0：10 篇用户列名 + 1 篇 "支持与帮助"
  - Batch 2 H+G：52 篇空表头 + 空粗体
  - Batch 3 D：169 篇 `\_` 全量还原
  - Batch 3 B-URL：158 篇 URL 实体包反引号
  - Batch 3 B+C 杂项：65 篇 JSON cell / Java 泛型
  - Batch 4 E：347 篇 ` lines` 后缀脚本清（2492 行）
