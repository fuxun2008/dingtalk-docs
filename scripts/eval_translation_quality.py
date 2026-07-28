#!/usr/bin/env python3
"""
换模型翻译质量测评（LLM-as-judge）：用一个**独立于翻译模型**的评委,对印尼语 (id)
译文做准确性 + 本地化程度 + 流畅度 + 术语一致性的 4 维打分,并逐条定位问题。

背景:id 译文由 translate_mdx_en2id.py（默认 opus-4-7）以英文母版为源翻译生成,
只跑过润色(生成期约束),从未被另一个模型独立评审。本脚本换用 **claude-opus-4-8**
(与 4-7 独立)当评委,给出可量化、可定位的质量报告。

- 只读评测:**不写任何译文**,只写 scripts/output/eval_docs/<lang>/report*.{json,md}。
- 对照:en 母版 <root>/<rel>  ↔  id 译文 id/<root>/<rel>（id 走 en→id,以英文为源）。
- 复用 translate_mdx_en2id.py 的机械设施:call_claude_cli / load_en2id_glossary /
  extract_hit_terms（DRY,不重造轮子）。
- 抽样:9 个帮助中心产品线 + 开放平台按篇数分层随机抽,确定性种子(可复现);
  支持 --full 全量、--only <root> 限定、--target N、--limit N。

CLI:
  # 干跑：只列抽样 + 命中术语,不调评委
  python3 scripts/eval_translation_quality.py --dry-run

  # 先跑 3 篇验证报告结构 / json 可解析 / cost 回传
  python3 scripts/eval_translation_quality.py --limit 3

  # 默认分层抽样 ~50 篇
  python3 scripts/eval_translation_quality.py --target 50 --concurrency 3

  # 只评某产品线全量
  python3 scripts/eval_translation_quality.py --only im --full

  # 全量 959 篇
  python3 scripts/eval_translation_quality.py --full
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path

# 复用翻译脚本的机械设施（不重造轮子）
sys.path.insert(0, str(Path(__file__).resolve().parent))
from translate_mdx_en2id import (  # noqa: E402
    REPO_ROOT,
    call_claude_cli,
    load_en2id_glossary,
    extract_hit_terms,
    strip_code_fence_wrapper,
)
from translate_mdx_en2ja import load_en2ja_glossary  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "eval_docs"

# 帮助中心产品线（每个是一个抽样层）；"open" = 开放平台;"overview" = 仓库根 index.mdx
HELP_ROOTS = ["aitable", "docs", "meetings", "drive", "mail", "calendar", "im", "contacts", "ai-minutes", "yida"]


# ---------------------------------------------------------------------------
# 评委 rubric（system prompt）
# ---------------------------------------------------------------------------

JUDGE_SYSTEM = """你是资深的印尼语 (Bahasa Indonesia) 技术文档本地化质量评审专家,母语级印尼语 + 精通英文技术文档。
你的任务:拿到「英文母版」和「印尼语译文」,严格评审译文质量,给出 4 个维度的 0-5 分打分,并逐条定位具体问题。

评审对象是钉钉国际版帮助中心的官方文档,面向印尼企业用户与 IT 管理员,要求母语级流畅 + 商务正式书面语 (bahasa baku)。

【4 个评分维度(每个 0-5 分,可给 0.5)】
1. accuracy 准确性:译文是否忠实传达英文原意。扣分项:漏译、错译、增译、语义偏移、否定/条件/数量译反、指代错误。
   - 5=完全忠实无偏差;4=个别细节轻微不精确;3=有 1-2 处影响理解的偏差;2=多处偏差;≤1=严重失真。
