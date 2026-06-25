#!/usr/bin/env python3
"""
批量为 mdx 生成/重写 SEO description（每语言独立，基于 body 内容）。

与 translate_mdx_batch.py 同一套基础设施：
- 走 `claude -p --bare` 子进程（不依赖 ANTHROPIC_API_KEY）
- asyncio + Semaphore 并发；单篇失败重试 3 次（指数退避）
- 报告：scripts/output/gen_descriptions/<lang>/{report.json,report.md}

输入三类（与 lint_seo_descriptions.py 同步语义）：
- missing : frontmatter 无 description 或为空字符串 → 从 0 生成
- short   : description 短于 LANG_THRESHOLDS[lang]["short"] → 重写
- long    : description 长于 LANG_THRESHOLDS[lang]["long"] → 重写

CLI:
  # 抽 5 篇 dry-run 看 prompt 质量
  python3 scripts/gen_seo_descriptions_batch.py --type missing --lang ja \\
      --only open/development --limit 5 --dry-run

  # 真跑（覆盖 short/long 必须 --force）
  python3 scripts/gen_seo_descriptions_batch.py --type missing --lang ja
  python3 scripts/gen_seo_descriptions_batch.py --type short --lang en \\
      --short-threshold 15 --force
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

# 复用同目录已有资产
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lint_seo_descriptions import (  # noqa: E402
    LANG_THRESHOLDS, classify, collect_mdx, extract_description,
)
from translate_mdx_batch import (  # noqa: E402
    call_claude_cli, sanitize_media,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
GLOSSARY_DIR = REPO_ROOT / "scripts" / "glossary"
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "gen_descriptions"

# Body 截断给 LLM 看的字符上限（防 token 爆炸；description 不需要全文）
BODY_TRUNCATE = 1800

# 品牌词白名单（注入 prompt，覆盖词库 missing）
BRAND_GLOSSARY_EN = {
    "钉钉": "DingTalk",
    "钉钉文档": "DingTalk Docs",
    "钉钉表格": "DingTalk Spreadsheet",
    "钉钉脑图": "DingTalk Mind",
    "钉钉白板": "DingTalk Whiteboard",
    "AI 表格": "AI Table",
    "AI表格": "AI Table",
    "智能填表": "Smart Form",
    "知识库": "Knowledge Base",
    "知识群": "Knowledge Group",
    "钉闪会": "Quick Meeting",
    "钉盘": "DingTalk Drive",
    "钉邮": "DingTalk Mail",
    "钉钉日历": "DingTalk Calendar",
    "钉钉会议": "DingTalk Meetings",
    "钉钉通讯录": "DingTalk Contacts",
    "钉钉群聊": "DingTalk Group Chat",
    "AI 闪记": "AI Minutes",
    "AI闪记": "AI Minutes",
    "钉钉开放平台": "DingTalk Open Platform",
}

BRAND_GLOSSARY_JA = {
    "钉钉": "DingTalk",
    "钉钉文档": "DingTalkドキュメント",
    "钉钉表格": "DingTalkスプレッドシート",
    "钉钉脑图": "DingTalk Mind",
    "钉钉白板": "DingTalk Whiteboard",
    "AI 表格": "AIテーブル",
    "AI表格": "AIテーブル",
    "智能填表": "スマートフォーム",
    "知识库": "ナレッジベース",
    "知识群": "ナレッジグループ",
    "钉闪会": "クイックミーティング",
    "钉盘": "DingTalk Drive",
    "钉邮": "DingTalkメール",
    "钉钉日历": "DingTalkカレンダー",
    "钉钉会议": "DingTalkミーティング",
    "钉钉通讯录": "DingTalk連絡先",
    "钉钉群聊": "DingTalkグループチャット",
    "AI 闪记": "AI議事録",
    "AI闪记": "AI議事録",
    "钉钉开放平台": "DingTalk Open Platform",
}


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM_RULES = """你是 SEO 文案专家，为钉钉国际版帮助中心的文档页生成 meta description。

