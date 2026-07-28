#!/usr/bin/env python3
"""
批量翻译 mdx：<root>/*.mdx (en 母版) → id/<root>/*.mdx (印尼文)。

与 translate_mdx_batch.py 的区别（专为「id 用 en 图 + 页数对齐 en」设计）：
- 源根 = 仓库根 <root>/（英文母版），目标 = id/<root>/。
- **保留图片 / 视频 / iframe / Frame 及其 URL 原样**（不剥离）——满足「印尼语图片用英文版图片、数量与英文一致」。
- en→id 词库：由 zh-en.json 与 zh-id.json 经共享 zh key 合成 en→id 对照表（强约束）。
- frontmatter description 走 **SEO 优化**：生成面向搜索的印尼语摘要，而非首段直译。

实现方式：通过 `claude -p --bare` 子进程调用（同 translate_mdx_batch.py）。

CLI:
  python3 scripts/translate_mdx_en2id.py --root meetings --concurrency 1
  python3 scripts/translate_mdx_en2id.py --root im                       # 跳过已存在的非占位译文，只补缺失
  python3 scripts/translate_mdx_en2id.py --root drive --only drive/index
  python3 scripts/translate_mdx_en2id.py --root contacts --dry-run --limit 2
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
# Prompt 资产（en → id）
# ---------------------------------------------------------------------------

SYSTEM_RULES = """你是钉钉国际版帮助中心的资深印尼语技术文档翻译。你的任务是把英文母版 mdx 译为印尼文 (Bahasa Indonesia)，作为官方文档面向印尼企业用户，必须达到母语级流畅 + 商务专业 (bahasa baku)。