2. localization 本地化程度:是否地道印尼语而非「机器直译腔 / 英式直译」。判据:
   - bahasa baku 正式度得当;IT 术语用印尼主流译法(Pengaturan/Fitur/Izin/File/Unduh/Unggah/Kelola/Bagikan…);
   - 技术缩写保持英文(API/SDK/URL/JSON/SSO/OAuth);品牌词不译(DingTalk/AI Table…);
   - 日期格式 `2 Juni 2026`、千分位 `.`、小数 `,`、拉丁标点;Heading 用 Sentence case;
   - 祈使句动作导向(Klik/Pilih/Buka,而非 Anda dapat mengklik);无冗长被动堆砌。
   - 5=完全地道,母语者写的一样;3=能读懂但有明显翻译腔或格式未本地化;≤1=通篇生硬直译。
3. fluency 流畅度:印尼语母语可读性——语序自然、搭配地道、无语法错误、无生硬拼接。
   - 5=顺畅自然;3=可读但有卡顿/别扭搭配;≤1=多处语法或搭配错误。
4. terminology 术语一致性:命中项目词库的术语是否按规定译法(见 user message 里的「命中术语 en→id 对照表」);
   同一术语全文是否统一。词库未覆盖的术语,判断是否专业且前后一致。
   - 5=全部按词库且统一;3=个别术语未按词库或前后不一;≤1=术语混乱。

【issues 逐条定位(最多 12 条,按 severity 降序)】
每条:severity(high/medium/low)、dimension(accuracy/localization/fluency/terminology)、
en(英文原文片段,≤120 字)、id(现译片段,≤120 字)、suggestion(建议改法,给出具体印尼语)、note(一句话说明为何是问题)。
- high=影响理解或误导用户;medium=明显翻译腔/术语不符/格式错;low=可优化的措辞。
- 只报真实问题;译文若确实高质量,issues 可为空数组,不要硬凑。
- 代码块内的 API 契约(字段名/方法/URL/状态码)本就应保持英文,**不要**报成问题;
  但代码块里 user-facing 的示例字面量(如 "content":"..." 的值)若没译成印尼语,可报 localization。

【输出格式(严格 JSON,第一个字符必须是 `{`,不要 markdown 代码围栏,不要任何前后缀说明)】
{
  "scores": {"accuracy": 4, "localization": 3, "fluency": 4, "terminology": 5},
  "overall": 4.0,
  "summary": "一句话总评(中文)",
  "issues": [
    {"severity": "high", "dimension": "accuracy", "en": "...", "id": "...", "suggestion": "...", "note": "..."}
  ]
}
overall = 4 维加权平均(accuracy 0.35 / localization 0.30 / fluency 0.20 / terminology 0.15),保留 1 位小数。"""


# 日文评审 rubric — 与 id 版同构,判据换为日文本地化标准
JUDGE_SYSTEM_JA = """你是资深的日本语技术文档本地化质量评审专家,母语级日文 + 精通英文技术文档。
你的任务:拿到「英文母版」和「日文译文」,严格评审译文质量,给出 4 个维度的 0-5 分打分,并逐条定位具体问题。

评审对象是钉钉国际版帮助中心的官方文档,面向日本企業ユーザーと IT 担当者,要求母语级流畅 + 商务敬体（です・ます調）。

【4 个评分维度(每个 0-5 分,可给 0.5)】
1. accuracy 准确性:译文是否忠实传达英文原意。扣分项:漏译、错译、增译、语义偏移、否定/条件/数量译反、指代错误。
2. localization 本地化程度:是否地道日文而非「英文直译腔」。判据:
   - 敬体です・ます調得当;外来语片假名规范;通用 IT 术语用日本主流译法(設定/機能/権限/ファイル/ダウンロード/アップロード/ログイン);
   - 技术缩写保持英文(API/SDK/URL/JSON/SSO/OAuth);品牌词不译(DingTalk/Yida/AI Table…);
   - 全角标点 。、「」（）;数字半角;日期 2026年6月2日;API 专有词前后半角空格(access token を取得);
   - 见出し体言止め或动词原形;避免「〜することができます」滥用。