铁律（违反则输出无效）：
1. 严格基于给定的 title + body 内容，不编造任何未在原文出现的事实、数字、产品名
2. 不复读 title 字面；要补充 title 没说清的"做什么 / 适用场景 / 解决什么问题"
3. 使用主动语态、动词导向；en/zh 用陈述句，ja 用敬体
4. 品牌名严格按下方术语表写法，不漂移（如 AI Table 不写成 AI 表格 / AI Sheet）
5. 不带任何标点修饰：感叹号、省略号、emoji、引号都不要
6. 输出纯文本一行，不带前后引号、不带 markdown、不带换行
7. 如 body 主要是图/视频/代码示例文本不够，基于 title + 同主题通用知识写一句概览
8. 长度严格控制（按本次 lang）；超过上限你的输出会被截断为无效，必须自己把控字数

【API 文档专项】当 body 是 OpenAPI / 服务端 API 参考时：
9. description 说"做什么业务"，**禁止**写入这些技术契约细节：
   - URL 路径（如 /v1.0/contact/role）、HTTP 方法（POST/GET）、状态码、错误码
   - JSON 字段名（access_token / corpId / userid / agent_id 等驼峰或下划线名）
   - 调用步骤（"指定 X 和 Y 调用接口"这种是正文工作）
10. 正确示范："企业管理员添加角色组并分配可见范围" ✓
    错误示范："POST /role/add_role_group 传 access_token 和 name 创建角色组" ✗

输入格式: 我会给你 [LANG] [TITLE] [BODY]
输出格式: 仅一行 description 文本，无其它任何字符"""

STYLE = {
    "en": (
        "本次目标语言: English\n"
        "长度: 50-160 字符（含空格），目标 80-140\n"
        "风格: Sentence-case，动作导向，避免 You can / It is recommended / In order to 等冗长结构\n"
        "示例:\n"
        "  GOOD: Configure granular access permissions for AI Table views and individual records.\n"
        "  GOOD: Set up automation rules in AI Table to trigger webhooks on record updates.\n"
        "  BAD : This article introduces how to use AI Table for collaboration. (复读 title + 空话)\n"
        "  BAD : AI Table is a powerful tool that you can use to... (空话 + 冗长)"
    ),
    "zh": (
        "本次目标语言: 简体中文\n"
        "长度: 25-80 字符（一个汉字算 1 字），目标 35-65\n"
        "风格: 陈述句，开头用动词或主语；避免「本文介绍」「快来体验」等空话\n"
        "示例:\n"
        "  GOOD: 在 AI 表格中设置自动化规则，记录字段变更时触发 webhook 通知\n"
        "  GOOD: 管理员配置视图与字段的协作权限，区分查看、编辑、管理三档\n"
        "  BAD : 本文介绍如何使用 AI 表格进行协作。（空话 + 复读 title）\n"
        "  BAD : 一起来体验吧！（无信息量）"
    ),
    "ja": (
        "今回の出力言語: 日本語（敬体 です・ます）\n"
        "長さ: 25-80 文字（漢字・かな1字を1とカウント）、目標 35-65\n"
        "スタイル: 簡潔な敬体、動詞中心；「本記事では〜について紹介します」のような前置きは禁止\n"
        "例:\n"
        "  GOOD: AIテーブルでビューとレコード単位のアクセス権限を設定し、協業範囲を制御します\n"
        "  GOOD: 自動化ルールを設定し、レコード更新時に Webhook で外部通知を送信します\n"
        "  BAD : 本記事では AIテーブルの使い方を紹介します。（前置き + 内容空虚）\n"
        "  BAD : ぜひお試しください！（情報量ゼロ）"
    ),
}


def build_system_prompt(lang: str) -> str:
    return SYSTEM_RULES + "\n\n" + STYLE[lang]


def build_brand_terms(text: str, lang: str) -> dict[str, str]:
    """从 BRAND_GLOSSARY 抽出 body 命中的品牌词对照。"""
    glossary = BRAND_GLOSSARY_EN if lang == "en" else (
        BRAND_GLOSSARY_JA if lang == "ja" else {}
    )
    hits = {}
    for zh, tgt in glossary.items():
        if zh in text:
            hits[zh] = tgt
    return hits


def build_user_message(lang: str, title: str, body: str, old_desc: str | None) -> str:
    brand_hits = build_brand_terms(title + " " + body, lang)
    parts = [f"[LANG] {lang}"]
    if brand_hits:
        parts.append(
            "本篇出现的品牌名（必须严格按下表写法）:\n```json\n"
            + json.dumps(brand_hits, ensure_ascii=False, indent=2)
            + "\n```"
        )
    parts.append(f"[TITLE] {title}")
    if old_desc:
        parts.append(
            f"[ORIGINAL_DESCRIPTION (待重写，原 {len(old_desc)} 字符，不符合 SEO 阈值)]\n{old_desc}"
        )
    body_truncated = body[:BODY_TRUNCATE]
    if len(body) > BODY_TRUNCATE:
        body_truncated += f"\n\n[…body 已截断，原 {len(body)} 字符]"
    parts.append(f"[BODY]\n{body_truncated}")
    parts.append("现在输出该页的 SEO description（只一行，无引号无 markdown）:")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Frontmatter 写回
# ---------------------------------------------------------------------------

DESC_LINE_RE = re.compile(r'^(?P<indent>[ \t]*)description:.*$', re.MULTILINE)
TITLE_LINE_RE = re.compile(r'^(?P<indent>[ \t]*)title:.*$', re.MULTILINE)


def split_frontmatter(text: str) -> tuple[str, str] | None:
    """Return (fm_content, rest) where fm_content excludes the leading and
    trailing --- delimiters. None if no parseable frontmatter."""
    if not text.startswith("---"):
        return None
    # Need a newline right after the leading ---
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    fm = text[4:end]  # skip leading "---\n"
    rest = text[end:]  # starts with \n---
    return fm, rest


def yaml_escape(s: str) -> str:
    """Escape for a YAML double-quoted scalar."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def write_description(text: str, new_desc: str) -> str:
    """Insert or replace `description:` in the leading frontmatter block.
    Returns the new text. Raises ValueError if frontmatter is unparseable."""
    parts = split_frontmatter(text)
    if parts is None:
        raise ValueError("no parseable leading frontmatter")
    fm, rest = parts
    new_line = f'description: "{yaml_escape(new_desc)}"'

    m = DESC_LINE_RE.search(fm)
    if m:
        # Preserve the line's original indent.
        new_fm = fm[:m.start()] + m.group("indent") + new_line + fm[m.end():]
    else:
        # Insert right after the title line; fall back to top of fm.
        tm = TITLE_LINE_RE.search(fm)
        if tm:
            insert_at = tm.end()
            new_fm = (
                fm[:insert_at] + "\n" + tm.group("indent") + new_line + fm[insert_at:]
            )
        else:
            new_fm = new_line + "\n" + fm

    return "---\n" + new_fm + rest


