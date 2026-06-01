# 词库源 csv

这里放语言同学维护的官方"中文-英文-日文"对照词库的 csv 导出文件。

## 数据来源

钉钉文档（需登录鉴权）：

| Sheet | 主题 | URL |
|---|---|---|
| `uPKb1dP` | 业务通用术语（成员/邮箱/登录/退出/...） | [打开](https://alidocs.dingtalk.com/i/nodes/7QG4Yx2JpOzXoN4PsYeYXQbGV9dEq3XD?iframeQuery=entrance%3Ddata%26sheetId%3DuPKb1dP) |
| `7eVC9FW` | AI 产品代号 / 公司名（AIX / Real / Chat Kit / ...） | [打开](https://alidocs.dingtalk.com/i/nodes/7QG4Yx2JpOzXoN4PsYeYXQbGV9dEq3XD?iframeQuery=entrance%3Ddata%26sheetId%3D7eVC9FW) |

## 更新流程

1. 打开钉钉文档（任一 sheet）
2. 顶部菜单 `…` → `导出` → `CSV`（或先 `导出` → `Numbers/Excel`，再用 Apple Numbers 另存为 CSV）
3. 把导出的 csv 覆盖到本目录（保留原文件名或重命名都行，脚本会扫所有 `.csv`）
4. 跑 `/docs-glossary-sync` 或 `python3 scripts/glossary_sync.py` 重新合并
5. 检查 `scripts/glossary/merge-report.md`，留意是否有新冲突
6. 通过 `/commit-flow` 提交

## csv 格式要求

三列：`中文文案,英语,日语`（首行为表头）。第二行如果是 `中文术语,English,日本語` 这种二级表头也会被脚本自动跳过。空行 / 缺少英文和日文的行会被丢弃。

## 不要做的事

- ❌ 手改 csv 内容（违反"语言同学是权威"的原则）。要改去钉钉文档改，然后重新导出
- ❌ 把 `.numbers` 二进制文件 commit 进仓库（已通过 `.gitignore` 忽略）
- ❌ 在本目录放非词库的 csv（脚本会扫所有 `.csv`，混入会污染词库）
