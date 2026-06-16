# IM EN Import Report

- 成功: **18 / 18**
- 缺失: 0
- title 不一致: 1
- NBSP 清洗: 3915（mdx 残留 0）

## 全表
| group | slug | title | desc_len | nbsp_cleaned | size |
|---|---|---|---|---|---|
| Getting Started | `chats-overview` | Get Started with Messages | 182 | 509 | 4854 |
| Send and Receive Messages | `chats-direct-message` | Start a Direct Message | 168 | 260 | 2473 |
| Send and Receive Messages | `chats-send-message` | Send and Format Messages | 185 | 215 | 2627 |
| Send and Receive Messages | `chats-text-formatting` | Format Text in Messages | 170 | 152 | 2009 |
| Send and Receive Messages | `chats-rich-messages` | Send Files and Use Composer Shortcuts | 162 | 279 | 2977 |
| Send and Receive Messages | `chats-start-video-conference` | Start a Video Conference from Messages | 152 | 88 | 1147 |
| Message Management | `chats-search` | Search Chat Records | 178 | 195 | 2253 |
| Message Management | `chats-message-actions` | Use Message and Conversation Actions | 167 | 330 | 3318 |
| Message Management | `chats-organize` | Manage the Conversation List | 196 | 181 | 1717 |
| Message Management | `chats-notifications` | Manage Message Notifications | 170 | 195 | 2063 |
| Message Management | `chats-service-conversation-settings` | Manage Service Conversation Settings | 181 | 103 | 1057 |
| Group Communication | `chats-group-chat` | Create and Manage a Group Chat | 163 | 260 | 2612 |
| Group Communication | `chats-group-management` | Manage Group Members and Permissions | 168 | 217 | 2386 |
| Group Communication | `chats-group-settings` | Configure Group Chat Settings | 198 | 223 | 2542 |
| Group Communication | `chats-group-advanced-management` | Open Advanced Group Management Settings | 141 | 194 | 2069 |
| Group Communication | `chats-group-announcement` | View Group Notices | 144 | 124 | 1191 |
| Group Communication | `chats-mentions` | Manage @Everyone Permissions | 149 | 108 | 1154 |
| FAQs | `chats-faq` | Messages FAQ | 172 | 282 | 2250 |

## title 不一致（用 H1 解析值落地）
- `chats-message-actions`: expected `Use Conversation List Actions` ≠ actual `Use Message and Conversation Actions`
