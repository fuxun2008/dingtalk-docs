---
description: 以英文母版为模板，在 zh/ 和 ja/ 同路径生成翻译占位（不机翻）
---

# Docs Translate — 翻译占位生成

针对已写好的英文 MDX 母版，在 `zh/` 与 `ja/` 同路径生成翻译占位，结构对齐，待人工/后续翻译。

**重要：本 skill 不调用机翻，只生成结构占位 + TODO 标记。**

## 参数

- `english-mdx-path`：相对仓库根的英文 mdx 文件路径，例如 `guides/messaging.mdx`

调用示例：`/docs-translate guides/messaging.mdx`

## 步骤

1. **校验母版**
   - 路径必须不以 `zh/` 或 `ja/` 开头
   - 文件必须存在
   - 必须含合法 front-matter（title / description）

2. **读母版并解析结构**
   - 提取 front-matter 的 `title` / `description`
   - 保留所有 MDX 组件（`<Card>`、`<CardGroup>`、`<Note>`、`<Tip>` 等）的标签和属性
   - 标题层级 / 列表 / 代码块 全部保留

3. **生成 zh/<path>**
   策略：
   - front-matter：`title: "TODO: 翻译 - <english title>"`、`description: "TODO: 翻译 - <english description>"`
   - 正文段落 / 标题 / 列表 → 替换为 `TODO: translate to zh - <英文原文>` 一行占位
   - MDX 组件结构保留，组件内的文本字段（title / 内容）替换为 `TODO: translate to zh`
   - 代码块、href、图片 src 等**保持原样**
   目录不存在用 `mkdir -p` 创建

4. **生成 ja/<path>**
   同上，把"zh"换成"ja"，"翻译"换成"翻訳"

5. **报告产物**
   列出生成的两个文件路径，提示用户：
   - 翻译完成后，自行替换 `TODO: translate` 占位
   - 如要变更母版结构，记得三处同步

## 注意事项
- 已存在的目标文件 → 询问"覆盖 / 跳过"，不要默认覆盖
- 不要修改母版任何内容
- 不要在占位里编造翻译——必须保留 `TODO:` 标记便于全文搜索

见 [[project-docs-i18n-convention]]
