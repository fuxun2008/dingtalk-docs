#!/usr/bin/env python3
"""
批量翻译 mdx：<root>/*.mdx (en 母版) → ja/<root>/*.mdx (日文)。

与 translate_mdx_batch.py 的区别（专为「ja 用 en 图 + 页数对齐 en」设计）：
- 源根 = 仓库根 <root>/（英文母版），目标 = ja/<root>/。
- **保留图片 / 视频 / iframe / Frame 及其 URL 原样**（不剥离）——满足「日语图片用英文版图片、数量与英文一致」。
- en→ja 词库：由 zh-en.json 与 zh-ja.json 经共享 zh key 合成 en→ja 对照表（强约束）。
- frontmatter description 走 **SEO 优化**：生成面向搜索的日语摘要，而非首段直译。

实现方式：通过 `claude -p --bare` 子进程调用（同 translate_mdx_batch.py）。

CLI:
  python3 scripts/translate_mdx_en2ja.py --root meetings --concurrency 1
  python3 scripts/translate_mdx_en2ja.py --root aitable                  # 跳过已存在的非占位译文，只补缺失
  python3 scripts/translate_mdx_en2ja.py --root open --only open/index
  python3 scripts/translate_mdx_en2ja.py --root contacts --dry-run --limit 2
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
# Prompt 资产（en → ja）
# ---------------------------------------------------------------------------

SYSTEM_RULES = """あなたはDingTalk国際版ヘルプセンターのシニア日本語テクニカルライター兼翻訳者です。英語の原文を、グローバル企業ユーザー向けの公式ドキュメントとして通用する日本語に翻訳します。ネイティブレベルの流暢さと、IT/ビジネス技術文書としての専門性・正確性を必ず満たしてください。

