# 阶段 0：钉钉文档归档自动下载

> 子 skill：作为 [[docs-dingtalk-onboard]] **阶段 1 之前**的数据获取步骤；产出 `~/Downloads/dingtalk-docs-archive/` 供 `import_archive.py` 消费

把"如何拿到钉钉文档帮助中心一个产品所有 mdx"从"自己读 `.claude/import/dingtalk_downloader/README.md` 逐脚本跑"压成一条命令。5 个脚本（build_manifest → auth_bootstrap → discover_endpoint → download → verify），中间 2 步要人工介入（扫码登录 / 浏览器抓 API），其余全自动。

## 适用场景

- 新接入一个 DingTalk 子产品的帮助文档（如 `calendar` / `meeting` / `mind` / `whiteboard`），从零拿原始 mdx
- 已有产品大版本更新，要重新拉一次最新 mdx 母版（用 `--force-redownload`）
- 排查某篇下载失败 / 登录态过期 / 端点变更

## 参数

- `--input <path>`（默认 `~/Downloads/<date>_DingTalk_Docs/<产品>.url/`）：钉钉文档导出的 `.url` 快捷方式目录，结构 `<group>/<page>.url`
- `--output <path>`（默认 `~/Downloads/dingtalk-docs-archive/`）：下载目标目录
- `--from-step <N>`（可选）：从第 N 步开始（断点续跑；前置已通过手动验证时用）
- `--to-step <N>`（可选）：只跑到第 N 步就停
- `--force-redownload`（可选）：忽略 manifest 状态全量重下（如端点变更后产物需要刷新）

## 执行流程（6 步，对应 5 脚本）

> **总原则**：每步开头先 `ls` / `cat` 看现状，已通过直接 skip。`storage_state.json` / `endpoint.json` / `manifest.json` **绝对不能提交**（已 gitignore，但跑前 grep 兜底）。

### 步骤 0 — 前置检查

```bash
cd .claude/import/dingtalk_downloader

# 依赖装好
python3 -c "import playwright" 2>&1 || echo "[err] pip install -r requirements.txt"
python3 -c "from playwright.sync_api import sync_playwright; sync_playwright().start()" 2>&1 | head -3 \
  || echo "[err] playwright install chromium"

# 输入目录在
test -d "<input-path>" || echo "[err] 输入目录不存在，先把钉钉文档导出 .url 包放到 ~/Downloads/"
```

任意失败 → 停下报具体怎么修。

### 步骤 1 — 扫 `.url` 生成 manifest（纯自动）

```bash
python3 build_manifest.py
```

读 `<input-path>` 下所有 `.url`，生成 `manifest.json`（每条 `{ group, title, url, status: "pending" }`）。

**验证**：
```bash
python3 -c "import json; m=json.load(open('manifest.json')); print(f'total: {len(m)}, groups: {len(set(x[\"group\"] for x in m))}')"
```

**通过条件**：total > 0 + groups 数对得上输入目录 group 数。

### 步骤 2 — 浏览器扫码登录（**人工**）

```bash
python3 auth_bootstrap.py
```

会弹 chromium 窗口打开钉钉文档登录页：
1. **用户扫码登录**
2. 登录成功后脚本自动保存 `storage_state.json`（含 cookie / localStorage）
3. 窗口关闭

**验证**：
```bash
test -f storage_state.json && du -h storage_state.json    # 一般 300-500 KB
```

**通过条件**：文件存在且 > 100 KB。如失败（小于 100 KB） → 重跑。

**安全提示**：`storage_state.json` 含登录 cookie，**绝对不能提交**（已 gitignore，但跑前 `git check-ignore storage_state.json` 兜底）。

### 步骤 3 — 抓导出 API 端点（**人工**）

```bash
python3 discover_endpoint.py
```

会弹 chromium 窗口（带步骤 2 的登录态）：
1. 脚本自动打开 manifest 第一条文档的 URL
2. **用户在工具栏手动点 "导出 → Markdown"**
3. 脚本通过 `page.on("request")` 拦截这次导出请求，记 URL / method / headers / body 模板到 `endpoint.json`
4. 窗口关闭

**验证**：
```bash
test -f endpoint.json && python3 -c "import json; e=json.load(open('endpoint.json')); print(e.get('url','MISSING'))"
```

**通过条件**：`endpoint.json` 存在 + 含合法 url 字段。

**陷阱**：
- 端点是**产品 specific** 的（不同产品归档可能用不同导出 API），新产品第一次跑必须重做
- 登录态过期（cookie 7 天）→ 回步骤 2

### 步骤 4 — 批量下载（纯自动，10-50 min）

