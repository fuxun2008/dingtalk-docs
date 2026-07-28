# AI Table 本地补充词库

> 本文件只收录**官方词库（`official/`）未覆盖**的 AI Table 专项术语，作为翻译时的补充约束。
>
> 维护规则：
> 1. **官方优先**：合并时官方词库覆盖本文件。如果某条术语已被官方收录，请从本文件删除（避免维护两份）。
> 2. **格式**：表格三列 `| 中文 | 英文 | 日文 |`（备注列可选，但只用于第 4 列起，解析时忽略）。
> 3. **多形式 zh**：用 `/` 分隔，例如 `AI 表格 / AI表格`，解析时拆为两个 key 共享同一英文/日文。
> 4. **风格指南**：见文末"风格指南"小节，不要改路径，会被翻译 skill 引用。
>
> 命令：`python3 scripts/glossary_sync.py` 重新合并并生成 `scripts/glossary/zh-en.json` 与 `zh-ja.json`。

## 品牌 / 产品实例

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| AI 表格（一个文档实例） | AI Table | AI Table | 顶层文档容器，与品牌名同形 |

## 核心实体

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 子记录 | subrecord | サブレコード | |
| 冻结列 | freeze column | 列を固定 | |

## 字段类型（AI Table 特有 / 与官方歧义时取此处）

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 日期 | Date | 日付 | AI Table 字段类型语境 |
| 复选框 | Checkbox | チェックボックス | |
| 百分比 | Percent | パーセント | |
| 电话 | Phone | 電話番号 | AI Table 字段类型语境 |
| 按钮 | Button | ボタン | AI Table 字段类型 |
| 修改人 | Last Modified By | 最終更新者 | 字段类型 |

## 视图类型（AI Table）

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 甘特图视图 | Gantt view | ガントチャートビュー | |
| 数据透视表视图 | Pivot view | ピボットビュー | |
| 查询页面 | Query page | クエリページ | |
| 打印视图 | Print layout | 印刷レイアウト | |

## 功能模块（AI Table 一级导航）

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 数据 | Data | データ | AI Table 一级导航语境 |

## 操作动作（AI Table）

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 重命名 | Rename | 名前を変更 | |
| 移动 | Move | 移動 | |
| 编辑描述 | Edit description | 説明を編集 | |
| 邀请协作者 | Invite collaborators | コラボレーターを招待 | |
| 一键启用 | Use this template | このテンプレートを使用 | |
| 保存为模板 | Save as template | テンプレートとして保存 | |
| 发布到模板中心 | Publish to template center | テンプレートセンターに公開 | |
| 全选 | Select all | すべて選択 | |
| 动作 | action | アクション | 自动化语境 |

## 权限 / 协作

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 仅协作者可见 | Collaborators only | コラボレーターのみ | |
| 企业内公开 | Public within organization | 組織内に公開 | |
| 互联网公开 | Public on the internet | インターネットに公開 | |
| 链接分享 | Share via link | リンクで共有 | |
| 二维码分享 | Share via QR code | QRコードで共有 | |

## 自动化 / AI

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 自动化工作流 | automation workflow | 自動化ワークフロー | |
| 循环节点 | loop node | ループノード | |
| 条件自动化 | conditional automation | 条件付き自動化 | |
| 按钮自动化 | button automation | ボタン自動化 | |
| AI 字段模板 | AI field template | AIフィールドテンプレート | |

## 数据集成

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 数据连接器 | data connector | データコネクタ | |
| 跨表同步 | cross-table sync | テーブル間同期 | |
| 钉钉考勤同步 | DingTalk attendance sync | DingTalk 勤怠同期 | |
| 钉钉日程同步 | DingTalk calendar sync | DingTalk カレンダー同期 | |
| 钉钉通讯录同步 | DingTalk contacts sync | DingTalk 連絡先同期 | |
| 钉钉审批同步 | DingTalk approval sync | DingTalk 承認同期 | |
| 钉钉电子表格同步 | DingTalk Spreadsheet sync | DingTalk Spreadsheet 同期 | |
| 钉钉待办同步 | DingTalk Todo sync | DingTalk Todo 同期 | |

## 套餐 / 版本

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 免费版 | Free plan | Freeプラン | |
| 企业版 | Business plan | Businessプラン | |
| 旗舰版 | Enterprise plan | Enterpriseプラン | |

