---
description: 提交流程 — lint检查 → 生成commit message → 提交
---

# 提交流程

执行完整的代码提交工作流。

## 步骤

0. **预读默认 aoneId**（无需用户输入）
   按优先级解析当前应使用的 aoneId：
   1. 读 user memory：`~/.claude/projects/<slug>/memory/user_aone_id.md` 是否存在；若存在，取里面的 ID 作为兜底默认
   2. 跑 `git log --oneline -20` 找最近的 `to #<id>`；若找到 → **优先使用 log 里的**（说明本项目用独立 aoneId）
   3. 都没有 → 留待步骤 5 询问用户
   把解析结果记下来，后续步骤 5/6 直接用，不再额外提问

1. **检查 Git 状态**
   ```bash
   git status
   ```
   如果没有更改，停止："没有需要提交的更改"

2. **运行 Lint 检查**
   ```bash
   pnpm lint
   ```
   如果有错误，先修复再继续（只修复本次变更文件中的问题）

3. **分析变更内容**
   ```bash
   git diff --staged
   git diff
   ```
   分析所有变更，理解本次修改的目的

4. **暂存文件**
   将相关文件 add 到暂存区（精确添加，不用 `git add .`）

5. **确认 Aone ID**
   使用步骤 0 解析出的 aoneId：
   - 步骤 0 已得出 ID → 直接用，不再询问
   - 步骤 0 没结果 → **停下来询问用户提供 Aone ID**（不可跳过！）
   - 用户在调用 skill 时传了 `aoneId=xxxxx` 参数 → **以参数为准**，覆盖步骤 0

6. **生成 Commit Message**
   遵循格式：`<type>: <description>。to #<aone-id>`
   - type: feat | fix | refactor | docs | chore | perf
   - description: 中文描述，简洁明了
   - **必须**以 `to #<aone-id>` 结尾（关联功能需求，用于代码统计）

7. **执行提交**
   ```bash
   git commit -m "<type>: <description>。to #<aone-id>"
   ```

## 注意事项

- 不要使用 `git add .` 或 `git add -A`
- 不要提交 .env、credentials 等敏感文件
- commit message 使用中文描述
- 遵循项目已有的 commit 风格（参考 git log）
- **【关键】commit message 必须带 `to #<aone-id>`，绝对不可省略！**

## Post-commit push 范围（默认 origin only）

commit 完成后**不自动 push**；用户单独说"push" 才推。push 时遵循：

- 默认只推 `origin`（GitLab 内部主仓）：`git push origin <branch>`
- **不要顺手 `git push github`**——除非用户明确说"双 push" / "推 github" / 当前分支是 `master`
- 仓库现有 2 个 remote：
  - `origin` → `git@gitlab.alibaba-inc.com:dingding/dingtalk-docs.git`（默认）
  - `github` → `git@github.com:fuxun2008/dingtalk-docs.git`（须明确授权）
- 详见 user memory `feedback-push-scope`
