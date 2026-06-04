---
description: 扫描本次会话，按四类候选记忆让用户复选并写入 memory 目录
---

# Memory Scan — 记忆扫描器

主动梳理当前会话里值得入库的信息，按 user/feedback/project/reference 四类列出候选，让用户多选确认后写入 memory 目录并更新 MEMORY.md 索引。

## 何时触发
- 用户输入 `/memory-scan`
- 较长会话结束前（≥ 30 轮对话或已完成一个非平凡任务）由我主动建议触发
- 用户说"记下来 / 以后都这样 / 这点很重要"——主动触发

## 步骤

1. **定位 memory 目录**
   ```bash
   ls ~/.claude/projects/<slug>/memory/ 2>/dev/null || echo "missing"
   ```
   `<slug>` 是当前 working directory 的转义形式（用 `/Users/foo/bar` → `-Users-foo-bar`）。
   若目录不存在，先 `mkdir -p` 创建。

2. **读现有索引避免重复**
   读 `MEMORY.md`，记下已有条目的 name，新候选与之去重（同名 → 视为"更新"而非"新增"）。

3. **梳理本次会话的候选**
   按四类各扫一遍：
   - **user**：用户角色 / 知识背景 / 长期身份信息（aoneId、GitHub 用户名、SSH key 状态、邮箱、办公方向）
   - **feedback**：用户对工作方式的偏好或纠正（"不要 X / 要 Y"、被采纳的非常规判断、需要授权才做的动作）
   - **project**：当前项目的非代码事实（技术栈选型背景、分支策略、待办的外部动作、人员分工、deadline）
   - **reference**：外部资源指针（dashboard URL、监控面板、Slack 频道、第三方工具）
   排除项：代码层面的 pattern、git log 能查到的、CLAUDE.md 已记录的、临时调试结论。

4. **用 AskUserQuestion 复选**
   每类一题（multiSelect: true），每个选项是一条候选，label 简短、description 说清楚"为什么值得存"。
   类目下 0 条候选 → 跳过这题。
   全部 0 条 → 输出"本次会话无值得入库的新信息"并退出。

5. **写入选中条目**
   每条独立文件 `<type>_<slug>.md`（snake_case），frontmatter 三字段：
   ```yaml
   ---
   name: <kebab-case-slug>
   description: <one-line summary>
   metadata:
     type: <user|feedback|project|reference>
   ---
   ```
   feedback / project 类正文要有 `**Why:**` 和 `**How to apply:**` 段落。
   关联其他条目用 `[[name]]` 链接（即使目标尚未存在也可以先写）。

6. **更新 MEMORY.md 索引**
   在对应分类下追加一行：`- [简短标题](file.md) — 一句话钩子`，≤ 150 字符。

7. **报告产物**
   列出本次新增/更新的文件路径清单。

## 注意事项
- 不要把可由 `git log` / `git blame` 查到的事实写成 memory
- 同名条目存在时用 Edit 更新而非 Write 覆盖
- MEMORY.md 控制在 200 行内（超过会被截断）
- 对 user 类条目要谨慎：避免任何带评判色彩的内容
