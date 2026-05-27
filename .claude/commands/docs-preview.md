---
description: 启动 mint dev 后台预览 + 死链检查 + playwright 抓三语首页截图 + 自动关闭
---

# Docs Preview — 文档站本地预览验证

启动 `mint dev` 后台进程，跑死链检查，用 playwright 打开三语首页验证渲染，结束后自动停止。

## 步骤

1. **确认在 dingtalk-docs 仓库根**
   ```bash
   pwd && ls docs.json 2>/dev/null
   ```
   不是则停下报错

2. **后台启动 mint dev**
   用 Bash `run_in_background: true` 启动：
   ```bash
   mint dev
   ```
   记下返回的 task_id，留待最后停止

3. **等待端口 3000 就绪**
   用 Monitor 等待"Local: http://localhost:3000"出现：
   ```bash
   until curl -sf http://localhost:3000 >/dev/null 2>&1; do sleep 1; done && echo "ready"
   ```
   超时 60s 仍未起来 → 读 mint dev 输出报错给用户

4. **死链检查**
   ```bash
   mint broken-links
   ```
   有死链 → 列出来，但继续下一步（不中断）

5. **playwright 抓三语首页**
   - `mcp__playwright__browser_navigate` → `http://localhost:3000/` → 截图存到 `/tmp/docs-preview-en.png`
   - 再访问 `/zh` → 截图 `/tmp/docs-preview-zh.png`
   - 再访问 `/ja` → 截图 `/tmp/docs-preview-ja.png`
   - 用 `mcp__playwright__browser_console_messages` 抓 error 级别日志

6. **关闭后台进程**
   用 TaskStop 停止步骤 2 的 mint dev 进程
   再 `mcp__playwright__browser_close`

7. **报告**
   - 三张截图路径
   - 死链清单（若有）
   - 浏览器 console error 清单（若有）
   - mint dev 任何 warning（若有）

## 注意事项
- mint dev 默认占用 3000，如果被占用先 `lsof -i:3000` 看一下并询问
- 任何步骤报错也要确保步骤 6 关闭进程（在 catch 里执行 TaskStop）
- 不要在 CI / 远端环境跑这个 skill，仅本地

见 [[project-docs-stack]]
