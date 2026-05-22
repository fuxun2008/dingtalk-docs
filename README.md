# DingTalk Help Center

Documentation site at **https://help.dingtalk.io** — powered by [Mintlify](https://mintlify.com).

Three languages (English / 中文 / 日本語) kept in identical mirrored structure for translation alignment.

> AI 协作者请同时阅读仓库根目录的 [`CLAUDE.md`](./CLAUDE.md)，里面定义了完整的写作约定、编码原则与安全准则。

## Local development

```bash
npm i -g mint        # one-time install
mint dev             # serve at http://localhost:3000
mint broken-links    # link check (run before every commit)
mint login           # one-time, enables local search
```

## Project structure

| Path | Purpose |
|---|---|
| `docs.json` | 站点配置：colors / languages / navigation / SEO |
| `index.mdx`、`quickstart.mdx`、`guides/` | 英文内容（默认语言） |
| `zh/` | 中文镜像（与英文同名同结构） |
| `ja/` | 日文镜像（与英文同名同结构） |
| `logo/light.svg`、`logo/dark.svg` | 浅 / 深色模式 logo |
| `favicon.svg` | 网站图标 |
| `.claude/commands/` | 项目级 Claude Code skill |

每新增一页都要在 **3 处 mdx + `docs.json` 3 个 language 块** 同步维护。

## Contributing

### 添加新页

推荐用项目级 skill 一次性维护三语 + navigation：

```
/docs-add-page <slug> <group>
# 例：/docs-add-page guides/messaging Guides
```

skill 会自动生成 `<slug>.mdx`、`zh/<slug>.mdx`、`ja/<slug>.mdx`，并在 `docs.json` 三个 language 块的对应 group 下追加 page 路径，最后跑 `mint broken-links`。

手动操作时，每添加 1 页 = 4 处改动：3 个 mdx 文件 + `docs.json` 3 处 navigation。

### 翻译已有英文页

```
/docs-translate <english-mdx-path>
# 例：/docs-translate guides/messaging.mdx
```

skill 会以英文母版为模板，在 `zh/` 与 `ja/` 同路径生成翻译占位（保留 MDX 组件结构，正文标 `TODO: translate`），人工填充。**不调用机翻**。

### 本地预览 + 三语首页截图

```
/docs-preview
```

后台启 `mint dev` + 死链检查 + Playwright 抓三语首页截图，完成后自动停止进程。

### 提交规范

完整规则见 [`CLAUDE.md` → Git 规范](./CLAUDE.md)，要点：

- commit message 格式：`<type>: <description>。to #82317048`
- 用 `/commit-flow` skill 自动完成 lint → 暂存 → 生成 message → 提交
- 暂存用精确 add，**不用** `git add .`

## Deployment

### 自动部署

Push 到 `main` → Mintlify GitHub App 监听 → 平台侧自动构建 → live at https://help.dingtalk.io。

仪表盘：https://dashboard.mintlify.com

### 自定义域名 DNS（一次性配置）

在域名服务商（如阿里云 / Cloudflare）添加以下记录：

| Type | Host | Value |
|---|---|---|
| CNAME | `help` | `cname.mintlify.builders` |
| TXT | `_acme-challenge.help` | _（Mintlify Dashboard 提供）_ |
| TXT | `_cf-custom-hostname.help` | _（Mintlify Dashboard 提供）_ |

完整流程：登录 Dashboard → Settings → Custom Domain → 按页面提示获取 TXT 值。
