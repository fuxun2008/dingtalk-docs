# DingTalk Docs Downloader（Phase 1）

把钉钉文档帮助中心的 351 篇线上文档批量下载到本地 markdown，为 Mintlify 三语接入做语料准备。详见 `/Users/yanxin/.claude/plans/markdown-mdx-robust-bubble.md`。

## 快速开始

```bash
cd /Users/yanxin/www/dingtalk-docs/.claude/import/dingtalk_downloader

# 一次性环境准备
pip install -r requirements.txt
playwright install chromium

# 跑全流程
python build_manifest.py        # 1. 扫描 .url → manifest.json
python auth_bootstrap.py        # 2. 浏览器扫码登录，保存 storage_state.json
python discover_endpoint.py     # 3. 抓包探测导出 API
python download.py              # 4. 批量下载（10-50 分钟，可断点续传）
python verify.py                # 5. 校验产物
```

## 输入 / 输出

- 输入：`/Users/yanxin/Downloads/2026_05_28_DingTalk_Docs/钉钉文档.url/`（15 分类 / 351 个 .url 快捷方式）
- 输出：`/Users/yanxin/Downloads/dingtalk-docs-archive/`（与源镜像同构的 .md 文件）

## 文件说明

| 文件 | 用途 | 可提交 |
|---|---|---|
| `requirements.txt` | Python 依赖 | ✅ |
| `build_manifest.py` | 扫 .url 生成 manifest | ✅ |
| `auth_bootstrap.py` | 登录态获取 | ✅ |
| `discover_endpoint.py` | 导出 API 探测 | ✅ |
| `download.py` | 批量下载主循环 | ✅ |
| `verify.py` | 产物校验 | ✅ |
| `manifest.json` | 下载清单 + 状态 | ❌ 不提交 |
| `endpoint.json` | 探测到的 API 端点 | ❌ 不提交（含内部 URL） |
| `storage_state.json` | 浏览器登录态（含 cookie） | ❌ **绝对不提交** |

`.claude/` 目录整个 gitignore，无意外泄露风险。

## 中断恢复

`download.py` 每篇下载后立即写 manifest，中断后重跑只处理 pending/failed。如果登录态过期，先重跑 `auth_bootstrap.py` 再续跑 `download.py`。
