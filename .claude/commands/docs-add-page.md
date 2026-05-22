---
description: 添加新文档页：三语 MDX 占位 + docs.json 三处 navigation 同步 + 链接校验
---

# Docs Add Page — 文档页一键新增

为 `dingtalk-docs` 添加一个新页面，自动维护三语镜像和 docs.json 三处 navigation 一致性。

## 参数

- `slug`：相对路径（不含扩展名），例如 `guides/messaging`
- `group`：page 所属的英文 group 名（必须已存在于 `docs.json` 的 en language 块里），例如 `Guides`

调用示例：`/docs-add-page guides/messaging Guides`

## 步骤

1. **校验参数**
   - 如果用户没传完整参数，停下来询问
   - 检查 `docs.json` 中 `navigation.languages[language=en].groups[*].group === <group>` 是否存在；不存在则停下询问"是否新建该 group"

2. **检查文件是否已存在**
   ```bash
   ls <slug>.mdx zh/<slug>.mdx ja/<slug>.mdx 2>/dev/null
   ```
   任一已存在 → 停下警告，避免覆盖用户内容

3. **生成三语 MDX 占位**
   分别写入 `<slug>.mdx`、`zh/<slug>.mdx`、`ja/<slug>.mdx`，目录不存在用 `mkdir -p` 创建：
   ```mdx
   ---
   title: "<根据 slug 推断的英文标题>"
   description: "<TODO: one-line description>"
   ---

   <!-- TODO: write content for this page -->
   ```
   中文/日文版本 title/description 暂时同英文，标 TODO，留给 [[docs-translate]] skill 处理

4. **更新 docs.json 三处 navigation**
   读 `docs.json`，在三个 language 块（`en` / `zh` / `ja`）的对应 group（按位置匹配，假设三语 groups 数组同序）下 `pages` 末尾追加：
   - en: `"<slug>"`
   - zh: `"zh/<slug>"`
   - ja: `"ja/<slug>"`
   用 Edit 工具精确插入，不要重写整个 JSON

5. **跑死链检查**
   ```bash
   mint broken-links
   ```
   有问题 → 报告给用户，不自动改

6. **报告产物**
   列出新增的 3 个 mdx + 修改的 docs.json，提示用户填充内容

## 约定
- slug 路径用 kebab-case，不含语言前缀
- group 名严格按 docs.json en 块的写法（中文版/日文版的 group 名会自然翻译，但 pages 路径段保持英文）
- 见 [[project-docs-i18n-convention]]