```bash
python3 download.py
```

按 manifest 顺序逐条调步骤 3 抓到的 endpoint，限速 1-2s/篇，每篇下载完立即写 manifest 状态（断点续传基础）。中断后重跑只处理 `pending` / `failed` 条目（除非 `--force-redownload`）。

**进度监控**：脚本边跑边打印 `[N/Total] <title> ... ok|failed`。可用 `Monitor` 跟踪：

```bash
tail -f download.log | grep --line-buffered -E 'ok|failed|error'
```

**陷阱**：
- 跑一段后报"登录页污染"（HTML 含登录 form 关键字）→ 登录态过期，回步骤 2 重做，**不要**重做步骤 3（endpoint 还能用）
- 大批连续失败（>10 篇）→ 停下来看 endpoint 是否变更（钉钉前端升级会换 URL），可能需要重跑步骤 3

### 步骤 5 — 校验产物（纯自动）

```bash
python3 verify.py
```

检查 4 项：
1. 数量 = manifest total
2. 无空 md（< 100 bytes 报警）
3. 无登录页污染（md 含 `dingtalk-passport` / `login` 等关键字报警）
4. H1 与 manifest title 一致（不一致报告，不强制失败）

**通过条件**：4 项全 pass，或失败条目 ≤ 5%（少量失败可手工补）。

### 步骤 6 — 报告 + 引导

```
✓ 钉钉文档归档下载完成：
  - 输入：<input-path>
  - 输出：<output-path>
  - 总篇数：N（成功 X / 失败 Y / 跳过 Z）
  - 失败条目：（如有）...

下一步：
- 接阶段 1：/docs-dingtalk-onboard <slug> --archive <output-path>
- 失败补救：rm 失败条目对应 md → 重跑 python3 download.py（断点续传）
- 端点失效后：rm endpoint.json → /docs-import-archive --from-step 3
```

## 关键陷阱（已踩过）

### 陷阱 1：`storage_state.json` / `endpoint.json` / `manifest.json` 绝不提交

三个文件含敏感信息（cookie / 内部 URL / 个人下载历史）。`.gitignore` 已通过白名单模式 fail-closed（`.claude/import/dingtalk_downloader/*` 全黑，只 `!*.py` / `!README.md` / `!requirements.txt`），但**跑前**：

```bash
git check-ignore .claude/import/dingtalk_downloader/storage_state.json && echo OK
```

返回 0（被忽略） → 安全。

### 陷阱 2：登录态过期分两步

- `auth_bootstrap.py` 拿到的 cookie 一般 7 天有效
- 下载到一半报登录页污染 → **只回步骤 2** 重做登录，**不要** 重做步骤 3（endpoint 没变）
- `discover_endpoint.py` 抓的端点除非钉钉前端升级，否则长期有效

### 陷阱 3：端点是产品 specific

不同 DingTalk 子产品（文档 / 表格 / 脑图 / 白板 / 知识库）的导出 API 可能不同。**新接入产品第一次跑必须重做步骤 3**。脚本不做端点缓存复用（`endpoint.json` 每次被新产品覆盖）。

### 陷阱 4：`--input` 目录结构必须严格 `<group>/<page>.url`

钉钉网页导出的 .url 包通常长这样：
```
钉钉文档.url/
├── 新手指南/
│   ├── 文档新手必看.url
│   └── ...
├── 快速上手/
└── ...
```

只支持两级（group + page）。不支持三级嵌套 group（如果遇到三级，先手工拍平成两级）。

### 陷阱 5：下载限速 1-2s/篇是经验值

钉钉文档服务端有限频，过快（< 1s/篇）会被封 IP 10-30 min。脚本默认 1.5s 间隔，**不要改快**。350 篇约 10 分钟，可接受。

## 与其他 skill 的协作

- `/docs-dingtalk-onboard` — 紧接下游：本 skill 产出 archive → onboard 阶段 1 `import_archive.py` 消费
- `/commit-flow` — 注意只提交脚本（README / *.py / requirements.txt），**不要**提交 manifest.json / endpoint.json / storage_state.json（已 gitignore 兜底）

## 历史基准（首批 2026-05-29）

| 步骤 | 用时 | 备注 |
|---|---|---|
| 1. build_manifest | < 5s | 351 条 |
| 2. auth_bootstrap | ~30s | 含人工扫码 |
| 3. discover_endpoint | ~1min | 含人工点导出 |
| 4. download | ~10min | 351 篇 / 1.5s 间隔 |
| 5. verify | < 10s | — |
| **总计** | **~15min** | — |

完整脚本：`.claude/import/dingtalk_downloader/README.md`