## DingTalk Docs 专项术语（产品名 / 子品牌）

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 钉钉文档 | DingTalk Docs | DingTalk Docs | 文档子产品的品牌名；不译为 ドキュメント |
| 钉钉表格 | DingTalk Spreadsheet | DingTalk Spreadsheet | 表格子产品的品牌名 |
| 钉钉脑图 / 智能脑图 / 思维导图 | DingTalk Mind | DingTalk Mind | 脑图子产品 |
| 钉钉白板 / 智能白板 | DingTalk Whiteboard | DingTalk Whiteboard | 白板子产品 |
| 知识库 | Knowledge Base | ナレッジベース | |
| 群知识库 | Group Knowledge Base | グループナレッジベース | |
| 知识小组 | Knowledge Group | ナレッジグループ | |
| 模板中心 | Template Center | テンプレートセンター | |
| 文档 AI / 文档AI | Doc AI | ドキュメント AI | DingTalk Docs 内置 AI 能力 |
| 在线文档 | Online document | オンラインドキュメント | 通用功能名 |
| 团队协作 | Team collaboration | チームコラボレーション | |
| 协作 | Collaboration | コラボレーション | |
| 协作者 | Collaborator | コラボレーター | |

## DingTalk Docs 文档结构 / 导航

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 新手指南 | Getting started | はじめに | |
| 快速上手 | Quickstart | クイックスタート | |
| 功能更新 | Release notes | リリースノート | |
| 管理员指引 | Admin guide | 管理者ガイド | |
| 客户案例 | Customer stories | 導入事例 | 日文按业界惯用译法 |
| 最佳实践 | Best practices | ベストプラクティス | |
| 进阶玩法 | Advanced | 高度な使い方 | |

## DingTalk Docs 编辑 / 协作功能

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 评论 | Comment | コメント | |
| 划词评论 | Inline comment | インラインコメント | |
| 版本历史 / 文档历史 | Version history | バージョン履歴 | |
| 版本恢复 | Restore version | バージョンを復元 | |
| 锁定段落 | Lock paragraph | 段落をロック | |
| 目录 | Table of contents | 目次 | |
| 大纲 | Outline | アウトライン | |
| 子页面 | Subpage | サブページ | |
| 实时编辑 | Real-time editing | リアルタイム編集 | |
| 离线编辑 | Offline editing | オフライン編集 | |
| 多人协作 | Multi-user collaboration | 複数ユーザーでのコラボレーション | |

## DingTalk Spreadsheet 专项

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 工作表 | Sheet | シート | |
| 工作簿 | Workbook | ワークブック | |
| 单元格 | Cell | セル | |
| 行 | Row | 行 | |
| 列 | Column | 列 | |
| 公式 | Formula | 数式 | |
| 函数 | Function | 関数 | |
| 数据透视表 | Pivot table | ピボットテーブル | |
| 条件格式 | Conditional formatting | 条件付き書式 | |
| 数据验证 | Data validation | データ検証 | |
| 冻结窗格 | Freeze panes | ウィンドウ枠の固定 | |

## DingTalk Docs 导入 / 导出

| 中文 | 英文 | 日文 | 备注 |
|---|---|---|---|
| 导出为 PDF | Export to PDF | PDFにエクスポート | |
| 导出为 Word | Export to Word | Wordにエクスポート | |
| 导出为图片 | Export as image | 画像としてエクスポート | |
| 打印 | Print | 印刷 | |
| 模板 | Template | テンプレート | 通用 |

---

## 风格指南（被翻译 skill 引用）

### 英文

- **美式英语**（color 不写 colour，realize 不写 realise）
- **句式**：直陈、命令式（"Click...", "Select..."），不用敬语堆砌
- **标题**：sentence case（仅首字母大写 + 专有名词大写），不用 Title Case：✅ "Create a new view" ❌ "Create A New View"
- **数字**：用阿拉伯数字 + 千分位（10,000 而非 10000）
- **代码 / 快捷键**：保留反引号格式（`` `Ctrl` + `/` ``）

### 日文

- **句末**：用「である」体或敬体「です・ます」均可，**整篇统一**，不要混用
- **标题**：体言止め（名词结尾），不用动词收尾
- **括号**：用全角「」『』 而非 ""，半角英文术语前后留半角空格
- **数字**：阿拉伯数字 + 半角逗号千分位
- **数据库 / 表格通用术语**：业界惯用译法优先（view → ビュー、record → レコード、field → フィールド、dashboard → ダッシュボード、form → フォーム、filter → フィルター、template → テンプレート）

### 品牌口径（强约束，三语共通）

- **DingTalk**：不翻译为 Ding Talk / 钉钉
- **AI Table**：统一首字母 + 空格；不写 Aitable / Ai-Table（避免与第三方 apitable.com 混淆）
- **AI Assistant** / **DingTalk Docs**：保持原样