鉄則（違反した訳文は無効）：
1. 翻訳対象は自然言語のみ：本文・frontmatter の title と description・リスト項目・表のセル内テキスト・見出しテキスト。
2. すべての MDX コンポーネントタグ (<Note> <Tip> <Warning> <Info> <Check> <Card> <CardGroup> <Steps> <Step> <Tabs> <Tab> <Accordion> <AccordionGroup> <CodeGroup> <Update> <Frame> <Icon>) と全 props (title / icon / href / cols / caption / ...) は一切変更せず、子ノードの可視テキストのみ翻訳する。
3. コードブロック ``` 内は 4 分類で処理（一律「保持」は禁止）：
   3a. API 契約（原様保持）：JSON フィールド名 / HTTP メソッド / ステータスコード / Header 名 / URL とプレースホルダ / 関数名 / メソッド名 / SDK 呼び出し / 変数名 / エラーコード文字列 / 既に英数字の enum 値。
   3b. サンプルリテラル（**日本語に書き換え必須**）：サンプル JSON 内の user-facing フィールド（title/content/text/key/value/description/desc/name/author/unit 等）の文字列値；表の example 列のサンプル値。
       例：`"content": "Monthly meeting notification"` → `"content": "月例ミーティング通知"`
       例：`"key": "Name"` / `"value": "John"` → `"key": "名前"` / `"value": "山田太郎"`
   3c. コードコメント + markdown 構文サンプル（**翻訳必須**）：` // ... ` ` # ... ` 行内コメント；```text``` ブロック内の純粋な markdown 構文説明。
   3d. API enum で中国語値が必須のもの（**中国語保持 + 日本語の行内注釈**）：例 `"sticker": "灯泡"  // 電球`。
   コードブロックの title="x" の x は訳さない；``` の後の lines / json lines 等の修飾子も触らない。
4. 【画像・メディアは原様保持】画像 ![alt](url)・<img/>・<video>...</video>・<iframe>...</iframe>・<Frame>...</Frame> とその URL は**完全にそのまま残す**（削除・改変しない）。alt / caption のテキストのみ日本語化する。画像 URL は英語版と完全一致でなければならない。
5. 内部相対リンク [text](/foo/bar) の URL は一切変更しない；アンカーテキストは翻訳可。外部リンク URL も不変；アンカーテキストは翻訳可。
6. frontmatter は title と description の value のみ翻訳；フィールド名は不変；その他フィールド（sidebarTitle、icon、tag 等）の value も不変。
7. 出力は必ず正当な mdx。```mdx ``` で囲まない、「以下が翻訳です」等の前後置きを一切付けない、最初の文字が mdx 本体であること。
8. 構造を 1:1 でミラー：すべての見出し（階層含む）・段落・リスト・表の行・画像行を保持；増やさず減らさず統合しない。
9. 句読点は日本語慣習に：。、「」（）；数字は半角；日付は 2026年6月2日 形式。
10. 技術語 API / SDK / URL / JSON / SaaS 等は英語のまま；DingTalk ブランド語は用語表に従う。"""

# SEO description 専用ルール（ユーザー必須要件）
SEO_DESCRIPTION_RULE = """【frontmatter description は SEO 最適化（必須）】
description は本文冒頭の直訳・切り詰めにせず、検索向けの日本語サマリーを生成すること：
- ページの価値を一文で明確に伝える
- コアキーワード（製品名・機能名・ユーザー意図語、例：DingTalk / AI Table / 自動化 / 権限設定 / 共有）を自然に織り込む
- 長さは全角 60〜120 文字程度（検索結果での切れを避ける）
- キーワードの羅列ではなく自然で読みやすい一文
- 1 つの明確なアクションまたはベネフィットを含める
- title の単なる言い換えにしない（補完情報を足す）
例：title「メンバーの追加」→ description「DingTalkで組織メンバーを一括追加・編集する方法を解説。連絡先の登録から部門への割り当てまで、管理者が効率的にメンバー管理を行う手順を紹介します。」"""

STYLE_JA = """スタイルガイド（日本語）：
- 想定読者：日本企業ユーザーと IT 担当者
- 文体：です・ます調（敬体）。FAQ は適度に柔らかくしても崩しすぎない
- 文：短文優先；日本語の自然な語順に再構成；外来語はカタカナ
- 見出し：体言止め または 動詞原形止め；「〜について」の乱用を避ける
- 用語：DingTalk ブランド語は訳さない；機能名は用語表優先；一般 IT 用語は日本の主流訳（設定 / 機能 / 権限 / ファイル / フォルダ / ダウンロード / アップロード / ログイン）
- 動作説明：簡潔な敬体「〜します」「〜してください」「〜を選択します」；「〜することができます」の乱用を避ける
- 機能更新：新機能 / 改善 / 修正 / 廃止
- 注意：英語直訳調・冗長な受動態・不要な「〜することが可能です」を避ける；自然な日本語に"""

# 開放平台 (Open Platform / OpenAPI) 専属ルール — root=open のみ注入
OPEN_PLATFORM_RULES = """開放平台 (Open Platform / OpenAPI) 専属ルール — 1 つでも違反すれば訳文無効：

【用語強制】
A. 「機器人 / robot / chatbot」は **ボット**（日本語）と訳す。**Robot/ロボットは禁止**。単一実体は Bot、配列・リストは bots。
B. 「应用 / application」は **App / アプリ** に統一（用語表優先）。
C. 「企业内部应用」→ 内部アプリ；「第三方应用」→ サードパーティアプリ；「服务端 API」→ サーバー API。

【API 契約 — 原様保持】
D. HTTP 動詞 / ステータスコード / Header 名 / Content-Type は不訳：POST / GET / 200 OK / 401 Unauthorized / Authorization / application/json。
E. JSON フィールド名 / パラメータ名は不訳：corpId / userid / unionid / access_token / grant_type 等。
F. API エンドポイント URL とパスプレースホルダ {corpId} は保持。
G. エラーコード文字列（InvalidParameter.AccessToken 等）は保持；エラーメッセージの自然文のみ翻訳。
H. コード例は鉄則 3 の 4 分類で処理。コメントは翻訳、メソッド名・変数名は保持。

【見出し / 文体】
I. API 専有語の前後に半角スペース（access token を取得する）。
J. 敬体 + 簡潔。「〜します」「〜してください」「〜を呼び出します」。"""


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


def load_en2ja_glossary() -> dict[str, str]:
    """zh-en.json と zh-ja.json を共有 zh key で合成し en→ja 対照表を作る。

    同一 en が複数の異なる ja に当たる曖昧ペア（例 Members→{メンバー, 全員を表示}）は
    誤った強約束になるため**丸ごと破棄**し、明確な 1:1 ペアのみ残す（高精度優先）。
    """
    from collections import defaultdict

    with (GLOSSARY_DIR / "zh-en.json").open(encoding="utf-8") as f:
        zh_en = json.load(f)
    with (GLOSSARY_DIR / "zh-ja.json").open(encoding="utf-8") as f:
        zh_ja = json.load(f)

    candidates: dict[str, set[str]] = defaultdict(set)
    for zh, en_val in zh_en.items():
        ja_val = zh_ja.get(zh)
        if not ja_val:
            continue
        en_key = en_val.strip().strip("`").strip()
        ja_clean = ja_val.strip().strip("`").strip()
        if not en_key or not ja_clean:
            continue
        candidates[en_key].add(ja_clean)

    return {en: next(iter(jas)) for en, jas in candidates.items() if len(jas) == 1}


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
            "本ページで命中したプロジェクト用語の en→ja 対照表（強約束 — 必ずこの通りに訳し、同義語に置き換えない）：\n"
            f"```json\n{terms_json}\n```\n\n"
            "表にない用語は、同等の専門性を保ちつつ自分の判断で訳すこと。\n\n"
            "---\n\n"
            "以下が英語の原文 mdx です。上記すべての鉄則・SEO ルール・スタイルガイドに従って日本語に翻訳してください（訳文 mdx をそのまま出力、前後置き禁止）：\n\n"
            f"{source}"
        )
    return (
        "以下が英語の原文 mdx です。すべての鉄則・SEO ルール・スタイルガイドに従って日本語に翻訳してください（訳文 mdx をそのまま出力、前後置き禁止）：\n\n"
        f"{source}"
    )