# ---------------------------------------------------------------------------
# 任务
# ---------------------------------------------------------------------------

@dataclass
class FileTask:
    path: Path
    rel: str
    lang: str
    kind: str  # missing / short / long
    old_desc: str  # "" for missing


@dataclass
class FileResult:
    rel: str
    lang: str
    kind: str
    status: str  # ok / skipped / failed / dry-run
    old_desc: str = ""
    new_desc: str = ""
    old_len: int = 0
    new_len: int = 0
    elapsed_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    error: str = ""


def gather_tasks(
    type_: str, lang: str, only: str | None,
    short_threshold: int | None, long_threshold: int | None,
) -> list[FileTask]:
    th = LANG_THRESHOLDS[lang].copy()
    if short_threshold is not None:
        th["short"] = short_threshold
    if long_threshold is not None:
        th["long"] = long_threshold

    tasks: list[FileTask] = []
    for p in collect_mdx(lang):
        rel = str(p.relative_to(REPO_ROOT))
        if only and not rel.startswith(only):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        desc = extract_description(text)
        if type_ == "missing":
            if desc:
                continue
            tasks.append(FileTask(path=p, rel=rel, lang=lang, kind="missing", old_desc=""))
        elif type_ == "short":
            if not desc or len(desc) >= th["short"]:
                continue
            tasks.append(FileTask(path=p, rel=rel, lang=lang, kind="short", old_desc=desc))
        elif type_ == "long":
            if not desc or len(desc) <= th["long"]:
                continue
            tasks.append(FileTask(path=p, rel=rel, lang=lang, kind="long", old_desc=desc))
    return tasks


