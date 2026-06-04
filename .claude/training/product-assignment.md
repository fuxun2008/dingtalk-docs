# 产品 ↔ slug ↔ 负责人对照表

> 这份表是其他所有培训资料的**单一真相源**。slug 一旦在 `docs.json` 注册就不能改名，所以本表先校准。

## 命名规则（来自 `CLAUDE.md` 命名约定段）

- **slug**：全英文小写 kebab-case；进入 `<slug>/`、`zh/<slug>/`、`ja/<slug>/` 三个目录名 + `docs.json` 三处 navigation
- **tab 显示名**：英文 tab 用产品官方英文名（品牌名不译，如 `AI Table` / `DingTalk Docs`）；中日 tab 自然翻译（`钉钉文档` / `ドキュメント`）
- **个人分支名**：`feat/<slug>`，例如 `feat/calendar` / `feat/im`

## 分工表

| # | 产品（中文） | tab 显示名（en / zh / ja） | slug | 负责人 | 中文文档源 | 篇数估算 | 状态 |
|---|---|---|---|---|---|---|---|
| 0 | 首页 | Overview / 总览 / 概要 | `overview`（已存在） | 砚心 | 对标 larksuite / slack help center | 5-8 篇 | ✓ 已落地 |
| 1 | AI 表格 | AI Table / AI 表格 / AI テーブル | `aitable` | 砚心 | https://wolai.dingtalk.com/iAA41DDCVKitBP6gFaBRnE | 210 | ✓ 已落地 |
| 2 | 在线文档 | DingTalk Docs / 钉钉文档 / ドキュメント | `docs` | 砚心 | https://alidocs.dingtalk.com/i/p/Y7kmbokZp3pgGLq2/docs/od245kZmnOeW4D4L73YEWYbzxL6R0wMQ | 349 | ✓ 已落地 |
| 3 | 开发者平台 | Open Platform / 开发者平台 / 開発者プラットフォーム | `open` | 砚心 | https://open.dingtalk.com/document/ | 待估 | 🔜 进行中 |
| 4 | IM | IM / 即时通讯 / メッセージ | `im` | 步鹤 | https://alidocs.dingtalk.com/i/p/Y7kmbokZp3pgGLq2/docs/OmLa2Gg0l5BW7zD1BZyP8vQAdYbnKEek | 待估 | 待启动 |
| 5 | 日历 | Calendar / 日历 / カレンダー | `calendar` | Summer | https://alidocs.dingtalk.com/i/p/Y7kmbokZp3pgGLq2/docs/7Y36k14mK9AV3pKq5zA1J5NqapjblR2D | 待估 | 待启动 |
| 6 | 音视频 | Meeting / 视频会议 / ビデオ会議 | `meeting` | 棠道 | https://alidocs.dingtalk.com/i/p/Y7kmbokZp3pgGLq2/docs/AY39rGpMPmeVN6raOQx0VOZkXKnaoNQ7 + https://alidocs.dingtalk.com/i/p/Y7kmbokZp3pgGLq2/docs/e5vdDPq4wYa8arMA9g9wWj7nbm10NkB9 | 待估（两源合并） | 待启动 |
| 7 | 通讯录 | Contacts / 通讯录 / 連絡先 | `contacts` | 惜柚 | https://alidocs.dingtalk.com/i/p/Y7kmbokZp3pgGLq2/docs/Mk5evdR04jBV5qZQRdyXVQL3x2OlParn | 待估 | 待启动 |
| 8 | 邮箱 | Mail / 邮箱 / メール | `mail` | 成洲 | https://alidocs.dingtalk.com/i/p/nb9XJKaNwORJ3myA/docs/93NwLYZXWyxXroNzC3llOoMa8kyEqBQm | 待估 | 待启动 |
| 9 | AI 听记 | AI Notes / AI 听记 / AI ノート | `ai-notes` | 未壹 | https://alidocs.dingtalk.com/i/p/Y7kmbokZp3pgGLq2/docs/em7AML0b9lBV2zn7vEg3VnNyqOD6vwro | 待估 | 待启动 |
| 10 | 钉盘 | Drive / 钉盘 / ドライブ | `drive` | 壹鸿 | https://alidocs.dingtalk.com/i/p/Y7kmbokZp3pgGLq2/docs/6wPdlBDrQk4JYrl0vX2Y8XKx72oEGeL5 | 待估 | 待启动 |

> 全部中文文档总库（兜底入口）：https://alidocs.dingtalk.com/i/p/Y7kmbokZp3pgGLq2/docs/k2wz1jPpZ30WoY1XPb0mJNnvrL4A6dxE

## 个人分支与 MR 对照

| 负责人 | 个人分支 | MR 目标 | 上线域名 |
|---|---|---|---|
| 步鹤 | `feat/im` | `origin/main` | https://help.dingtalk.io/im |
| Summer | `feat/calendar` | `origin/main` | https://help.dingtalk.io/calendar |
| 棠道 | `feat/meeting` | `origin/main` | https://help.dingtalk.io/meeting |
| 惜柚 | `feat/contacts` | `origin/main` | https://help.dingtalk.io/contacts |
| 成洲 | `feat/mail` | `origin/main` | https://help.dingtalk.io/mail |
| 未壹 | `feat/ai-notes` | `origin/main` | https://help.dingtalk.io/ai-notes |
| 壹鸿 | `feat/drive` | `origin/main` | https://help.dingtalk.io/drive |
| 砚心 | `feat/open` | `origin/main` | https://help.dingtalk.io/open |
| 砚心 | — | CR + merge + 同步 `github/main` | — |

## 检查这张表是否正确

```bash
# 1. 看现有 docs.json 已注册的 tab，slug 是否一致
grep -E '"tab"|/aitable/|/docs/|/overview/' docs.json | head -20

# 2. 别人是否已经先把你的 slug 占了
ls aitable docs overview 2>/dev/null   # 应只见已落地三个
ls im calendar meeting contacts mail ai-notes drive open 2>/dev/null   # 应全部不存在
```

如果你的 slug 已被占用 → 找砚心对齐改名，**不要自己改本表**。