### 跨页链接

- 内部链接用相对路径 `/aitable/...`
- 指向尚未翻译的目标页时，链向中文 `/zh/aitable/...` 作为兜底（试点期间临时方案）

---

# 开放平台 (Open Platform / OpenAPI)

> 本节为钉钉开放平台开发者文档专项术语，对标 Google API Docs / Microsoft Learn 的开发者文档命名习惯。
>
> **三条强约束（也写进了 `translate_mdx_batch.py` 的 `OPEN_PLATFORM_RULES`，prompt 层双保险）**：
>
> 1. **「机器人」⇒ `Bot` / `ボット`**（单数，DingTalk 聊天机器人语境，**绝不译为 Robot**）。official 词库收的是 `Bots`（复数语境），开放平台单实体一律 `Bot`。
> 2. **英文 Heading 使用 Sentence case + 专有名词大写**（DingTalk、API、SDK、OAuth、Webhook、JSAPI、HTTP、URL、JSON、AccessToken 等保持原大小写）。✅ `Get the access token of an internal app`  ❌ `get the access token of an internal app`  ❌ `Get The Access Token Of An Internal App`
> 3. **API 契约字符串不译**：HTTP 动词 / 状态码 / Header 名 / Content-Type / JSON 字段名 / 路径参数名 / 查询参数名 / 错误码字符串 / API 端点 URL 全部保持原样。代码示例中的注释可译，但变量名 / 函数名 / SDK 方法名不译。

## 应用类型 / 平台分类

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 企业内部应用 | Internal app | 社内アプリ | Aplikasi internal | 区别于第三方应用；专有概念 |
| 第三方应用 | Third-party app | サードパーティアプリ | Aplikasi pihak ketiga |  |
| 第三方企业应用 | Third-party enterprise app | サードパーティ社内アプリ | Aplikasi perusahaan pihak ketiga | 与"第三方应用"语义微差，按上下文取舍 |
| 第三方个人应用 | Third-party personal app | サードパーティ個人アプリ | Aplikasi personal pihak ketiga |  |
| 第三方组件应用 | Third-party component app | サードパーティコンポーネントアプリ | Aplikasi komponen pihak ketiga |  |
| H5 应用 / H5应用 | H5 app | H5アプリ | Aplikasi H5 | 钉钉术语，不译为 HTML5 |
| 微应用 | Micro app | マイクロアプリ | Aplikasi mikro |  |
| 小程序 | Mini program | ミニプログラム | Mini program |  |
| 服务窗 | Service account | サービスアカウント | Akun layanan |  |
| 应用类型 | App type | アプリタイプ | Jenis aplikasi |  |

## 鉴权 / 凭证 / OAuth

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 鉴权 | Authentication | 認証 | Autentikasi | 区别于授权 Authorization |
| 授权 | Authorization | 認可 | Otorisasi |  |
| 鉴权方式 | Authentication method | 認証方法 | Metode autentikasi |  |
| 凭证 | Credential | 認証情報 | Kredensial |  |
| 应用凭证 | App credential | アプリ認証情報 | Kredensial aplikasi |  |
| 访问凭证 | Access credential | アクセス認証情報 | Kredensial akses |  |
| 调用凭证 | API credential | API 認証情報 | Kredensial API | 业务文档常用替代说法 |
| accessToken / Access Token / 访问令牌 | access token | アクセストークン | access token | 文中行文表达；JSON 字段保持 `accessToken` 原样不译 |
| access_token | access_token | access_token | access_token | JSON 字段名 / 参数名，**保持原样不译** |
| refreshToken / Refresh Token / 刷新令牌 | refresh token | リフレッシュトークン | refresh token | 同上 |
| jsapi_ticket | jsapi_ticket | jsapi_ticket | jsapi_ticket | 保持原样 |
| corpId | corpId | corpId | corpId | 保持原样 |
| suiteKey / suiteSecret / suiteTicket | suiteKey / suiteSecret / suiteTicket | suiteKey / suiteSecret / suiteTicket | suiteKey / suiteSecret / suiteTicket | 保持原样 |
| 应用 Client ID / Client ID | client ID | クライアント ID | client ID | 文中行文；JSON 字段 `client_id` 保持原样 |
| 应用 Client Secret / Client Secret | client secret | クライアントシークレット | client secret | 同上；JSON 字段 `client_secret` 保持原样 |
| AppKey | AppKey | AppKey | AppKey | **保持单词不拆**；official "App Key" 是旧译，本批次按一体词 |
| AppSecret | AppSecret | AppSecret | AppSecret | 同上 |
| 签名 | signature | 署名 | Tanda tangan | official 已有，沿用 |
| 时间戳 | timestamp | タイムスタンプ | Stempel waktu |  |
| 随机串 / Nonce / nonce | nonce | nonce | nonce | 保持小写 |
| 加签 | sign request | リクエスト署名 | Tanda tangani permintaan | 动词短语 |
| 验签 | verify signature | 署名検証 | Verifikasi tanda tangan |  |
| OAuth 2.0 授权 | OAuth 2.0 authorization | OAuth 2.0 認可 | Otorisasi OAuth 2.0 |  |
| 授权码 / authorization_code | authorization code | 認可コード | authorization_code | JSON 字段 `authorization_code` 保持原样 |
| 授权类型 / grant_type | grant type | 認可タイプ | grant_type | JSON 字段 `grant_type` 保持原样 |
| 客户端模式 / client_credentials | client credentials | クライアント資格情報 | client_credentials | 同上 |
| 单点登录 / SSO | single sign-on | シングルサインオン | Single Sign-On |  |
| 免登 | silent login | サイレントログイン | Login senyap | DingTalk 专有概念 |
| 扫码登录 | QR code login | QR コードログイン | Login kode QR |  |
| 应用授权 | App authorization | アプリ認可 | Otorisasi App |  |

