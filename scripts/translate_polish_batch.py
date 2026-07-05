#!/usr/bin/env python3
"""
批量润色已译 mdx：<root>/*.mdx (en) 或 ja/<root>/*.mdx (ja) → 同路径覆盖。

与 translate_mdx_batch.py 的关系：
- translate：zh → 目标语言（首译）
- polish：目标语言 → 同语言（语言层打磨，不改语义）

实现方式：通过 `claude -p --bare --model claude-opus-4-7` 子进程调用，与翻译批次一致。

特性：
- 内嵌 10 条 review checklist 作为强约束（术语 / 句长 / 主动语态 / 链接锚 / 列表平行 / 时态 / 标点 / 大小写 / 代码块标题 / alt）
- 词库强约束：命中术语注入到 user message
- 占位拒绝：检测到 TODO 占位即 skip + 报错（先用 translate-batch）
- 已 polish 标记：frontmatter 加 `polished: true`，二次跑默认 skip
- 安全护栏：对比前后链接数 / 组件标签数，差异 > 0 拒绝写入
- 断点续跑 + 失败重试 3 次（指数退避 3/6/12s）
- 报告：scripts/output/polish_docs/<lang>/{report.json,report.md}

CLI:
  python3 scripts/translate_polish_batch.py --root docs --lang en
  python3 scripts/translate_polish_batch.py --root docs --lang ja --concurrency 4
  python3 scripts/translate_polish_batch.py --root aitable --lang en --only aitable/dashboard --limit 3
  python3 scripts/translate_polish_batch.py --root docs --lang en --force
  python3 scripts/translate_polish_batch.py --root docs --lang en --dry-run --limit 2
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
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "polish_docs"


# ---------------------------------------------------------------------------
# Prompt 资产
# ---------------------------------------------------------------------------

POLISH_RULES = """你是钉钉国际版帮助中心的资深技术文档润色编辑。你的任务是对已经翻译过的英 / 日 mdx 做语言层面打磨，让它达到母语级流畅 + 商务专业。