铁律（违反则译文无效）：
1. 仅翻译自然语言段落、frontmatter 的 title 与 description、列表项、表格单元格文本、heading 文本。
2. 保留所有 MDX 组件标签 (<Note> <Tip> <Warning> <Info> <Check> <Card> <CardGroup> <Steps> <Step> <Tabs> <Tab> <Accordion> <AccordionGroup> <CodeGroup> <Update> <Frame> <Icon>) 及其全部 props (title / icon / href / cols / caption / ...) 完全不动，只译子节点可见文本。
3. 代码块 ``` 内部按 4 类区分处理（严禁一刀切「全部不动」）：
   3a. API 契约（保留原样）：JSON 字段名 / HTTP 方法 / 状态码 / Header 名 / URL 与占位符 / 函数名 / 方法名 / SDK 调用 / 变量名 / 错误码字符串 / 已是英文或数字的 enum 值。
   3b. 示例字面量（**必须译为印尼语**）：示例 JSON 中 user-facing 字段（title/content/text/key/value/description/desc/name 等）的字符串值；表格 example 列的示例值。
       例：`"content": "Monthly meeting notification"` → `"content": "Notifikasi rapat bulanan"`
       例：`"key": "Name"` / `"value": "John"` → `"key": "Nama"` / `"value": "Budi"`
   3c. 代码注释 + markdown 语法示例（**必须翻译**）：` // ... ` ` # ... ` 行内注释；```text``` 块内的纯 markdown 语法说明。
   3d. API enum 必传中文值（**保留原值 + 加印尼语行内注释**）：例 `"sticker": "灯泡"  // Bohlam`。
   代码块 title="x" 的 x 不译；``` 后的 lines / json lines 等修饰符不动。
4. 【图片/媒体原样保留】图片 ![alt](url)、<img/>、<video>...</video>、<iframe>...</iframe>、<Frame>...</Frame> 及其 URL **完全保持原样**（不删不改）。仅把 alt / caption 文本译为印尼语。图片 URL 必须与英文版完全一致。
5. 内部相对链接 [text](/foo/bar) 的 URL 完全不动；锚文本可翻译。外链 URL 不动；锚文本可翻译。
6. frontmatter 只翻 title 与 description 的 value；字段名不动；其它字段（sidebarTitle、icon、tag 等）value 不动。
7. 输出必须是合法 mdx，严禁包裹在 ```mdx ``` 里，严禁加「以下是翻译」等前后缀，第一个字符必须就是 mdx 内容。
8. 结构 1:1 镜像：保留所有 heading（含层级）、段落、列表、表格行、图片行；不增不减不合并。
9. 标点用拉丁习惯：. , ? ! " ( )（同英文）；印尼语千分位用「.」小数用「,」（1.000）；日期 2 Juni 2026 格式。
10. 技术词 API / SDK / URL / JSON / SaaS 等保持英文；钉钉品牌词遵术语表。"""

# SEO description 专用规则（用户必须要求）
SEO_DESCRIPTION_RULE = """【frontmatter description 走 SEO 优化（必须）】
description 不要是首段直译或截断，而要生成面向搜索的印尼语摘要：
- 一句话清楚传达页面价值
- 自然织入核心关键词（产品名 / 功能名 / 用户意图词，如 DingTalk / AI Table / otomatisasi / pengaturan izin / berbagi）
- 长度约 100–160 字符（避免搜索结果被截断）
- 不是关键词堆砌，而是自然可读的一句话
- 含一个明确的动作或收益
- 不只是 title 的改写（补充信息）
例：title「Menambahkan anggota」→ description「Pelajari cara menambahkan dan mengelola anggota organisasi di DingTalk secara massal — dari registrasi kontak hingga penetapan departemen, panduan bagi admin untuk mengelola anggota secara efisien.」"""

STYLE_ID = """Panduan gaya (Bahasa Indonesia):
- 目标读者：印尼企业用户与 IT 管理员（pengguna perusahaan & admin IT）
- 语气：clear、profesional、动作导向（imperative：Klik X / Pilih X / Buka X，不写 Anda dapat mengklik）；FAQ 可适度口语但保持 bahasa baku
- 句式：短句优先；避免被动堆砌；一句话讲一件事
- Heading：Sentence case（仅首字母 + 专有名词大写），避免 Title Case
- 用词：通用 IT 术语用印尼语主流译法 — Pengaturan / Fitur / Izin / File / Folder / Unduh / Unggah / Masuk / Keluar / Kelola / Bagikan / Hapus / Simpan / Kirim
- 技术缩写保持英文：API / SDK / URL / JSON / SaaS / SSO / OAuth / Webhook / H5 / QR
- 品牌词不译（遵术语表）：DingTalk / DingTalk Docs / DingTalk Spreadsheet / DingTalk Mind / DingTalk Whiteboard / Knowledge Base / AI Table / AI Minutes
- 功能更新条目：Baru / Ditingkatkan / Diperbaiki / Tidak digunakan lagi
- 注意：避免英式直译腔、冗长被动语态；追求自然印尼语"""

# 开放平台 (Open Platform / OpenAPI) 专属规则 — 仅 root=open 注入（id 当前范围不含 open，保留以备扩展）
OPEN_PLATFORM_RULES = """开放平台 (Open Platform / OpenAPI) 专属规则 — 违反任意一条则译文无效：

【术语强制】
A. 「机器人 / robot / chatbot」译为 **Bot**（英文），**禁用 Robot**。单实体用 Bot，数组/列表用 bots。
B. 「应用 / application」统一译为 **Aplikasi**（或保留 App，遵术语表）。
C. 「企业内部应用」→ Aplikasi internal；「第三方应用」→ Aplikasi pihak ketiga；「服务端 API」→ Server API。

【API 契约 — 保持原样】
D. HTTP 动词 / 状态码 / Header 名 / Content-Type 不译：POST / GET / 200 OK / 401 Unauthorized / Authorization / application/json。
E. JSON 字段名 / 参数名不译：corpId / userid / unionid / access_token / grant_type 等。
F. API 端点 URL 与路径占位符 {corpId} 保持。
G. 错误码字符串（InvalidParameter.AccessToken 等）保持；仅错误消息自然文翻译。
H. 代码示例按铁律 3 的 4 类处理。注释翻译，方法名 / 变量名保持。

【Heading / 语气】
I. 印尼文 Heading 用 Sentence case（仅首字母 + 专有名词大写，不模仿英文源文的 Title Case）；动作导向祈使句（Klik / Panggil / Konfigurasikan）。"""


# 宜搭 (YiDA) 专属规则 — 仅 root=yida 注入
YIDA_RULES = """宜搭 (YiDA) 专属规则 — 违反任意一条则译文无效：

【品牌 / 产品名】
A. **YiDA** 是品牌名，原样保留不译；YiDA Dedicated / YiDA platform / YiDA app 同理。
B. Cool App / low-code / DingTalk 保持英文原样。

【API 契约 — 保持原样】（developer-features / integration 篇目多见）
C. JSON 字段名 / 参数名不译：formUuid / formInstId / appType / processCode / formDataJson / searchFieldJson / systemToken 等。
D. 实例 ID / 组件标识保持：FORM-xxx / FINST-xxx / APP_xxx / textField_kkm9o5cd 等。
E. 接口路径（/v1/form/saveFormData.json 等）保持。

【URL 保护】
F. www.yidaapps.com / yida-support.oss-*.aliyuncs.com / docs.aliwork.com / img.alicdn.com 的 URL 完全不动。
G. 内部相对链接 [text](/yida/...) 的 URL 原样保持（后处理统一改前缀），仅锚文本翻译。

【表格列头 / 用词】
H. Parameter→Parameter / Description→Deskripsi / Required→Wajib / Example→Contoh / Notes→Catatan；
   Feature→Fitur / Supported→Didukung / Not supported→Tidak didukung。
I. 套餐：Free→Edisi Gratis / Basic→Edisi Basic / Professional→Edisi Professional / Dedicated→Edisi Dedicated。"""


# ---------------------------------------------------------------------------
# 占位検出・命中用語・コードフェンス
# ---------------------------------------------------------------------------

PLACEHOLDER_RE_TITLE = re.compile(r"^title:\s*[\"']?.*(?:TODO translate|TODO 翻訳|TODO 翻译)", re.MULTILINE)
PLACEHOLDER_RE_BODY = re.compile(r"\{/\*\s*TODO:?\s*(?:Translate from|.*?から翻訳|.*?翻译自)", re.IGNORECASE)


def is_placeholder(text: str) -> bool:
    return bool(PLACEHOLDER_RE_TITLE.search(text) or PLACEHOLDER_RE_BODY.search(text))


CODE_FENCE_WRAPPER_RE = re.compile(r"^```(?:mdx?|markdown)?\s*\n(.*)\n```\s*$", re.DOTALL)


def strip_code_fence_wrapper(text: str) -> str:
    """LLM が全文を ```mdx ... ``` で囲んだ場合に剥がす。"""
    m = CODE_FENCE_WRAPPER_RE.match(text.strip())
    if m:
        return m.group(1)
    return text


def load_en2id_glossary() -> dict[str, str]:
    """zh-en.json 与 zh-id.json 经共享 zh key 合成 en→id 对照表。

    同一 en 命中多个不同 id 的歧义对（如 Members→{Anggota, Lihat semua}）会造成
    错误强约束，因此**整对丢弃**，只保留明确 1:1 对（高精度优先）。
    """
    from collections import defaultdict

    with (GLOSSARY_DIR / "zh-en.json").open(encoding="utf-8") as f:
        zh_en = json.load(f)
    with (GLOSSARY_DIR / "zh-id.json").open(encoding="utf-8") as f:
        zh_id = json.load(f)

    candidates: dict[str, set[str]] = defaultdict(set)
    for zh, en_val in zh_en.items():
        id_val = zh_id.get(zh)
        if not id_val:
            continue
        en_key = en_val.strip().strip("`").strip()
        id_clean = id_val.strip().strip("`").strip()
        if not en_key or not id_clean:
            continue
        candidates[en_key].add(id_clean)

    return {en: next(iter(ids)) for en, ids in candidates.items() if len(ids) == 1}