## 权限 / 范围 / 调用控制

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 权限点 | permission scope | 権限スコープ | Cakupan izin | 钉钉开放平台核心概念 |
| 权限范围 | permission scope | 権限スコープ | Cakupan izin | 与"权限点"同义 |
| 接口权限 | API permission | API 権限 | Izin API |  |
| 申请权限 | Request permission | 権限をリクエスト | Minta izin | 动词；avoid "apply for" |
| 授予权限 | Grant permission | 権限を付与 | Berikan izin |  |
| 撤回权限 | Revoke permission | 権限を取り消し | Cabut izin |  |
| 调用频率 / API 调用频率 | rate limit | レート制限 | Batas laju | 业界标准译法 |
| 限流 | rate limit | レート制限 | Batas laju | 同上 |
| 限速 | throttling | スロットリング | Pembatasan laju | 偏严格场景 |
| 调用次数 | call count | 呼び出し回数 | Jumlah panggilan |  |
| 配额 | quota | クォータ | Kuota |  |
| 调用上限 | rate limit | レート制限 | Batas laju |  |
| 命名空间 | namespace | 名前空間 | Namespace |  |
| 通讯录可见范围 | contact visibility scope | 連絡先可視範囲 | Cakupan visibilitas kontak | DingTalk 通讯录术语 |

## HTTP / 请求 / 响应（API 文档骨架词）

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 请求 | request | リクエスト | Permintaan |  |
| 响应 | response | レスポンス | Respons |  |
| 请求方式 / 请求方法 | HTTP method | HTTP メソッド | Metode HTTP |  |
| 接口地址 / 接口 URL | HTTP URL | HTTP URL | URL HTTP |  |
| 请求头 | request header | リクエストヘッダー | Header permintaan |  |
| 响应头 | response header | レスポンスヘッダー | Header respons |  |
| 请求体 | request body | リクエストボディ | Isi permintaan (request body) |  |
| 响应体 | response body | レスポンスボディ | Isi respons (response body) |  |
| 请求参数 | request parameter | リクエストパラメータ | Parameter permintaan |  |
| 响应参数 | response parameter | レスポンスパラメータ | Parameter respons |  |
| 路径参数 | path parameter | パスパラメータ | Parameter jalur |  |
| 查询参数 | query parameter | クエリパラメータ | Parameter kueri |  |
| 请求示例 | Request example | リクエスト例 | Contoh permintaan | Heading 用法（Sentence case） |
| 响应示例 | Response example | レスポンス例 | Contoh respons |  |
| 调用示例 | Code example | コード例 | Contoh kode | 含 SDK 调用代码场景 |
| 返回示例 | Response example | レスポンス例 | Contoh respons | 与"响应示例"同义合并 |
| 错误示例 | Error response example | エラーレスポンス例 | Contoh respons error |  |
| 调用接口 | Call the API | API を呼び出す | Panggil API | 动词短语 |
| 接入流程 | Integration flow | 統合フロー | Alur integrasi |  |
| 接入说明 | Integration guide | 統合ガイド | Panduan integrasi |  |
| 接口说明 | API description | API 説明 | Deskripsi API |  |
| 接口调用说明 | API call description | API 呼び出し説明 | Deskripsi panggilan API |  |
| 调用说明 | Usage notes | 使用上の注意 | Catatan penggunaan |  |
| 字段类型 | Field type | フィールドタイプ | Tipe field | official 有，但 ja 拼写有误 (フォールド)，本批次纠正 |
| 字段名 | Field name | フィールド名 | Nama field |  |
| 字段含义 | Field description | フィールドの説明 | Deskripsi field |  |
| 是否必填 | Required | 必須 | Wajib | 表格列头惯用 |
| 必填 | Required | 必須 | Wajib |  |
| 非必填 | Optional | 任意 | Opsional |  |
| 选填 | Optional | 任意 | Opsional |  |
| 默认值 | Default | デフォルト | Default |  |
| 示例值 | Example | 例 | Contoh |  |
| 取值范围 | Allowed values | 許容値 | Nilai yang diizinkan |  |
| 枚举值 | Enum values | 列挙値 | Nilai enum |  |
| 数据类型 | Data type | データ型 | Tipe data |  |
| 数组 | array | 配列 | array |  |
| 对象 | object | オブジェクト | object |  |
| 字符串 | string | 文字列 | string |  |
| 数字 | number | 数値 | number |  |
| 布尔 | boolean | 真偽値 | boolean |  |
| 整型 | integer | 整数 | integer |  |
| 长整型 | long | long | long |  |
| 浮点型 | float | 浮動小数点 | float |  |
| 时间戳 (毫秒) | Unix timestamp (ms) | Unix タイムスタンプ (ミリ秒) | Unix timestamp (ms) |  |
| 时间戳 (秒) | Unix timestamp (s) | Unix タイムスタンプ (秒) | Unix timestamp (s) |  |

