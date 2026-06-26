#!/usr/bin/env python3
"""
把日语文档里被原样保留的英文 **UI/功能标签** 译成日文；品牌/API/专有名词保留英文。

流程：
1. 读 /tmp/en_tokens.json（已收集的去重英文 bold token）。
2. 一次 claude 调用 → JSON {token: 日文 | "__KEEP__"}。
3. 对 --list 文件集，把 `**token**`（允许内部首尾空格）替换为 `**日文**`（KEEP 的不动）。

用法：
  python3 scripts/fix_ja_english_labels.py --list /tmp/newset.txt --tokens /tmp/en_tokens.json            # dry-run（出映射 + 计数）
  python3 scripts/fix_ja_english_labels.py --list /tmp/newset.txt --tokens /tmp/en_tokens.json --apply
"""
from __future__ import annotations
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from translate_mdx_en2ja import call_claude_cli  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
MAP_OUT = Path("/tmp/en_label_map.json")

SYS = """あなたはDingTalk国際版ヘルプセンターの日本語ローカリゼーション担当です。
英語のままヘルプ文書に残ってしまった太字ラベルのリストを受け取り、各ラベルを「日本語に訳す」か「英語のまま残す(__KEEP__)」かを判定します。

【__KEEP__（英語のまま）にするもの】
- ブランド/製品名：DingTalk, AI Table, DingTalk Docs, DingTalk Mind, DingTalk Whiteboard, Aliyun, Teambition, NetEase Cloud Music 等
- API/技術識別子・コンソール用語：AccessKey, AccessKey ID, AccessKey Secret, App ID, App Secret, App Key, AppKey, API Key, API key, Client Secret, EngineCode, unionId, corpId, Webhook, App Security, ID, SDK, URL, JSON, IANA Time Zone Database
- OS/プラットフォーム名：Windows, Mac, iOS, Android（"Windows:" のようなコロン付きもKEEP）
- 1～2文字の汎用記号的ラベル：OK, Aa, Free（文脈上ボタン名で訳すと不自然なもの）。ただし明確なUI動作なら訳す
- データのプレースホルダ値：Unnamed Column_X など

【日本語に訳すもの（UI/機能/設定/ボタン/メニュー名）】
- 例：Sign in→サインイン, Confirm→確認, Enter→入力, More→もっと見る, Users→ユーザー,
  Data sync center→データ同期センター, Breakout Rooms→ブレイクアウトルーム,
  Calendar Settings→カレンダー設定, First day of week→週の最初の曜日,
  End Discussion→ディスカッションを終了, Permission management→権限管理,
  Authentication management→認証管理, Dev config→開発設定, Create cool app→アプリを作成,
  DingTalk apps→DingTalkアプリ, Enterprise→企業版, Business→ビジネス版
- 自然で簡潔な日本語、DingTalk日本語UIの一般的表現に合わせる。

出力は厳密に JSON オブジェクトのみ（{"<英語token>":"<日本語 or __KEEP__>", ...}）。
入力の全 token を漏れなく含めること。前後の説明・コードフェンス禁止。"""


def build_user(tokens: list[str]) -> str:
    lst = "\n".join(tokens)
    return f"以下の英語ラベルを判定し、JSON で返してください（全件）：\n\n{lst}"


def extract_json(s: str) -> dict:
    s = s.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"```\s*$", "", s)
    m = re.search(r"\{.*\}", s, re.DOTALL)
    return json.loads(m.group(0)) if m else {}


async def get_map(tokens: list[str], model: str) -> dict:
    out, _ = await call_claude_cli(SYS, build_user(tokens), model, 180)
    return extract_json(out)


def apply_map(files: list[str], mp: dict, apply: bool) -> tuple[int, int]:
    # 只替换有日文译文（非 __KEEP__）的 token；长 token 先替换，避免子串冲突
    trans = {k: v for k, v in mp.items() if v and v != "__KEEP__" and v != k}
    pats = sorted(trans.keys(), key=len, reverse=True)
    total = files_hit = 0
    for rel in files:
        p = REPO / rel
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8")
        cnt = 0
        for tok in pats:
            # **token**（内部首尾允许空格）→ **日文**
            t, k = re.subn(r"\*\*\s*" + re.escape(tok) + r"\s*\*\*", f"**{trans[tok]}**", t)
            cnt += k
        if cnt:
            files_hit += 1
            total += cnt
            if apply:
                p.write_text(t, encoding="utf-8")
    return files_hit, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", required=True)
    ap.add_argument("--tokens", required=True)
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    tokens = list(json.loads(Path(args.tokens).read_text()).keys())
    files = [l.strip() for l in Path(args.list).read_text().splitlines() if l.strip()]

    if MAP_OUT.exists():
        mp = json.loads(MAP_OUT.read_text())
        print(f"[info] 复用已有映射 {MAP_OUT}（{len(mp)} 条）")
    else:
        mp = asyncio.run(get_map(tokens, args.model))
        MAP_OUT.write_text(json.dumps(mp, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[info] 生成映射 → {MAP_OUT}（{len(mp)} 条）")

    keep = [k for k, v in mp.items() if v in ("__KEEP__", k) or not v]
    trans = {k: v for k, v in mp.items() if k not in keep}
    print(f"\n=== KEEP({len(keep)}) ===")
    print("  " + ", ".join(sorted(keep)))
    print(f"\n=== 译日文({len(trans)}) ===")
    for k in sorted(trans):
        print(f"  {k}  →  {trans[k]}")
    miss = [t for t in tokens if t not in mp]
    if miss:
        print(f"\n[warn] {len(miss)} token 未在映射中: {miss}")

    fh, nt = apply_map(files, mp, args.apply)
    print(f"\n{'[applied]' if args.apply else '[dry-run]'} 受影响文件 {fh}，可替换 token {nt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
