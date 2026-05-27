# AI Table 源端缺图清单 (Source-Missing Images)

本文档记录 wolai 源端导出时丢失的图片引用。这些图片在原始导出语料 (`/Users/yanxin/github/dingtalk_ai_table`) 的对应 `image/` 目录中**不存在**，因此 mdx 引用了但实际拷贝时无文件。

**总计**: 85 unique 缺图引用，分布于 11 个章节。

## 已知 wolai 数据损失模式

- `*.png.mark.png`: 标注后文件的二次后缀，源端只保留了未标注版（去掉 `.mark.png` 后缀通常能找到原图，但 mdx 引用走的是带后缀路径）
- `*.gif` 中含截屏自动命名（如 `DingTalk录屏_xxxx_xxx.gif`）：录屏文件命名超长导致写盘失败
- URL 编码截断（如 `%E9%92%89%E9%92%89%E5%BD%95%E5%B1%8F_2025-03-18_Fn`）：wolai 编辑器粘贴时路径截断

## 处置

- mdx 中保留原引用，浏览器将显示 404 占位
- 后续可由产品/运营同学按章节人工补图（找作者重传 / 截图替换）
- 不影响其他功能：所有内部链接、非缺图引用均正常

## 按章节明细

### ai-assistant (2)

- `AI 表格“万能贴”使用说明/AI 表格“万能贴”使用说明` → `image/image__EGkvii-ep.png.mark.png`
- `AI 表格“万能贴”使用说明/AI 表格“万能贴”使用说明` → `image/image_UbDCcXP3Go.png.mark.png`

### application-mode (28)

- `视图组件/视图组件` → `image/image_7wS8ekkXC1.png.mark.png`
- `按钮/按钮` → `image/image_AjsZC8OGj3.png.mark.png`
- `视图组件/视图组件` → `image/image_b06h8Y7lfQ.png.mark.png`
- `过滤器/过滤器` → `image/image_DMeLs4q8T3.png.mark.png`
- `视图组件/视图组件` → `image/image_Ez5oIL5b_w.png.mark.png`
- `过滤器/过滤器` → `image/image_FBCN1yEwNs.png.mark.png`
- `过滤器/过滤器` → `image/image_fT7mnasLGy.png.mark.png`
- `过滤器/过滤器` → `image/image_fzc_EW9KoE.png.mark.png`
- `过滤器/过滤器` → `image/image_GfF5oNSfKg.png.mark.png`
- `过滤器/过滤器` → `image/image_huSXhDwo9v.png.mark.png`
- `视图组件/视图组件` → `image/image_ICzerJsEDo.png.mark.png`
- `按钮/按钮` → `image/image_lJUCBbec3b.png.mark.png`
- `按钮/按钮` → `image/image_lPuHUxoI6z.png.mark.png`
- `视图组件/视图组件` → `image/image_meuJZjYnB8.png.mark.png`
- `全新应用模式/全新应用模式` → `image/image_n376DF5FOp.png.mark.png`
- `视图组件/视图组件` → `image/image_oTZmEMa9v4.png.mark.png`
- `按钮/按钮` → `image/image_OY8N8g-OF-.png.mark.png`
- `视图组件/视图组件` → `image/image_qJdKy6f6t3.png.mark.png`
- `全新应用模式/全新应用模式` → `image/image_Qp0ETJd22y.png.mark.png`
- `全新应用模式/全新应用模式` → `image/image_Qv8aBdgcSW.png.mark.png`
- `按钮/按钮` → `image/image_Rok8KZWroq.png.mark.png`
- `过滤器/过滤器` → `image/image_shQbYkNcyj.png.mark.png`
- `按钮/按钮` → `image/image_WGDqpGFAL-.png.mark.png`
- `过滤器/过滤器` → `image/image_Wi7IsYc784.png.mark.png`
- `视图组件/视图组件` → `image/image_XzDyD5Wf_H.png.mark.png`
- `过滤器/过滤器` → `image/image_yLx-R56Lp6.png.mark.png`
- `过滤器/过滤器` → `image/image_ysDi0ymXqM.png.mark.png`
- `视图组件/视图组件` → `image/image_ZrKEbLCEJw.png.mark.png`

### automation (6)

- `自动化更多「执行动作」使用指南/钉钉会议室节点-使用指南/钉钉会议室节点-使用指南` → `image/%E6%88%AA%E5%B1%8F2025-08-24_GV3F5QBt_W`
- `自动化更多「执行动作」使用指南/钉钉会议室节点-使用指南/钉钉会议室节点-使用指南` → `image/0144590f-0d89-48e3-a777-f0c95b64eb03_-ktIxz586Z.png.mark.png`
- `自动化更多「执行动作」使用指南/钉钉会议室节点-使用指南/钉钉会议室节点-使用指南` → `image/251fb9de-4c39-4fbf-9aab-35d4721ce98d_3PIGdTDzB_.png.mark.png`
- `自动化更多「执行动作」使用指南/钉钉会议室节点-使用指南/钉钉会议室节点-使用指南` → `image/38ea69df-3fd8-4ba1-9511-05762b0477c7_lv_lWQbNxT.png.mark.png`
- `调用三方工作流应用（coze-百炼）/调用三方工作流应用（coze-百炼）` → `image/%E7%BB%84_jRJ57KqrFs`
- `调用三方工作流应用（coze-百炼）/调用三方工作流应用（coze-百炼）` → `image/%E7%BB%84_RWyrTd32uz`