## 错误处理

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 错误码 | error code | エラーコード | Kode error |  |
| 错误信息 | error message | エラーメッセージ | Pesan error |  |
| 异常 | error | エラー | Error | "异常"在钉钉文档语境多指 API 错误，不译 exception |
| 异常处理 | error handling | エラーハンドリング | Penanganan error |  |
| 错误处理 | error handling | エラーハンドリング | Penanganan error |  |
| 调用失败 | The call failed | 呼び出しに失敗 | Panggilan gagal |  |
| 调用成功 | The call succeeded | 呼び出しに成功 | Panggilan berhasil |  |
| 业务错误 | business error | ビジネスエラー | Error bisnis |  |
| 系统错误 | system error | システムエラー | Error sistem |  |
| 参数错误 | parameter error | パラメータエラー | Error parameter |  |
| 权限不足 | insufficient permissions | 権限不足 | Izin tidak memadai |  |
| 鉴权失败 | authentication failed | 認証失敗 | Autentikasi gagal |  |
| 令牌过期 | token expired | トークンの有効期限切れ | Token kedaluwarsa |  |
| 重试 | retry | 再試行 | Coba lagi |  |
| 重试机制 | retry mechanism | リトライ機構 | Mekanisme coba-lagi |  |
| 指数退避 | exponential backoff | 指数バックオフ | Exponential backoff |  |

## 事件 / 回调 / Webhook

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 事件 | event | イベント | Peristiwa |  |
| 事件订阅 | event subscription | イベントサブスクリプション | Langganan peristiwa |  |
| 事件类型 | event type | イベントタイプ | Tipe peristiwa |  |
| 事件回调 | event callback | イベントコールバック | Callback peristiwa |  |
| 回调 | callback | コールバック | Callback |  |
| 回调地址 / 回调 URL | callback URL | コールバック URL | URL callback |  |
| 同步回调 | synchronous callback | 同期コールバック | Callback sinkron |  |
| 异步回调 | asynchronous callback | 非同期コールバック | Callback asinkron |  |
| 服务端事件 | server event | サーバーイベント | Peristiwa server |  |
| 推送 | push | プッシュ | Push |  |
| 消息推送 | Message push | メッセージプッシュ | Push pesan |  |
| 注册回调 | Register a callback | コールバックを登録 | Daftarkan callback | 动词短语 |
| 注销回调 | Unregister a callback | コールバックを解除 | Batalkan pendaftaran callback |  |
| 群机器人 Webhook | Group bot webhook | グループボット Webhook | Webhook bot grup | "群机器人 → Group bot" |
| outgoing 机制 | outgoing webhook | アウトゴーイング Webhook | Webhook keluar (outgoing webhook) |  |

