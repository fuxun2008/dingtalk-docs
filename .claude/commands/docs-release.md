---
description: 发布流程 — 把 feat/docs 合并进 main 并双推 github + gitlab（触发 Mintlify 线上发布）
---

# 发布流程 (docs-release)

把功能分支合并进 `main`，并将 **两个分支** 同步推送到 **两个远端**（GitHub + 阿里内网 GitLab）。
推送 `main` 到 GitHub 会触发 Mintlify 自动构建并发布到 https://help.dingtalk.io。

## 参数

- `source`（可选）：待合并的功能分支，默认 `feat/docs`
- `target`（可选）：合并目标分支，默认 `main`

## 前置约束（SOP §1）

本 skill 会 **合并 + 推送远端 + 触发线上发布**，属高影响外发动作。
执行到「步骤 5 推送」前必须 **停下来给出摘要并取得用户明确授权**，用户确认后才 push。

## 步骤

1. **摸清远端与分支状态**
   ```bash
   git remote -v          # 确认 github(GitHub) 与 origin(GitLab) 两个远端都在
   git branch -vv
   git rev-parse --abbrev-ref HEAD
   ```
   - 预期两个远端：`github` → GitHub、`origin` → gitlab.alibaba-inc.com
   - 若远端名/数量与预期不符 → 停下来向用户确认，不臆测

2. **fetch 两端 + 核对合并关系**
   ```bash
   git fetch origin --quiet && git fetch github --quiet
   git log --oneline -1 <target>
   git log --oneline -1 origin/<target>
   git log --oneline -1 github/<target>
   git rev-list --left-right --count <target>...<source>
   ```
   - 确认本地 `<target>` 与 `origin/<target>`、`github/<target>` 一致（未落后）
   - 若本地 `<target>` 落后远端 → 先 `git pull --ff-only`，落后无法快进则停下来报告
   - 记录 `<source>` 相对 `<target>` 的 ahead/behind

3. **预演冲突 + 确认待并入 commit**
   ```bash
   git log --oneline <target>..<source>          # 将并入的 commit 清单
   git diff --name-only <target>..<source>        # 受影响文件
   git merge-tree $(git merge-base <target> <source>) <target> <source> | grep -i "CONFLICT\|<<<<<<" | head
   ```
   - 若预演出现 CONFLICT → 停下来报告冲突文件，交用户决定，**不自动解冲突**
   - 若 `<source>` 无独有 commit（ahead=0）→ 停止："`<source>` 无新提交，无需合并"

4. **切到 target 执行 --no-ff 合并**
   ```bash
   git checkout <target>
   git merge --no-ff <source> -m "Merge branch '<source>'：<一句话 what>。to #<aone-id>"
   ```
   - `--no-ff` 与 main 既有历史风格一致（每次合并留 merge commit）
   - aoneId 沿用 `/commit-flow` 步骤 0 的解析规则（log 里的 `to #<id>`，本项目为 `82317048`）
   - merge message 的 what 用一句话概括 `<source>` 本批改动

5. **⚠️ 推送前授权闸门（SOP §1）**
   向用户输出摘要并 **等待明确授权**：
   - 将合并的 commit 数 + 一句话 what
   - 将执行的 4 次 push：`<target>`→github、`<target>`→origin、`<source>`→github、`<source>`→origin
   - **明确警告**：推送 `<target>` 到 github 会触发 Mintlify 线上自动发布（help.dingtalk.io 立即更新）
   - 用户确认后才继续；用户在调用时已明说"直接发布/直接推"则可跳过等待

6. **双分支 × 双远端推送（4 次）**
   ```bash
   git push github <target>
   git push origin <target>
   git push github <source>
   git push origin <source>
   ```
   - pre-push 钩子会自动校验 `sitemap.xml` in sync，留意其输出
   - 任一 push 失败（非快进 / 权限 / 钩子拦截）→ 停下来报告，**不加 --force**

7. **汇报结果**
   用表格列出「分支 × 远端」4 格的推送结果（新旧 SHA 或 up-to-date），
   并再次提示：main 已推 GitHub → Mintlify 正在构建，稍后 help.dingtalk.io 生效。

## 注意事项

- **两个远端都要推**：`github`(对外) + `origin`(阿里内网 GitLab)，缺一不可
- **绝不 `--force` / `--force-with-lease`**：本流程是快进式合并推送，出现非快进说明有人抢先推，须先 fetch 复核
- **不主动 push `<source>` 以外的其他分支**
- merge commit message 必带 `to #<aone-id>`
- 合并前 target 必须与两个远端同步；不同步先对齐再合并
- 若用户只想预览不想上线 → 建议只推 `<source>`，暂不推 `<target>`