### dashboards (1)

- `使用 AI表格 仪表盘/使用 AI表格 仪表盘` → `image/2025-09-12_DEgIEOfwM0`

### data-connectors (3)

- `数据连接中心/数据连接中心` → `image/2025-09-17_1y3cSiC21X`
- `钉钉OA审批数据同步/钉钉OA审批数据同步` → `image/2026-01-19_mUAU_x_Lr6`
- `钉钉OA审批数据同步/钉钉OA审批数据同步` → `image/2026-01-19_szRZAfiiks`

### fields (21)

- `字段类型列表/双向关联/双向关联` → `image/%E9%92%89%E9%92%89%E5%BD%95%E5%B1%8F_2025-03-18__f`
- `字段类型列表/双向关联/双向关联` → `image/%E9%92%89%E9%92%89%E5%BD%95%E5%B1%8F_2025-03-18_Fn`
- `字段类型列表/流程/流程` → `image/DingTalk录屏_2025-03-18`
- `字段类型列表/流程/流程` → `image/DingTalk录屏_2025-03-18`
- `字段类型列表/流程/流程` → `image/DingTalk录屏_2025-03-18`
- `字段类型列表/流程/流程` → `image/DingTalk录屏_2025-03-18`
- `字段类型列表/查找引用/查找引用` → `image/DingTalk录屏_2025-03-18`
- `字段类型列表/单向关联/单向关联` → `image/DingTalk录屏_2025-03-18`
- `字段类型列表/单向关联/单向关联` → `image/DingTalk录屏_2025-03-18`
- `字段类型列表/单向关联/单向关联` → `image/DingTalk录屏_2025-03-18`
- `字段类型列表/单向关联/单向关联` → `image/DingTalk录屏_2025-03-18`
- `字段类型列表/双向关联/双向关联` → `image/DingTalk录屏_2025-03-18`
- `字段类型列表/双向关联/双向关联` → `image/DingTalk录屏_2025-03-18`
- `字段类型列表/行政区域/行政区域` → `image/DingTalk录屏_2025-03-19`
- `字段类型列表/行政区域/行政区域` → `image/DingTalk录屏_2025-03-19`
- `字段类型列表/按钮/按钮` → `image/DingTalk录屏_2025-03-21`
- `字段类型列表/手写签名/手写签名` → `image/DingTalk录屏_2025-03-21`
- `字段类型列表/地理位置/地理位置` → `image/DingTalk录屏_2025-03-21`
- `字段类型列表/进度/进度` → `image/DingTalk录屏_2025-03-24`
- `字段类型列表/进度/进度` → `image/DingTalk录屏_2025-03-24`
- `字段类型列表/按钮/按钮` → `image/DingTalk录屏_2025-03-28`

### forms (14)

- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`
- `表单明细表：一次填写，多条提交/表单明细表：一次填写，多条提交` → `image/DingTalk录屏_2025-12-25`

### formulas (5)

- `使用函数/使用 AI表格 DATEDIF函数/使用 AI表格 DATEDIF函数` → `image/DingTalk录屏_2025-04-14`
- `使用函数/使用 AI表格 DATEDIF函数/使用 AI表格 DATEDIF函数` → `image/DingTalk录屏_2025-04-14`
- `使用函数/使用 AI表格 IFERROR函数/使用 AI表格 IFERROR函数` → `image/%E9%98%BF%E9%87%8C%E9%92%89%E5%BD%95%E5%B1%8F_2025`
- `使用函数/使用 AI表格 TEXT函数/使用 AI表格 TEXT函数` → `image/DingTalk录屏_2025-04-14`
- `使用AI生成公式/使用AI生成公式` → `image/DingTalk录屏_2025-04-07`

### getting-started (1)

- `钉钉AI表格快速上手/钉钉AI表格快速上手` → `image/image_9X9ISmyvZS.png.mark.png`

### more (3)

- `自定义仪表盘中心/自定义仪表盘中心` → `image/image_d7qAYNTG0_.png.mark.png`
- `AI 表格“万能贴”优先使用申请/AI 表格“万能贴”优先使用申请` → `image/image_jyUziJHsDM.png.mark.png`
- `AI 表格“万能贴”优先使用申请/AI 表格“万能贴”优先使用申请` → `image/image_v8L_uN3mdi.png.mark.png`

### views (1)

- `查询页面/查询页面` → `image/image_0CdrbBEf_p.png.mark.png`