## 服务端 API / JSAPI / SDK

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 服务端 API / 服务端API | Server API | サーバー API | Server API | DingTalk 开放平台一级分类；保持半角空格 |
| 服务端 | Server-side | サーバーサイド | Sisi server |  |
| 客户端 | Client-side | クライアントサイド | Sisi klien |  |
| 新版服务端 API | Server API v2 | サーバー API v2 | Server API v2 | 钉钉的"新版"特指 v2 |
| 旧版 API | Legacy API | 旧版 API | API lama |  |
| JSAPI | JSAPI | JSAPI | JSAPI | DingTalk 前端 JS 桥；保持原样不译 |
| H5 JSAPI | H5 JSAPI | H5 JSAPI | H5 JSAPI |  |
| 小程序 JSAPI | Mini program JSAPI | ミニプログラム JSAPI | JSAPI mini program |  |
| SDK | SDK | SDK | SDK |  |
| 服务端 SDK | Server SDK | サーバー SDK | Server SDK |  |
| 接入指南 | Integration guide | 統合ガイド | Panduan integrasi |  |
| 调用指南 | Usage guide | 使用ガイド | Panduan penggunaan |  |
| 开发指南 | Developer guide | 開発者ガイド | Panduan developer |  |
| 快速开始 | Quickstart | クイックスタート | Panduan cepat |  |
| 入门指南 | Getting started | はじめに | Memulai |  |

## 机器人 / Bot（**关键强约束：永远 Bot，绝不 Robot**）

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 机器人 | Bot | ボット | Bot | **强约束**：DingTalk 聊天机器人语境单数；official "Bots" 仅用在列表性语境 |
| 钉钉机器人 | DingTalk Bot | DingTalk ボット | DingTalk Bot |  |
| 群机器人 | Group bot | グループボット | Bot grup |  |
| 智能机器人 | Bot | ボット | Bot |  |
| 单聊机器人 | Single-chat bot | シングルチャットボット | Bot obrolan tunggal |  |
| 企业机器人 | Enterprise bot | 社内ボット | Bot perusahaan |  |
| 自定义机器人 | Custom bot | カスタムボット | Bot kustom |  |
| 机器人消息 | Bot message | ボットメッセージ | Pesan Bot |  |
| 机器人卡片 | Bot card | ボットカード | Kartu Bot |  |
| Stream 模式机器人 | Stream-mode bot | Stream モードボット | Bot mode Stream |  |
| 机器人接入 | Bot integration | ボット統合 | Integrasi Bot |  |

## 即时通信 / 消息 / 卡片

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 即时通信 / IM | IM | IM | IM | 保持缩写 |
| 群 / 群组 | group | グループ | Grup | "群"高频；"群组"二字时同义合并 |
| 群成员 | group member | グループメンバー | Anggota grup |  |
| 群主 | group owner | グループオーナー | Pemilik grup |  |
| 群管理员 | group admin | グループ管理者 | Admin grup |  |
| 会话 | conversation | 会話 | Percakapan | official "Chat" 偏聊天界面；"会话 ID / 会话类型"语境用 conversation 更标准 |
| 会话 ID | conversation ID | 会話 ID | ID percakapan |  |
| 会话类型 | conversation type | 会話タイプ | Tipe percakapan |  |
| 单聊 | one-to-one chat | 1 対 1 チャット | Chat satu lawan satu | official "Direct Message" 偏私信平台用语；DingTalk 开放平台沿用 one-to-one |
| 群聊 | group chat | グループチャット | Chat grup | official 一致 |
| 消息 | message | メッセージ | Pesan |  |
| 主动发送消息 | Send a message | メッセージを送信 | Kirim pesan |  |
| 撤回消息 | Recall a message | メッセージを取り消し | Tarik pesan |  |
| 模板消息 | Template message | テンプレートメッセージ | Pesan template |  |
| 工作通知 | Work notification | 業務通知 | Notifikasi kerja | DingTalk 专有概念 |
| 普通消息 | Plain message | 通常メッセージ | Pesan teks biasa |  |
| 卡片消息 | Card message | カードメッセージ | Pesan kartu |  |
| 交互式卡片 | Interactive card | インタラクティブカード | Kartu interaktif |  |
| 卡片回调 | Card callback | カードコールバック | Callback kartu |  |
| AI 卡片 | AI card | AI カード | Kartu AI |  |
| @消息 | Mention | メンション | Sebut (Mention) |  |
| @所有人 | Mention all | 全員メンション | Sebut semua |  |

