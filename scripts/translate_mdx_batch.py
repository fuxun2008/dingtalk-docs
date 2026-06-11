#!/usr/bin/env python3
"""
批量翻译 mdx：zh/<root>/*.mdx → <root>/*.mdx (en) 或 ja/<root>/*.mdx (ja)。

实现方式：通过 `claude -p --bare --model claude-opus-4-7` 子进程调用。
（阿里内网网关限制：opus 计划仅限 Claude Code 内使用，直接调 SDK 会被 400。）

特性：
- 三段 system prompt 合并通过 --system-prompt 传入
- 命中词库术语作为强约束注入 user message
- 图 / 视频 / iframe / 含图 Frame 强制剥离（prompt 铁律 + 后置正则双保险）
- asyncio 控并发；单篇失败重试 3 次（指数退避）
- 断点续跑：检测目标 mdx 是否仍是占位
- 报告：scripts/output/translate_docs/<lang>/{report.json,report.md}

CLI:
  python3 scripts/translate_mdx_batch.py --root docs --lang en
  python3 scripts/translate_mdx_batch.py --root docs --lang ja --concurrency 4
  python3 scripts/translate_mdx_batch.py --root docs --lang en --only docs/dingtalk-docs --limit 3
  python3 scripts/translate_mdx_batch.py --root docs --lang en --force
  python3 scripts/translate_mdx_batch.py --root docs --lang en --dry-run --limit 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
GLOSSARY_DIR = REPO_ROOT / "scripts" / "glossary"
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "translate_docs"


# ---------------------------------------------------------------------------
# Prompt 资产
# ---------------------------------------------------------------------------

SYSTEM_RULES = """你是钉钉国际版帮助中心的资深技术文档翻译。你的译文将作为官方文档面向全球企业用户，必须达到母语级流畅 + 商务专业。

