# IM EN Import Report

- 成功: **18 / 18**
- 缺失: 0
- title 不一致: 1
- NBSP 清洗: 3915（mdx 残留 0）

## 全表
| group | slug | title | desc_len | nbsp_cleaned | size |
|---|---|---|---|---|---|
| Getting Started | `chats-overview` | Get Started with Messages | 160 | 509 | 4832 |
| Send and Receive Messages | `chats-direct-message` | Start a Direct Message | 160 | 260 | 2465 |
| Send and Receive Messages | `chats-send-message` | Send and Format Messages | 95 | 215 | 2537 |
| Send and Receive Messages | `chats-text-formatting` | Format Text in Messages | 148 | 152 | 1987 |
| Send and Receive Messages | `chats-rich-messages` | Send Files and Use Composer Shortcuts | 160 | 279 | 2975 |
| Send and Receive Messages | `chats-start-video-conference` | Start a Video Conference from Messages | 106 | 88 | 1101 |
| Message Management | `chats-search` | Search Chat Records | 105 | 195 | 2180 |
| Message Management | `chats-message-actions` | Use Message and Conversation Actions | 112 | 330 | 3263 |
| Message Management | `chats-organize` | Manage the Conversation List | 160 | 181 | 1681 |
| Message Management | `chats-notifications` | Manage Message Notifications | 106 | 195 | 1999 |
| Message Management | `chats-service-conversation-settings` | Manage Service Conversation Settings | 160 | 103 | 1036 |
| Group Communication | `chats-group-chat` | Create and Manage a Group Chat | 97 | 260 | 2546 |
| Group Communication | `chats-group-management` | Manage Group Members and Permissions | 101 | 217 | 2319 |
| Group Communication | `chats-group-settings` | Configure Group Chat Settings | 100 | 223 | 2444 |
| Group Communication | `chats-group-advanced-management` | Open Advanced Group Management Settings | 84 | 194 | 2012 |
| Group Communication | `chats-group-announcement` | View Group Notices | 149 | 124 | 1196 |
| Group Communication | `chats-mentions` | Manage @Everyone Permissions | 119 | 108 | 1124 |
| FAQs | `chats-faq` | Messages FAQ | 127 | 282 | 2205 |

## title 不一致（用 H1 解析值落地）
- `chats-message-actions`: expected `Use Conversation List Actions` ≠ actual `Use Message and Conversation Actions`