铁律（违反则润色无效，会被脚本拒绝写入）：
1. 【绝不改语义】不增删任何信息点、不合并段落、不重排节顺序；信息密度与原文 1:1。
2. 【绝不改链接】所有 [text](url) 中 url 完全保持不变；锚文本 text 仅当明显机翻或无意义时才微调。
3. 【绝不改 frontmatter 字段名】title / description 的 value 可微调风格；其它字段 (sidebarTitle / icon / tag / sidebar_position 等) 完全不动。
4. 【绝不改组件】所有 MDX 组件标签 (<Note> <Tip> <Warning> <Info> <Check> <Card> <CardGroup> <Steps> <Step> <Tabs> <Tab> <Accordion> <AccordionGroup> <CodeGroup> <Update> <Frame> <Icon>) 的标签名 / 嵌套结构 / props (title / icon / href / cols / caption / ...) 完全不动；只润色子节点中的可见文本。
5. 【绝不改代码块】``` 代码块内部内容完全不动；代码块的 title="x" 中 x 仅当机翻明显时才润色。
6. 【绝不改图片 / 视频】保留所有 ![alt](url)、<img>、<video>、<iframe>、<Frame> 完全不动；alt 文本仅在明显是机翻碎片时才修改。
7. 输出必须是合法 mdx，严禁包裹在 ```mdx ``` 代码块里，严禁加任何"以下是润色后"前后缀，第一个字符必须就是 mdx 内容。
8. 在 frontmatter 末尾追加一行 `polished: true`（如果已有就保留，不重复添加）；其它字段顺序不动。
9. 如果原文已经达标（无需任何修改），原样输出（仍需追加 polished: true 标记）。"""


REVIEW_CHECKLIST = """Review checklist（按以下 10 维度逐条审视并改进）：

1. 术语一致性：未在术语表中出现的同义词统一为词库首选译法（见下方术语注入表）
2. 句长：长复合句拆短；英文单句不超 30 词；日文单句不超 50 字
3. 语态：英文优先 imperative / active voice（"Click X" 而非 "You can click X"）；日文用 です・ます調 + 体言止め混合避免单调
4. 链接锚文本：[text](/foo) 中 text 与目标页 frontmatter title 风格一致；不留 [click here] [これ] 之类无意义锚文本
5. 列表平行：同级 bullet 起首词性 / 时态 / 单复数对齐
6. 时态：description / heading 多用现在时；release notes 行业表达规范化（New / Improved / Fixed / Deprecated 或 新機能 / 改善 / 修正 / 廃止）
7. 标点：英文用半角 . , ? ! "" ()；日文用全角 。、「」（）；不混用全 / 半角
8. 大小写：英文 heading 用 sentence case（仅首字母 + 专有名词大写），不用 Title Case
9. 代码块标题：```bash title="..." 中 title 文本通顺、有意义，不直翻中文
10. 截图 alt：![alt](url) 中 alt 是描述性短句，不是机翻碎片"""


STYLE_EN = """风格指南（英文）：
- 目标读者：钉钉国际版企业用户与 IT 管理员
- 语气：清晰、专业、动作导向（imperative voice）
- 句式：短句优先；避免被动语态；避免长定语；一句话讲一件事
- Heading：Sentence case；避免 Title Case
- 用词：避免 Chinglish；避免口语俚语；优先朴素商务英文
- 数字 / 日期：1,000；24-hour；日期 Month DD, YYYY
- 标点：全英文 + 直引号 ""
- 品牌词不译：DingTalk / DingTalk Docs / DingTalk Spreadsheet / DingTalk Mind / DingTalk Whiteboard / Knowledge Base / AI Table 遵循术语表"""


STYLE_JA = """風格指南（日文）：
- 目标读者：日本企業ユーザーと IT 担当者
- 语气：です・ます調（敬体）
- 句式：短文优先；按日语自然语序重构；外来语用片假名
- 见出し：体言止め or 动词原形结句；避免「〜について」滥用
- 用词：钉钉品牌词不译；功能名优先用词库；通用 IT 术语用日本主流译法（設定 / 機能 / 権限 / ファイル / フォルダ / ダウンロード / アップロード / ログイン）
- 标点：、。「」（）；数字半角；日付 2026年6月2日
- 注意：避免中文式 kanji 顺序、避免「的」直译为「の」过多"""


STYLE_ID = """Panduan gaya (Bahasa Indonesia)：
- 目标读者：印尼企业用户与 IT 管理员（bahasa baku 商务书面语）
- 语气：清晰、专业、动作导向（imperative：Klik / Pilih / Buka，不写 Anda dapat mengklik）
- 句式：短句优先；避免被动堆砌；一句话讲一件事
- Heading：Sentence case；避免 Title Case
- 用词：通用 IT 术语用印尼语主流译法（Pengaturan / Fitur / Izin / File / Folder / Unduh / Unggah / Masuk / Kelola / Bagikan / Simpan / Kirim）
- 技术缩写保持英文：API / SDK / URL / JSON / SaaS / SSO / OAuth / H5 / QR
- 数字 / 日期：千分位「.」小数「,」（1.000）；日期 2 Juni 2026
- 标点：拉丁标点 . , ? ! " ( )
- 品牌词不译：DingTalk / DingTalk Docs / DingTalk Spreadsheet / DingTalk Mind / DingTalk Whiteboard / Knowledge Base / AI Table / AI Minutes 遵循术语表
- 功能更新：Baru / Ditingkatkan / Diperbaiki / Tidak digunakan lagi"""


# 开放平台 (Open Platform / OpenAPI) 专属润色规则 — 仅 root=open 注入，防止润色改坏 API 契约
OPEN_PLATFORM_POLISH_RULES = """开放平台 (Open Platform / OpenAPI) 专属规则 — 润色时违反任意一条则无效：

【术语一致（润色时统一，但不得误译）】
A. 「机器人」一律 Bot（英文），**绝不 Robot**；已是 Bot 的保持。
B. API 契约字符串一律保持原样，禁止「顺手翻译」：JSON 字段名 / 参数名（access_token / corpId / userid / unionId / grant_type 等）/ HTTP 动词 / 状态码 / Header 名 / Content-Type / API 端点 URL 与 {占位符} / 错误码字符串（如 InvalidParameter.AccessToken）。这些即使看起来「像没翻译」，也**必须留英文原样**。
C. 技术缩写保持英文：API / SDK / URL / JSON / OAuth / JSAPI / Webhook / SSO / H5 / IM。
D. 代码块内部（含注释、变量名、方法名、SDK 调用）完全不动（已被铁律 5 覆盖，此处再次强调）。

