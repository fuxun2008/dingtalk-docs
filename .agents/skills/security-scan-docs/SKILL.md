---
name: security-scan-docs
version: 1.0.0
description: "Privacy and security scan tailored to the MDX docs site: corpId, real phone numbers and emails, tokens, internal domains, QR codes and employee IDs. Use before a new product lands, as a monthly health check, or as a pre-push gate. Distinct from the generic TS/JS security-scan."
description_zh: "文档站隐私安全扫描：扫 corpId / 真手机号 / 内网域名 / token / 二维码是否漏出（区别于通用 TS/JS 的 security-scan）。"
user-invocable: true
argument-hint: "[--root <name>]"
---
# 文档站隐私安全扫描

> 子 skill：与 [[docs-dingtalk-onboard]] 阶段 6/8（新产品入库前最后防线）/ 周期性体检配套使用。**不同于** `/security-scan`（那条是 TS/JS 项目通用，对纯 MDX 文档站不适用）。

## 适用场景

- **新产品入库前**：[[docs-dingtalk-onboard]] 阶段 6 / 8 之后，提交前最后扫一遍 corpId / 真手机号 / 内网域名是否漏出
- **周期性体检**：每月跑一次（钉钉文档导出常带客户企业 ID）
- **单产品级专项**：用 `--root <name>` 限定，速度更快
- **CI gate**（未来）：退码 0/1/2 可作为 push 前 hook

## 参数

- `--root <name>`（可选）：限单产品根（`aitable` / `docs` / `open` / `mail` / `im` 等）
- `--lang en|zh|ja|all`（默认 `all`）
- `--severity CRITICAL|HIGH|MEDIUM|LOW`（默认 `LOW`，即全部）
- `--no-py`（可选）：跳过 `scripts/*.py`

## 执行流程（3 阶段）

### Phase 1 — 扫描

```bash
python3 scripts/security_scan_docs.py [--root <slug>] [--lang <lang>]
```

13 类 detector（基于 2026-06-12 首次扫描实测）：

| Severity | Detector | 说明 |
|---|---|---|
| CRITICAL | `api_key_prefix` | sk-/AKIA/AIza/xoxb/ghp/gho/glpat 前缀 token |
| CRITICAL | `jwt` | 三段式 JWT |
| CRITICAL | `db_conn_string` | mysql/postgres/mongodb/redis 含密码连接串 |
| CRITICAL | `private_key_block` | PEM 私钥起始标记 |
| HIGH | `dingtalk_corpid` | `ding[a-f0-9]{16,32}` |
| HIGH | `dingtalk_access_token` | `x-acs-dingtalk-access-token: ...` |
| HIGH | `chinese_phone` | 11 位中国大陆手机号（白名单测试号） |
| HIGH | `id_card_china` | 18 位身份证（年月日校验） |
| HIGH | `bank_card_unionpay` | 银联卡 62 开头 16-19 位 |
| HIGH | `email_internal` | @alibaba-inc/@alibaba/@alipay-inc/@antgroup |
| MEDIUM | `internal_domain` | `*.alibaba-inc.com` 等内网域名 |
| MEDIUM | `internal_system_url` | aone/teambition/atomic/code.alibaba 等内部系统 |
| LOW | `private_ipv4` | RFC1918 私有 IP |

产物：`scripts/output/security_scan/report.md`（按 severity → detector → 唯一 match 三级分组）。

**退码**：
- `0` — 0 HIGH/CRITICAL（可入库）
- `1` — HIGH 命中
- `2` — CRITICAL 命中

### Phase 2 — Review 报告（用户决策）

打开 `scripts/output/security_scan/report.md`，按 severity → detector 逐项判断：

| 决策 | 适用场景 | 操作 |
|---|---|---|
| **R** Replace | 真实敏感（真员工手机号 / 真客户 corpId / 内网域名） | 用 placeholder 替换：手机号→`13800138000`，corpId→`dingxxxxxxxxxxxx`，邮箱→`zhangsan@example.com`，内网域名→对外域名 |
| **W** Whitelist | 钉钉官方公开示例（文档站例子已 .com 上展示多年） | 加入 `scripts/security_scan_docs_whitelist.yaml` 对应 detector 节 |
| **I** Ignore | detector 误报（如 postId 长数字串被当手机号） | 在 `security_scan_docs.py` 该 detector 的 `context_skip` 加正则；或修正主 pattern |

### Phase 3 — 修复（用户授权后）

- **Replace 项**：用 `SearchReplace` 工具精确替换（不批量 sed，避免误伤）
- **Whitelist 项**：追加到 yaml + 重跑 scan 验证 0 命中
- **detector 改进**：编辑 `security_scan_docs.py`，重跑 scan 验证

每个改动跑一次 `python3 scripts/security_scan_docs.py` 验证退码，再 commit。

## 关键陷阱（已踩过）

### 陷阱 1：钉钉官方公开示例 ≠ 敏感数据

钉钉开放平台官方文档（open.dingtalk.com）多年来用固定示例 token / corpId / 手机号（如 `18513027676`、`zhangsan@alibaba-inc.com`、`x-acs-dingtalk-access-token:cnNTbW1YbU9sL2p6aFJZdEgvdlQrQT01`）。**这些示例对外公开已久，安全影响为 0**，应直接入白名单，不要 redact（否则会与钉钉开放平台官网文档不一致，降低开发者复制可用性）。

### 陷阱 2：长数字串误报手机号

`postId%3D16710067201` 这种 11 位数字 ID 会被 `chinese_phone` 正则命中。已在 `chinese_phone` 加 `context_skip`：上下文含 `postId` / `articleCode` / `goods` 等关键词时跳。

### 陷阱 3：内网域名 ≠ 一定外泄

`yida.alibaba-inc.com` 是阿里内部宜搭表单域名，但**部分表单对外开放给开发者填**（如 `/o/dingtalk-jjfa` 钉钉试用申请）。review 时确认链接是否真对外可用，可用就改对外域名（`yida.dingtalk.com`），不可用就改 placeholder 或删链接。

### 陷阱 4：白名单宁可严格，不要宽

白名单加进去后该值永远跳过。**只白名单"确认无业务影响 + 多年公开"的值**（钉钉开放平台官方文档示例符合）；客户 corpId / 业务部门真手机号 / 内部表单链接都不应白名单。

## 与其他 skill 协作

- `/docs-dingtalk-onboard` — 阶段 6 / 8 之后提交前跑本 skill
- `/security-scan` — 通用 TS/JS 项目用那条；文档站用本条
- `/commit-flow` — Phase 3 修复后用此提交

## 历史基准（2026-06-12 首次扫描）

- 文件数：2894
- CRITICAL: 0
- HIGH: 208（85 phone + 96 token + 21 corpid + 6 email）
- MEDIUM: 3（yida.alibaba-inc.com）
- LOW: 0
- 白名单初版：4 个工信部/示例手机号
- review 后期望终态：白名单 ~250 条 + replace ~10 处真实敏感 + 6 处邮箱 example.com 化

完整事件记录：commit 待入仓。
