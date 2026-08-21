# 钉钉文档校对工具

面向运营同学的本地化校对工具。**顶部菜单选产品模块（帮助中心各 tab + 开放平台），左右各选一种语言（中 / 英 / 日）做双栏对照；两侧都可编辑——双击段落改文字、改标题描述、删/换图片视频、删段落，ALT+S 一键写回 mdx 文件。还可整篇删除（三语 mdx + docs.json 导航 + 孤儿图）。**

不部署、不联网、不动 git；保存只改文件，提交由人工 `git diff` → `git commit` 处理。

---

## 给运营：零基础一键安装（推荐）

**适用：Mac 电脑，没装过 git / Node.js 也没关系。**

打开「终端」（Spotlight 搜 Terminal），粘贴以下命令并回车：

```bash
curl -fsSL https://gitlab.alibaba-inc.com/dingding/dingtalk-docs/-/raw/main/tools/review/install.sh | bash
```

首次约需 **5–15 分钟**（含下载工具、克隆仓库、安装依赖），脚本会自动：

1. 检测并安装 Xcode CLT、Homebrew、Node.js、pnpm
2. 生成 SSH 密钥并打开 GitLab 等你贴一次公钥（**唯一手动步骤**）
3. 克隆仓库到 `~/dingtalk-docs`
4. 安装依赖并启动校对工具，浏览器自动打开 `http://localhost:5173`
5. 在桌面创建「启动校对工具.command」快捷方式

**以后启动**：双击桌面上的 **启动校对工具.command** 即可。

---

## 进阶：手动安装（已熟悉终端的同学）

```bash
# 1. 装 Node.js 18+ 与 pnpm（已装跳过）
brew install node && corepack enable && corepack prepare pnpm@latest --activate

# 2. clone 仓库
git clone git@gitlab.alibaba-inc.com:dingding/dingtalk-docs.git ~/dingtalk-docs
cd ~/dingtalk-docs/tools/review

# 3. 装依赖并启动
pnpm install
pnpm dev
```

浏览器自动打开 `http://localhost:5173`，看到三栏界面即就绪。

---

## 日常校对流程

1. 左侧菜单挑一篇文档 → 中（参考）+ 英（编辑）同时加载
2. 看到不顺的英文段落 → **双击**进入编辑器
3. 改完按 **⌘/Ctrl + Enter** 确认（或点旁边别处自动保留），段落左侧出现蓝色 dirty 条
4. 按 **ALT+S**（或右上「保存」按钮）写回磁盘
5. 改下一段，或按 **↑/↓** 切换上下一篇

## 英文图片全自动批处理 V3

顶部点击 **图片批处理**，填写处理范围和 CDN 上传页后，点击 **全自动处理普通截图**。后台会自动完成：

1. 扫描中英文 MDX，排除已完成项和重复引用。
2. 下载普通 PNG/JPEG/WebP 产品截图；视频、GIF、SVG、超大图和复杂长图进入延期清单，不阻塞任务。
3. 并发调用 Codex 生成英文截图，保持原尺寸和交互状态，并将敏感信息替换为测试数据。
4. 用 macOS Vision 自动 OCR/二维码复检；残留中文或隐私风险的图片不上传、不回写。
5. 使用本机专用 Chrome 登录态，每批最多 20 张上传到 CDN；首张通过页面“无线链接”校验后自动映射其余链接。
6. 预检 MDX 结构、保存本地备份、原子回写英文文档，再验证 CDN 可访问性。

任务状态保存在 `tools/review/.cache/image-automation/`，关闭面板不影响运行，重新打开会恢复进度。CDN Cookie 只由 Chrome 自身保存，工具不读取、不导出 Cookie。首次 SSO 失效时，在自动打开的 Chrome 中登录一次；在等待时限内登录成功后任务会自动继续。

默认同时生成 4 张截图；可通过 `YIDA_IMAGE_GENERATION_CONCURRENCY=1..24` 调整。高并发会受图片生成服务配额影响，建议先用小批次实测吞吐，再将范围改为 `yida` 跑全量。

