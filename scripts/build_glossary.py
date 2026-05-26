#!/usr/bin/env python3
"""
build_glossary.py — 解析 scripts/glossary.md 的 zh-en 术语表，
并通过 Claude API 派生出 zh-ja 表。

输出：
  scripts/glossary/zh-en.json
  scripts/glossary/zh-ja.json

格式：{"zh": "tgt"}，按 zh key 长度倒序排（图片翻译时长术语优先匹配）。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent
GLOSSARY_MD = ROOT / "glossary.md"
OUT_DIR = ROOT / "glossary"
OUT_DIR.mkdir(exist_ok=True)

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")


# ---------- Step A: 解析 glossary.md ----------

def parse_glossary_md(path: Path) -> dict[str, str]:
    """从 markdown 表格提取 zh -> en 映射。

    表格格式：| 中文 | 英文 | [备注] |
    跳过表头/分隔行/品牌不译说明。
    "/ " 分隔的多义条目拆开（如 "AI 表格 / AI表格"）。
    """
    text = path.read_text(encoding="utf-8")
    pairs: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| ---"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue
        zh, en = cols[0], cols[1]
        # 跳过表头（第一行）
        if zh in {"中文", "中文 / 英文", ""} or en in {"英文", ""}:
            continue
        # 拆 zh 中的多义（"AI 表格 / AI表格"）
        zh_variants = [v.strip() for v in re.split(r"\s*/\s*", zh) if v.strip()]
        # 拆 en 的多选只取第一个（"Duplicate（结构）/ Copy（数据）" → 取 Duplicate）
        en_clean = re.split(r"\s*/\s*", en)[0]
        en_clean = re.sub(r"（.*?）|\(.*?\)", "", en_clean).strip()
        if not en_clean:
            continue
        for v in zh_variants:
            # 不收过短或过于通用的词避免误命中
            if len(v) < 2:
                continue
            pairs[v] = en_clean
    return pairs


# ---------- Step B: 派生 zh -> ja ----------

JA_DERIVATION_PROMPT = """你是 SaaS 产品 UI 术语本地化专家。下面是一份"中文 → 英文" UI 术语对照表（钉钉旗下 AI Table 协同表格产品）。

请为每一项给出**地道的日文 UI 用语**翻译，遵循以下规则：

1. 品牌名保持原样：DingTalk / AI Table / AI Assistant / DingTalk Docs（不翻译）
2. 数据库 / 表格 UI 通用术语优先用业界惯用译法（如 view → ビュー、record → レコード、field → フィールド、dashboard → ダッシュボード、form → フォーム、filter → フィルター、template → テンプレート）
3. 操作动作用辞书形（連体形）即可（"新建" → "新規作成"，"删除" → "削除"，"导出" → "エクスポート"）
4. 字段类型保持英文+ローマ字 习惯（Single Select → シングルセレクト、Multiple Select → マルチセレクト、Date → 日付、Number → 数値）
5. 如果某个术语完全保留英文更自然（如 Webhook、Lookup），就保留英文不译

只输出 JSON：
```json
{
  "中文术语1": "日文翻译1",
  "中文术语2": "日文翻译2",
  ...
}
```

不要包裹 markdown，不要解释。直接输出 JSON。

输入（zh -> en）：
{pairs_json}
"""


def derive_japanese(zh_en: dict[str, str]) -> dict[str, str]:
    client = anthropic.Anthropic()
    pairs_json = json.dumps(zh_en, ensure_ascii=False, indent=2)
    prompt = JA_DERIVATION_PROMPT.replace("{pairs_json}", pairs_json)

    print(f"调 Claude 派生日文：{len(zh_en)} 条术语，model={MODEL}")
    resp = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    # 去掉可能的 markdown 包裹
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    return json.loads(text)


# ---------- Main ----------

def main() -> int:
    if not GLOSSARY_MD.exists():
        print(f"错误：{GLOSSARY_MD} 不存在", file=sys.stderr)
        return 1

    zh_en = parse_glossary_md(GLOSSARY_MD)
    print(f"从 glossary.md 抽出 {len(zh_en)} 条 zh-en 术语")

    # 按 zh key 长度倒序，长术语优先（图片翻译做长尾匹配时避免短词覆盖长词）
    zh_en_sorted = dict(sorted(zh_en.items(), key=lambda kv: -len(kv[0])))

    out_zh_en = OUT_DIR / "zh-en.json"
    out_zh_en.write_text(
        json.dumps(zh_en_sorted, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  → {out_zh_en}")

    zh_ja = derive_japanese(zh_en)
    # 同样按长度倒序
    zh_ja_sorted = dict(sorted(zh_ja.items(), key=lambda kv: -len(kv[0])))
    out_zh_ja = OUT_DIR / "zh-ja.json"
    out_zh_ja.write_text(
        json.dumps(zh_ja_sorted, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  → {out_zh_ja}（{len(zh_ja)} 条）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