铁律（违反则译文无效）：
1. 仅翻译自然语言段落、frontmatter 的 title 与 description、列表项、表格单元格文本、heading 文本。
2. 保留所有 MDX 组件标签 (<Note> <Tip> <Warning> <Info> <Check> <Card> <CardGroup> <Steps> <Step> <Tabs> <Tab> <Accordion> <AccordionGroup> <CodeGroup> <Update> <Frame> <Icon>) 及其全部 props (title / icon / href / cols / caption / ...) 完全不动，只译子节点的可见文本。
3. 保留所有代码块 ``` 内部内容完全不动；代码块的 title="x" 中的 x 不译。
4. 【强制移除】删除所有图片引用 ![alt](path)、HTML <img/> 标签、<video>...</video>、<iframe>...</iframe>、含图 <Frame>...</Frame>—整段删除，前后空行折叠为一行。如果 <Frame> 内只是纯文本 caption 无图，可保留为段落。
5. 保留所有内部相对链接 [text](/foo/bar) 的 URL 完全不动；锚文本可翻译。外链 URL 不动；锚文本可翻译。
6. frontmatter 只翻 title 与 description 的 value；字段名不动；其它字段（sidebarTitle、icon、tag 等）的 value 不动。
7. 输出必须是合法 mdx，严禁包裹在 ```mdx ``` 代码块里，严禁加任何"以下是翻译"前后缀，第一个字符必须就是 mdx 内容。
8. 结构 1:1 镜像：保留所有 heading（含层级）、段落、列表、表格行（图片行除外）；不增不减不合并。
9. 中文标点改为目标语言习惯：英文用 . , ? ! "" ()；日文用 。、「」（）。
10. 技术词如 API / SDK / URL / JSON / SaaS 保持英文；钉钉品牌词遵循术语表。"""

STYLE_EN = """风格指南（英文）：
- 目标读者：钉钉国际版企业用户与 IT 管理员
- 语气：清晰、专业、动作导向（imperative voice：Click X，不写 You can click X）
- 句式：短句优先；避免被动语态；避免长定语；一句话讲一件事
- Heading：Sentence case（仅首字母大写 + 专有名词大写）；避免 Title Case
- 用词：避免 Chinglish；避免口语俚语；优先朴素商务英文
- 数字 / 日期：1,000；24-hour；日期 Month DD, YYYY
- 标点：全英文 + 直引号 ""
- 品牌词不译：DingTalk / DingTalk Docs / DingTalk Spreadsheet / DingTalk Mind / DingTalk Whiteboard / Knowledge Base / AI Table 遵循术语表
- 功能更新条目优先用 release-notes 行业表达：New / Improved / Fixed / Deprecated"""

STYLE_JA = """風格指南（日文）：
- 目标读者：日本企業ユーザーと IT 担当者
- 语气：です・ます調（敬体）。FAQ 可适度口语化但不破調
- 句式：短文优先；按日语自然语序重构；外来语用片假名
- 见出し：体言止め or 动词原形结句；避免「〜について」滥用
- 用词：钉钉品牌词不译；功能名优先用词库；通用 IT 术语用日本主流译法（設定 / 機能 / 権限 / ファイル / フォルダ / ダウンロード / アップロード / ログイン）
- 标点：、。「」（）；数字半角；日付 2026年6月2日
- 注意：避免中文式 kanji 顺序、避免「的」直译为「の」过多
- 功能更新用：新機能 / 改善 / 修正 / 廃止"""


# 开放平台 (Open Platform / OpenAPI) 专属铁律 — 仅 root=open 注入
# 对标 Google API Docs / Microsoft Learn 的开发者文档质量
OPEN_PLATFORM_RULES = """开放平台 (Open Platform / OpenAPI) 专属铁律 — 违反任意一条则译文无效：

【强制术语 — 覆盖词库】
A. 「机器人」译为 **Bot**（单数 / 英文）/ **ボット**（日文），**绝对不译为 Robot/ロボット**。
   - 适用：所有 DingTalk 聊天机器人 / chatbot 语境
   - 即便词库给出 Bots（复数），单实体场景一律改 Bot；列表 / 数组场景才用 bots
   - 复合词：DingTalk Bot / Group bot / Custom bot / Stream-mode bot
B. 「应用」一致译为 **App**（不要 Application）
C. 「企业内部应用」→ **Internal app**；「第三方应用」→ **Third-party app**；「服务端 API」→ **Server API**

【API 契约 — 严格保持原样不译】
D. HTTP 动词 / 状态码 / Header 名 / Content-Type 完全不译：
   POST / GET / PUT / DELETE / PATCH / 200 OK / 401 Unauthorized / Authorization / Content-Type / application/json
E. JSON 字段名 / 路径参数名 / 查询参数名 **完全不译**（这些是面向程序的契约）：
   corpId / userid / unionid / client_id / client_secret / access_token / refresh_token / grant_type
   / authorization_code / request_id / dept_id / role_id / agent_id / nonce / timestamp / signature
   即使中文上下文叫"用户 ID"，但当它作为 JSON 字段或表格里的"参数名"列出时，保持 `userid` 原样
F. API 端点 URL 与路径占位符不译：
   https://api.dingtalk.io/v1.0/oauth2/{corpId}/token 中 {corpId} 保持
G. 错误码字符串不译（如 InvalidParameter.AccessToken / NotAuthorized / ServiceUnavailable）；
   错误消息中的自然语言文本才译（如 "参数错误：accessToken 已过期" → "Invalid parameter: access token has expired"）
H. 代码示例 ```code``` 块内容完全不动；代码块的 title="x" 中的 x 不译；
   代码中的注释 `// ...` `# ...` 可译，但变量名 / 函数名 / SDK 方法名不译
   （`// 获取访问令牌` → `// Get the access token`；但 `getAccessToken()` 保持）

【Heading 大小写 — 体现专业性】
I. 英文 Heading（# / ## / ### 等）一律 **Sentence case + 专有名词大写**：
   ✅ "Get the access token of an internal app"
   ❌ "Get The Access Token Of An Internal App"  （Title Case 错）
   ❌ "get the access token of an internal app"  （首字母必须大写）
   专有名词强制大写：DingTalk / API / SDK / URL / HTTP / OAuth / JSON / Webhook / JSAPI / H5 / SaaS / SSO / QR
   品牌词强制大小写：DingTalk / DingTalk Bot / DingTalk Docs / DingTalk Spreadsheet / DingTalk Mind