### 手动恢复通道

顶部点击 **图片批处理**，输入范围（例如 `yida/intro`）后按以下顺序操作：

1. **扫描/恢复**：递归扫描中文和英文 MDX，按结构定位目标位置，识别 PNG/JPEG/WebP、GIF、SVG、视频及视频封面。
2. **准备资源**：并发下载所选媒体；GIF 以 2 fps 提取最多 40 个代表帧，SVG 提取 `text/tspan` 文本节点，静态图保留原文件。
3. **复制批量生成任务**：把所选任务合并成一次 Codex 请求，任务中包含稳定 ID、本地源文件、预期输出位置、GIF 帧和 SVG 文本。
4. **批量上传 CDN**：一次上传 20～50 个生成文件，保留工具生成的文件名。
5. **导入上传结果**：支持每行一个 URL（按选择顺序）、`任务ID,URL,alt`、`文件名,URL` 或 JSON。
6. **预检回写**：重新扫描目标结构并验证修改后的 MDX，但不写磁盘。
7. **批量回写 MDX**：预检通过后，对有 CDN 地址的任务执行原子写回。

批处理状态保存在 `tools/review/.cache/image-batches/`，下载、抽帧和生成文件保存在 `tools/review/output/image-batch/`。两个目录均被 Git 忽略，可断点续跑，不会进入提交。

### 格式与隐私策略

- 静态图：生成任务要求保持尺寸、布局、颜色、图标和交互状态。
- GIF：代表帧用于翻译与一致性检查，最终英文 GIF 放到任务的 `expected_output` 路径后即可进入批量上传。
- SVG：优先翻译文本节点；路径化文字或嵌入位图进入图像处理任务。
- 视频：视频本体默认跳过，但 poster 封面作为独立图片处理。
- 手机号、邮箱、企业账号、token、二维码、UID 和 URL 不再导致任务跳过；准备阶段使用 macOS Vision 在本机执行 OCR/二维码预检，只保存风险类型、不保存识别原文。生成任务要求替换为无效测试数据、通用头像或遮挡内容；生成文件再次执行“准备资源”时会做输出复检，仍命中则转为“需复核”。姓名和头像等难以机械判断的内容继续由生成任务和人工验收兜底。

### CDN 映射示例

```text
任务ID,https://cdn.example.invalid/image.png,English screenshot description
生成文件名-en.png,https://cdn.example.invalid/image.png
```

只粘贴 CDN URL 时，URL 数量必须和当前已选任务数量一致，工具按选择顺序绑定。

## 提交给作者

```bash
cd ~/dingtalk-docs
git diff                 # 看自己改了什么
git add aitable/...mdx   # 加进暂存（按文件 add，不要 git add .）
git commit -m "docs: 优化某某章节英文表述。to #82317048"
git push                 # 推到远端，会触发线上自动构建
```

---

## 功能速览

| 区域 | 行为 |
|---|---|
| 左侧导航树 | 按 `docs.json` 章节顺序展示 215 篇 AI Table 文档；当前页高亮 + dirty 蓝点 |
| 中间中文栏 | 只读，对照参考 |
| 右侧英文栏 | 可编辑；段落悬停高亮 + 中文栏同步联动 + 滚动联动 |
| Frontmatter 卡片 | 顶部 title / description 可编辑（保存时回写 YAML） |
| 双击段落 | 进入 inline 编辑器，附带 **B / I / Link / Code** 工具栏 |
| ALT+S | 保存当前页所有 dirty（含 frontmatter） |
| ↑/↓ | 按导航顺序切上下一页（如有未保存会弹确认） |
| 切页/关页 | 未保存自动拦截 → 保存 / 放弃 / 取消三选一 |
| URL hash | 自动持久化，刷新不丢位置 |

---

## 编辑规则

### 可编辑

- 普通段落、标题、列表、引用、表格
- frontmatter 的 `title` 与 `description`

