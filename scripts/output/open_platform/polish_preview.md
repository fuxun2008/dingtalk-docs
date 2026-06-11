# polish 预览（dry-run）

> 生成：2026-06-09 06:39:08 UTC
> 输入：`zh/open/{development,dingstart}/*.mdx` 共 539 篇
> 启用 transformer：dead_links, notes, orphan_lang, empty_headings, image_alts, description_dedup

## 命中汇总

| ID | 规则 | 命中数 | 受影响文件 |
|---|---|---:|---:|
| dead_links | 1. 删 /document/ 死链 → 纯文本 | 499 | 162 |
| notes | 2. **说明**/**重要** → <Note>/<Warning> | 111 | 74 |
| orphan_lang | 3. 孤立 lang 行合并到 fenced code | 63 | 63 |
| empty_headings | 4. 删空标题（无非空内容到下级） | 24 | 20 |
| image_alts | 5. ![image] → ![{nearest_heading}] | 242 | 62 |
| description_dedup | 6. desc == 首段 → 取中段或 title | 465 | 465 |

## 样例（前 8 条 per transformer）

### dead_links — 1. 删 /document/ 死链 → 纯文本

- `development/add-a-role-group.mdx`: [获取企业内部应用的access\_token](/document/development/obtain-orgapp-token#) → `获取企业内部应用的access\_token`
- `development/add-api-permission.mdx`: [新版服务端API](/document/development/how-to-call-apis#) → `新版服务端API`
- `development/add-enterprise-external-contacts.mdx`: [获取企业内部应用的access\_token](/document/development/obtain-orgapp-token#) → `获取企业内部应用的access\_token`
- `development/add-role-information-to-employees-in-batches.mdx`: [获取企业内部应用的access\_token](/document/development/obtain-orgapp-token#) → `获取企业内部应用的access\_token`
- `development/address-book-add-role.mdx`: [获取企业内部应用的access\_token](/document/development/obtain-orgapp-token#) → `获取企业内部应用的access\_token`
- `development/address-book-creation-department-established-department.mdx`: [获取企业内部应用的access\_token](/document/development/obtain-orgapp-token#) → `获取企业内部应用的access\_token`
- `development/address-book-deletion-department.mdx`: [获取企业内部应用的access\_token](/document/development/obtain-orgapp-token#) → `获取企业内部应用的access\_token`
- `development/address-book-employee-operations.mdx`: [获取企业内部应用的access\_token](/document/development/obtain-orgapp-token#) → `获取企业内部应用的access\_token`

### notes — 2. **说明**/**重要** → <Note>/<Warning>

