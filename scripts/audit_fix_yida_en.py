#!/usr/bin/env python3
"""
宜搭 en 文档全量抽查后的精准修复批处理（一次性）。

只修三类真问题（详见审计计划），别的一律不动：
  A 普通名词误大写：正文句中被错误首字母大写的普通名词改回小写（the App→the app 等）。
  B 首段与 description 雷同：首段实质复述 frontmatter description → 改写为具体导语或删除。
  C 游离中文：正文散文里混入的 CJK（非代码块/示例数据/i18n 语言名）译成英文。

实现方式与 translate_polish_batch.py 一致：`claude -p --bare` 子进程调用。
复用其经过验证的：CLI 调用、链接/组件数漂移护栏、报告、失败重试。

差异点：
- 输入用显式文件列表 `--files-from`（223 文件散落各组，非单一前缀）。
- 默认 concurrency=1（阿里网关限流坑：密集并发触发 exit1 空输出，见 memory）。
- frontmatter 完全不动（不加 polished 标记；这些文件本就 polished:true）。
- 断点续跑：读上次 report.json，跳过已 ok 的文件（--force 忽略）。
- 不注入词库：审计修复范围窄，词库会诱导 LLM 做 A/B/C 以外的同义词改写。

CLI:
  python3 scripts/audit_fix_yida_en.py --files-from scripts/output/audit_yida_en/affected.txt --dry-run --limit 3
  python3 scripts/audit_fix_yida_en.py --files-from scripts/output/audit_yida_en/affected.txt --concurrency 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import re
from dataclasses import dataclass, asdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "audit_yida_en"

LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
COMPONENT_OPEN_RE = re.compile(r"<([A-Z][A-Za-z]*)\b")
CODE_FENCE_WRAPPER_RE = re.compile(r"^```(?:mdx?|markdown)?\s*\n(.*)\n```\s*$", re.DOTALL)


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

AUDIT_FIX_RULES = """你是钉钉国际版帮助中心的资深英文技术文档编辑。任务：对一篇【已是英文】的 mdx 做三类精准修复，除此之外不做任何改动。

【只修这三类】
A. 普通名词误大写：把正文句子中间被错误首字母大写的普通名词改回小写，例如 the App→the app、an App→an app、the User→the user、the Field→the field、the Department→the department、the Connector→the connector、the Authorization→the authorization、the Formula→the formula、the Chart→the chart、the Notification→the notification、the Step→the step、the Permission→the permission，及它们的复数。
   【务必彻底 —— 这是最常被漏改的一类】逐行逐个表格单元格检查，不要只改前几处就停：
   - 常见漏网词还包括：Employee(s)、Domain、Error、Instance(s)、Template(s)、Record(s)、Component(s)、Column、Row、Value、Submits/Submitted/Created/Approved/Enabled/Disabled（做普通动词/形容词时）、Your（句中 within Your organization→within your organization）。
   - 例：the Organization belongs to→the organization belongs to；Apps Created→apps created；instance Submits→instance submits；by Employees→by employees；second-level Domain→second-level domain；this Error→this error。
   - 但仍严守下方大小写例外（专有功能名 / 组件名 / heading / 加粗 UI 标签 / 句首）。
B. 首段与 description 雷同：若正文的第一个自然段（frontmatter 之后第一段可见文字）实质是在复述 frontmatter 的 description（信息重复），把这一段改写成一句具体的、非重复的定位/导语；若它没有任何新增信息，直接删除该段。只处理这一处，正文其余段落不动。
C. 游离中文：正文散文里若混入中文字符（且不在代码块、不是被讨论的示例数据、不是 i18n 语言名列表），译成对应英文。