# 英語語境では単語境界でマッチ（Bot が Both に誤マッチするのを防ぐ）
def _term_pattern(term: str) -> re.Pattern:
    # 英数字始まり・終わりなら \b、それ以外は素直に escape
    left = r"\b" if term[:1].isalnum() else ""
    right = r"\b" if term[-1:].isalnum() else ""
    return re.compile(left + re.escape(term) + right, re.IGNORECASE)


def extract_hit_terms(source: str, glossary: dict[str, str], cap: int = 90) -> dict[str, str]:
    """英語ソースに出現する en key を長い順に拾う（上限 cap でプロンプト肥大を防ぐ）。"""
    hits: dict[str, str] = {}
    for en in sorted(glossary.keys(), key=len, reverse=True):
        if len(en) < 2:
            continue
        if _term_pattern(en).search(source):
            hits[en] = glossary[en]
            if len(hits) >= cap:
                break
    return hits


def build_user_message(hits: dict[str, str], source: str) -> str:
    if hits:
        terms_json = json.dumps(hits, ensure_ascii=False, indent=2)
        return (
            "本篇命中的项目术语 en→id 对照表（强约束 — 必须严格按此译，不得换同义词）：\n"
            f"```json\n{terms_json}\n```\n\n"
            "凡未在表中出现的术语，按你自己的判断译，保持同等专业度。\n\n"
            "---\n\n"
            "下面是英文原文 mdx。按上面所有铁律、SEO 规则、风格指南译为印尼文（直接输出译文 mdx，不要任何前后缀）：\n\n"
            f"{source}"
        )
    return (
        "下面是英文原文 mdx。按所有铁律、SEO 规则、风格指南译为印尼文（直接输出译文 mdx，不要任何前后缀）：\n\n"
        f"{source}"
    )


