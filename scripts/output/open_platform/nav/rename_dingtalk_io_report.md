# 开放平台 mdx `dingtalk.com` → `dingtalk.io` 全量替换报告

- 总替换次数：**2668**
- 涉及文件数：**367**
- 作用域：`zh/open/**/*.mdx`
- 范围说明：不区分子域名 / 不区分上下文，所有 `dingtalk.com` 字面值一律改为 `dingtalk.io`
- 死链处理：用户已确认死链 OK，等 `*.dingtalk.io` 子域陆续上线后自然恢复
- **mint broken-links 复测**：改前 220 / 80 → 改后 220 / 80（**无变化**）。原因：mint 的 broken-links 只校验内部相对路径，不发起 HTTPS 探活验证外链可达性，所以 `open.dingtalk.io`（实际未上线）这类外链即使死，构建器也不会报。
- 真实死链证据靠：git diff（追踪改了哪些链接）+ 浏览器人肉点击（属于跨期任务，本次不修复）。

## 文件级替换次数（倒序前 30）

-   45  zh/open/development/server-api-error-codes-1.mdx
-   22  zh/open/development/set-robot-quick-entrance.mdx
-   19  zh/open/development/update-cell-properties.mdx
-   18  zh/open/development/update-meeting-room-information.mdx
-   17  zh/open/development/create-a-meeting-room.mdx
-   16  zh/open/development/the-robot-sends-a-group-message.mdx
-   15  zh/open/development/update-subscription-calendar.mdx
-   14  zh/open/development/create-subscription-calendar.mdx
-   14  zh/open/development/get-node-by-link.mdx
-   13  zh/open/development/the-robot-sends-ordinary-messages-in-a-person-to-person-conversation.mdx
-   13  zh/open/development/transfer-exclusive-account-to-main-administrator-creator.mdx
-   12  zh/open/development/api-noatable-createfield.mdx
-   12  zh/open/development/chatbots-send-one-on-one-chat-messages-in-batches.mdx
-   12  zh/open/development/create-schedule.mdx
-   12  zh/open/development/robot-message-type.mdx
-   11  zh/open/development/add-or-modify-visibility-settings-for-address-book-restrictions.mdx
-   11  zh/open/development/add-schedule-participant.mdx
-   11  zh/open/development/api-getrecord.mdx
-   11  zh/open/development/api-noatable-deleterecords.mdx
-   11  zh/open/development/api-noatable-updatefield.mdx
-   11  zh/open/development/api-noatable-updaterecords.mdx
-   11  zh/open/development/batch-withdrawal-of-single-chat-robot-messages-in-person-to-person-conversations.mdx
-   11  zh/open/development/bulk-move-files-or-folders.mdx
-   11  zh/open/development/copy-an-object.mdx
-   11  zh/open/development/copy-files-or-folders-in-bulk.mdx
-   11  zh/open/development/custom-robots-send-group-messages.mdx
-   11  zh/open/development/delete-classic-workbooks.mdx
-   11  zh/open/development/delete-schedule-participant.mdx
-   11  zh/open/development/documentation-faq.mdx
-   11  zh/open/development/modify-event.mdx
- ... 共 367 个文件
