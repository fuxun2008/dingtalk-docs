---
name: docs-prune-orphan-images
version: 1.0.0
description: "Scan local image assets and physically delete images no longer referenced by any MDX file. Use after deleting MDX sections, after trimming one language mirror, or to slim the repository."
description_zh: "文档孤儿图清理：找出不再被任何 mdx 引用的本地图片并物理删除。"
user-invocable: true
argument-hint: "[<scope>] [--dry-run]"
---
# 文档孤儿图清理

扫描本仓库的本地图片资源，找出 **不再被任何 mdx 引用** 的图片并物理删除。

## 适用场景

- 删除 mdx 章节后，该章节引用的本地图片可能成为孤儿
- 三语镜像（en / zh / ja）中的某个语言被裁剪内容后，对应 `images/` 目录可能残留
- 仓库瘦身（PNG/GIF 是大头）

## 参数

- `<scope>`（可选）：限定扫描范围。可传：
  - mdx 路径（如 `aitable/automation/create-todo-or-event.mdx`）→ 仅扫该 mdx 所在 `images/` 目录
  - 目录前缀（如 `aitable/automation/`）→ 扫该前缀下所有 `images/` 目录
  - 省略 → 扫全仓 `aitable/` + `zh/aitable/` + `ja/aitable/` 下所有 `images/`

## 执行步骤

1. **列出候选**：`find <scope>/images -type f` 收集所有本地图片
2. **逐张验证**：对每张图，跑 `grep -rl --include="*.mdx" "<filename>" .`
   - 引用数 = 0 → 孤儿
   - 引用数 ≥ 1 → 跳过
3. **报告 + 删除**：列出孤儿清单（含每张大小）、合计释放空间，然后 `rm -v` 物理删除
4. **不需要二次确认**——验证零引用即可删（见 feedback memory `feedback_orphan_image_auto_cleanup`）

## 关键约束（避免误删）

- **只用文件名 grep**，不要用全路径 grep——zh / ja 镜像可能引用同名文件但路径前缀不同，全路径会漏判
- **CJK 文件名直接用**，不要 URL-encode（mdx 里 CJK 保持原样，见 `project_mdx_image_batch_pitfalls`）
- **仅扫 `aitable/` 三语前缀**，不要碰 `docs/` / `overview/` 等其他产品目录除非用户明确指定
- 删除前用 `du -sh` 记录目录体积，删除后再报一次，方便用户感知收益

## 调用示例

```
/docs-prune-orphan-images aitable/automation/create-todo-or-event.mdx
```
预期输出：
- 候选 N 张
- 孤儿 M 张（列名 + 大小）
- 删除 → 释放 X.X MB

## 与 commit-flow 的协作

孤儿清理通常和"删除 mdx 章节"是同一个改动。**清理完不要自动 commit**，让用户后续 `/commit-flow` 一次性提交"内容删除 + 孤儿清理"。