def build_system_prompt(root: str = "") -> str:
    sections = [SYSTEM_RULES, SEO_DESCRIPTION_RULE, STYLE_ID]
    if root == "open":
        sections.append(OPEN_PLATFORM_RULES)
    if root == "yida":
        sections.append(YIDA_RULES)
    sections.append("本次任务把英文 mdx 译为印尼文（Bahasa Indonesia，商务书面语 bahasa baku）。直接输出译文 mdx，不加任何前后缀说明。")
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# 翻訳ユニット
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
    # user_msg 作为 positional prompt 传入（而非 stdin），规避 claude CLI 高负载下 3s stdin
    # 握手竞争导致的 "no stdin data received" 死锁；prompt 体量 ~20-40KB 远低于 ARG_MAX(1MB)。
    proc = await asyncio.create_subprocess_exec(
        "claude", "-p", "--bare",
        "--model", model,
        "--system-prompt", system_prompt,
        "--tools", "",
        "--no-session-persistence",
        "--output-format", "json",
        user_msg,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
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

    # 既存の非占位訳文はスキップ（aitable の既存 144 篇を保護 / 断点続跑）
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
                cleaned = strip_code_fence_wrapper(result_text).strip() + "\n"
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

        backoff = 2 ** attempt * 3
        print(f"  ! {rel} attempt {attempt + 1} failed: {last_err}; retry in {backoff}s", file=sys.stderr)
        await asyncio.sleep(backoff)

    return FileResult(rel=rel, status="failed", error=last_err)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def gather_tasks(
    root: str,
    only: str | None,
    bucket_id: int | None = None,
    bucket_count: int | None = None,
) -> list[FileTask]:
    # 特例：root == "." 只译仓库根的 index.mdx（Overview 首页）→ id/index.mdx
    if root in (".", ""):
        src = REPO_ROOT / "index.mdx"
        if not src.exists():
            sys.exit(f"ERROR: root index.mdx not found: {src}")
        return [FileTask(source=src, target=REPO_ROOT / "id" / "index.mdx", rel="index.mdx")]

    en_root = REPO_ROOT / root
    if not en_root.exists():
        sys.exit(f"ERROR: en source dir not found: {en_root}")
    target_base = REPO_ROOT / "id" / root

    tasks: list[FileTask] = []
    for mdx in sorted(en_root.rglob("*.mdx")):
        rel = mdx.relative_to(en_root)
        target = target_base / rel
        rel_str = str(Path(root) / rel)
        if only and not rel_str.startswith(only):
            continue
        tasks.append(FileTask(source=mdx, target=target, rel=rel_str))

    # 多进程分桶：按文件大小 round-robin 均衡，各桶交给独立 OS 进程（concurrency=1）跑，
    # 规避 asyncio 多子进程 stdin 死锁（claude CLI 3s stdin 超时竞争）。
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
        "# EN→JA Translation Report",
        "",
        f"- 开始：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(started))}",
        f"- 结束：{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ended))}",
        f"- 用时：{round(ended - started, 1)}s",
        "",
        f"- 总：{total} / ok: {ok} / skipped: {skipped} / failed: {failed} / dry-run: {dry}",
        f"- input tokens: {sum_in:,} / output tokens: {sum_out:,} / cost: ${sum_cost:.4f}",
        "",
    ]
    if failed:
        lines += ["## 失败清单", ""]
        for r in results:
            if r.status == "failed":
                lines.append(f"- `{r.rel}`：{r.error}")
        lines.append("")
    report_md.write_text("\n".join(lines), encoding="utf-8")


