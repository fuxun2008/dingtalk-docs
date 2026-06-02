# 翻译词库同步

把语言同学维护的"中文-英文-日文"官方词库（钉钉文档导出的 csv）合并进项目，生成翻译流程消费的 `scripts/glossary/zh-en.json` 与 `zh-ja.json`。

## 适用场景

- 语言同学在钉钉文档更新了词库 → 你导出新 csv 覆盖 `scripts/glossary/import/`
- 在 `scripts/glossary/local-supplements.md` 增删了本地 AI Table 专项术语
- 想看一遍当前词库的合并状态 / 冲突清单

## 参数

- `--dry-run`（可选）：只算 diff 不写文件
- `--source <csv-path>`（可选）：只解析指定 csv，跳过其他

## 执行步骤

1. **前置检查**：确认 `scripts/glossary/import/` 至少有 1 个 `.csv` 文件。否则报错并提示：
   > 去钉钉文档 [词库 sheet](https://alidocs.dingtalk.com/i/nodes/7QG4Yx2JpOzXoN4PsYeYXQbGV9dEq3XD) 导出最新 csv，放到 `scripts/glossary/import/`
2. **跑同步脚本**：
   ```bash
   python3 scripts/glossary_sync.py
   ```
   若用户传了 `--dry-run` 或 `--source`，原样透传。
3. **展示报告摘要**：读 `scripts/glossary/merge-report.md`，把"统计表格"段（official 条数、本地补充被采纳数、最终条数、冲突数）回显给用户。
4. **diff 概览**：
   ```bash
   git diff --stat scripts/glossary/
   ```
   让用户看到哪些 JSON 变了。
5. **冲突预警**：如果 `scripts/glossary/official/conflicts.json` 非空，提示用户：
   > 发现 N 条 official 内部冲突，已在 `scripts/glossary/official/conflicts.json`。如需统一，反馈给语言同学。
6. **不自动提交**。引导用户：
   > 如要提交，跑 `/commit-flow`（commit message 建议 `docs: 同步语言同学官方词库（X 条新增）。to #82317048`）

## 关键约束

- **不调任何外网 API**：日文直接来自官方 csv，不再调 Claude 派生
- **不覆盖 `local-supplements.md`**：本地补充由人维护，脚本只读
- **保留路径兼容**：最终消费产物 `scripts/glossary/zh-en.json` 和 `zh-ja.json` 路径不变，上游 `translate_chapter_api.py` / `docs-translate` 无需改

## 词库分层（看一眼就明白）

```
import/*.csv       源（语言同学的钉钉文档导出）
    ↓ glossary_sync.py
official/*.json    规范化后的官方词库
    +
local-supplements.md   本地补充（官方未覆盖的 AI Table 专项 + 风格指南）
    ↓ 合并：official 优先
zh-en.json / zh-ja.json   最终消费产物
```

## 词库源（钉钉文档 URL）

- 业务通用：https://alidocs.dingtalk.com/i/nodes/7QG4Yx2JpOzXoN4PsYeYXQbGV9dEq3XD（sheetId=uPKb1dP）
- AI 产品代号（悟空版）：https://alidocs.dingtalk.com/i/nodes/7QG4Yx2JpOzXoN4PsYeYXQbGV9dEq3XD（sheetId=7eVC9FW）