- `development/add-api-permission.mdx`: **重要** → <Warning>: 并非所有接口均可直接开通。部分接口属于非公开开放能力，需提交审批并通过审核后方可使用；另有部分高级接口可能涉及付费或特定资质要求，请以具体接
- `development/add-api-permission.mdx`: **说明** → <Note>: 此解决方法目前仅限于调用新版服务端API时适用。
- `development/add-or-modify-visibility-settings-for-address-book-restrictions.mdx`: **说明** → <Note>: 本接口的限制查看设置与OA后台的限制查看设置是相互独立存储，最终生效结果两边的设置是或的关系。比如：同一个部门，本接口或者OA后台有任意一方
- `development/asynchronous-sending-of-enterprise-session-messages.mdx`: **说明** → <Note>: 如果接口发送成功，接收人没有收到信息，可调用[获取工作通知消息的发送结果](/zh/open/development/gets-the-re
- `development/asynchronous-sending-of-enterprise-session-messages.mdx`: **说明** → <Note>: 详细的限制说明，请参考[调用频率限制](/zh/open/development/call-frequency-limit)。
- `development/authorization-overview.mdx`: **说明** → <Note>: 无论使用哪种权限类型调用DingTalk OpenAPI，都需要先获取对应权限类型的访问凭证accessToken。
- `development/authorization-overview.mdx`: **重要** → <Warning>: 使用不同的accessToken调用同一个API，可能获取的数据有所不同，详情参考具体的API文档说明。
- `development/calendar-participant-process.mdx`: **重要** → <Warning>: 服务端API差异详情参见旧版API VS 新版API。以下接口均使用服务端API接口，SDK下载详情参见服务端SDK下载。

### orphan_lang — 3. 孤立 lang 行合并到 fenced code

- `development/add-a-role-group.mdx`: `curl` → ```curl
- `development/add-enterprise-external-contacts.mdx`: `curl` → ```curl
- `development/add-role-information-to-employees-in-batches.mdx`: `curl` → ```curl
- `development/address-book-add-role.mdx`: `curl` → ```curl
- `development/address-book-creation-department-established-department.mdx`: `curl` → ```curl
- `development/address-book-deletion-department.mdx`: `curl` → ```curl
- `development/address-book-update-department.mdx`: `curl` → ```curl
- `development/asynchronous-sending-of-enterprise-session-messages.mdx`: `curl` → ```curl

### empty_headings — 4. 删空标题（无非空内容到下级）

- `development/check-whether-the-administrator-has-application-management-permissions.mdx`: H2 `接口调用说明`
- `development/dingtalk-retrieve-user-information.mdx`: H2 `**接口调用说明**`
- `development/im-session-overview.mdx`: H3 `**templateId**`
- `development/obtain-the-list-of-robots-in-the-group.mdx`: H2 `**接口调用说明**`
- `development/permission-pointp-mapping-document.mdx`: H1 `权限点映射文档`
- `development/timing-push.mdx`: H2 `高阶用法—订阅式服务`
- `development/video-conference-overview.mdx`: H4 `image`
- `dingstart/configure-secure-domain-name.mdx`: H2 `适用对象`

### image_alts — 5. ![image] → ![{nearest_heading}]

- `development/add-api-permission.mdx:L40`: alt=`image` → `添加普通接口调用权限`
- `development/add-api-permission.mdx:L57`: alt=`image` → `添加特殊接口调用权限`
- `development/address-book-employee-operations.mdx:L7`: alt=`image` → `预期效果`
- `development/asynchronous-address-book-file-content-translation.mdx:L13`: alt=`image` → `接口调用说明`
- `development/asynchronous-address-book-file-content-translation.mdx:L27`: alt=`image` → `接口调用说明`
- `development/calendar-participant-process.mdx:L7`: alt=`image` → `预期效果`
- `development/calendar-participant-process.mdx:L10`: alt=`image` → `预期效果`
- `development/calendar-participant-process.mdx:L13`: alt=`image` → `预期效果`

### description_dedup — 6. desc == 首段 → 取中段或 title

- `development/add-a-meeting-room.mdx`: `调用本接口，在指定日程中预定会议室。` → `预定会议室`
- `development/add-a-role-group.mdx`: `调用本接口，创建角色组。` → `创建角色组`
- `development/add-api-permission.mdx`: `调用钉钉服务端接口前，需要先添加所需接口的调用权限，应用创建后，系统默认添加身份验证和消息通知接口权` → `添加接口调用权限`
- `development/add-enterprise-external-contacts.mdx`: `调用本接口，添加企业外部联系人。` → `添加外部联系人`
- `development/add-folder.mdx`: `调用本接口，在存储空间内添加文件夹。` → `添加文件夹`
- `development/add-or-modify-visibility-settings-for-address-book-restrictions.mdx`: `调用本接口，新增或修改员工、部门、角色限制查看通讯录的设置。` → `新增或修改限制查看通讯录设置`
- `development/add-or-update-the-hidden-settings-of-the-employee-property.mdx`: `调用本接口，设置用户属性可见性。` → `设置用户属性可见性`
- `development/add-permissions-file.mdx`: `调用本接口，根据文件uuid、操作者unionId和权限id等信息，实现权限成员权限的添加。` → `添加权限`