# ---------------------------------------------------------------------------
# 单篇生成
# ---------------------------------------------------------------------------

FENCE_TRIM_RE = re.compile(r"^['\"\s]*|['\"\s]*$")


def trim_llm_output(s: str) -> str:
    """Strip whitespace, leading/trailing quotes, leading bullet markers."""
    s = s.strip()
    s = s.strip("​﻿")  # zwsp / bom
    # Strip a single layer of outer quotes
    if len(s) >= 2 and s[0] in '\'"' and s[-1] == s[0]:
        s = s[1:-1].strip()
    # If LLM output multi-line, keep only first non-empty line
    for line in s.splitlines():
        line = line.strip()
        if line:
            s = line
            break
    return s


def extract_title_and_body(text: str) -> tuple[str, str]:
    """Extract frontmatter title (best-effort) and sanitized body."""
    parts = split_frontmatter(text)
    if parts is None:
        return "", sanitize_media(text)
    fm, rest = parts
    # rest starts with "\n---"; the body is whatever follows
    body_start = rest.find("\n", 3)  # skip the trailing --- line
    body = rest[body_start + 1 :] if body_start != -1 else ""
    body_clean = sanitize_media(body)

    title = ""
    m = re.search(
        r'^title:\s*"((?:[^"\\]|\\.)*)"\s*$'
        r'|^title:\s*\'((?:[^\'\\]|\\.)*)\'\s*$'
        r'|^title:\s*(\S.*?)\s*$',
        fm,
        re.MULTILINE,
    )
    if m:
        title = m.group(1) or m.group(2) or m.group(3) or ""
    return title, body_clean


async def gen_one(
    task: FileTask, system_prompt: str, model: str, timeout_s: int,
    dry_run: bool, sem: asyncio.Semaphore, force: bool,
) -> FileResult:
    rel = task.rel
    try:
        text = task.path.read_text(encoding="utf-8")
    except Exception as e:
        return FileResult(
            rel=rel, lang=task.lang, kind=task.kind, status="failed",
            error=f"read: {e}",
        )

    title, body = extract_title_and_body(text)
    if not title and not body.strip():
        return FileResult(
            rel=rel, lang=task.lang, kind=task.kind, status="failed",
            error="empty title and body",
        )

    user_msg = build_user_message(task.lang, title, body, task.old_desc)

    if dry_run:
        return FileResult(
            rel=rel, lang=task.lang, kind=task.kind, status="dry-run",
            old_desc=task.old_desc, old_len=len(task.old_desc),
        )

    last_err = ""
    for attempt in range(3):
        async with sem:
            t0 = time.time()
            try:
                result_text, usage = await call_claude_cli(
                    system_prompt, user_msg, model, timeout_s,
                )
                elapsed = time.time() - t0
                new_desc = trim_llm_output(result_text)
                if not new_desc:
                    raise RuntimeError("LLM returned empty after trim")
                # Hard guard: prevent absurdly long output that would bloat
                # the file even if the LLM ignored length rules.
                if len(new_desc) > 300:
                    new_desc = new_desc[:300].rstrip()
                new_text = write_description(text, new_desc)
                if new_text == text:
                    raise RuntimeError("write_description produced identical text")
                task.path.write_text(new_text, encoding="utf-8")
                return FileResult(
                    rel=rel, lang=task.lang, kind=task.kind, status="ok",
                    old_desc=task.old_desc, new_desc=new_desc,
                    old_len=len(task.old_desc), new_len=len(new_desc),
                    elapsed_s=round(elapsed, 2),
                    input_tokens=usage.get("input_tokens", 0) or 0,
                    output_tokens=usage.get("output_tokens", 0) or 0,
                    cost_usd=usage.get("cost_usd", 0.0) or 0.0,
                )
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
        backoff = 2 ** attempt * 3
        print(f"  ! {rel} attempt {attempt+1} failed: {last_err}; retry in {backoff}s",
              file=sys.stderr)
        await asyncio.sleep(backoff)

    return FileResult(
        rel=rel, lang=task.lang, kind=task.kind, status="failed",
        old_desc=task.old_desc, old_len=len(task.old_desc), error=last_err,
    )


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