### 锁定不可改（v1 安全策略）

| 块类型 | 原因 |
|---|---|
| MDX 组件（如 `<Frame>` `<CardGroup>`） | 改坏会导致整页构建失败 |
| 代码块 | 多数有语义，运营校对场景不应动 |
| 表格 | mdast 表格语法易错，先用 readonly 占位 |
| 图片 / GIF / SVG | 通过“图片批处理”或单图本地化入口处理；不直接编辑原始 MDX 语法 |
| 分割线 / 未识别块 | 保留原样 |

锁定块会显示为虚线灰色占位卡片，告诉你这里是「MDX 组件」「代码块」等。

### 写错怎么办

保存时服务端会用 remark 重新解析；如果 MDX 语法不合法（如标签未闭合），保存会失败并在右上角红字提示具体位置。你可以撤销改动（直接 `git checkout aitable/...mdx`）后再试。

---

## 工程结构

```
tools/review/
├── package.json
├── vite.config.ts            前端 + /api middleware（同端口 5173）
├── tsconfig.json
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx               三栏布局 + 快捷键
    ├── server/               Vite middleware（Node 侧）
    │   ├── routes.ts         GET /api/nav  GET/POST /api/page
    │   ├── fs-safe.ts        路径白名单 + 原子写
    │   ├── mdx-parse.ts      remark 解析 → blocks[] with offsets
    │   └── nav-parse.ts      读 docs.json → AI Table 导航树
    ├── shared/
    │   ├── frontmatter.ts    YAML 解析与回写（共享给前后端）
    │   └── types.ts
    ├── components/
    │   ├── NavTree.tsx       左侧菜单
    │   ├── BlockPane.tsx     中/英栏块级渲染
    │   ├── InlineEditor.tsx  双击编辑器 + 工具栏
    │   ├── FrontmatterCard.tsx
    │   ├── SaveBar.tsx       右上保存按钮 + 错误显示
    │   └── ConfirmDialog.tsx
    ├── hooks/
    │   ├── useNavigation.ts
    │   ├── usePageState.ts   当前页 + dirty + save/navigate
    │   └── useScrollSync.ts  中英栏滚动同步
    ├── lib/
    │   └── apply-edits.ts    多 dirty 反向 offset 替换算法
    └── styles/app.css
```

---

## 安全护栏（自动启用，无需配置）

1. **路径白名单**：服务端只接受 `aitable/`、`zh/aitable/`、`ja/aitable/` 三个前缀，禁止 `..` 与绝对路径
2. **拒绝创建新文件**：保存时若目标 mdx 不存在，直接报错（防止运营笔误生成空页）
3. **MDX 语法校验**：保存前服务端用 remark 重新解析，失败拒绝写入并返回错误位置
4. **原子写**：`tmp → rename`，避免被 mint dev 半文件读到
5. **保存只动文件**：不内置 git commit/push，所有版本控制由人工处理
6. **批量回写有门槛**：没有有效 HTTP(S) CDN 地址的任务一律拒绝写入；写入前重新定位并验证 MDX

---

## 常见问题

**Q：保存了但 mint dev 没刷新？**
A：mint dev watch 是异步的，几秒后会重载。如果一直不刷新，看 mint dev 控制台是否报 MDX 编译错误。

**Q：双击没反应？**
A：当前块是锁定类型（MDX 组件 / 代码块 / 表格 / 图片）。运营场景不动这些，属于预期行为。

**Q：改了 frontmatter title，菜单没更新？**
A：菜单是从 `zh/aitable/...` 的中文母版读 title，改英文不影响左侧菜单。这是预期行为。

**Q：能编辑中文吗？**
A：v1 锁定。中文是母版，校对工作针对英文翻译；如需改中文请直接编辑文件。

**Q：日文（ja）呢？**
A：v1 不开放。如有需求第二期加第三栏。

**Q：5173 端口被占了？**
A：`pnpm dev -- --port 5174` 或先 `lsof -i :5173 | grep LISTEN` 看占用进程。
