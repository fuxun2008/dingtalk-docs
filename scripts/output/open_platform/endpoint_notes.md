# open.dingtalk.com 抓取端点嗅探笔记

> 嗅探日期：2026-06-09
> 方法：chrome-devtools MCP 打开示例页 + list_network_requests + get_network_request

## 核心结论

正文 + 目录均为**阿里云 OSS 静态文件**，**anonymous + 无 cookie + 无 referer** 即可获取。无需 playwright、无需登录、无需账号。

## 关键 endpoint

### 1. 目录元数据（每 namespace 一份）

```
GET https://icms-document.oss-cn-beijing.aliyuncs.com/zh-CN/dingtalk/{namespace}/meta.json
```

实测：
- `development` namespace：HTTP 200，1.02 MB，**2478 个 doc + 535 个 directory**
- `dingstart` namespace：HTTP 200，68 KB，**146 个 doc + 42 个 directory**

**JSON 树形结构**（递归）：
```json
{
  "title": "应用开发",
  "slug": "development",
  "spaceSlug": "dingtalk",
  "topics": [
    {
      "id": 5985137,
      "parentId": 0,
      "type": "directory",   // 或 "doc"
      "title": "服务端 API",
      "slug": "server",
      "sort": 4,
      "children": [
        {
          "type": "doc",
          "title": "概述",
          "slug": "contacts-overview",     // 叶子的 slug 用于拼正文 URL
          "shortDescription": "...",
          "labels": [...]
        }
      ]
    }
  ]
}
```

### 2. 正文 HTML（每篇一份）

```
GET https://icms-document.oss-cn-beijing.aliyuncs.com/zh-CN/dingtalk/{namespace}/topics/{slug}.html
```

示例：
```
https://icms-document.oss-cn-beijing.aliyuncs.com/zh-CN/dingtalk/development/topics/server-api-calling-guide.html
→ HTTP 200, ~22.8 KB
```

**HTML 形态**：阿里 ICMS 文档系统服务端渲染，标准语义 HTML。
- 标题层级：`<h1 class="title">` / `<h2>` / `<h3>` 等
- 段落：`<p>`，行内强调：`<b>` / `<span style="color:rgb(23,26,29)">`
- 列表：`<ol>` / `<ul>` + `<li>`
- 表格：`<table>` + `<colgroup>` + `<tbody>` + `<tr>` + `<td>`（支持 colspan / rowspan）
- 代码：`<code class="code">` / `<code class="code doc-code">`（行内 / 块级）
- 提示框：`<div type="note" class="note note-note">` / `class="note note-important"` ← 后续可映射 Mintlify `<Note>` / `<Warning>`
- 图片：`<img src="https://help-static-aliyun-doc.aliyuncs.com/assets/img/zh-CN/.../pXXXXXX.png">`
- 内链：`<a href="/document/development/{slug}#" class="xref">`（站内交叉引用）
- 外链：`<a href="https://oa.dingtalk.com/" target="_blank">`
- 锚点：节点带 `id="hash"`，可用 `#hash` 跳转

### 3. 辅助 endpoint（本次抓取不需要，留作记录）

| URL | 用途 | 是否需要 |
|---|---|---|
| `https://open.dingtalk.com/api/docCenter/getDocInfoByUrl?docUrl=...` | 单篇元信息（标题/slug） | ❌ meta.json 已覆盖 |
| `https://open.dingtalk.com/api/docCenter/getDocPageGroupList` | tab/group 列表 | ❌ |
| `https://open.dingtalk.com/api/getDocumentMark?...` | 文档打分 | ❌ |
| `https://open.dingtalk.com/api/isLogin` | 登录态检查 | ❌ |

## 关于范围的发现

- **development namespace 全量 2478 篇** ≫ 指导 md 的 410 篇精选
- 用户指导 md 只列了「服务端 API」一级分组下的子集（剔除了客户端 API、事件订阅、新版服务端、历史文档等）
- **本次抓取必须严格按指导 md 清单走**（410 篇），不能用 development meta.json 全量
- dingstart namespace 146 篇符合"先全量抓 raw、后续约束阶段过滤"的策略，直接全量

## 请求 headers（参考）

实测 anonymous（无 cookie / 无 referer）即可。但完整匹配浏览器请求可避免被风控：

```http
GET .../meta.json HTTP/1.1
Host: icms-document.oss-cn-beijing.aliyuncs.com
Accept: application/json, text/plain, */*
Accept-Encoding: gzip, deflate, br
Accept-Language: zh-CN,zh;q=0.9
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ...
Origin: https://open.dingtalk.com
Referer: https://open.dingtalk.com/
```

CORS 响应头开放 `Access-Control-Allow-Origin: *`，不构成跨域限制。

## 风控估计

OSS 静态资源不太可能严格 rate-limit，但仍按 plan：`concurrency=4` + `sleep 0.5s` + 429/503 指数退避 起步。