def write_report(results: list[FileResult], out_dir: Path, started: float, ended: float) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(
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
        "# Description Generation Report",
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
        lines += ["## 失败清单", ""]
        for r in results:
            if r.status == "failed":
                lines.append(f"- `{r.rel}`：{r.error}")
        lines.append("")

    lines += [
        "## 改前/改后样例（前 30）",
        "",
        "| rel | kind | old_len → new_len | new_description |",
        "|---|---|---|---|",
    ]
    ok_results = [r for r in results if r.status == "ok"]
    for r in ok_results[:30]:
        old_disp = r.old_desc[:40].replace("|", "\\|") if r.old_desc else "_(missing)_"
        new_disp = r.new_desc.replace("|", "\\|")
        lines.append(
            f"| {r.rel} | {r.kind} | {r.old_len} → {r.new_len} | {new_disp} |"
        )
    if len(ok_results) > 30:
        lines.append(f"\n_(共 {len(ok_results)} 条 ok，仅显示前 30)_")

    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def main_async(args: argparse.Namespace) -> int:
    model = args.model or os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
    system_prompt = build_system_prompt(args.lang)
    sem = asyncio.Semaphore(args.concurrency)

    tasks = gather_tasks(
        args.type, args.lang, args.only,
        args.short_threshold, args.long_threshold,
    )
    if args.limit:
        tasks = tasks[: args.limit]

    if args.type in ("short", "long") and not args.force and not args.dry_run:
        print(f"[error] --type {args.type} would overwrite existing descriptions; "
              f"add --force (or run --dry-run first)", file=sys.stderr)
        return 2

    print(
        f"[info] lang={args.lang} type={args.type} 任务数={len(tasks)} "
        f"concurrency={args.concurrency} model={model} timeout={args.timeout}s"
    )
    if args.dry_run:
        print("[info] dry-run：不调 LLM、不写文件，只列任务")
    elif args.force:
        print("[info] force=true：会覆盖已有 description")

    started = time.time()
    coros = [
        gen_one(t, system_prompt, model, args.timeout, args.dry_run, sem, args.force)
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
            preview = r.new_desc[:60].replace("\n", " ")
            print(
                f"[{done}/{len(tasks)}] {icon} {r.rel}  {r.old_len}→{r.new_len}  "
                f"{r.elapsed_s}s  ${r.cost_usd:.4f}  · {preview}"
            )
        elif r.status == "failed":
            print(f"[{done}/{len(tasks)}] {icon} {r.rel}  FAILED: {r.error}", file=sys.stderr)
        else:
            print(f"[{done}/{len(tasks)}] {icon} {r.rel}  {r.status}")

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
    p = argparse.ArgumentParser(description="批量生成/重写 mdx SEO description")
    p.add_argument("--type", required=True, choices=["missing", "short", "long"])
    p.add_argument("--lang", required=True, choices=["en", "zh", "ja"])
    p.add_argument("--only", default=None, help="路径前缀过滤")
    p.add_argument("--limit", type=int, default=0, help="只跑前 N 篇")
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--model", default=None,
                   help="默认 claude-haiku-4-5-20251001；可切 claude-sonnet-4-6 等")
    p.add_argument("--timeout", type=int, default=120, help="单次 claude CLI 调用超时")
    p.add_argument("--force", action="store_true",
                   help="短/长类型覆盖已有 description（必备）")
    p.add_argument("--dry-run", action="store_true", help="只列任务，不调 LLM")
    p.add_argument("--short-threshold", type=int, default=None, dest="short_threshold",
                   help="覆盖 LANG_THRESHOLDS 的 short 阈值（如 15 只跑明显 garbage）")
    p.add_argument("--long-threshold", type=int, default=None, dest="long_threshold",
                   help="覆盖 LANG_THRESHOLDS 的 long 阈值（如 250 只跑严重超长）")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main_async(args)))
