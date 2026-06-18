# MDX 质量审计 + 外链死链清理

> 子 skill：作为 [[docs-dingtalk-onboard]] 流水线第 6 / 8 阶段调用（也可独立跑）

把 MDX 语法审计（`scripts/audit_mdx_quality.py`）和钉钉外链死链探针（`scripts/check_external_links.py`）两步串起来，一次性出报告或落盘修复。

## 适用场景

- 翻译批次入库前的最后清场（确保不带 `++text++` / `** X**` 破碎粗体 / 死外链入仓）
- 周期性体检（每周/每月跑一次，钉钉文档侧迁移/下线会持续产新死链）
- 单产品级专项治理（用 `--root <name>` 限定）

## 参数

- `--root <name>`（可选）：限定单产品根，如 `docs` / `aitable`；不传则扫全仓
- `--lang en|zh|ja|all`（默认 `all`）：限定单语言镜像
- `--apply`（可选）：实际写盘修复（默认 dry-run）；**写盘前必须用户明确授权**
- `--skip-links`（可选）：只跑 syntax 审计，跳过 HTTP 探针（适合无网或只想看本地语法）
- `--skip-syntax`（可选）：只跑外链探针，跳过 syntax 审计
- `--concurrency <N>`（默认 8）：外链 HTTP 探针并发数
- `--no-cache`（可选）：跳过 URL 缓存重探（缓存默认 24h TTL）

## 执行流程（4 步）

### 步骤 1 — 前置检查（fail fast）

```bash
test -f scripts/audit_mdx_quality.py
test -f scripts/check_external_links.py
python3 -c 'import httpx' 2>&1 || echo "[err] httpx 未装：pip install httpx"
```

任意检查失败 → 停下来报具体怎么修。

### 步骤 2 — MDX 语法审计（除非 `--skip-syntax`）

```bash
python3 scripts/audit_mdx_quality.py [--root <root>] [--lang <lang>] [--apply]
```

脚本检测 8 类（A/B/C/E/F/G/H 自动修；D/I/J/K 仅报告人审）：

**自动修（auto-fix）**
- **A. `++text++`**：剥 `++` 留内层
- **B. `** X**` 破碎粗体**：修空格
- **C. `[label](https:xxx)` 废占位 URL**：去链留文
- **E. 空 `<Note>` 块**：整段删
- **F. release-notes 内 `<Note>` 标签行**：剥
- **G. release-notes/index 4 空格缩进**：夺为 0
- **H. `**X****Y**` 破碎嵌套粗体（恰好 4 连星）**：删 `****` 合并为单段 `**XY**`

**仅报告人审**
- **D. `[https://...](url)` URL-as-label**：label 是整段 URL，人工改文案
- **I. 同段 ≥4 段独立 `**bold**` 行**：建议改 `<CardGroup>`（启发式，按 H1-H4 section 内统计）
- **J. 连续 ≥2 张移动端截图**：建议 flex 容器；移动端启发式 = alt 含 `lQDPKH` / `IMG_` 前缀，或 URL crop / 文件名内嵌尺寸高瘦比 h/w≥1.5
- **K. `[xxx.mp4](alidocs.dingtalk.*/...)`**：钉钉附件 mp4 链接，建议改 `<video>` 标签直引 OSS mp4

跑完读 `scripts/output/audit_mdx/syntax-report.md` 头部回显：

```
- 模式：apply | dry-run
- 扫描文件数：N
- 命中文件数：N
- 命中总数：N
- 已修改文件数：N（仅 apply）
```

**A/B/C 命中数 > 0 但 D 命中数 > 0 是正常的**：D 需要人工判断 label 该改成什么文案。

### 步骤 3 — 外链死链探针（除非 `--skip-links`）

```bash
python3 scripts/check_external_links.py [--root <root>] [--lang <lang>] \
    [--apply] [--concurrency <N>] [--no-cache]
```

只探针白名单域：`docs.dingtalk.io` / `alidocs.dingtalk.com` / `alidocs.dingtalk.io`。

死链判定（三类均 auto-fix：`[label](dead)` → `label`）：

1. **`dead_redirect`**：最终 URL path 含 `/exception` 或 query 含 `type=notfound`
2. **`dead_body`**：响应 body 含 `Wiki not found` / `The Wiki you accessed does not exist` 等多语种文案（SPA 命中率极低）
3. **`dead_empty_title`**：SSR `<meta property="og:title" content="">` 为空——实测主信号源

网络异常（超时/连接拒绝/5xx）→ `network_error`，**不自动判死**，列报告人审。

跑完读 `scripts/output/check_links/dead-links.md` 头部回显：

```
- 模式：apply | dry-run
- 探针 URL 总数：N
- 引用 occurrence 总数：N
- 已修改文件数：N（仅 apply）
按状态统计：alive / dead_redirect / dead_body / dead_empty_title / network_error
```

### 步骤 4 — 报告与引导

按本次模板回显：

```
✓ MDX 质量审计完成：
  - syntax：A/B/C 修 X 处 / D 待人审 Y 处
  - 外链：死链 N（redirect / body / og:title 空）/ 网络异常 N / 存活 N
  - 拟改 / 已改 mdx 文件 N，去链占位 M

下一步：
- review：git diff --stat（看改动面）
- 提交：/commit-flow
  建议 commit message：docs: MDX 质量审计——++ 标记剥离 + 死外链去链留文（XX 文件）。to #82317048
- 本地预览：/docs-preview
```

