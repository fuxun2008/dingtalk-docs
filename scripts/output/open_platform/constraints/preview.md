# 约束规则预览（dry-run）

> 生成时间：2026-06-09 05:40:35 UTC
> 输入：`scripts/output/open_platform/raw/` 共 553 篇
> 启用规则：**14 / 16 条**（高风险 5 条默认 OFF）
> 受影响篇数：**350** / 553

## 规则列表与启用状态

> **删除** = 应用后真实删除的段；**跳过** = 命中但在表格里，需人工 review 不自动删

| ID | 规则 | 风险 | 启用 | 命中篇数 | 删除 | 跳过(表格) |
|---|---|:-:|:-:|---:|---:|---:|
| A1 | 开发者后台域名 open-dev.dingtalk.com → open-dev.dingtalk.io | 🟢 low | ✅ | 74 | 136 | — |
| A2 | 管理后台域名 oa.dingtalk.com → oa.dingtalk.io | 🟢 low | ✅ | 25 | 38 | — |
| B1 | 删第三方企业应用 / 第三方个人应用相关段落 | 🟡 medium | ✅ | 260 | 62 | 529 |
| B2 | 删小程序段落（同段含「微应用」则保留） | 🔴 high | 🚫 | 35 | 69 | 63 |
| B3 | 删委托商服务 / 委托应用 | 🟢 low | ✅ | 1 | 0 | 1 |
| B4 | 删互动卡片 / 场景群 | 🟡 medium | ✅ | 41 | 118 | 51 |
| B5 | 删行业通讯录 / 上下游组织 / 上下级组织 | 🟢 low | ✅ | 2 | 3 | 4 |
| B6 | 删定制应用 | 🟢 low | ✅ | 2 | 0 | 2 |
| B7 | 删直播 | 🔴 high | 🚫 | 4 | 13 | 7 |
| B8 | 删 AI 助理 / Agoal | 🟢 low | ✅ | 3 | 0 | 3 |
| B9 | 删工作台相关章节（H1-H6 标题含「工作台」） | 🟡 medium | ✅ | 25 | 33 | — |
| C1 | 删服务端 SDK 章节（H1-H6 标题含语言名 + SDK/示例/集成） | 🟡 medium | ✅ | 1 | 1 | — |
| C1b | 删服务端 SDK 代码块（lang ∈ java/python/php/go/js/ts/csharp/ruby/kotlin/scala/node） | 🟡 medium | ✅ | 0 | 0 | — |
| C2 | 删 SDK 开发环境安装（IDE / Maven / JDK / Gradle / IntelliJ / Eclipse） | 🟡 medium | ✅ | 6 | 0 | 7 |
| C3 | 删服务端调试工具 API Explorer | 🟢 low | ✅ | 4 | 0 | 4 |
| D1 | 删收费 / 计费 / 套餐版本（基础/标准/企业/旗舰/高级版） | 🔴 high | 🚫 | 17 | 9 | 19 |
| D2 | 删获取微应用后台免登 accessToken（『微应用 + 免登 + accessToken』20 字内共现） | 🟢 low | ✅ | 2 | 0 | 2 |

> 🚫 默认 OFF 规则（B2/B7/B9/C1/D1）也跑了 dry-run 计数，未真正影响 preview 文件；
> 若审完想启用，加 `--enable B7,B9` 重跑 preview，或直接 `--apply --enable ...`。

## 按规则详情（启用）

### ✅ A1 — 开发者后台域名 open-dev.dingtalk.com → open-dev.dingtalk.io
- 风险：low | 命中：74 篇 | 替换：136 处
- 真正会删除（删除样例前 5）：
  - `development/add-api-permission.md` L31: open-dev.dingtalk.com
  - `development/add-api-permission.md` L45: open-dev.dingtalk.com
  - `development/add-api-permission.md` L62: open-dev.dingtalk.com
  - `development/api-doc-updatecontent.md` L11: open-dev.dingtalk.com
  - `development/asynchronous-sending-of-enterprise-session-messages.md` L59: open-dev.dingtalk.com

### ✅ A2 — 管理后台域名 oa.dingtalk.com → oa.dingtalk.io
- 风险：low | 命中：25 篇 | 替换：38 处
- 真正会删除（删除样例前 5）：
  - `development/common-errors.md` L59: oa.dingtalk.com
  - `development/contacts-overview.md` L24: oa.dingtalk.com
  - `development/contacts-overview.md` L243: oa.dingtalk.com
  - `development/contacts-overview.md` L255: oa.dingtalk.com
  - `development/contacts-overview.md` L261: oa.dingtalk.com