## 通讯录扩展（official 已覆盖大部分，仅补缺口）

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 子部门 | sub-department | 子部門 | Subdepartemen |  |
| 父部门 | parent department | 親部門 | Departemen induk |  |
| 根部门 | root department | ルート部門 | Departemen root |  |
| 部门 ID | department ID | 部門 ID | ID departemen |  |
| 部门列表 | department list | 部門リスト | Daftar departemen |  |
| 用户 ID / userid | user ID | ユーザー ID | ID pengguna | JSON 字段 `userid` 保持原样 |
| 员工 | employee | 従業員 | Karyawan | 等同 user 时优先 user |
| 成员 | member | メンバー | Anggota | 群成员、部门成员场景 |
| 角色组 | role group | ロールグループ | Grup peran |  |
| 外部联系人 | external contact | 社外連絡先 | Kontak eksternal |  |
| 企业账号 | enterprise account | 企業アカウント | Akun perusahaan |  |
| 企业 | organization | 組織 | Organisasi | DingTalk 国际化语境 organization 比 enterprise 更通用 |
| 组织 | organization | 組織 | Organisasi |  |
| 组织 ID / corpId | organization ID | 組織 ID | ID organisasi | JSON 字段 `corpId` 保持原样 |
| unionId | unionId | unionId | unionId | 保持原样 |

## 日程 / 会议 / 音视频

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 日程 | event | 予定 | Peristiwa | official 已有 |
| 日历 | calendar | カレンダー | Kalender |  |
| 日程参与者 | event attendee | 予定参加者 | Peserta acara |  |
| 忙闲 | free/busy | フリー/ビジー | Senggang/sibuk |  |
| 会议 | conference | 会議 | Konferensi |  |
| 会议室 | meeting room | 会議室 | Ruang rapat |  |
| 智能会议室 | Smart meeting room | スマート会議室 | Ruang rapat pintar |  |
| 视频会议 | video conference | ビデオ会議 | Konferensi video |  |
| 入会 | join the conference | 会議に参加 | Gabung ke konferensi |  |
| 主持人 | host | ホスト | Host |  |
| 与会者 | participant | 参加者 | Partisipan |  |

## 文档 / 文件 / 知识库

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 文档 | document | ドキュメント | Dokumen | 通用语境；品牌名 DingTalk Docs 保留 |
| 文件 | file | ファイル | File |  |
| 文件夹 | folder | フォルダ | Folder |  |
| 文件节点 / dentry | dentry | dentry | dentry | 钉钉文档 API 内部数据结构名，保持不译 |
| 工作空间 / workspace | workspace | ワークスペース | Ruang kerja |  |
| 知识库 | Knowledge Base | ナレッジベース | Basis Pengetahuan | 与已有一致 |
| 上传 | Upload | アップロード | Unggah |  |
| 下载 | Download | ダウンロード | Unduh |  |
| 分块上传 | Multipart upload | マルチパートアップロード | Unggahan multipart |  |
| 初始化分块上传 | Initiate a multipart upload | マルチパートアップロードを開始 | Inisiasi unggahan multipart |  |
| 上传完成 | Complete upload | アップロードを完了 | Selesaikan unggahan |  |
| 文件预览 | File preview | ファイルプレビュー | Pratinjau file |  |
| 转码 | Transcode | トランスコード | Transkode |  |

## AI 表格 / 数据 / 字段

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 数据表 | data table | データテーブル | Tabel data | open 语境用 data table 而非 base，避免与 AI Table 品牌词混淆 |
| 数据表 ID | data table ID | データテーブル ID | ID tabel data |  |
| 字段 | field | フィールド | Bidang |  |
| 记录 | record | レコード | Rekaman |  |
| 工作表 | sheet | シート | Sheet | DingTalk Spreadsheet 语境 |
| 单元格 | cell | セル | Sel |  |

## 待办 / 审批 / 其他业务

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 待办 | task | タスク | Tugas | official "To-Do" 在国际版用 task 更普适 |
| 待办列表 | Task list | タスクリスト | Daftar tugas |  |
| 审批 | approval | 承認 | Persetujuan | official 已有 |
| 审批单 | Approval form | 承認フォーム | Formulir persetujuan |  |
| 审批流程 | Approval workflow | 承認ワークフロー | Alur kerja persetujuan |  |

## Heading 大小写规范实例（专业性体现）