async def main_async(args: argparse.Namespace) -> int:
    model = args.model or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
    glossary = load_en2id_glossary()
    system_prompt = build_system_prompt(args.root)
    sem = asyncio.Semaphore(args.concurrency)

    tasks = gather_tasks(args.root, args.only, args.bucket_id, args.bucket_count)
    if args.limit:
        tasks = tasks[: args.limit]

    print(
        f"[info] EN→ID root={args.root} 任务数={len(tasks)} only={args.only} "
        f"concurrency={args.concurrency} model={model} glossary_en2id={len(glossary)}"
    )
    if args.dry_run:
        print("[info] dry-run：只统计命中术语，不调 LLM、不写文件")

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
            print(f"[{done}/{len(tasks)}] {icon} {r.rel}  {r.elapsed_s}s out={r.output_tokens} ${r.cost_usd:.3f} hits={r.hit_terms_count}")
        elif r.status == "failed":
            print(f"[{done}/{len(tasks)}] {icon} {r.rel}  FAILED: {r.error}", file=sys.stderr)
        else:
            print(f"[{done}/{len(tasks)}] {icon} {r.rel}  {r.status}")

    ended = time.time()
    suffix = f"_{args.root}"
    if args.only:
        suffix += "_" + re.sub(r"[^a-zA-Z0-9]+", "-", args.only)
    if args.bucket_id is not None and args.bucket_count:
        suffix += f"_bucket{args.bucket_id}of{args.bucket_count}"
    write_report(results, OUTPUT_DIR / "id", started, ended, suffix)

    failed = [r for r in results if r.status == "failed"]
    print(f"\n[done] report: {OUTPUT_DIR / 'id' / f'report{suffix}.md'}")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="批量翻译 mdx：<root>/ (en 母版) → id/<root>/ (印尼文，保留图片)")
    p.add_argument("--root", required=True, help="en 母版根目录名，如 meetings / aitable / contacts")
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--model", default=None, help="覆盖默认 ANTHROPIC_MODEL")
    p.add_argument("--timeout", type=int, default=300, help="单次 claude CLI 调用超时秒数")
    p.add_argument("--only", default=None, help="只跑路径前缀，如 aitable/data-connectors")
    p.add_argument("--limit", type=int, default=0, help="只跑前 N 篇")
    p.add_argument("--force", action="store_true", help="覆盖非占位的已译文件")
    p.add_argument("--dry-run", action="store_true", help="只列任务 + 命中术语")
    p.add_argument("--bucket-id", type=int, default=None, dest="bucket_id",
                   help="多进程分桶：本进程跑桶 N（0..bucket_count-1），与 --bucket-count 配合")
    p.add_argument("--bucket-count", type=int, default=None, dest="bucket_count",
                   help="多进程分桶总数；各桶独立 OS 进程 concurrency=1 跑，规避 stdin 死锁")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main_async(args)))
