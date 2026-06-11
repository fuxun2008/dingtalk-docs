# 开放平台 nav 重构报告（官方树版）

## 服务端 API

- 顶级 group 数：8
- 累计 group 数（含嵌套子组）：87
- 总页数：406
- 最大嵌套深度：4
- 剪掉的空 group（官方有但本地无任何对应页）：323
- 官方树有但本地缺 mdx 的页数：1440
    - {'docName': '服务端SDK下载', 'slug': 'download-the-server-side-sdk', 'ns': 'development'}
    - {'docName': 'API 权限列表', 'slug': 'permission-pointp-mapping-document', 'ns': 'development'}
    - {'docName': '概述', 'slug': 'function-description', 'ns': 'development'}
    - {'docName': '授权说明', 'slug': 'applications-authorization', 'ns': 'development'}
    - {'docName': '接入流程', 'slug': 'instructions-for-use', 'ns': 'development'}
    - {'docName': '授权套件SDK', 'slug': 'unified-licensing-suite-sdk', 'ns': 'development'}
    - {'docName': '概述', 'slug': 'event-subscription-overview', 'ns': 'development'}
    - {'docName': '获取推送失败的事件列表', 'slug': 'obtain-the-event-list-of-failed-push-messages', 'ns': 'development'}
    - {'docName': '小程序应用免登', 'slug': 'small-program-application-free-of-registration', 'ns': 'development'}
    - {'docName': '网页应用（H5微应用）免登', 'slug': 'enterprise-internal-application-logon-free', 'ns': 'development'}
    - {'docName': '实现网页方式登录应用（登录第三方网站）', 'slug': 'tutorial-obtaining-user-personal-information', 'ns': 'development'}
    - {'docName': '开发并测试第三方企业网页应用（H5）免登', 'slug': 'web-applications-h5', 'ns': 'development'}
    - {'docName': '开发并测试第三方企业小程序应用免登', 'slug': 'applications-without-registration', 'ns': 'development'}
    - {'docName': '应用管理后台免登', 'slug': 'log-on-site-application-management-backend', 'ns': 'development'}
    - {'docName': '第三方个人应用免登并获取用户信息', 'slug': 'quickstart', 'ns': 'development'}
    - {'docName': '获取微应用后台免登的accessToken', 'slug': 'obtain-the-access-token-of-the-micro-application-background-without-log-on', 'ns': 'development'}
    - {'docName': '获取应用管理后台免登的用户信息', 'slug': 'obtains-the-identity-of-an-application-administrator', 'ns': 'development'}
    - {'docName': '获取用户授权的持久授权码', 'slug': 'persistent-authorization-code', 'ns': 'development'}
    - {'docName': '获取第三方应用授权企业的accessToken', 'slug': 'obtain-the-access-token-of-the-authorized-enterprise-1', 'ns': 'development'}
    - {'docName': '获取第三方个人应用的access_token', 'slug': 'obtain-personal-application', 'ns': 'development'}
    - ... 共 1440 条
- 本地 zh/open/development/ 下未挂入 nav 的孤儿 mdx：0

### 服务端 API — 顶级 group 一览

- **API 调用指南** — 直挂 4 页  (1 子组)
- **认证与授权** — 直挂 0 页  (2 子组)
- **通讯录管理** — 直挂 5 页  (9 子组)
- **日程** — 直挂 2 页  (7 子组)
- **音视频** — 直挂 1 页  (3 子组)
- **AI 表格** — 直挂 3 页  (3 子组)
- **文档/文件** — 直挂 0 页  (8 子组)
- **即时通信** — 直挂 1 页  (3 子组)

## 开发指南

- 顶级 group 数：3
- 累计 group 数（含嵌套子组）：6
- 总页数：10
- 最大嵌套深度：3
- 剪掉的空 group（官方有但本地无任何对应页）：24
- 官方树有但本地缺 mdx 的页数：99
    - {'docName': '应用类型与能力说明', 'slug': 'application-type-introduction', 'ns': 'dingstart'}
    - {'docName': '企业内部应用学习指南', 'slug': 'org-learning-map', 'ns': 'dingstart'}
    - {'docName': '第三方企业应用学习指南', 'slug': 'isv-learning-map', 'ns': 'dingstart'}
    - {'docName': '获取开发者权限', 'slug': 'get-developer-permissions', 'ns': 'dingstart'}
    - {'docName': '应用创建与配置', 'slug': 'create-application', 'ns': 'dingstart'}
    - {'docName': '应用开发与监控', 'slug': 'dingstart-development-application', 'ns': 'dingstart'}
    - {'docName': '部署方式介绍', 'slug': 'introduction-to-deployment-methods', 'ns': 'dingstart'}
    - {'docName': '方式一：启用数据安全中心（推荐）', 'slug': 'enable-data-security-center', 'ns': 'dingstart'}
    - {'docName': '方式二：接入钉钉安全渲染组件', 'slug': 'access-dingtalk-secure-rendering-components', 'ns': 'dingstart'}
    - {'docName': '导入资源到计算巢', 'slug': 'import-resources-compute-nest', 'ns': 'dingstart'}
    - {'docName': '钉钉账号绑定阿里云账号', 'slug': 'bind-a-dingtalk-account-to-an-alibaba-cloud-account', 'ns': 'dingstart'}
    - {'docName': '配置并更新安全域名', 'slug': 'configure-update-secure-domain-name', 'ns': 'dingstart'}
    - {'docName': '钉钉安全域名', 'slug': 'config-domain-name', 'ns': 'dingstart'}
    - {'docName': '（可选）测试应用', 'slug': 'test-dingtalk-app', 'ns': 'dingstart'}
    - {'docName': '发布应用', 'slug': 'publish-dingtalk-application', 'ns': 'dingstart'}
    - {'docName': '自建应用审核配置', 'slug': 'self-built-application-audit-configuration', 'ns': 'dingstart'}
    - {'docName': '应用自检与分发', 'slug': 'selfcheck-dingtalk-app', 'ns': 'dingstart'}
    - {'docName': '安全运营', 'slug': 'safe-operation', 'ns': 'dingstart'}
    - {'docName': '常见问题', 'slug': 'application-configuration-and-management', 'ns': 'development'}
    - {'docName': '客户端SDK介绍', 'slug': 'mini-app-client-jsapi-overview', 'ns': 'dingstart'}
    - ... 共 99 条
- 本地 zh/open/dingstart/ 下未挂入 nav 的孤儿 mdx：0

### 开发指南 — 顶级 group 一览

- **平台简介** — 直挂 1 页
- **开发指南** — 直挂 1 页
- **开发机器人应用** — 直挂 0 页  (2 子组)