def build_system_prompt(root: str = "") -> str:
    sections = [SYSTEM_RULES, SEO_DESCRIPTION_RULE, STYLE_JA]
    if root == "open":
        sections.append(OPEN_PLATFORM_RULES)
    sections.append("本タスクは英語 mdx を日本語（敬体 です・ます）に翻訳します。訳文 mdx をそのまま出力し、説明の前後置きは付けないこと。")
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

def gather_tasks(root: str, only: str | None) -> list[FileTask]:
    en_root = REPO_ROOT / root
    if not en_root.exists():
        sys.exit(f"ERROR: en source dir not found: {en_root}")
    target_base = REPO_ROOT / "ja" / root

    tasks: list[FileTask] = []
    for mdx in sorted(en_root.rglob("*.mdx")):
        rel = mdx.relative_to(en_root)
        target = target_base / rel
        rel_str = str(Path(root) / rel)
        if only and not rel_str.startswith(only):
            continue
        tasks.append(FileTask(source=mdx, target=target, rel=rel_str))
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
    glossary = load_en2ja_glossary()
    system_prompt = build_system_prompt(args.root)
    sem = asyncio.Semaphore(args.concurrency)

    tasks = gather_tasks(args.root, args.only)
    if args.limit:
        tasks = tasks[: args.limit]

    print(
        f"[info] EN→JA root={args.root} 任务数={len(tasks)} only={args.only} "
        f"concurrency={args.concurrency} model={model} glossary_en2ja={len(glossary)}"
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
    write_report(results, OUTPUT_DIR / "ja", started, ended, suffix)

    failed = [r for r in results if r.status == "failed"]
    print(f"\n[done] report: {OUTPUT_DIR / 'ja' / f'report{suffix}.md'}")
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="批量翻译 mdx：<root>/ (en 母版) → ja/<root>/ (日文，保留图片)")
    p.add_argument("--root", required=True, help="en 母版根目录名，如 meetings / aitable / contacts")
    p.add_argument("--concurrency", type=int, default=1)
    p.add_argument("--model", default=None, help="覆盖默认 ANTHROPIC_MODEL")
    p.add_argument("--timeout", type=int, default=300, help="单次 claude CLI 调用超时秒数")
    p.add_argument("--only", default=None, help="只跑路径前缀，如 aitable/data-connectors")
    p.add_argument("--limit", type=int, default=0, help="只跑前 N 篇")
    p.add_argument("--force", action="store_true", help="覆盖非占位的已译文件")
    p.add_argument("--dry-run", action="store_true", help="只列任务 + 命中术语")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main_async(args)))
