# AI Table Glossary — 术语表（中英对照）

> 翻译过程中保持一致性的核心术语表。新增 group 翻译时优先复用，新术语首次出现请追加到此处。

## 品牌 / 产品名（不翻译）

| 中文 | 英文 |
|---|---|
| 钉钉 | DingTalk |
| AI 表格 / AI表格 | AI Table |
| AI 助理 | AI Assistant |
| 钉钉文档 | DingTalk Docs |

> 即使中文写作"AI表格"无空格，英文一律统一为 `AI Table`（带空格）。
> 不要写 "Aitable" / "Ai-Table"，会与同名第三方产品（apitable.com）混淆。

## 核心实体 / 数据模型

| 中文 | 英文 | 备注 |
|---|---|---|
| AI 表格（一个文档实例） | AI Table | 顶层文档容器 |
| 数据表 | table | 一个 AI Table 内可包含多张 table |
| 视图 | view | grid view / kanban view 等 |
| 记录 | record | 数据表中的一行 |
| 字段 | field | 数据表中的一列 |
| 单元格 | cell | |
| 仪表盘 | dashboard | |
| 表单 | form | |
| 主字段 | primary field | 第一列，不可删 |
| 子记录 | subrecord | |
| 分组 | grouping | 名词；动作用 group |
| 筛选 | filter | |
| 排序 | sort | |
| 冻结列 | freeze column | |
| 文件夹 | folder | |
| 附件 | attachment | |
| 模板中心 | template center | |

## 字段类型（与产品 UI 一致）

| 中文 | 英文 |
|---|---|
| 文本 | Text |
| 数字 | Number |
| 单选 | Single Select |
| 多选 | Multiple Select |
| 日期 | Date |
| 人员 | Member |
| 附件 | Attachment |
| 复选框 | Checkbox |
| 评分 | Rating |
| 进度 | Progress |
| 货币 | Currency |
| 百分比 | Percent |
| 电话 | Phone |
| 邮箱 | Email |
| 链接 | URL |
| 公式 | Formula |
| 创建人 / 创建时间 | Created By / Created Time |
| 修改人 / 修改时间 | Last Modified By / Last Modified Time |
| 自动编号 | Auto Number |
| 单向关联 | One-Way Link |
| 双向关联 | Two-Way Link |
| 查找引用 | Lookup |
| 关联引用 | Linked Reference |
| 按钮 | Button |
| 工作流 | Workflow |
| AI 字段 | AI Field |

## 视图类型

| 中文 | 英文 |
|---|---|
| 表格视图 | Grid view |
| 看板视图 | Kanban view |
| 甘特图视图 | Gantt view |
| 日历视图 | Calendar view |
| 画册视图 | Gallery view |
| 数据透视表视图 | Pivot view |
| 表单视图 | Form view |
| 查询页面 | Query page |
| 打印视图 | Print layout |

## 功能模块（一级导航）

| 中文 | 英文 |
|---|---|
| 数据 | Data |
| 自动化 | Automation |
| 应用 | App |
| 表单 | Form |

## 操作动作

| 中文 | 英文 |
|---|---|
| 新建 / 添加 | Create / Add |
| 重命名 | Rename |
| 复制 | Duplicate（结构）/ Copy（数据） |
| 移动 | Move |
| 删除 | Delete |
| 编辑描述 | Edit description |
| 导入 | Import |
| 导出 | Export |
| 分享 | Share |
| 邀请协作者 | Invite collaborators |
| 一键启用 | Use this template / Apply with one click |
| 保存为模板 | Save as template |
| 发布到模板中心 | Publish to template center |
| 撤销 / 重做 | Undo / Redo |
| 全选 | Select all |
| 查找 | Find |
| 评论 | Comment |

## 权限 / 协作

| 中文 | 英文 |
|---|---|
| 高级权限 | Advanced Permissions |
| 角色 | role |
| 协作者 | collaborator |
| 仅协作者可见 | Collaborators only |
| 企业内公开 | Public within organization |
| 互联网公开 | Public on the internet |
| 链接分享 | Share via link |
| 二维码分享 | Share via QR code |

## 自动化 / AI

| 中文 | 英文 |
|---|---|
| 自动化工作流 | automation workflow |
| 触发器 | trigger |
| 动作 | action |
| 循环节点 | loop node |
| 条件自动化 | conditional automation |
| 按钮自动化 | button automation |
| AI 字段 | AI field |
| AI 字段模板 | AI field template |
| Webhook | webhook |

## 数据集成

| 中文 | 英文 |
|---|---|
| 数据连接器 | data connector |
| 跨表同步 | cross-table sync |
| 钉钉考勤同步 | DingTalk attendance sync |
| 钉钉日程同步 | DingTalk calendar sync |
| 钉钉通讯录同步 | DingTalk contacts sync |
| 钉钉审批同步 | DingTalk approval sync |
| 钉钉电子表格同步 | DingTalk Spreadsheet sync |
| 钉钉待办同步 | DingTalk Todo sync |

## 套餐 / 版本

| 中文 | 英文 |
|---|---|
| 免费版 | Free plan |
| 企业版 | Business plan |
| 旗舰版 | Enterprise plan |

## 风格指南

- **美式英语**（color 不写 colour，realize 不写 realise）
- **句式**：直陈、命令式（"Click...", "Select..."），不用敬语堆砌
- **标题**：sentence case（仅首字母大写 + 专有名词大写），不用 Title Case：✅ "Create a new view" ❌ "Create A New View"
- **数字**：英文文档用阿拉伯数字 + 阿拉伯式千分位（10,000 而非 10000）
- **代码 / 快捷键**：保留中文版的反引号格式（`` `Ctrl` + `/` ``）
- **跨页链接**：相对路径 `/aitable/...`；指向尚未翻译的页时，链向中文 `/zh/aitable/...` 兜底（试点期间临时方案）
- **品牌口径**：DingTalk（不翻译为 Ding Talk / 钉钉），AI Table（统一首字母 + 空格）
