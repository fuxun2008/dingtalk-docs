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
| `docs.json` | 站点配置：colors / languages / navigation（含 tabs / navbar / footer）/ SEO |
| `aitable/` | AI Table tab — 英文产品文档（首发唯一 tab） |
| `zh/aitable/` | 中文镜像（与英文同名同结构） |
| `ja/aitable/` | 日文镜像（与英文同名同结构） |
| `favicon.ico` | 网站图标 |
| `logo/` | 本地 logo（light / dark） |
| `.claude/commands/` | 项目级 Claude Code skill |
| `.claude/import/` | 导入资产记录（缺图清单 / 死链白名单） |

每新增一页都要在 **3 处 mdx + `docs.json` 3 个 language 块的对应 tab → group** 同步维护。

## Contributing

### 添加新页

推荐用项目级 skill 一次性维护三语 + navigation：

```
/docs-add-page <product> <slug> <group>
# 例：/docs-add-page aitable quick-start Introduction
```

`<product>` 是产品 slug：当前仅 `aitable`，未来按需扩展。
skill 会自动生成对应路径下的 `<slug>.mdx`、`zh/.../`、`ja/.../`，并在 `docs.json` 三个 language 块 → 对应 tab → 对应 group 下追加 page 路径，最后跑 `mint broken-links`。

手动操作时，每添加 1 页 = 4 处改动：3 个 mdx 文件 + `docs.json` 3 处 navigation（定位到正确的 tab → group）。

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

### 面向运营的校对工具

非技术同学校对英文翻译时，不必直接改 mdx，用本地双栏工具即可：

```bash
cd tools/review
pnpm install        # 首次
pnpm dev            # http://localhost:5173
```

中（参考）+ 英（编辑）双栏对照，双击英文段落 inline 改，ALT+S 写回文件。详见 [`tools/review/README.md`](./tools/review/README.md)。

## Deployment

### 自动部署

Push 到 `main` → Mintlify GitHub App 监听 → 平台侧自动构建 → live at https://help.dingtalk.io。

仪表盘：https://dashboard.mintlify.com

## 外部调用方接入

面向钉钉客户端 / 业务前端 / 任何想链到帮助中心的「问号入口」。

### 三语 URL 形态

| 语言 | URL 形态 | 适用场景 |
|---|---|---|
| English | `https://help.dingtalk.io/<product>/<slug>` | 调用方已知用户语言为 en |
| 中文 | `https://help.dingtalk.io/zh/<product>/<slug>` | 调用方已知用户语言为 zh |
| 日本語 | `https://help.dingtalk.io/ja/<product>/<slug>` | 调用方已知用户语言为 ja |
| 未知 | `https://help.dingtalk.io/<product>/<slug>`（同 en） | 调用方不确定语言，默认走英文 |

注意事项：

- `<product>` slug 永远英文（`im` / `docs` / `aitable` / `drive` / `open` ...），不翻译；只有路径前缀按语言加 `/zh` 或 `/ja`
- **帮助中心不做自动语言重定向**——访问 `/` 始终落到英文首页，不会按浏览器语言自动跳转（client-side redirect 在 Mintlify Hobby 上会有可见的「EN→ZH 闪动」，体验不可控，故取消）
- 业务调用方若**有用户语言上下文**，必须自行拼对应语言前缀；**不要**只发英文链期待客户端兜底

### 两个语言切换入口

帮助中心有**两套语言切换 UI**，互不冲突：

| 入口 | 出现位置 | 行为 |
|---|---|---|
| 首页 LangMenu（自实现） | 三语首页右上 | 跳目标语言首页 |
| Mintlify 顶部切换器 | 文档页右上 | 改 URL 前缀切到对应语言 |

设计取舍：

- **不做自动语言重定向**：曾尝试 `navigator.language + referrer` 多层兜底自动跳，但 Mintlify Hobby 无 server-side redirect / 无 head script 注入，**client-side redirect 必然先渲染英文页再 JS 跳转**，用户能看到明显的「EN→ZH 闪动 + 等待」。Google、Stripe、Apple 等国际站做法：默认语言加 LangMenu，用户主动切换。本站采用同样模式
- 升级 Mintlify Pro 后可解锁 `customScripts` 注入全站 JS，但相比闪动的 UX 收益不大，未列入规划
