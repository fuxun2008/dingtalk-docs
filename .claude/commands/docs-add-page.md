---
description: 添加新文档页：定位到指定产品 tab，三语 MDX 占位 + docs.json 三处 navigation 同步 + 链接校验
---

# Docs Add Page — 文档页一键新增

为 `dingtalk-docs` 添加一个新页面，自动维护三语镜像和 docs.json 三处 navigation 一致性。

## 参数

- `product`：产品 slug，必须是 `docs.json` 已存在的 tab 之一：
  - `overview` — 默认 tab（页面落在仓库根，**不加路径前缀**）
  - `aitable` — AI Table 产品（路径前缀 `aitable/`）
  - `docs` — DingTalk Docs 产品（路径前缀 `docs/`）
  - 未来新增产品同理（先在 docs.json 加 tab，再用本 skill）
- `slug`：相对于产品的路径（不含扩展名），例如 `quick-start` 或 `guides/messaging`
- `group`：page 所属的**英文 group 名**（必须已存在于 `docs.json` 对应 tab 下），例如 `Introduction` 或 `Guides`

调用示例：
- `/docs-add-page overview guides/messaging Guides`
- `/docs-add-page aitable quick-start Introduction`
- `/docs-add-page docs collaboration Introduction`

## 路径规则

| product | 英文路径 | 中文路径 | 日文路径 |
|---|---|---|---|
| `overview` | `<slug>.mdx` | `zh/<slug>.mdx` | `ja/<slug>.mdx` |
| `aitable` | `aitable/<slug>.mdx` | `zh/aitable/<slug>.mdx` | `ja/aitable/<slug>.mdx` |
| `docs` | `docs/<slug>.mdx` | `zh/docs/<slug>.mdx` | `ja/docs/<slug>.mdx` |
| 其他 | `<product>/<slug>.mdx` | `zh/<product>/<slug>.mdx` | `ja/<product>/<slug>.mdx` |

## 步骤

1. **校验参数**
   - 缺参数 → 停下询问
   - 读 `docs.json`，确认 `navigation.languages[language=en].tabs[*].tab` 里有匹配的产品 tab：
     - `overview` → tab 名为 `Overview`
     - `aitable` → tab 名为 `AI Table`
     - `docs` → tab 名为 `DingTalk Docs`
     - 其他 → 列出已存在 tabs 让用户选；或确认新建（新建 tab 不在本 skill 范围，让用户先手动加）
   - 在目标 tab 下检查 `groups[*].group === <group>` 是否存在；不存在则停下询问"是否新建该 group"

2. **检查文件是否已存在**
   按上面"路径规则"表算出三语路径，然后：
   ```bash
   ls <en-path> <zh-path> <ja-path> 2>/dev/null
   ```
   任一已存在 → 停下警告，避免覆盖用户内容

3. **生成三语 MDX 占位**
   分别写入三语路径，目录不存在用 `mkdir -p` 创建：
   ```mdx
   ---
   title: "<根据 slug 推断的英文标题>"
   description: "<TODO: one-line description>"
   ---

   <!-- TODO: write content for this page -->
   ```
   中文/日文版本 title/description 暂时同英文，标 TODO，留给 [[docs-translate]] skill 处理

4. **更新 docs.json 三处 navigation**
   读 `docs.json`，在三个 language 块（`en` / `zh` / `ja`）的对应 tab → 对应 group 下 `pages` 末尾追加：
   - en tab 内：`"<en-page-path>"`（不含 .mdx 扩展名）
   - zh tab 内：`"zh/<...>"` 同理
   - ja tab 内：`"ja/<...>"` 同理

   **tabs 按位置匹配**：假设三语 `tabs[]` 数组同序（en[N] = zh[N] = ja[N] 是同一个产品）。
   **groups 按 group 名匹配**：找到 group 名等于 `<group>` 在英文里对应位置的索引，三语用同索引（因为三语 groups 数组也应同序）。
   用 Edit 工具精确插入，不要重写整个 JSON。

5. **跑死链检查**
   ```bash
   mint broken-links
   ```
   有问题 → 报告给用户，不自动改

6. **报告产物**
   列出新增的 3 个 mdx + 修改的 docs.json，提示用户填充内容

## 约定
- slug 路径段用 kebab-case，**保持英文**，不含语言前缀
- product slug 也保持英文（与 tab 显示名解耦，tab 名可翻译，slug 永远英文）
- group 名严格按 docs.json en 块的写法（中文/日文 group 名会自然翻译，但 pages 路径段保持英文）
- 跨产品不要互链（让用户用顶部 tab 切换）
- 见 [[project-docs-i18n-convention]]