【强制保留 —— 违反则本次修复无效被脚本拒绝写入】
1. frontmatter 完全不动：--- 之间所有字段（title / description / polished / sidebarTitle / icon / tag ...）的值与顺序全部保持原样，不新增、不删除、不重排任何字段。
2. 所有链接 [text](url)：url 与锚文本 text 完全不变；全篇链接总数不得增减。
3. 所有 MDX 组件（<Note> <Tip> <Warning> <Info> <Check> <Card> <CardGroup> <Steps> <Step> <Tabs> <Tab> <Accordion> <AccordionGroup> <CodeGroup> <Update> <Frame> <Icon> 等）标签名/嵌套结构/props 完全不动；组件标签总数不得增减。
4. 所有代码块 ``` 内部内容（含其中的中文、注释、示例 URL、JSON、错误日志）完全不动——即使看起来像未翻译。
5. 图片/视频/<img>/<video>/<iframe> 完全不动。
6. 【大小写例外，必须保持大写】句首单词；所有 heading（# 开头的行）；**加粗的 UI 标签**（如 **Batch Authorization**、**Authorized**、**Frozen**、**Merge Cells**）；专有品牌/功能名：DingTalk、YiDA、DingTalk Organization Structure、Work Notifications、To-Do、Data Preparation、Data Factory、Open API、Quick BI、DataV 等；表格里作为功能名的行标签。拿不准是否专名时，一律保持原样不动。
7. 不做 A/B/C 以外的任何"润色"：不改句式、不改语态、不改标点、不动没有问题的段落与词。若整篇没有 A/B/C 问题，原样逐字输出。

输出：直接输出修复后的完整 mdx，第一个字符必须是 ---（frontmatter 起始横线）。严禁用 ``` 包裹，严禁任何"以下是修复后""Here is"之类前后缀，严禁输出解释。"""


def build_user_message(source: str) -> str:
    return (
        "下面是一篇 en mdx 全文。按上述铁律只修 A/B/C 三类问题，直接输出修复后的完整 mdx（不要任何前后缀）：\n\n"
        + source
    )


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def count_links_and_components(text: str) -> tuple[int, int]:
    links = len(LINK_RE.findall(text))
    comps = len(COMPONENT_OPEN_RE.findall(text))
    return links, comps


def strip_code_fence_wrapper(text: str) -> str:
    m = CODE_FENCE_WRAPPER_RE.match(text.strip())
    return m.group(1) if m else text


# ---------------------------------------------------------------------------
# 任务 / 结果
# ---------------------------------------------------------------------------

@dataclass
class FileTask:
    target: Path
    rel: str


@dataclass
class FileResult:
    rel: str
    status: str  # ok / skipped / failed / dry-run / unchanged
    elapsed_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    src_chars: int = 0
    changed: bool = False
    error: str = ""


# ---------------------------------------------------------------------------
# Claude CLI 调用（照搬 translate_polish_batch 的稳定实现）
# ---------------------------------------------------------------------------

async def call_claude_cli(system_prompt: str, user_msg: str, model: str, timeout_s: int) -> tuple[str, dict]:
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
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
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
# 单篇修复
# ---------------------------------------------------------------------------

async def fix_one(
    task: FileTask,
    system_prompt: str,
    model: str,
    timeout_s: int,
    dry_run: bool,
    sem: asyncio.Semaphore,
) -> FileResult:
    rel = task.rel
    try:
        source_text = task.target.read_text(encoding="utf-8")
    except Exception as e:
        return FileResult(rel=rel, status="failed", error=f"read: {e}")

    src_links, src_comps = count_links_and_components(source_text)
    user_msg = build_user_message(source_text)

    if dry_run:
        print(f"[dry-run] {rel}  chars={len(source_text)}  links={src_links}  comps={src_comps}")
        return FileResult(rel=rel, status="dry-run", src_chars=len(source_text))

    last_err = ""
    for attempt in range(3):
        async with sem:
            t0 = time.time()
            try:
                result_text, usage = await call_claude_cli(system_prompt, user_msg, model, timeout_s)
                elapsed = time.time() - t0
                cleaned = strip_code_fence_wrapper(result_text)
                # 护栏：链接 / 组件数漂移即拒绝
                dst_links, dst_comps = count_links_and_components(cleaned)
                if dst_links != src_links:
                    raise RuntimeError(f"link drift: src={src_links} dst={dst_links}")
                if dst_comps != src_comps:
                    raise RuntimeError(f"component drift: src={src_comps} dst={dst_comps}")
                # 护栏：必须以 frontmatter 起始，避免 LLM 吞掉 ---
                if not cleaned.lstrip().startswith("---"):
                    raise RuntimeError("output missing frontmatter start")
                changed = cleaned != source_text
                if changed:
                    task.target.write_text(cleaned, encoding="utf-8")
                return FileResult(
                    rel=rel,
                    status="ok" if changed else "unchanged",
                    elapsed_s=round(elapsed, 2),
                    input_tokens=usage.get("input_tokens", 0) or 0,
                    output_tokens=usage.get("output_tokens", 0) or 0,
                    cost_usd=usage.get("cost_usd", 0.0) or 0.0,
                    src_chars=len(source_text),
                    changed=changed,
                )
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
        backoff = 2 ** attempt * 3
        print(f"  ! {rel} attempt {attempt + 1} failed: {last_err}; retry in {backoff}s", file=sys.stderr)
        await asyncio.sleep(backoff)

    return FileResult(rel=rel, status="failed", error=last_err, src_chars=len(source_text))


# ---------------------------------------------------------------------------
# 文件收集 + 断点续跑
# ---------------------------------------------------------------------------

def gather_tasks(files_from: Path) -> list[FileTask]:
    if not files_from.exists():
        sys.exit(f"ERROR: --files-from not found: {files_from}")
    tasks: list[FileTask] = []
    for line in files_from.read_text(encoding="utf-8").splitlines():
        rel = line.strip()
        if not rel or rel.startswith("#"):
            continue
        p = (REPO_ROOT / rel).resolve()
        if not p.exists():
            print(f"[warn] 列表中文件不存在，跳过: {rel}", file=sys.stderr)
            continue
        tasks.append(FileTask(target=p, rel=rel))
    return tasks


def load_done_rels(report_json: Path) -> set[str]:
    """断点续跑：上次 report 里 ok / unchanged 的文件跳过。"""
    if not report_json.exists():
        return set()
    try:
        prior = json.loads(report_json.read_text(encoding="utf-8"))
    except Exception:
        return set()
    return {r["rel"] for r in prior if r.get("status") in ("ok", "unchanged")}


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

def write_report(results: list[FileResult], out_dir: Path, started: float, ended: float) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total = len(results)
    ok = sum(1 for r in results if r.status == "ok")
    unchanged = sum(1 for r in results if r.status == "unchanged")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")
    sum_cost = sum(r.cost_usd for r in results)
    sum_in = sum(r.input_tokens for r in results)
    sum_out = sum(r.output_tokens for r in results)
    lines = [
        "# Audit-Fix (yida en) Report", "",
        f"- 用时：{round(ended - started, 1)}s",
        f"- 总：{total} / 改动 ok: {ok} / 无改动: {unchanged} / skipped: {skipped} / failed: {failed}",
        f"- input tokens: {sum_in:,} / output tokens: {sum_out:,} / cost: ${sum_cost:.4f}", "",
    ]
    if failed:
        lines += ["## 失败清单", ""]
        lines += [f"- `{r.rel}`：{r.error}" for r in results if r.status == "failed"]
        lines.append("")
    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


async def main_async(args: argparse.Namespace) -> int:
    model = args.model or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
    sem = asyncio.Semaphore(args.concurrency)

    tasks = gather_tasks(Path(args.files_from))
    if not args.force and not args.dry_run:
        done = load_done_rels(OUTPUT_DIR / "report.json")
        if done:
            before = len(tasks)
            tasks = [t for t in tasks if t.rel not in done]
            print(f"[resume] 上次已完成 {len(done)} 篇，本次剩 {len(tasks)}/{before}")
    if args.limit:
        tasks = tasks[: args.limit]

    print(f"[info] 任务数={len(tasks)} concurrency={args.concurrency} model={model} timeout={args.timeout}s"
          + ("  [dry-run]" if args.dry_run else ""))

    started = time.time()
    coros = [fix_one(t, AUDIT_FIX_RULES, model, args.timeout, args.dry_run, sem) for t in tasks]
    results: list[FileResult] = []
    done = 0
    for coro in asyncio.as_completed(coros):
        r = await coro
        results.append(r)
        done += 1
        icon = {"ok": "✓", "unchanged": "·", "skipped": "·", "failed": "✗", "dry-run": "?"}.get(r.status, "?")
        if r.status == "ok":
            print(f"[{done}/{len(tasks)}] {icon} {r.rel}  {r.elapsed_s}s  in={r.input_tokens} out={r.output_tokens} ${r.cost_usd:.3f}")
        elif r.status == "failed":
            print(f"[{done}/{len(tasks)}] {icon} {r.rel}  FAILED: {r.error}", file=sys.stderr)
        else:
            print(f"[{done}/{len(tasks)}] {icon} {r.rel}  {r.status}")

    ended = time.time()
    write_report(results, OUTPUT_DIR, started, ended)
    print(f"\n[done] report: {OUTPUT_DIR / 'report.md'}")
    return 1 if any(r.status == "failed" for r in results) else 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="宜搭 en 抽查修复批处理（A 误大写 / B 首段去重 / C 游离中文）")
    p.add_argument("--files-from", required=True, help="待处理文件列表（每行一个 repo 相对路径）")
    p.add_argument("--concurrency", type=int, default=1, help="并发路数（默认 1，避网关限流）")
    p.add_argument("--model", default=None, help="覆盖默认 ANTHROPIC_MODEL")
    p.add_argument("--timeout", type=int, default=240, help="单次 claude 调用超时秒")
    p.add_argument("--limit", type=int, default=0, help="只跑前 N 篇")
    p.add_argument("--force", action="store_true", help="忽略断点，全部重跑")
    p.add_argument("--dry-run", action="store_true", help="只列任务，不调 LLM 不写文件")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async(parse_args())))