J. 日文标题：体言止め或动词原形结句；API 类专有词前后留半角空格（access token を取得する）

【动作导向语气 — 开发者文档标准】
K. 英文：祈使句 + 主动语态 — "Click..." / "Call..." / "Send a request to..." / "Configure the webhook"
   避免：You can click... / It is possible to... / You should... / It is recommended that you...
L. 日文：敬体 + 简洁 — 「〜します」「〜してください」「〜を呼び出します」
   避免：「〜することができます」滥用、「〜することをお勧めします」冗长

【表格列头惯用】
M. 英文：Name / Type / Required / Example / Description（不写 "Required or not"）
N. 日文：名前 / タイプ / 必須 / 例 / 説明"""


# ---------------------------------------------------------------------------
# 工具：占位检测、命中术语、sanitize
# ---------------------------------------------------------------------------

PLACEHOLDER_RE_TITLE = re.compile(r"^title:\s*[\"']?.*(?:TODO translate|TODO 翻訳|TODO 翻译)", re.MULTILINE)
PLACEHOLDER_RE_BODY = re.compile(r"\{/\*\s*TODO:?\s*(?:Translate from|.*?から翻訳|.*?翻译自)", re.IGNORECASE)


def is_placeholder(text: str) -> bool:
    return bool(PLACEHOLDER_RE_TITLE.search(text) or PLACEHOLDER_RE_BODY.search(text))


IMG_LINE_RE = re.compile(r"^[ \t]*!\[[^\]]*\]\([^)]*\)[ \t]*$", re.MULTILINE)
IMG_TAG_RE = re.compile(r"<img\b[^>]*?/?>", re.IGNORECASE)
VIDEO_BLOCK_RE = re.compile(r"<video\b[^>]*?>.*?</video>", re.IGNORECASE | re.DOTALL)
VIDEO_SELF_RE = re.compile(r"<video\b[^>]*?/>", re.IGNORECASE)
IFRAME_BLOCK_RE = re.compile(r"<iframe\b[^>]*?>.*?</iframe>", re.IGNORECASE | re.DOTALL)
IFRAME_SELF_RE = re.compile(r"<iframe\b[^>]*?/>", re.IGNORECASE)
FRAME_BLOCK_RE = re.compile(r"<Frame\b[^>]*?>(.*?)</Frame>", re.IGNORECASE | re.DOTALL)
FRAME_SELF_RE = re.compile(r"<Frame\b[^>]*?/>", re.IGNORECASE)
MULTI_EMPTY_LINE_RE = re.compile(r"\n{3,}")
CODE_FENCE_WRAPPER_RE = re.compile(r"^```(?:mdx?|markdown)?\s*\n(.*)\n```\s*$", re.DOTALL)


def sanitize_media(text: str) -> str:
    """删除图 / 视频 / iframe / 含图 Frame；折叠连续空行。"""
    text = VIDEO_BLOCK_RE.sub("", text)
    text = VIDEO_SELF_RE.sub("", text)
    text = IFRAME_BLOCK_RE.sub("", text)
    text = IFRAME_SELF_RE.sub("", text)

    def _frame_filter(m: re.Match) -> str:
        inner = m.group(1).strip()
        if not inner:
            return ""
        if IMG_TAG_RE.search(inner) or "![" in inner:
            return ""
        return inner

    text = FRAME_BLOCK_RE.sub(_frame_filter, text)
    text = FRAME_SELF_RE.sub("", text)
    text = IMG_TAG_RE.sub("", text)
    text = IMG_LINE_RE.sub("", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = MULTI_EMPTY_LINE_RE.sub("\n\n", text)
    return text.strip() + "\n"


def strip_code_fence_wrapper(text: str) -> str:
    """如果 LLM 把整篇包在 ```mdx ... ``` 里，剥掉。"""
    m = CODE_FENCE_WRAPPER_RE.match(text.strip())
    if m:
        return m.group(1)
    return text


def load_glossary(lang: str) -> dict[str, str]:
    path = GLOSSARY_DIR / f"zh-{lang}.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def extract_hit_terms(source: str, glossary: dict[str, str]) -> dict[str, str]:
    hits: dict[str, str] = {}
    for zh in sorted(glossary.keys(), key=len, reverse=True):
        if zh and zh in source:
            hits[zh] = glossary[zh]
    return hits


def build_user_message(hits: dict[str, str], source: str) -> str:
    if hits:
        terms_json = json.dumps(hits, ensure_ascii=False, indent=2)
        return (
            "本篇命中的项目术语对照表（强约束 — 必须严格按此译，不得自由发挥）：\n"
            f"```json\n{terms_json}\n```\n\n"
            "凡未在表中出现的中文术语，按你自己的判断译，保持与上表同等专业度。\n\n"
            "---\n\n"
            "下面是源 mdx 全文，按上面所有铁律和风格指南翻译它（直接输出译文 mdx，不要任何前后缀）：\n\n"
            f"{source}"
        )
    return (
        "下面是源 mdx 全文，按所有铁律和风格指南翻译它（直接输出译文 mdx，不要任何前后缀）：\n\n"
        f"{source}"
    )


def build_system_prompt(lang: str, root: str = "") -> str:
    style = STYLE_EN if lang == "en" else STYLE_JA
    target = "英文（American English）" if lang == "en" else "日文（敬体 です・ます）"
    sections = [SYSTEM_RULES, style]
    if root == "open":
        sections.append(OPEN_PLATFORM_RULES)
    sections.append(f"本次任务把中文 mdx 译为 {target}。直接输出译文 mdx，不要前后缀说明。")
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# 翻译单元
# ---------------------------------------------------------------------------

@dataclass
class FileTask:
    source: Path
    target: Path
    rel: str = ""


@dataclass
class FileResult:
    rel: str
    status: str  # ok / skipped / failed / dry-run
    elapsed_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    hit_terms_count: int = 0
    error: str = ""


async def call_claude_cli(system_prompt: str, user_msg: str, model: str, timeout_s: int) -> tuple[str, dict]:
    """调用 claude -p --bare，返回 (result_text, usage_dict)"""
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", "--bare",
        "--model", model,
        "--system-prompt", system_prompt,
        "--tools", "",
        "--no-session-persistence",
        "--output-format", "json",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=user_msg.encode("utf-8")),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        raise RuntimeError(f"timeout after {timeout_s}s")
    if proc.returncode != 0:
        raise RuntimeError(f"claude exit {proc.returncode}: {stderr.decode('utf-8', errors='replace')[:500]}")
    try:
        data = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise RuntimeError(f"non-json output: {e}; first 300 bytes: {stdout[:300]!r}")
    if data.get("is_error"):
        raise RuntimeError(f"api_error: {data.get('api_error_status')} subtype={data.get('subtype')}")
    result = data.get("result", "")
    if not result:
        raise RuntimeError(f"empty result; stop_reason={data.get('stop_reason')}")
    return result, data.get("usage", {}) | {"cost_usd": data.get("total_cost_usd", 0.0)}


async def translate_one(
    task: FileTask,
    glossary: dict[str, str],
    system_prompt: str,
    model: str,
    timeout_s: int,
    dry_run: bool,
    sem: asyncio.Semaphore,
    force: bool,
) -> FileResult:
    rel = task.rel
    try:
        source_text = task.source.read_text(encoding="utf-8")
    except Exception as e:
        return FileResult(rel=rel, status="failed", error=f"read source: {e}")

    if task.target.exists() and not force:
        existing = task.target.read_text(encoding="utf-8")
        if not is_placeholder(existing):
            return FileResult(rel=rel, status="skipped")

    hits = extract_hit_terms(source_text, glossary)
    user_msg = build_user_message(hits, source_text)

    if dry_run:
        print(f"[dry-run] {rel}  hit_terms={len(hits)}  src_chars={len(source_text)}")
        return FileResult(rel=rel, status="dry-run", hit_terms_count=len(hits))

    last_err = ""
    for attempt in range(3):
        async with sem:
            t0 = time.time()
            try:
                result_text, usage = await call_claude_cli(system_prompt, user_msg, model, timeout_s)
                elapsed = time.time() - t0
                cleaned = sanitize_media(strip_code_fence_wrapper(result_text))
                task.target.parent.mkdir(parents=True, exist_ok=True)
                task.target.write_text(cleaned, encoding="utf-8")
                return FileResult(
                    rel=rel,
                    status="ok",
                    elapsed_s=round(elapsed, 2),
                    input_tokens=usage.get("input_tokens", 0) or 0,
                    output_tokens=usage.get("output_tokens", 0) or 0,
                    cache_creation_tokens=usage.get("cache_creation_input_tokens", 0) or 0,
                    cache_read_tokens=usage.get("cache_read_input_tokens", 0) or 0,
                    cost_usd=usage.get("cost_usd", 0.0) or 0.0,
                    hit_terms_count=len(hits),
                )
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"

        backoff = 2 ** attempt * 3  # 3 / 6 / 12s
        print(f"  ! {rel} attempt {attempt + 1} failed: {last_err}; retry in {backoff}s", file=sys.stderr)
        await asyncio.sleep(backoff)

    return FileResult(rel=rel, status="failed", error=last_err)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def gather_tasks(
    root: str,
    lang: str,
    only: str | None,
    bucket_id: int | None = None,
    bucket_count: int | None = None,
) -> list[FileTask]:
    zh_root = REPO_ROOT / "zh" / root
    if not zh_root.exists():
        sys.exit(f"ERROR: source dir not found: {zh_root}")
    if lang == "en":
        target_base = REPO_ROOT / root
    elif lang == "ja":
        target_base = REPO_ROOT / "ja" / root
    else:
        sys.exit(f"ERROR: lang must be en or ja, got {lang}")

    tasks: list[FileTask] = []
    for mdx in sorted(zh_root.rglob("*.mdx")):
        rel = mdx.relative_to(zh_root)
        target = target_base / rel
        rel_str = str(Path(root) / rel)
        if only and not rel_str.startswith(only):
            continue
        tasks.append(FileTask(source=mdx, target=target, rel=rel_str))

    if bucket_id is not None and bucket_count and bucket_count > 1:
        if not 0 <= bucket_id < bucket_count:
            sys.exit(f"ERROR: bucket_id must be in [0, {bucket_count}), got {bucket_id}")
        sized = sorted(tasks, key=lambda t: t.source.stat().st_size, reverse=True)
        buckets: list[list[FileTask]] = [[] for _ in range(bucket_count)]
        sizes = [0] * bucket_count
        for t in sized:
            i = sizes.index(min(sizes))
            buckets[i].append(t)
            sizes[i] += t.source.stat().st_size
        tasks = sorted(buckets[bucket_id], key=lambda t: t.rel)
        print(
            f"[bucket] id={bucket_id}/{bucket_count} files={len(tasks)} "
            f"bytes={sizes[bucket_id]:,} (total all buckets bytes={sum(sizes):,})"
        )

    return tasks


def write_report(results: list[FileResult], out_dir: Path, started: float, ended: float, suffix: str = "") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / f"report{suffix}.json"
    report_md = out_dir / f"report{suffix}.md"

    report_json.write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    total = len(results)
    ok = sum(1 for r in results if r.status == "ok")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")
    dry = sum(1 for r in results if r.status == "dry-run")
    sum_in = sum(r.input_tokens for r in results)
    sum_out = sum(r.output_tokens for r in results)
    sum_cost = sum(r.cost_usd for r in results)

    lines = [
        "# Translation Batch Report",
        "",
        f"- 开始：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(started))}",
        f"- 结束：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ended))}",
        f"- 用时：{round(ended - started, 1)}s",
        "",
        f"- 总：{total} / ok: {ok} / skipped: {skipped} / failed: {failed} / dry-run: {dry}",
        f"- input tokens: {sum_in:,}",
        f"- output tokens: {sum_out:,}",
        f"- cost: ${sum_cost:.4f}",
        "",
    ]
    if failed:
        lines.append("## 失败清单")
        lines.append("")
        for r in results:
            if r.status == "failed":
                lines.append(f"- `{r.rel}`：{r.error}")
        lines.append("")

    lines.append("## 全量明细（前 100）")
    lines.append("")
    lines.append("| rel | status | elapsed | in | out | cost | hits |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in results[:100]:
        lines.append(
            f"| {r.rel} | {r.status} | {r.elapsed_s}s | {r.input_tokens} | {r.output_tokens} | ${r.cost_usd:.4f} | {r.hit_terms_count} |"
        )
    if total > 100:
        lines.append(f"\n_（共 {total} 条，仅显示前 100；全量见 report.json）_")

    report_md.write_text("\n".join(lines), encoding="utf-8")


async def main_async(args: argparse.Namespace) -> int:
    model = args.model or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
    glossary = load_glossary(args.lang)
    system_prompt = build_system_prompt(args.lang, args.root)
    sem = asyncio.Semaphore(args.concurrency)

    tasks = gather_tasks(args.root, args.lang, args.only, args.bucket_id, args.bucket_count)
    if args.limit:
        tasks = tasks[: args.limit]

    print(
        f"[info] lang={args.lang} root={args.root} 任务数={len(tasks)} "
        f"concurrency={args.concurrency} model={model} timeout={args.timeout}s"
    )
    if args.dry_run:
        print("[info] dry-run：只统计命中术语，不调 LLM、不写文件")
    if args.force:
        print("[info] force=true：会覆盖非占位的已译文件")

    started = time.time()
    coros = [
        translate_one(t, glossary, system_prompt, model, args.timeout, args.dry_run, sem, args.force)
        for t in tasks
    ]
    results: list[FileResult] = []
    done = 0
    for coro in asyncio.as_completed(coros):
        r = await coro
        results.append(r)
        done += 1
        icon = {"ok": "✓", "skipped": "·", "failed": "✗", "dry-run": "?"}.get(r.status, "?")
        if r.status == "ok":
            print(
                f"[{done}/{len(tasks)}] {icon} {r.rel}  {r.elapsed_s}s  "
                f"in={r.input_tokens} out={r.output_tokens} ${r.cost_usd:.3f} hits={r.hit_terms_count}"
            )
        elif r.status == "failed":
            print(f"[{done}/{len(tasks)}] {icon} {r.rel}  FAILED: {r.error}", file=sys.stderr)
        else:
            print(f"[{done}/{len(tasks)}] {icon} {r.rel}  {r.status}")

    ended = time.time()
    out_dir = OUTPUT_DIR / args.lang
    report_suffix = f"_bucket{args.bucket_id}of{args.bucket_count}" if args.bucket_id is not None and args.bucket_count else ""
    write_report(results, out_dir, started, ended, report_suffix)

    failed = [r for r in results if r.status == "failed"]
    print(f"\n[done] report: {out_dir / f'report{report_suffix}.md'}")
    if failed:
        print(f"[warn] {len(failed)} 篇失败，详见报告")
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="批量翻译 mdx：zh/<root>/ → <root>/ (en) 或 ja/<root>/ (ja)")
    p.add_argument("--root", required=True, help="zh 下的根目录，如 docs / aitable")
    p.add_argument("--lang", required=True, choices=["en", "ja"])
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--model", default=None, help="覆盖默认 ANTHROPIC_MODEL，如 claude-sonnet-4-6")
    p.add_argument("--timeout", type=int, default=240, help="单次 claude CLI 调用超时秒数")
    p.add_argument("--only", default=None, help="只跑路径前缀，如 docs/dingtalk-docs")
    p.add_argument("--limit", type=int, default=0, help="只跑前 N 篇")
    p.add_argument("--force", action="store_true", help="覆盖非占位的已译文件")
    p.add_argument("--dry-run", action="store_true", help="只列任务 + 命中术语")
    p.add_argument("--bucket-id", type=int, default=None, dest="bucket_id",
                   help="多进程分桶：本进程跑桶 N（0..bucket_count-1），与 --bucket-count 配合")
    p.add_argument("--bucket-count", type=int, default=None, dest="bucket_count",
                   help="多进程分桶总数；按文件大小 LPT 算法均衡分配")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main_async(args)))