【风格】
E. 英文/印尼文 Heading 用 Sentence case + 专有名词大写；动作导向祈使句（Klik / Panggil / Konfigurasikan）。
F. 参数表列头统一：Name / Type / Required / Example / Description（印尼文 Nama / Tipe / Wajib / Contoh / Deskripsi）。"""


# ---------------------------------------------------------------------------
# 检测：占位 / 已 polish / 链接组件统计
# ---------------------------------------------------------------------------

PLACEHOLDER_RE_TITLE = re.compile(r"^title:\s*[\"']?.*(?:TODO translate|TODO 翻訳|TODO 翻译)", re.MULTILINE)
PLACEHOLDER_RE_BODY = re.compile(r"\{/\*\s*TODO:?\s*(?:Translate from|.*?から翻訳|.*?翻译自)", re.IGNORECASE)
POLISHED_RE = re.compile(r"^polished:\s*true\s*$", re.MULTILINE)
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
CODE_FENCE_WRAPPER_RE = re.compile(r"^```(?:mdx?|markdown)?\s*\n(.*)\n```\s*$", re.DOTALL)

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
COMPONENT_OPEN_RE = re.compile(r"<([A-Z][A-Za-z]*)\b")


def is_placeholder(text: str) -> bool:
    return bool(PLACEHOLDER_RE_TITLE.search(text) or PLACEHOLDER_RE_BODY.search(text))


def is_polished(text: str) -> bool:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return False
    return bool(POLISHED_RE.search(m.group(1)))


def count_links_and_components(text: str) -> tuple[int, dict[str, int]]:
    links = len(LINK_RE.findall(text))
    comps: dict[str, int] = {}
    for name in COMPONENT_OPEN_RE.findall(text):
        comps[name] = comps.get(name, 0) + 1
    return links, comps


def strip_code_fence_wrapper(text: str) -> str:
    m = CODE_FENCE_WRAPPER_RE.match(text.strip())
    if m:
        return m.group(1)
    return text


# ---------------------------------------------------------------------------
# 词库
# ---------------------------------------------------------------------------

def load_glossary(lang: str) -> dict[str, str]:
    path = GLOSSARY_DIR / f"zh-{lang}.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def extract_hit_terms(text: str, glossary: dict[str, str]) -> dict[str, str]:
    """polish 输入是目标语言译文；按词库 value（已译词）反查命中。"""
    hits: dict[str, str] = {}
    for zh, target in glossary.items():
        if not target:
            continue
        # 简单词出现检测：用 value 在译文中匹配；命中即记录
        if target in text:
            hits[zh] = target
    return hits


def build_user_message(hits: dict[str, str], source: str) -> str:
    if hits:
        terms_json = json.dumps(hits, ensure_ascii=False, indent=2)
        terms_block = (
            "本篇命中的项目术语对照表（强约束 — 同义词请统一为下表 value 的首选译法）：\n"
            f"```json\n{terms_json}\n```\n\n"
            "凡未在表中出现的术语保持原样，不要「过度润色」反而引入不一致。\n\n"
            "---\n\n"
        )
    else:
        terms_block = ""
    return (
        terms_block
        + "下面是已译 mdx 全文，按所有铁律和 Review checklist 做语言层打磨（直接输出润色后 mdx，不要任何前后缀）：\n\n"
        + source
    )


def build_system_prompt(lang: str, root: str = "") -> str:
    style = {"en": STYLE_EN, "ja": STYLE_JA, "id": STYLE_ID}[lang]
    target = {
        "en": "英文（American English）",
        "ja": "日文（敬体 です・ます）",
        "id": "印尼文（Bahasa Indonesia，bahasa baku）",
    }[lang]
    open_block = f"\n\n{OPEN_PLATFORM_POLISH_RULES}" if root == "open" else ""
    return (
        f"{POLISH_RULES}\n\n{REVIEW_CHECKLIST}\n\n{style}{open_block}\n\n"
        f"本次任务：对已经是 {target} 的 mdx 做语言层润色，不改语义、不改链接、不改组件。"
    )


# ---------------------------------------------------------------------------
# 任务 / 结果
# ---------------------------------------------------------------------------

@dataclass
class FileTask:
    target: Path
    rel: str = ""


@dataclass
class FileResult:
    rel: str
    status: str  # ok / skipped / failed / dry-run
    elapsed_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    hit_terms_count: int = 0
    src_chars: int = 0
    error: str = ""


# ---------------------------------------------------------------------------
# Claude CLI 调用
# ---------------------------------------------------------------------------

async def call_claude_cli(system_prompt: str, user_msg: str, model: str, timeout_s: int) -> tuple[str, dict]:
    # user_msg 作为 positional prompt 传入（而非 stdin），规避 claude CLI 高负载下 3s stdin
    # 握手竞争导致的 "no stdin data received" 死锁；prompt 体量远低于 ARG_MAX(1MB)。
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


# ---------------------------------------------------------------------------
# 单篇打磨
# ---------------------------------------------------------------------------

async def polish_one(
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
        source_text = task.target.read_text(encoding="utf-8")
    except Exception as e:
        return FileResult(rel=rel, status="failed", error=f"read target: {e}")

    if is_placeholder(source_text):
        return FileResult(
            rel=rel, status="skipped", src_chars=len(source_text),
            error="placeholder — run /docs-translate-batch first",
        )

    if not force and is_polished(source_text):
        return FileResult(rel=rel, status="skipped", src_chars=len(source_text), error="already polished")

    hits = extract_hit_terms(source_text, glossary)
    user_msg = build_user_message(hits, source_text)
    src_links, src_comps = count_links_and_components(source_text)

    if dry_run:
        print(f"[dry-run] {rel}  hit_terms={len(hits)}  src_chars={len(source_text)}  links={src_links}  comps={sum(src_comps.values())}")
        return FileResult(
            rel=rel, status="dry-run",
            hit_terms_count=len(hits), src_chars=len(source_text),
        )

    last_err = ""
    for attempt in range(3):
        async with sem:
            t0 = time.time()
            try:
                result_text, usage = await call_claude_cli(system_prompt, user_msg, model, timeout_s)
                elapsed = time.time() - t0
                cleaned = strip_code_fence_wrapper(result_text)
                # 安全护栏：对比前后链接 / 组件
                dst_links, dst_comps = count_links_and_components(cleaned)
                if dst_links != src_links:
                    raise RuntimeError(f"link count drift: src={src_links} dst={dst_links}")
                src_total = sum(src_comps.values())
                dst_total = sum(dst_comps.values())
                if dst_total != src_total:
                    raise RuntimeError(f"component count drift: src={src_total} dst={dst_total}")
                # 强制 polished 标记（如果 LLM 漏了）
                if not is_polished(cleaned):
                    cleaned = ensure_polished_flag(cleaned)
                task.target.write_text(cleaned, encoding="utf-8")
                return FileResult(
                    rel=rel,
                    status="ok",
                    elapsed_s=round(elapsed, 2),
                    input_tokens=usage.get("input_tokens", 0) or 0,
                    output_tokens=usage.get("output_tokens", 0) or 0,
                    cost_usd=usage.get("cost_usd", 0.0) or 0.0,
                    hit_terms_count=len(hits),
                    src_chars=len(source_text),
                )
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"

        backoff = 2 ** attempt * 3
        print(f"  ! {rel} attempt {attempt + 1} failed: {last_err}; retry in {backoff}s", file=sys.stderr)
        await asyncio.sleep(backoff)

    return FileResult(rel=rel, status="failed", error=last_err, src_chars=len(source_text))


def ensure_polished_flag(text: str) -> str:
    """在 frontmatter 末尾追加 polished: true（如果还没有）。"""
    if is_polished(text):
        return text
    m = FRONTMATTER_RE.match(text)
    if not m:
        # 没有 frontmatter，不动
        return text
    fm = m.group(1).rstrip()
    new_fm = fm + "\npolished: true"
    return text[: m.start()] + f"---\n{new_fm}\n---\n" + text[m.end():]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def gather_tasks(root: str, lang: str, only: str | None) -> list[FileTask]:
    # 特例：root == "." 只润色语言根的 index.mdx（Overview 首页）
    if root in (".", ""):
        base = REPO_ROOT if lang == "en" else REPO_ROOT / lang
        idx = base / "index.mdx"
        if not idx.exists():
            sys.exit(f"ERROR: index.mdx not found: {idx}")
        rel_str = "index.mdx" if lang == "en" else str(Path(lang) / "index.mdx")
        return [FileTask(target=idx, rel=rel_str)]

    if lang == "en":
        target_base = REPO_ROOT / root
    elif lang == "ja":
        target_base = REPO_ROOT / "ja" / root
    elif lang == "id":
        target_base = REPO_ROOT / "id" / root
    else:
        sys.exit(f"ERROR: lang must be en / ja / id, got {lang}")

    if not target_base.exists():
        sys.exit(f"ERROR: target dir not found: {target_base}")

    tasks: list[FileTask] = []
    for mdx in sorted(target_base.rglob("*.mdx")):
        rel = mdx.relative_to(target_base)
        rel_str = str(Path(root) / rel) if lang == "en" else str(Path(lang) / root / rel)
        if only and not rel_str.startswith(only):
            continue
        tasks.append(FileTask(target=mdx, rel=rel_str))
    return tasks


def write_report(results: list[FileResult], out_dir: Path, started: float, ended: float) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_json = out_dir / "report.json"
    report_md = out_dir / "report.md"

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
        "# Polish Batch Report",
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
    lines.append("| rel | status | elapsed | in | out | cost | hits | chars |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results[:100]:
        lines.append(
            f"| {r.rel} | {r.status} | {r.elapsed_s}s | {r.input_tokens} | {r.output_tokens} | ${r.cost_usd:.4f} | {r.hit_terms_count} | {r.src_chars} |"
        )
    if total > 100:
        lines.append(f"\n_（共 {total} 条，仅显示前 100；全量见 report.json）_")

    report_md.write_text("\n".join(lines), encoding="utf-8")


async def main_async(args: argparse.Namespace) -> int:
    model = args.model or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
    glossary = load_glossary(args.lang)
    system_prompt = build_system_prompt(args.lang, args.root)
    sem = asyncio.Semaphore(args.concurrency)

    tasks = gather_tasks(args.root, args.lang, args.only)
    if args.limit:
        tasks = tasks[: args.limit]

    print(
        f"[info] lang={args.lang} root={args.root} 任务数={len(tasks)} "
        f"concurrency={args.concurrency} model={model} timeout={args.timeout}s"
    )
    if args.dry_run:
        print("[info] dry-run：只统计命中术语 + 字符数，不调 LLM、不写文件")
    if args.force:
        print("[info] force=true：忽略 polished 标记，重新打磨")

    started = time.time()
    coros = [
        polish_one(t, glossary, system_prompt, model, args.timeout, args.dry_run, sem, args.force)
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
            extra = f" ({r.error})" if r.error else ""
            print(f"[{done}/{len(tasks)}] {icon} {r.rel}  {r.status}{extra}")

    ended = time.time()
    out_dir = OUTPUT_DIR / args.lang
    write_report(results, out_dir, started, ended)

    failed = [r for r in results if r.status == "failed"]
    print(f"\n[done] report: {out_dir / 'report.md'}")
    if failed:
        print(f"[warn] {len(failed)} 篇失败，详见报告")
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="批量润色已译 mdx：<root>/ (en) / ja/<root>/ (ja) / id/<root>/ (id) 同路径覆盖；不改语义，只改语言质量。",
    )
    p.add_argument("--root", required=True, help="产品根目录名，如 docs / aitable")
    p.add_argument("--lang", required=True, choices=["en", "ja", "id"])
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--model", default=None, help="覆盖默认 ANTHROPIC_MODEL")
    p.add_argument("--timeout", type=int, default=240, help="单次 claude CLI 调用超时秒数")
    p.add_argument("--only", default=None, help="只跑路径前缀，如 docs/dingtalk-docs")
    p.add_argument("--limit", type=int, default=0, help="只跑前 N 篇")
    p.add_argument("--force", action="store_true", help="忽略 polished 标记重新打磨")
    p.add_argument("--dry-run", action="store_true", help="只列任务 + 命中术语 + 字符数")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main_async(args)))
