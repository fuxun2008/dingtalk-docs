# AI Table 文档校对工具

面向运营同学的本地化校对工具。**双栏对照中文母版与英文译文，双击英文段落即可修改，ALT+S 一键写回 mdx 文件。**

不部署、不联网、不动 git；保存只改文件，提交由人工 `git diff` → `git commit` 处理。

---

## 给运营的 3 步上手

### 1. 首次准备（每人一次）

```bash
# 1. 装 git（已装跳过）
# 2. 装 Node.js 18+ 与 pnpm（已装跳过）
npm i -g pnpm

# 3. clone 仓库
git clone git@github.com:fuxun2008/dingtalk-docs.git
cd dingtalk-docs/tools/review

# 4. 装依赖（约 30 秒）
pnpm install
```

### 2. 每次启动

```bash
cd dingtalk-docs/tools/review
pnpm dev
```

浏览器自动打开 `http://localhost:5173`，看到三栏界面即就绪。

### 3. 日常校对流程

1. 左侧菜单挑一篇文档 → 中（参考）+ 英（编辑）同时加载
2. 看到不顺的英文段落 → **双击**进入编辑器
3. 改完按 **⌘/Ctrl + Enter** 确认（或点旁边别处自动保留），段落左侧出现蓝色 dirty 条
4. 按 **ALT+S**（或右上「保存」按钮）写回磁盘
5. 改下一段，或按 **↑/↓** 切换上下一篇

### 提交给作者

```bash
cd dingtalk-docs
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
| 图片 | 已与产品确认本期不动 |
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
