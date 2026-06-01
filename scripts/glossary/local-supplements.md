# AI Table 本地补充词库

> 本文件只收录**官方词库（`official/`）未覆盖**的 AI Table 专项术语，作为翻译时的补充约束。
>
> 维护规则：
> 1. **官方优先**：合并时官方词库覆盖本文件。如果某条术语已被官方收录，请从本文件删除（避免维护两份）。
> 2. **格式**：表格三列 `| 中文 | 英文 | 日文 |`（备注列可选，但只用于第 4 列起，解析时忽略）。
> 3. **多形式 zh**：用 `/` 分隔，例如 `AI 表格 / AI表格`，解析时拆为两个 key 共享同一英文/日文。
> 4. **风格指南**：见文末"风格指南"小节，不要改路径，会被翻译 skill 引用。
>
> 命令：`python3 scripts/glossary_sync.py` 重新合并并生成 `scripts/glossary/zh-en.json` 与 `zh-ja.json`。

## 品牌 / 产品实例

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| AI 表格（一个文档实例） | AI Table | AI Table | 顶层文档容器，与品牌名同形 |

## 核心实体

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 子记录 | subrecord | サブレコード | |
| 冻结列 | freeze column | 列を固定 | |

## 字段类型（AI Table 特有 / 与官方歧义时取此处）

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 日期 | Date | 日付 | AI Table 字段类型语境 |
| 复选框 | Checkbox | チェックボックス | |
| 百分比 | Percent | パーセント | |
| 电话 | Phone | 電話番号 | AI Table 字段类型语境 |
| 按钮 | Button | ボタン | AI Table 字段类型 |
| 修改人 | Last Modified By | 最終更新者 | 字段类型 |

## 视图类型（AI Table）

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 甘特图视图 | Gantt view | ガントチャートビュー | |
| 数据透视表视图 | Pivot view | ピボットビュー | |
| 查询页面 | Query page | クエリページ | |
| 打印视图 | Print layout | 印刷レイアウト | |

## 功能模块（AI Table 一级导航）

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 数据 | Data | データ | AI Table 一级导航语境 |

## 操作动作（AI Table）

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 重命名 | Rename | 名前を変更 | |
| 移动 | Move | 移動 | |
| 编辑描述 | Edit description | 説明を編集 | |
| 邀请协作者 | Invite collaborators | コラボレーターを招待 | |
| 一键启用 | Use this template | このテンプレートを使用 | |
| 保存为模板 | Save as template | テンプレートとして保存 | |
| 发布到模板中心 | Publish to template center | テンプレートセンターに公開 | |
| 全选 | Select all | すべて選択 | |
| 动作 | action | アクション | 自动化语境 |

## 权限 / 协作

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 仅协作者可见 | Collaborators only | コラボレーターのみ | |
| 企业内公开 | Public within organization | 組織内に公開 | |
| 互联网公开 | Public on the internet | インターネットに公開 | |
| 链接分享 | Share via link | リンクで共有 | |
| 二维码分享 | Share via QR code | QRコードで共有 | |

## 自动化 / AI

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 自动化工作流 | automation workflow | 自動化ワークフロー | |
| 循环节点 | loop node | ループノード | |
| 条件自动化 | conditional automation | 条件付き自動化 | |
| 按钮自动化 | button automation | ボタン自動化 | |
| AI 字段模板 | AI field template | AIフィールドテンプレート | |

## 数据集成

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 数据连接器 | data connector | データコネクタ | |
| 跨表同步 | cross-table sync | テーブル間同期 | |
| 钉钉考勤同步 | DingTalk attendance sync | DingTalk 勤怠同期 | |
| 钉钉日程同步 | DingTalk calendar sync | DingTalk カレンダー同期 | |
| 钉钉通讯录同步 | DingTalk contacts sync | DingTalk 連絡先同期 | |
| 钉钉审批同步 | DingTalk approval sync | DingTalk 承認同期 | |
| 钉钉电子表格同步 | DingTalk Spreadsheet sync | DingTalk Spreadsheet 同期 | |
| 钉钉待办同步 | DingTalk Todo sync | DingTalk Todo 同期 | |

## 套餐 / 版本

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 免费版 | Free plan | Freeプラン | |
| 企业版 | Business plan | Businessプラン | |
| 旗舰版 | Enterprise plan | Enterpriseプラン | |

---

## 风格指南（被翻译 skill 引用）

### 英文

- **美式英语**（color 不写 colour，realize 不写 realise）
- **句式**：直陈、命令式（"Click...", "Select..."），不用敬语堆砌
- **标题**：sentence case（仅首字母大写 + 专有名词大写），不用 Title Case：✅ "Create a new view" ❌ "Create A New View"
- **数字**：用阿拉伯数字 + 千分位（10,000 而非 10000）
- **代码 / 快捷键**：保留反引号格式（`` `Ctrl` + `/` ``）

### 日文

- **句末**：用「である」体或敬体「です・ます」均可，**整篇统一**，不要混用
- **标题**：体言止め（名词结尾），不用动词收尾
- **括号**：用全角「」『』 而非 ""，半角英文术语前后留半角空格
- **数字**：阿拉伯数字 + 半角逗号千分位
- **数据库 / 表格通用术语**：业界惯用译法优先（view → ビュー、record → レコード、field → フィールド、dashboard → ダッシュボード、form → フォーム、filter → フィルター、template → テンプレート）

### 品牌口径（强约束，三语共通）

- **DingTalk**：不翻译为 Ding Talk / 钉钉
- **AI Table**：统一首字母 + 空格；不写 Aitable / Ai-Table（避免与第三方 apitable.com 混淆）
- **AI Assistant** / **DingTalk Docs**：保持原样

### 跨页链接

- 内部链接用相对路径 `/aitable/...`
- 指向尚未翻译的目标页时，链向中文 `/zh/aitable/...` 作为兜底（试点期间临时方案）
