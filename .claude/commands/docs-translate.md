# 文档翻译（带词库强约束）

把一篇英文 mdx 母版翻译成中文 / 日文版本，自动注入项目词库作为术语强约束。

## 适用场景

- 新增一篇英文 mdx 后，需要为 `zh/` 和 `ja/` 镜像生成对应翻译
- 已有翻译文件需要按最新词库重新审校

## 参数

- `<source-path>`：源文件 mdx 路径（必填）。可以是 en（仓库根）、zh（`zh/`）、或 ja（`ja/`）下的任意 mdx
- `--targets <zh,ja>`（可选，默认根据 source 推断："en 源 → zh,ja"；"zh 源 → en,ja"；"ja 源 → en,zh"）
- `--no-write`（可选）：只输出翻译草稿到 stdout，不写文件

## 执行步骤

1. **读源文件**：解析 frontmatter（`title` + `description`）和正文
2. **加载词库**：
   - `scripts/glossary/zh-en.json`
   - `scripts/glossary/zh-ja.json`
   - `scripts/glossary/local-supplements.md` 末尾的"风格指南"段（按目标语言抽取对应小节）
3. **命中术语**：扫一遍源文里出现的所有词库 key（按 key 长度倒序，避免短词覆盖长词），输出"本次翻译命中的术语对照表"
4. **调 Claude 翻译**（model 用 `claude-opus-4-7`，按 `~/.claude/rules/typescript-coding-style.md` 的 prompt caching 约定缓存系统 prompt）：
   - **system prompt**：
     - 你是钉钉国际版文档译者
     - 强约束：以下术语**必须严格**按对照表译，不得自由发挥（命中术语清单）
     - 风格指南（按目标语言）
     - 输出**仅** mdx 正文，frontmatter 单独翻译，正文不要包 ```mdx 代码块
   - **user message**：源 mdx 内容
5. **写入目标路径**：
   - 目标路径推断：源是 `aitable/foo.mdx` → 目标 `zh/aitable/foo.mdx` 和 `ja/aitable/foo.mdx`（en 源场景）
   - **新文件 frontmatter title 翻译，正文写入翻译结果**
   - 如果目标已存在：默认**不覆盖**，提示用户用 `--force` 覆盖（或手动 diff 合并）
6. **后置检查**：
   ```bash
   mint broken-links   # 翻译产生新文件，跑一次确认链接没断
   ```
7. **不自动 commit**。引导用户跑 `/commit-flow`

## 关键约束

- **图片不翻译**：mdx 里的 `![alt](images/xxx.png)` 路径保持原样（按 memory `project_image_translation_rejected_approaches`，en/ja 统一用 zh 的中文截图）
- **代码块不翻译**：被 `` ``` `` 包裹的代码块原样保留
- **链接保留原文**：内部相对路径 `[xxx](/aitable/foo)` 不动；外链文本可翻译
- **MDX 组件保留**：`<Note>`, `<Card>`, `<Steps>` 等标签和属性不译，只译子节点文本
- **三语镜像同结构**：写完后确认 zh / ja 与 en 同 slug 同目录层级

## 词库强约束的实现要点

```python
# pseudo-code 给 Claude SDK
hit_terms_en = {k: v for k, v in zh_en.items() if k in source_chinese_text_or_en_back_translation_keys}
# 实际：以英文为源时，反查 value 命中
hit_terms_en = {k: v for k, v in zh_en.items() if v in source_text}

system = f"""你是钉钉国际版文档译者。

强约束 — 以下术语必须严格按对照表译，不得自由发挥：
{json.dumps(hit_terms_en, ensure_ascii=False, indent=2)}

风格指南（{target_lang}）：
{style_guide_section}

输出：仅 mdx 正文（frontmatter 我单独处理）。
"""
```

## 调用示例

```
/docs-translate aitable/forms/form-basics.mdx
```
预期输出：
- 命中术语 N 条
- 翻译 zh: `zh/aitable/forms/form-basics.mdx` （写入 / skipped if exists）
- 翻译 ja: `ja/aitable/forms/form-basics.mdx`
- `mint broken-links` 通过

## 与其他 skill 的协作

- `/docs-glossary-sync` — 词库更新后再跑本 skill，让翻译用上最新术语
- `/docs-add-page` — 建页后立刻 `/docs-translate <en-path>` 生成两语镜像
- `/commit-flow` — 翻译完成后用户授权提交