**不自动 commit / push**（按 user memory `feedback_commit_authorization.md`）。

## 关键陷阱（已踩过）

### Pitfall 1: SPA 站点的死链判定靠 og:title，不靠 body

钉钉文档站 `docs.dingtalk.io` 是 SPA，body 内容 JS 渲染，HTTP 探针只能拿到静态壳。`dead_body` 标记几乎抓不到任何死链。**真正有效的信号是 SSR 注入的 `<meta property="og:title">`**：活公开文档有真实标题，死/受限/exception 页面均空。

### Pitfall 2: docs.dingtalk.io ≠ alidocs.dingtalk.com

2026-06-02 批次抽样 8/8 验证：docs.dingtalk.io 上 og:title 空的 URL 全部在 alidocs.dingtalk.com 上活着——即"没镜像到国际 .io 域名"。**用户决策（已写死）：按原 spec 去链留文**，不做域名替换尝试。

### Pitfall 3: --apply 没有 backup

脚本不做备份。**用户应在干净 worktree 跑**，或者 `git stash` 后再跑。误改可 `git checkout -- <path>` 撤销。本 skill **绝不**在脏 worktree 上盲跑 `--apply`，先 `git status` 看一眼是惯例。

### Pitfall 4: 探针缓存 24h，怀疑误判要手删

缓存路径：`scripts/output/check_links/url-cache.json`。如怀疑钉钉文档侧已修复/已下线导致探针缓存过期判断错误，删了 cache 再跑或加 `--no-cache`。

### Pitfall 5: D 类（url_as_label）不自动改

D 类是 `[https://full-url](url)` 形态——label 把整段 URL 当文案了。脚本不能机器判断该改成什么显示文字，**只报告**。修法：人工把 label 改成正常文案（章节标题 / 短描述），或直接删掉链接保留 URL 文本。

### Pitfall 6: I/J/K 类是启发式建议

- **I（CardGroup 候选）**：基于 H1-H4 section 内 `**bold**` 段落数 ≥4 触发。**会有假阳性**——`**Q:**` `**A:**` 这种 Q&A 段、`步骤一/步骤二` 这种自然有 4 段 bold 的章节都会被命中。判断时看是不是真"6 个并列场景描述"——这种适合用 `<CardGroup cols={2}>` + 每个 `<Card title icon>`；Q&A 段保持 bold 段落即可。
- **J（移动端截图组）**：基于 alt 文件名前缀（`lQDPKH` / `IMG_`）+ URL crop / 文件名嵌尺寸高瘦比（h/w≥1.5）。命中后建议用：

  ```mdx
  <div style={{display: 'flex', gap: '12px', justifyContent: 'center', flexWrap: 'wrap', margin: '16px 0'}}>
    <img src="url1" alt="..." style={{width: '32%', minWidth: '180px', borderRadius: '8px', boxShadow: '0 2px 12px rgba(0,0,0,0.08)'}} />
    <img src="url2" alt="..." style={{width: '32%', minWidth: '180px', borderRadius: '8px', boxShadow: '0 2px 12px rgba(0,0,0,0.08)'}} />
    <img src="url3" alt="..." style={{width: '32%', minWidth: '180px', borderRadius: '8px', boxShadow: '0 2px 12px rgba(0,0,0,0.08)'}} />
  </div>
  ```

  2 张图改 `width: '48%'` `minWidth: '200px'`。**PC 截图不应用此规则**——PC 横向截图本身就宽，并排会被压缩到看不清。

- **K（钉钉附件 mp4）**：建议用：

  ```mdx
  <video controls width="100%" style={{borderRadius: '8px', boxShadow: '0 4px 16px rgba(0,0,0,0.1)', margin: '8px 0'}}>
    <source src="https://alidocs2.oss-cn-zhangjiakou.aliyuncs.com/res/.../xxx.mp4?Expires=...&Signature=..." type="video/mp4" />
    您的浏览器不支持 video 标签。
  </video>
  ```

  注意 OSS 签名 URL 含 `Expires=` 会过期。优先拿不带签名的永久直链（资源 ID 直链），实在没有再用签名直链并记一笔过期时间。

## 与其他 skill 的协作

- `/docs-translate-batch` — 翻译批次完成后顺手跑本 skill 清场
- `/docs-translate <single-path>` — 单文件翻译完后跑 `--limit 1` 局部审计
- `/commit-flow` — 审计完成后用户授权提交（aoneId `82317048`）
- `/docs-preview` — 大批量修改后视觉验证

## 历史基准（2026-06-02 首批清洗）

| 模式 | 命中 | 已修 | 备注 |
|---|---|---|---|
| A. `++text++` | 547 处 / 122 文件 | 133 文件 / 628 处 | 三语全量 |
| B. `** X**` | <100 处 | 同上 | 主要在 EN 译文 |
| C. `https:xxx` | 3 处 | 3 文件 / 3 处 | intro-ai-table 三语 |
| D. url_as_label | 192 处 / 87 文件 | 0（人审） | 留待逐篇人工改 |
| 外链死链 | 93 URL / 420 占位 / 168 文件 | 同 | og:title 空全部 auto-fix |