3. fluency 流畅度:日文母语可读性——语序自然、搭配地道、无语法错误、无中文式 kanji 顺序。
4. terminology 术语一致性:命中项目词库的术语是否按规定译法(见 user message 里的「命中术语 en→ja 对照表」);同一术语全文是否统一。

【issues 逐条定位(最多 12 条,按 severity 降序)】
每条:severity(high/medium/low)、dimension(accuracy/localization/fluency/terminology)、
en(英文原文片段,≤120 字)、id(现译片段,≤120 字,此处放日文译文)、suggestion(建议改法,给出具体日文)、note(一句话说明为何是问题)。
- 只报真实问题;译文若确实高质量,issues 可为空数组,不要硬凑。
- 代码块内的 API 契约(字段名/方法/URL/状态码)本就应保持英文,**不要**报成问题。

【输出格式(严格 JSON,第一个字符必须是 `{`,不要 markdown 代码围栏,不要任何前后缀说明)】
{
  "scores": {"accuracy": 4, "localization": 3, "fluency": 4, "terminology": 5},
  "overall": 4.0,
  "summary": "一句话总评(中文)",
  "issues": [
    {"severity": "high", "dimension": "accuracy", "en": "...", "id": "...", "suggestion": "...", "note": "..."}
  ]
}
overall = 4 维加权平均(accuracy 0.35 / localization 0.30 / fluency 0.20 / terminology 0.15),保留 1 位小数。"""


def build_judge_user_message(en_src: str, id_src: str, hits: dict[str, str], lang: str = "id") -> str:
    tgt_label = {"id": "印尼语译文", "ja": "日文译文"}.get(lang, f"{lang} 译文")
    parts: list[str] = []
    if hits:
        terms_json = json.dumps(hits, ensure_ascii=False, indent=2)
        parts.append(
            f"本篇命中的项目术语 en→{lang} 对照表(评 terminology 维度的强参照 —— 译文应严格按此译法):\n"
            f"```json\n{terms_json}\n```"
        )
    parts.append("=== 英文母版 (source) ===\n" + en_src)
    parts.append(f"=== {tgt_label} (translation to evaluate) ===\n" + id_src)
    parts.append("请严格按 system 里的 rubric 评审,只输出 JSON。")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 任务收集 + 分层抽样
# ---------------------------------------------------------------------------

@dataclass
class DocTask:
    product: str
    en_source: Path
    id_target: Path
    rel: str  # 相对 id/ 的路径,如 im/chats-faq.mdx


def product_of(rel: Path) -> str:
    parts = rel.parts
    if len(parts) == 1:  # id/index.mdx
        return "overview"
    return parts[0]


def gather_all_docs(lang: str) -> list[DocTask]:
    lang_root = REPO_ROOT / lang
    if not lang_root.exists():
        sys.exit(f"ERROR: 译文目录不存在: {lang_root}")
    tasks: list[DocTask] = []
    for mdx in sorted(lang_root.rglob("*.mdx")):
        rel = mdx.relative_to(lang_root)
        en_source = REPO_ROOT / rel  # en 母版在仓库根
        if not en_source.exists():
            continue  # 无 en 对照的跳过（不评）
        tasks.append(
            DocTask(product=product_of(rel), en_source=en_source, id_target=mdx, rel=str(rel))
        )
    return tasks


def stratified_sample(docs: list[DocTask], target: int, min_per: int, seed: int) -> list[DocTask]:
    """按 product 分层比例抽样,每层至少 min_per 篇,确定性(seed 可复现)。"""
    by_product: dict[str, list[DocTask]] = defaultdict(list)
    for d in docs:
        by_product[d.product].append(d)
    total = len(docs)
    rng = random.Random(seed)
    sample: list[DocTask] = []
    for product in sorted(by_product):
        items = sorted(by_product[product], key=lambda d: d.rel)  # 确定性顺序
        n_prop = round(target * len(items) / total) if total else 0
        n = min(len(items), max(min_per, n_prop))
        sample.extend(rng.sample(items, n))
    return sorted(sample, key=lambda d: d.rel)


# ---------------------------------------------------------------------------
# 评审单元
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    rel: str
    product: str
    status: str  # ok / failed / skipped / dry-run
    accuracy: float = 0.0
    localization: float = 0.0
    fluency: float = 0.0
    terminology: float = 0.0
    overall: float = 0.0
    summary: str = ""
    issues: list = field(default_factory=list)
    hit_terms_count: int = 0
    elapsed_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str = ""


JSON_OBJ_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_judge_json(text: str) -> dict:
    """解析评委输出:先剥代码围栏,再退化为抓第一个 {...} 块。"""
    cleaned = strip_code_fence_wrapper(text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = JSON_OBJ_RE.search(cleaned)
        if not m:
            raise
        return json.loads(m.group(0))


def _num(v, default: float = 0.0) -> float:
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return default


async def eval_one(
    task: DocTask,
    glossary: dict[str, str],
    model: str,
    timeout_s: int,
    dry_run: bool,
    sem: asyncio.Semaphore,
    lang: str = "id",
    judge_system: str = JUDGE_SYSTEM,
) -> EvalResult:
    en_src = task.en_source.read_text(encoding="utf-8")
    id_src = task.id_target.read_text(encoding="utf-8")
    hits = extract_hit_terms(en_src, glossary)

    if dry_run:
        return EvalResult(rel=task.rel, product=task.product, status="dry-run", hit_terms_count=len(hits))

    user_msg = build_judge_user_message(en_src, id_src, hits, lang)
    last_err = ""
    async with sem:
        for attempt in range(3):
            t0 = time.time()
            try:
                result_text, usage = await call_claude_cli(judge_system, user_msg, model, timeout_s)
                data = parse_judge_json(result_text)
                scores = data.get("scores", {})
                return EvalResult(
                    rel=task.rel,
                    product=task.product,
                    status="ok",
                    accuracy=_num(scores.get("accuracy")),
                    localization=_num(scores.get("localization")),
                    fluency=_num(scores.get("fluency")),
                    terminology=_num(scores.get("terminology")),
                    overall=_num(data.get("overall")),
                    summary=str(data.get("summary", ""))[:400],
                    issues=data.get("issues", []) if isinstance(data.get("issues"), list) else [],
                    hit_terms_count=len(hits),
                    elapsed_s=round(time.time() - t0, 2),
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    cost_usd=usage.get("cost_usd", 0.0),
                )
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
                backoff = 2 ** attempt * 3
                print(f"  ! {task.rel} attempt {attempt + 1} failed: {last_err}; retry in {backoff}s", file=sys.stderr)
                await asyncio.sleep(backoff)
    return EvalResult(rel=task.rel, product=task.product, status="failed", hit_terms_count=len(hits), error=last_err)


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

def write_report(results: list[EvalResult], out_dir: Path, model: str, started: float, ended: float, suffix: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"report{suffix}.json").write_text(
        json.dumps([asdict(r) for r in results], ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ok = [r for r in results if r.status == "ok"]
    failed = [r for r in results if r.status == "failed"]

    def avg(attr: str) -> float:
        return round(sum(getattr(r, attr) for r in ok) / len(ok), 2) if ok else 0.0

    # 按产品线汇总
    by_prod: dict[str, list[EvalResult]] = defaultdict(list)
    for r in ok:
        by_prod[r.product].append(r)

    # 问题模式统计
    dim_sev: dict[tuple[str, str], int] = defaultdict(int)
    total_issues = 0
    for r in ok:
        for iss in r.issues:
            if not isinstance(iss, dict):
                continue
            total_issues += 1
            dim_sev[(iss.get("dimension", "?"), iss.get("severity", "?"))] += 1

    L: list[str] = [
        "# 印尼语翻译质量测评报告(换模型 LLM-as-judge)",
        "",
        f"- 评委模型:`{model}`(译文由 opus-4-7 生成,评委独立)",
        f"- 开始:{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(started))}",
        f"- 结束:{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ended))}  用时 {round(ended - started)}s",
        f"- 抽样:{len(results)} 篇 / ok {len(ok)} / failed {len(failed)}",
        f"- 成本:${sum(r.cost_usd for r in ok):.4f} / output tokens {sum(r.output_tokens for r in ok):,}",
        "",
        "## 总体均分(0-5)",
        "",
        "| 维度 | 均分 |",
        "|---|---|",
        f"| accuracy 准确性 | {avg('accuracy')} |",
        f"| localization 本地化 | {avg('localization')} |",
        f"| fluency 流畅度 | {avg('fluency')} |",
        f"| terminology 术语 | {avg('terminology')} |",
        f"| **overall 综合** | **{avg('overall')}** |",
        "",
        "## 各产品线综合均分",
        "",
        "| 产品线 | 篇数 | overall | accuracy | localization | fluency | terminology |",
        "|---|---|---|---|---|---|---|",
    ]
    for product in sorted(by_prod):
        rs = by_prod[product]
        def pavg(attr: str) -> float:
            return round(sum(getattr(r, attr) for r in rs) / len(rs), 2)
        L.append(
            f"| {product} | {len(rs)} | {pavg('overall')} | {pavg('accuracy')} | "
            f"{pavg('localization')} | {pavg('fluency')} | {pavg('terminology')} |"
        )

    L += ["", "## 问题分布(维度 × 严重度)", "", f"共 {total_issues} 条问题", "", "| 维度 | high | medium | low |", "|---|---|---|---|"]
    for dim in ["accuracy", "localization", "fluency", "terminology"]:
        L.append(f"| {dim} | {dim_sev.get((dim,'high'),0)} | {dim_sev.get((dim,'medium'),0)} | {dim_sev.get((dim,'low'),0)} |")

    # 最低分 Top 15
    lowest = sorted(ok, key=lambda r: r.overall)[:15]
    L += ["", "## 综合分最低 15 篇(优先复核)", "", "| overall | acc | loc | flu | term | 篇目 | 总评 |", "|---|---|---|---|---|---|---|"]
    for r in lowest:
        L.append(
            f"| {r.overall} | {r.accuracy} | {r.localization} | {r.fluency} | {r.terminology} | `{r.rel}` | {r.summary} |"
        )

    # 高严重度问题清单(前 40)
    high_issues: list[tuple[str, dict]] = []
    for r in ok:
        for iss in r.issues:
            if isinstance(iss, dict) and iss.get("severity") == "high":
                high_issues.append((r.rel, iss))
    if high_issues:
        L += ["", "## 高严重度问题清单(前 40)", ""]
        for rel, iss in high_issues[:40]:
            L.append(f"- **`{rel}`** [{iss.get('dimension','?')}] {iss.get('note','')}")
            L.append(f"  - en: {iss.get('en','')}")
            L.append(f"  - id: {iss.get('id','')}")
            L.append(f"  - 建议: {iss.get('suggestion','')}")

    if failed:
        L += ["", "## 失败清单", ""]
        for r in failed:
            L.append(f"- `{r.rel}`:{r.error}")

    (out_dir / f"report{suffix}.md").write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def main_async(args: argparse.Namespace) -> int:
    model = args.model or os.environ.get("EVAL_MODEL", "claude-opus-4-8")
    if args.lang == "ja":
        glossary = load_en2ja_glossary()
        judge_system = JUDGE_SYSTEM_JA
    else:
        glossary = load_en2id_glossary()
        judge_system = JUDGE_SYSTEM

    docs = gather_all_docs(args.lang)
    if args.only:
        docs = [d for d in docs if d.rel.startswith(args.only)]
        if not docs:
            sys.exit(f"ERROR: --only {args.only} 未匹配任何 {args.lang} 译文")

    if args.sample:
        selected = stratified_sample(docs, args.target, args.min_per, args.seed)
    elif args.full or args.only:
        selected = sorted(docs, key=lambda d: d.rel)
    else:
        selected = stratified_sample(docs, args.target, args.min_per, args.seed)
    if args.limit:
        selected = selected[: args.limit]

    # 抽样分布打印
    dist: dict[str, int] = defaultdict(int)
    for d in selected:
        dist[d.product] += 1
    print(
        f"[info] lang={args.lang} 语料总={len(docs)} 抽样={len(selected)} "
        f"model={model} concurrency={args.concurrency} glossary_en2id={len(glossary)}"
    )
    print("[info] 抽样分布:" + ", ".join(f"{p}={dist[p]}" for p in sorted(dist)))
    if args.dry_run:
        print("[info] dry-run:只列抽样 + 命中术语,不调评委、不写报告明细")

    sem = asyncio.Semaphore(args.concurrency)
    started = time.time()
    coros = [eval_one(d, glossary, model, args.timeout, args.dry_run, sem, args.lang, judge_system) for d in selected]
    results: list[EvalResult] = []
    done = 0
    for coro in asyncio.as_completed(coros):
        r = await coro
        results.append(r)
        done += 1
        if r.status == "ok":
            print(f"[{done}/{len(selected)}] ✓ {r.rel}  overall={r.overall} "
                  f"(a{r.accuracy}/l{r.localization}/f{r.fluency}/t{r.terminology}) issues={len(r.issues)} ${r.cost_usd:.3f}")
        elif r.status == "failed":
            print(f"[{done}/{len(selected)}] ✗ {r.rel}  FAILED: {r.error}", file=sys.stderr)
        else:
            print(f"[{done}/{len(selected)}] · {r.rel}  {r.status} hits={r.hit_terms_count}")
    ended = time.time()

    if args.dry_run:
        print(f"\n[dry-run] 抽样 {len(results)} 篇,命中术语合计 {sum(r.hit_terms_count for r in results)}")
        return 0

    results.sort(key=lambda r: r.rel)
    if args.only:
        suffix = "_" + re.sub(r"[^a-zA-Z0-9]+", "-", args.only).strip("-")
    else:
        suffix = "_full" if args.full else f"_sample{len(results)}"
    write_report(results, OUTPUT_DIR / args.lang, model, started, ended, suffix)
    failed = [r for r in results if r.status == "failed"]
    ok = [r for r in results if r.status == "ok"]
    print(f"\n[done] report: {OUTPUT_DIR / args.lang / f'report{suffix}.md'}")
    if ok:
        print(f"[done] overall 均分 = {round(sum(r.overall for r in ok)/len(ok), 2)}  失败 {len(failed)} 篇")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="换模型 LLM-as-judge:评审印尼语译文质量(只读,不改译文)")
    p.add_argument("--lang", default="id", help="被评语言目录(默认 id)")
    p.add_argument("--model", default=None, help="评委模型(默认 claude-opus-4-8;须独立于翻译用的 opus-4-7)")
    p.add_argument("--target", type=int, default=50, help="分层抽样目标篇数(默认 50)")
    p.add_argument("--min-per", type=int, default=2, dest="min_per", help="每个产品线最少抽样篇数(默认 2)")
    p.add_argument("--seed", type=int, default=42, help="抽样随机种子(可复现)")
    p.add_argument("--full", action="store_true", help="全量评审(忽略抽样)")
    p.add_argument("--sample", action="store_true", help="即使指定 --only 也按 --target 分层随机抽样")
    p.add_argument("--only", default=None, help="只评某路径前缀,如 im / aitable / open/development")
    p.add_argument("--limit", type=int, default=0, help="只跑前 N 篇(抽样/全量之后再截断)")
    p.add_argument("--concurrency", type=int, default=3)
    p.add_argument("--timeout", type=int, default=300, help="单次 claude CLI 调用超时秒数")
    p.add_argument("--dry-run", action="store_true", help="只列抽样 + 命中术语,不调评委")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async(parse_args())))
