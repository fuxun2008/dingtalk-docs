# oa 文档外链人工 review 表

> 生成于 oa 文档质量优化（阶段 2）。列出 oa/ 与 zh/oa/ 全部**文本链接**（`[text](url)`，不含图片）。
> 探针时间探活：alidocs 走 `check_external_links.py`（og:title SSR），其余走 `curl -L` HTTP 状态。

## 汇总

| 类别 | 条数 | 处理 |
|---|---|---|
| alidocs FCM 指路（指向仓内已有页） | 4 | **已内链化** → `/oa/fcm-push-notification-setup`（zh 加前缀） |
| oa.dingtalk.io 管理后台应用入口 | 6 | 保留（登录/功能入口，非文档，无仓内对应页） |
| open.dingtalk.com 开放平台 API 文档 | 4 | 保留（外部开发者文档） |
| console.firebase.google.com | 2 | 保留（第三方，FCM 配置需要） |
| developer.apple.com | 2 | 保留（第三方，App 分发需要） |
| www.axialis.com | 1 | 保留（第三方工具教程，仅 zh） |
| **合计** | **19** | 内链 4 / 保留 15 |

**死链：0**（全部探活 200 / og:title 非空）。

## 保留外链明细（15 条，人工核对目标是否仍恰当）

| 文件:行 | 链接文本 | URL | 探活 | 说明 |
|---|---|---|---|---|
| oa/how-to-log-in-to-admin-console.mdx:16 | https://oa.dingtalk.io/ | https://oa.dingtalk.io/ | 200 | 管理后台登录入口 |
| zh/oa/how-to-log-in-to-admin-console.mdx:16 | 同上 | https://oa.dingtalk.io/ | 200 | |
| oa/ai-minutes-equity-allocation.mdx:6 | AI Minutes > Minutes Equity Allocation | https://oa.dingtalk.io/meeting_oa#/flash_minutes/equity | 200 | 后台深链 |
| zh/oa/ai-minutes-equity-allocation.mdx:6 | 同上 | 同上 | 200 | |
| oa/video-meetings-allocate-equity.mdx:8 | Admin Console | https://oa.dingtalk.io/ | 200 | |
| zh/oa/video-meetings-allocate-equity.mdx:8 | 同上 | https://oa.dingtalk.io/ | 200 | |
| oa/sso.mdx:14 | Query User Details API | https://open.dingtalk.com/document/orgapp/query-user-details | 200 | 开放平台 API |
| oa/sso.mdx:14 | Create SSO Account API | https://open.dingtalk.com/document/orgapp/create-an-sso-account | 200 | |
| zh/oa/sso.mdx:14 | 查询用户详情 API | https://open.dingtalk.com/document/orgapp/query-user-details | 200 | |
| zh/oa/sso.mdx:14 | 创建 SSO 账号 API | https://open.dingtalk.com/document/orgapp/create-an-sso-account | 200 | |
| oa/fcm-push-notification-setup.mdx:18 | Firebase 控制台 | https://console.firebase.google.com/ | 200 | 第三方 |
| zh/oa/fcm-push-notification-setup.mdx:18 | 同上 | https://console.firebase.google.com/ | 200 | |
| oa/create-package.mdx:56 | Apple 非公开分发 | https://developer.apple.com/support/unlisted-app-distribution/ | 200 | 第三方 |
| zh/oa/create-package.mdx:56 | 同上 | https://developer.apple.com/support/unlisted-app-distribution/ | 200 | |
| zh/oa/packaging-material-management.mdx:77 | Axialis 图标教程 | https://www.axialis.com/tutorials/tutorial-iw023.html | 200 | 第三方，仅 zh 有 |

## 已内链化明细（4 条）

| 文件:行 | 原 URL | 改为 |
|---|---|---|
| oa/packaging-material-management.mdx:33,111 | alidocs.dingtalk.com/i/nodes/R1zknDm0…（FCM 指南） | /oa/fcm-push-notification-setup |
| zh/oa/packaging-material-management.mdx:33,110 | alidocs.dingtalk.com/i/nodes/20eMKjyp…（申请开通FCM推送引导） | /zh/oa/fcm-push-notification-setup |