| ✅ 正确 | ❌ 错误 | 说明 |
|---|---|---|
| `Obtain the access token of an internal app` | `Obtain The Access Token Of An Internal App` | 不使用 Title Case |
| `Obtain the access token of an internal app` | `obtain the access token of an internal app` | 首字母必须大写 |
| `Get user by userid` | `Get user by userId` / `Get User By UserId` | `userid` 是 JSON 字段名（DingTalk 真实字段全小写），保持原样 |
| `Call the JSAPI` | `Call the jsapi` / `Call The Jsapi` | JSAPI 是缩写，全大写 |
| `Integrate with OAuth 2.0` | `Integrate With Oauth 2.0` | OAuth 是品牌专有，按官方大小写 |
| `DingTalk Bot quickstart` | `Dingtalk bot quickstart` / `DingTalk bot QuickStart` | DingTalk 品牌词；quickstart 一个词 |
| `Webhook callback events` | `webhook callback events` / `WebHook Callback Events` | Webhook 是专有词，首字母大写；其余 sentence case |

## 日文标点 / 风格补充

- API 类专有词前后**留半角空格**：`access token を取得する` ✓ ／`access tokenを取得する` ✗
- 命令式动词偏好「〜します」/「〜してください」短句，避免「〜することができます」滥用
- 表格列头用名词：「必須」「タイプ」「説明」「例」

## 宜搭（Yida）专项术语（品牌 / 产品）

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 宜搭 | Yida | Yida | Yida | 品牌词不译，与 yidaapps.com 域名一致；禁止 Easy Build / YiDa |
| 专属宜搭 | Yida Dedicated | Yida専用版 | Yida Dedicated |  |
| 酷应用 | Cool App | クールアプリ | Cool App | 钉钉官方能力名 |
| 低代码 | low-code | ローコード | low-code |  |
| 连接器工厂 | Connector Factory | コネクタファクトリー | Connector Factory |  |
| 模板中心 | Template Center | テンプレートセンター | Pusat Template |  |

## 宜搭 表单 / 组件

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 普通表单 | regular form | 通常フォーム | formulir biasa |  |
| 流程表单 | workflow form | ワークフローフォーム | formulir alur kerja |  |
| 子表单 | subform | サブフォーム | subformulir |  |
| 关联表单 | associated form | 関連フォーム | formulir terkait |  |
| 表单组件 | form component | フォームコンポーネント | komponen formulir |  |
| 成员组件 | member component | メンバーコンポーネント | komponen anggota |  |
| 明细组件 | detail component | 明細コンポーネント | komponen rincian |  |
| 表单设计器 | form designer | フォームデザイナー | desainer formulir |  |
| 页面设计器 | page designer | ページデザイナー | desainer halaman |  |
| 自定义页面 | custom page | カスタムページ | halaman kustom |  |
| 数据管理页 | data management page | データ管理ページ | halaman manajemen data |  |
| 表单实例 | form instance | フォームインスタンス | instans formulir |  |
| 公式函数 | formula function | 数式関数 | fungsi formula |  |
| 提交校验 | submission validation | 送信時検証 | validasi pengiriman |  |
| 数据校验 | data validation | データ検証 | validasi data |  |
| 数据联动 | data linkage | データ連動 | keterkaitan data |  |

## 宜搭 流程 / 报表 / 页面

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 流程设计 | workflow design | ワークフロー設計 | desain alur kerja |  |
| 流程实例 | workflow instance | ワークフローインスタンス | instans alur kerja |  |
| 审批人 | approver | 承認者 | penyetuju |  |
| 聚合表 | aggregate table | 集計テーブル | tabel agregat |  |
| 报表 | report | レポート | laporan | 宜搭报表设计语境 |
| 门户 | portal | ポータル | portal |  |
| 门户设计 | portal design | ポータル設計 | desain portal |  |
| JS 动作面板 | JS action panel | JS アクションパネル | panel aksi JS |  |

## 宜搭 管理 / 平台

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 平台管理 | platform management | プラットフォーム管理 | manajemen platform |  |
| 权限组 | permission group | 権限グループ | grup izin |  |
| 应用分发 | app distribution | アプリ配布 | distribusi aplikasi |  |
| 工作空间 | workspace | ワークスペース | ruang kerja | 专属宜搭语境 |
| 集成自动化 | integration & automation | 統合と自動化 | integrasi & otomatisasi |  |
| 集成&自动化 | Integration & Automation | 統合と自動化 | Integrasi & Otomatisasi | 分组名 |

## 宜搭 套餐版本

| 中文 | 英文 | 日文 | 印尼语 | 备注 |
|---|---|---|---|---|
| 轻享版 | Basic edition | ベーシック版 | Edisi Basic | 宜搭套餐 |
| 专业版 | Professional edition | プロフェッショナル版 | Edisi Professional | 宜搭套餐 |
| 专属版 | Dedicated edition | 専用版 | Edisi Dedicated | 宜搭套餐 |