### ✅ B1 — 删第三方企业应用 / 第三方个人应用相关段落
- 风险：medium | 命中：260 篇 | 删除：62 处 | 跳过(表格)：529 处
- 备注：多见于「适用对象」段，建议保留人工 spot check
- 真正会删除（删除样例前 5）：
  - `development/add-api-permission.md` L7: [text] 本文档适用于在钉钉开放平台开发的企业内部应用、第三方企业应用和第三方企业应用开发者。
  - `development/add-api-permission.md` L108: [text] 第三方企业应用在接入[统一授权套件](/document/development/unified-licensing-suite-sdk#)时，权限点Code作为的`rpcScope`或`fieldScope`参数值。
  - `development/api-gettoken.md` L3: [text] 如果你的应用需要使用应用权限点，无论是企业内部应用还是第三方企业应用，都应通过本接口获取应用级别的 Access Token。该凭证用于调用钉钉开放平台中受权限保护的 API 接口。
  - `development/api-gettoken.md` L7: [text] 此接口用于获取企业内部应用或第三方企业应用调用API所需的Access Token，适用于所有需要通过应用身份鉴权调用钉钉开放平台接口的场景。
  - `development/apsara-file-storage-for-hdfs-overview.md` L7: [text] 媒体文件是钉钉提供的开放能力之一，可以在企业内部应用和第三方企业应用内的文件储存场景使用。
- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：
  - `development/add-a-meeting-room.md` L9: [table] |  |  | ⏎ | --- | --- | ⏎ | 字段 | 值 | ⏎ | HTTP URL | https://api.dingtalk.com/v1.0/calendar/users/{userId}/calendars/{calendarId}/events/{eventId}/meetingRooms |…
  - `development/add-a-meeting-room.md` L19: [table] |  |  |  |  | ⏎ | --- | --- | --- | --- | ⏎ | 名称 | 类型 | 是否必填 | 描述 | ⏎ | x-acs-dingtalk-access-token | String | 是 | 调用该接口的访问凭证，通过以下获取：   - 企业内部应用，调用[获取企业内部应用的acc…
  - `development/add-api-permission.md` L9: [list] - **企业内部应用**：由企业自主开发并仅供本企业使用的应用，适用于组织内部系统集成场景。 ⏎ - **第三方企业应用**：由ISV（独立软件开发商）开发，供多个企业客户安装使用的服务型应用。 ⏎ - **第三方个人应用**：产品方案商开发者开发，提供给钉钉上个人用户使用的应用。

### ✅ B3 — 删委托商服务 / 委托应用
- 风险：low | 命中：1 篇 | 删除：0 处 | 跳过(表格)：1 处
- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：
  - `development/data-faq.md` L61: [list] - 在开发者后台创建内部应用时，如下图所示，选择的开发方式为**委托商服务开发，**导致应用管理中未显示。

### ✅ B4 — 删互动卡片 / 场景群
- 风险：medium | 命中：41 篇 | 删除：118 处 | 跳过(表格)：51 处
- 备注：「互动卡片」是消息卡片新形态，海外不开放；命中段落整删
- 真正会删除（删除样例前 5）：
  - `development/create-a-group-plug-in.md` L7: [text] 快捷入口（群插件）为场景群及对应的群模板的核心组成部分，是串联业务的关键节点。
  - `development/create-a-group-plug-in.md` L9: [text] 一个场景群通常会配置多个插件，指向一个业务场景中的不同流程和节点，这样就可以在一个群中快速地找到和使用该业务场景相关的全部服务。例如如一个项目群，就会将【今日任务】、【项目进度管理】、【需求列表】等业务节点作为插件配置到群内，方便进行项目管理。
  - `development/development-robot-overview.md` L129: [text] 群模板机器人只支持在场景群内发送群聊消息，不支持发送单聊消息。
  - `development/group-assistant-sends-a-message.md` L7: [text] 本文档展示了，创建一个企业内部应用，使用**场景群**提供的API，实现群助手发送消息流程：
  - `development/group-chat-bot-overview.md` L14: [text] 所谓群聊机器人，指可以在群内使用的机器人，目前主要为webhook机器人和企业自建机器人两大类，另外通过场景群模板的方式，也可以预先配置好机器人并通过启用模板的方式安装到群内。
- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：
  - `development/create-a-group-plug-in.md` L17: [list] 1. 登录[钉钉开发者后台](https://open-dev.dingtalk.io/#/index)。 ⏎ 2. 在**开发者后台**页面，选择**场景群**，点击创建**群插件**。![创建群插件](https://help-static-aliyun-doc.aliyuncs.com/assets/img/zh…
  - `development/group-assistant-sends-a-message.md` L9: [list] 1. 选择目标应用，进入应用详情页，单击基础信息 > 凭证与基础信息。 ⏎ 2. 获取应用 Client ID 和 Client Secret。 ⏎ 3. 申请发送群助手消息接口权限。 ⏎ 4. 获取应用访问凭证，[获取企业内部应用的accessToken](/document/development/obtain-t…
  - `development/group-assistant-sends-a-message.md` L26: [list] 1. 选择目标应用，进入应用详情页，单击**基础信息** > **凭证与基础信息**。 ⏎ 2. 获取应用 Client ID 和 Client Secret。 ⏎ 3. 单击**开发配置** > **权限管理**，在权限搜索框中输入`qyapi_chat_manage`，并申请权限。 ⏎ 4. 获取应用访问凭证[获取…

### ✅ B5 — 删行业通讯录 / 上下游组织 / 上下级组织
- 风险：low | 命中：2 篇 | 删除：3 处 | 跳过(表格)：4 处
- 真正会删除（删除样例前 5）：
  - `development/contacts-overview.md` L165: [heading] #### **行业通讯录**
  - `development/contacts-overview.md` L197: [heading] #### **上下游组织**
  - `development/contacts-overview.md` L211: [heading] #### 上下级组织
- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：
  - `development/contacts-overview.md` L167: [table] |  |  |  | ⏎ | --- | --- | --- | ⏎ | API | 说明 | API 版本 | ⏎ | [获取部门详情](/document/orgapp/industry-address-book-api-for-obtaining-department-information#) | 根据部门ID…
  - `development/contacts-overview.md` L199: [table] |  |  |  | ⏎ | --- | --- | --- | ⏎ | API | 说明 | API 版本 | ⏎ | [创建上下游组织](/document/development/create-a-cooperation-space#) | 创建上下游组织。 | 新版 | ⏎ | [解除关联组织](/docume…
  - `development/contacts-overview.md` L213: [table] |  |  |  | ⏎ | --- | --- | --- | ⏎ | API | 说明 | API 版本 | ⏎ | [解除关联组织](/document/development/disassociate-an-organization#) | 解除关联组织关系。 | 新版 | ⏎ | [获取主干组织列表](/do…

### ✅ B6 — 删定制应用
- 风险：low | 命中：2 篇 | 删除：0 处 | 跳过(表格)：2 处
- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：
  - `development/authorization-overview.md` L45: [table] |  |  |  | ⏎ | --- | --- | --- | ⏎ | 授权凭证 | 应用场景 | 获取方式 | ⏎ | 用户accessToken | 需要登录用户授权的应用。 | [获取用户token](/document/development/obtain-user-token#) | ⏎ | 企业内部应用a…
  - `dingstart/application-type-introduction.md` L19: [table] |  |  |  |  |  | ⏎ | --- | --- | --- | --- | --- | ⏎ | **应用类型** | **定位** | **适用场景** | **核心特征** | **支持能力** | ⏎ | **企业内部应用** | 仅供单一企业内部使用的私有化定制应用，无需上架审核 | 内部审批工具、…

### ✅ B8 — 删 AI 助理 / Agoal
- 风险：low | 命中：3 篇 | 删除：0 处 | 跳过(表格)：3 处
- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：
  - `development/api-updatescheduleconfsettings.md` L25: [table] | 名称 | 类型 | 是否必填 | 描述 | ⏎ | --- | --- | --- | --- | ⏎ | creatorUnionId | String | 是 | 预约会议创建人 unionId。 | ⏎ | scheduleConferenceId | String | 是 | 预约会议 ID。 | ⏎ | …
  - `development/create-appointment-meeting.md` L25: [table] | 名称 | 类型 | 是否必填 | 描述 | ⏎ | --- | --- | --- | --- | ⏎ | creatorUnionId | String | 是 | 创建者unionId。 | ⏎ | title | String | 是 | 预约会议标题。标题最大长度限制不允许超过50。超过50字符时会被截断。…
  - `development/server-api-error-codes-1.md` L9: [table] |  |  |  |  | ⏎ | --- | --- | --- | --- | ⏎ | HttpCode | 错误码 | 错误信息 | 说明 | ⏎ | 200 | - | OK | 请求成功。 | ⏎ | 200 | content.dublication | update the same content | …

### ✅ B9 — 删工作台相关章节（H1-H6 标题含「工作台」）
- 风险：medium | 命中：25 篇 | 删除：33 处
- 备注：从段落级降级到章节级 — 只删标题含「工作台」的整节；段落 / 列表 / 表格里的「工作台」token 不再误删；默认 ON
- 真正会删除（删除样例前 5）：
  - `development/data-faq.md` L37: ### **在工作台无法找到企业内部应用**
  - `development/message-link-description.md` L20: ## 消息链接在PC端工作台打开
  - `development/use-sensitive-permissions.md` L67: ### 工作台授权
  - `dingstart/add-self-built-interactive-cards-to-the-workbench.md` L1: # 自建工作台卡片的创建和使用
  - `dingstart/application-visible-range.md` L126: ## 步骤三：添加应用到工作台

### ✅ C1 — 删服务端 SDK 章节（H1-H6 标题含语言名 + SDK/示例/集成）
- 风险：medium | 命中：1 篇 | 删除：1 处
- 备注：精准化：只在 H1-H6 标题里匹配；保留段落里的 HTTP 调用方式；改默认 ON
- 真正会删除（删除样例前 5）：
  - `development/development-mlogon-faq.md` L49: ### **服务端代码（Node.js 示例）**

### ✅ C2 — 删 SDK 开发环境安装（IDE / Maven / JDK / Gradle / IntelliJ / Eclipse）
- 风险：medium | 命中：6 篇 | 删除：0 处 | 跳过(表格)：7 处
- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：
  - `development/custom-bot-to-send-group-chat-messages.md` L17: [table] |  |  | ⏎    | --- | --- | ⏎    | **开发环境** | **说明** | ⏎    | Java | - 已安装 JDK 1.8 及以上 - 已安装 Maven 3 | ⏎    | Python | - Python 3 |
  - `development/group-template-robot-sends-group-chat-message.md` L15: [list] - Java：已安装 JDK 1.8 及以上 ⏎    - Java：已安装 Maven 3
  - `development/the-application-robot-in-the-enterprise-sends-a-single-chat.md` L15: [table] |  |  | ⏎    | --- | --- | ⏎    | **开发环境** | **说明** | ⏎    | Java | - 已安装 JDK 1.8 及以上 - 已安装 Maven 3 | ⏎    | Python | - Python 3 |

### ✅ C3 — 删服务端调试工具 API Explorer
- 风险：low | 命中：4 篇 | 删除：0 处 | 跳过(表格)：4 处
- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：
  - `development/api-doc-updatecontent.md` L9: [table] | 应用类型 | 是否支持 | 权限 | API Explorer调试 | ⏎ | --- | --- | --- | --- | ⏎ | 企业内部应用 | 支持 | 企业存储文件写权限 | [API Explorer](https://open-dev.dingtalk.io/apiExplorer#/?devTyp…
  - `development/batch-setup-group-administrator.md` L9: [table] | 应用类型 | 是否支持 | 权限 | API Explorer调试 | ⏎ | --- | --- | --- | --- | ⏎ | 企业内部应用 | 支持 | 钉钉群基础信息管理权限 | [API Explorer](https://open-dev.dingtalk.io/apiExplorer#/?devT…
  - `development/get-file-thumbnails-in-bulk.md` L15: [table] |  |  |  |  | ⏎ | --- | --- | --- | --- | ⏎ | 应用类型 | 是否支持 | 权限 | API Explorer调试 | ⏎ | 企业内部应用 | 支持 | 企业存储文件读权限 | [API Explorer](https://open-dev.dingtalk.io/apiE…

### ✅ D2 — 删获取微应用后台免登 accessToken（『微应用 + 免登 + accessToken』20 字内共现）
- 风险：low | 命中：2 篇 | 删除：0 处 | 跳过(表格)：2 处
- 备注：放宽：原 pattern 仅同段紧邻匹配 0 命中，现在三关键词只要 20 字范围内即触发
- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：
  - `development/sso-overview.md` L52: [table] |  |  | ⏎ | --- | --- | ⏎ | 步骤 | 说明 | ⏎ | 步骤一：获取免登授权码**。** | 当企业管理员登录[钉钉管理后台](http://oa.dingtalk.io/)后，点击**工作台**中的应用，会自动跳转到应用的后台地址，钉钉会把code参数追加到此URL地址中。请保存code参…
  - `dingstart/basic-concepts-beta.md` L136: [list] - **定义**：配合 `CorpId` 使用的密钥。 ⏎ - **用途**：主要用于获取微应用后台免登所需的 `access_token`，实现管理员从钉钉后台单点登录到第三方管理系统，无需重复输入账号密码 ⏎ - **场景**：常用于企业SaaS系统的后台集成，提升运维效率与安全性。 ⏎ - **获取**：登录[*…

## 按规则详情（默认 OFF，仅展示影响范围）

### 🚫 B2 — 删小程序段落（同段含「微应用」则保留）
- 风险：high | 命中：35 篇 | 删除：69 处 | 跳过(表格)：63 处
- 备注：同段含「微应用」时本规则会跳过该段；但海外仍可能误删；默认 OFF
- 真正会删除（删除样例前 5）：
  - `development/check-whether-the-administrator-has-application-management-permissions.md` L7: [text] 例如，产品服务商上架了第三方企业应用，名称为三方ISV小程序。某个测试企业开通了三方ISV小程序，小明是测试企业的管理员。产品服务商调用本接口，可查询小明是否拥有三方ISV小程序应用的管理权限。如图： ![](https://img.alicdn.com/imgextra/i2/O1CN01hIxCzR1OjsgzEu…
  - `development/create-a-group-plug-in.md` L189: [text] 主要用于调试小程序，以及appx框架开发。通过此方式打开的小程序，直接通过url启动主文档。不会进入包管理流程，也不会触发保活逻辑。miniAppId仅用于做接口校验等。
  - `development/create-a-swarm-plug-in-1.md` L35: [heading] ## **跳转到小程序**
  - `development/create-a-swarm-plug-in-1.md` L139: [text] 主要用于调试小程序，以及appx框架开发。通过此方式打开的小程序，直接通过url启动主文档。不会进入包管理流程，也不会触发保活逻辑。miniAppId仅用于做接口校验等。
  - `development/data-faq.md` L45: [heading] ### **小程序开发工具调试内部应用提示“抱歉，你不在应用的可使用范围内，请联系管理员修改配置”**
- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：
  - `development/contacts-overview.md` L232: [list] - [创建、获取、更新和删除企业员工](/document/development/address-book-employee-operations#) ⏎ - [创建、获取、更新和删除企业部门](/document/development/operations-related-to-address-book-depa…
  - `development/create-a-group-plug-in.md` L73: [table] |  |  | ⏎   | --- | --- | ⏎   | 参数 | 说明 | ⏎   | container\_type | 展现的容器：  - browser: 浏览器 - slide\_panel：左划面板 - work\_platform：工作台 | ⏎   | corpid | 企业的corpid。 | …
  - `development/create-a-group-plug-in.md` L108: [table] |  |  |  | ⏎      | --- | --- | --- | ⏎      | 参数 | 是否必填 | 说明 | ⏎      | panelHeight | 否 | 浮窗高度，可以是屏幕占比百分比，也可以是确定的高度。  - percent50，含义是占比屏幕的50%，数字在(0-100]之间，大于小于…

### 🚫 B7 — 删直播
- 风险：high | 命中：4 篇 | 删除：13 处 | 跳过(表格)：7 处
- 备注：「直播间」「直播课」等也会命中；默认 OFF
- 真正会删除（删除样例前 5）：
  - `development/video-conference-overview.md` L78: [heading] ## **直播**
  - `development/video-conference-overview.md` L82: [text] 钉钉直播具有直播预约、权限自由设置、多群联播、实时互动、直播录制、直播数据统计等完善功能，打破时间和空间上的限制，方便的完成一场直播活动，高效上传下达，改变传统培训管理模式。
  - `development/video-conference-overview.md` L84: [text] 对于企业培训、招聘宣讲、活动直播、在线课堂等多种场景，钉钉直播能够轻松搞定，同时提供专业的重保服务，确保现场执行团队顺利部署及调试设备，保障直播线上到线下的整体质量和体验。
  - `development/video-conference-overview.md` L95: [heading] ### **如何发起直播**
  - `development/video-conference-overview.md` L97: [text] 在**钉钉PC客户端**页面，单击客户端左侧**更多**，依次单击**直播 > 发起直播。**
- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：
  - `development/server-api-error-codes-1.md` L9: [table] |  |  |  |  | ⏎ | --- | --- | --- | --- | ⏎ | HttpCode | 错误码 | 错误信息 | 说明 | ⏎ | 200 | - | OK | 请求成功。 | ⏎ | 200 | content.dublication | update the same content | …
  - `development/video-conference-overview.md` L40: [table] |  |  |  | ⏎ | --- | --- | --- | ⏎ | **API** | **API说明** | **API版本** | ⏎ | [创建视频会议](/document/development/create-a-video-conference#) | 创建视频会议。 | 新版 | ⏎ | [关闭视频…
  - `development/video-conference-overview.md` L88: [list] - 直播预约：可提前获得直播链接进行宣传，打通钉钉日历，开播前进行提醒。 ⏎ - 权限自由设置：主播可设置直播为公开可见或企业内可见。 ⏎ - 多群联播：轻松将单场直播同步到多个群。 ⏎ - 实时互动：指出连麦、聊天、点赞、签到、答题等丰富的互动形式。 ⏎ - 直播录制：自动保存直播录像，方便直播内容沉淀和二次传播。 …

### 🚫 D1 — 删收费 / 计费 / 套餐版本（基础/标准/企业/旗舰/高级版）
- 风险：high | 命中：17 篇 | 删除：9 处 | 跳过(表格)：19 处
- 备注：「企业版」单独不算，会和应用类型冲突；当前模式只匹配套餐场景关键词；默认 OFF
- 真正会删除（删除样例前 5）：
  - `development/ai-table-overview.md` L7: [text] AI 表格支持丰富的自动化场景，例如包装批次码与出库编码的智能比对、电商评价实时同步至群聊并沉淀到多维表等，大幅提升企业数据处理效率。自2025年9月1日起，AI表格的服务端OpenAPI已纳入钉钉企业自建应用的付费计量体系，标准版组织每月享有固定免费调用额度，用尽后提供最长5天的缓冲保护期。开发者可结合自动化模板、机…
  - `dingstart/develop-group-chat-coolapp-interactive-card.md` L27: [text] 互动卡片高级版搭建平台更多详情参见[互动卡片高级版搭建平台](/document/download/card-building-platform#)。
  - `dingstart/develop-group-chat-coolapp-interactive-card.md` L40: [heading] ## 互动卡片高级版发送消息
  - `dingstart/develop-group-chat-coolapp-interactive-card.md` L45: [heading] ## 互动卡片高级版发送吊顶卡片
  - `dingstart/group-chat-coolapp-interactive-card.md` L118: [text] 调用服务单API-[发送钉钉互动卡片（高级版）](/document/orgapp/send-interactive-dynamic-cards-1#)接口，实现发送吊顶卡片。
- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：
  - `development/api-createdevicecustomtemplate.md` L644: [table] |  |  |  |  | ⏎ | --- | --- | --- | --- | ⏎ | HttpCode | 错误码 | 错误信息 | 说明 | ⏎ | 400 | param.error | Param Error | 参数错误 | ⏎ | 400 | no.permission | No Permission …
  - `development/api-updatedevicecustomtemplate.md` L653: [table] |  |  |  |  | ⏎ | --- | --- | --- | --- | ⏎ | HttpCode | 错误码 | 错误信息 | 说明 | ⏎ | 400 | param.error | Param Error | 参数错误 | ⏎ | 400 | no.permission | No Permission …
  - `development/create-an-sso-account.md` L24: [table] |  |  |  |  |  | ⏎ | --- | --- | --- | --- | --- | ⏎ | 名称 | 类型 | 是否必填 | 示例值 | 描述 | ⏎ | userid | String | 否 | zhangsan | 员工唯一标识ID（不可修改），长度为1~64个字符。  **说明**     -…

## ⚠️ 整文删建议 — 体积剩 < 30%

> 经过 rules 处理后正文剩余比例低于阈值，文档基本被掏空，建议 `--apply --drop-near-empty` 时整文不写入 clean/，由人工决定是否入库。

| 文件 | 原 (B) | 后 (B) | 剩余比 |
|---|---:|---:|---:|
| `dingstart/self-built-workbench-card-integrated-connector.md` | 376,244 | 1 | 0.0% |
| `dingstart/three-way-workbench-card-integration-connector.md` | 376,158 | 1 | 0.0% |
| `dingstart/add-self-built-interactive-cards-to-the-workbench.md` | 8,165 | 1 | 0.0% |
| `dingstart/support-pc-workbench-1.md` | 8,035 | 1 | 0.0% |
| `dingstart/creation-and-use-of-tripartite-ecological-cards.md` | 7,695 | 1 | 0.0% |
| `dingstart/edit-custom-workbench.md` | 3,705 | 1 | 0.0% |
| `dingstart/call-the-workbench-api.md` | 3,350 | 1 | 0.0% |
| `dingstart/custom-workbench-background-management.md` | 2,476 | 1 | 0.0% |
| `dingstart/publish-effective-custom-workbench.md` | 1,708 | 1 | 0.1% |
| `dingstart/preview-update-custom-workbench.md` | 1,648 | 1 | 0.1% |
| `dingstart/create-a-custom-workbench.md` | 1,392 | 1 | 0.1% |
| `dingstart/create-a-workbench-template.md` | 1,074 | 1 | 0.1% |
| `dingstart/custom-workbench-and-self-built-components.md` | 3,284 | 92 | 2.8% |
| `dingstart/overview-of-workbench-template.md` | 1,154 | 327 | 28.3% |

## 按文件命中 Top 30

- `dingstart/group-chat-coolapp-interactive-card.md` (24 处): B4×24
- `dingstart/develop-group-chat-coolapp-interactive-card.md` (18 处): B4×18
- `development/pure-pull-mode-process-guide.md` (16 处): A1×1, A2×1, B4×14
- `dingstart/private-chat-coolapp-develop-interactive-cards.md` (16 处): B4×16
- `development/server-api-error-codes-1.md` (15 处): A1×11, B1×1, B4×1, B5×1, B8×1
- `dingstart/basic-concepts-beta.md` (14 处): A1×6, A2×3, B1×4, D2×1
- `development/group-assistant-sends-a-message.md` (13 处): A1×8, B4×5
- `development/data-faq.md` (11 处): A1×8, A2×1, B3×1, B9×1
- `development/im-session-overview.md` (11 处): A1×1, B4×10
- `development/contacts-overview.md` (10 处): A2×4, B5×6
- `dingstart/application-visible-range.md` (10 处): A1×4, A2×4, B1×1, B9×1
- `dingstart/group-chat-coolapp-overview.md` (9 处): B4×9
- `dingstart/step-2-develop-three-party-application-components.md` (9 处): A1×3, B1×4, B9×2
- `development/notification-of-work-withdrawal.md` (8 处): A1×3, B1×4, C3×1
- `development/sso-overview.md` (8 处): A2×3, B1×4, D2×1
- `dingstart/create-and-configure-an-application.md` (8 处): A1×1, B1×7
- `dingstart/third-party-enterprise-robots.md` (8 处): A2×2, B1×6
- `development/add-api-permission.md` (7 处): A1×3, B1×4
- `dingstart/interactive-card-message-sending-process.md` (7 处): B4×7
- `development/asynchronous-sending-of-enterprise-session-messages.md` (6 处): A1×1, B1×5
- `development/create-a-group-plug-in.md` (6 处): A1×1, B1×2, B4×3
- `development/development-robot-overview.md` (6 处): B1×5, B4×1
- `development/queries-the-details-of-a-dedicated-account.md` (6 处): A1×1, B1×5
- `dingstart/develop-webapp-frontend.md` (6 处): B1×5, C2×1
- `dingstart/permanent-type-suspended-ceiling.md` (6 处): B4×6
- `dingstart/private-chat-coolapp-overview.md` (6 处): B4×6
- `dingstart/responding-to-interactive-messages.md` (6 处): B4×6
- `dingstart/selfcheck-dingtalk-app.md` (6 处): A1×3, B1×3
- `development/api-gettoken.md` (5 处): B1×5
- `development/common-errors.md` (5 处): A1×1, A2×1, B1×3
- … 还有 307 篇，详见 `changes.json` 或 `preview/{ns}/{slug}.diff.md`
