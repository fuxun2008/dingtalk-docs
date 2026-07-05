#!/usr/bin/env python3
"""glossary_sync.py — 把语言同学的官方三语词库合并进项目。

数据流：
  scripts/glossary/import/*.csv         （语言同学源 csv：中文,英语,日语）
      ↓ 解析 + 去表头 + 去空
  scripts/glossary/official/            （官方词库规范化 JSON）
      ├── zh-en.json
      ├── zh-ja.json
      └── conflicts.json                同 key 不同译法的冲突清单
      ↓ 合并（official 优先，本地补充未覆盖项）
  scripts/glossary/local-supplements.md （本地补充的 AI Table 专项 + 风格指南）
      ↓
  scripts/glossary/zh-en.json           （最终消费产物，路径与旧版兼容）
  scripts/glossary/zh-ja.json
  scripts/glossary/merge-report.md      （本次合并诊断）

用法：
  python3 scripts/glossary_sync.py                # 真跑
  python3 scripts/glossary_sync.py --dry-run      # 只算 diff 不写
  python3 scripts/glossary_sync.py --source <csv> # 只解析指定 csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parent
GLOSSARY_DIR = ROOT / "glossary"
IMPORT_DIR = GLOSSARY_DIR / "import"
OFFICIAL_DIR = GLOSSARY_DIR / "official"
LOCAL_SUPPLEMENTS_MD = GLOSSARY_DIR / "local-supplements.md"
FINAL_ZH_EN = GLOSSARY_DIR / "zh-en.json"
FINAL_ZH_JA = GLOSSARY_DIR / "zh-ja.json"
FINAL_ZH_ID = GLOSSARY_DIR / "zh-id.json"
MERGE_REPORT = GLOSSARY_DIR / "merge-report.md"

# 表头识别（语言同学 csv 第一行 + 部分 csv 第二行二级表头）
HEADER_TOKENS_ZH = {"中文文案", "中文术语", "中文", "原文"}
HEADER_TOKENS_EN = {"英语", "English", "Eng", "EN", "英文"}
HEADER_TOKENS_JA = {"日语", "日本語", "Japanese", "JA", "日文"}
HEADER_TOKENS_ID = {"印尼语", "Indonesian", "ID"}


def is_header_row(zh: str, en: str, ja: str, id_: str = "") -> bool:
    return (
        zh in HEADER_TOKENS_ZH
        or en in HEADER_TOKENS_EN
        or ja in HEADER_TOKENS_JA
        or id_ in HEADER_TOKENS_ID
    )


def normalize_value(s: str) -> str:
    """去前后空白 + NBSP；保留中间空格。"""
    if s is None:
        return ""
    return s.replace(" ", " ").strip()


def iter_csv_rows(csv_path: Path) -> Iterator[tuple[str, str, str, str]]:
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        for row in reader:
            if len(row) < 3:
                continue
            zh, en, ja = normalize_value(row[0]), normalize_value(row[1]), normalize_value(row[2])
            id_ = normalize_value(row[3]) if len(row) >= 4 else ""
            yield zh, en, ja, id_


def parse_official_csvs(
    csv_paths: list[Path],
) -> tuple[dict[str, str], dict[str, str], dict[str, str], list[dict]]:
    """合并多个 csv → (zh-en, zh-ja, zh-id, conflicts)。

    conflicts: 同 key 不同译法记录。后出现的不覆盖，但记进 conflicts。
    """
    zh_en: dict[str, str] = {}
    zh_ja: dict[str, str] = {}
    zh_id: dict[str, str] = {}
    conflicts: list[dict] = []

    for csv_path in csv_paths:
        for zh, en, ja, id_ in iter_csv_rows(csv_path):
            if not zh:
                continue
            if is_header_row(zh, en, ja, id_):
                continue
            if not en and not ja and not id_:
                continue
            for target, mapping, lang in (
                (en, zh_en, "en"),
                (ja, zh_ja, "ja"),
                (id_, zh_id, "id"),
            ):
                if not target:
                    continue
                if zh in mapping and mapping[zh] != target:
                    conflicts.append(
                        {
                            "zh": zh,
                            "lang": lang,
                            "kept": mapping[zh],
                            "ignored": target,
                            "source": csv_path.name,
                        }
                    )
                    continue
                mapping[zh] = target

    return zh_en, zh_ja, zh_id, conflicts


def parse_supplements_md(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """从 local-supplements.md 抽 (zh-en, zh-ja)。

    支持两种表格：
    - | 中文 | 英文 | [备注] |
    - | 中文 | 英文 | 日文 | [备注] |
    """
    zh_en: dict[str, str] = {}
    zh_ja: dict[str, str] = {}
    if not path.exists():
        return zh_en, zh_ja

    text = path.read_text(encoding="utf-8")
    in_table = False
    has_ja_col = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            in_table = False
            continue
        if re.match(r"^\|\s*-+", line):
            continue
        cols = [normalize_value(c) for c in line.strip("|").split("|")]
        if len(cols) < 2:
            continue

        # 表头识别
        if not in_table:
            in_table = True
            has_ja_col = len(cols) >= 3 and cols[2] in HEADER_TOKENS_JA
            continue
        if cols[0] in HEADER_TOKENS_ZH:
            has_ja_col = len(cols) >= 3 and cols[2] in HEADER_TOKENS_JA
            continue

        zh_raw, en_raw = cols[0], cols[1]
        ja_raw = cols[2] if has_ja_col and len(cols) >= 3 else ""

        # 拆 "AI 表格 / AI表格" 这种多形式 zh
        zh_variants = [v.strip() for v in re.split(r"\s*/\s*", zh_raw) if v.strip()]
        # en 多选取第一个，去 (...) 注释
        en_clean = re.split(r"\s*/\s*", en_raw)[0]
        en_clean = re.sub(r"（.*?）|\(.*?\)", "", en_clean).strip()
        ja_clean = re.split(r"\s*/\s*", ja_raw)[0] if ja_raw else ""
        ja_clean = re.sub(r"（.*?）|\(.*?\)", "", ja_clean).strip()

        for zh in zh_variants:
            if len(zh) < 2:
                continue
            if en_clean:
                zh_en[zh] = en_clean
            if ja_clean:
                zh_ja[zh] = ja_clean

    return zh_en, zh_ja


def merge_with_official(
    official: dict[str, str],
    supplements: dict[str, str],
) -> tuple[dict[str, str], dict]:
    """official 优先；supplements 仅补充 official 未覆盖的 key。返回 (合并结果, 统计)。"""
    merged: dict[str, str] = dict(official)
    supplement_added = 0
    for zh, target in supplements.items():
        if zh in merged:
            continue
        merged[zh] = target
        supplement_added += 1
    stats = {
        "official_count": len(official),
        "supplement_total": len(supplements),
        "supplement_added": supplement_added,
        "supplement_skipped_covered": len(supplements) - supplement_added,
        "merged_total": len(merged),
    }
    return merged, stats


def sort_by_key_len_desc(d: dict[str, str]) -> dict[str, str]:
    return dict(sorted(d.items(), key=lambda kv: (-len(kv[0]), kv[0])))


def write_json(path: Path, data: dict | list, *, dry_run: bool) -> str:
    body = json.dumps(data, ensure_ascii=False, indent=2)
    if dry_run:
        return f"(dry-run) would write {path.relative_to(GLOSSARY_DIR.parent)}: {len(body)} bytes"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return f"wrote {path.relative_to(GLOSSARY_DIR.parent)}: {len(body)} bytes"


def render_report(
    csv_files: list[Path],
    official_en: dict[str, str],
    official_ja: dict[str, str],
    conflicts: list[dict],
    supp_en: dict[str, str],
    supp_ja: dict[str, str],
    en_stats: dict,
    ja_stats: dict,
) -> str:
    en_conflicts = [c for c in conflicts if c["lang"] == "en"]
    ja_conflicts = [c for c in conflicts if c["lang"] == "ja"]
    lines = [
        "# Glossary Merge Report",
        "",
        f"_generated by `scripts/glossary_sync.py`_",
        "",
        "## 输入",
        "",
    ]
    for p in csv_files:
        lines.append(f"- `{p.relative_to(GLOSSARY_DIR.parent)}`")
    lines += [
        "",
        f"- 本地补充：`{LOCAL_SUPPLEMENTS_MD.relative_to(GLOSSARY_DIR.parent)}`"
        f"（zh-en {len(supp_en)} 条 / zh-ja {len(supp_ja)} 条）",
        "",
        "## Official（语言同学权威词库）",
        "",
        f"| 语向 | 条数 |",
        f"|---|---|",
        f"| zh → en | {len(official_en)} |",
        f"| zh → ja | {len(official_ja)} |",
        f"| 内部冲突（en） | {len(en_conflicts)} |",
        f"| 内部冲突（ja） | {len(ja_conflicts)} |",
        "",
        "## 合并（official + 本地补充）",
        "",
        f"| 语向 | official | 本地补充被采纳 | 本地补充被覆盖跳过 | 最终条数 |",
        f"|---|---|---|---|---|",
        f"| zh → en | {en_stats['official_count']} | {en_stats['supplement_added']} | {en_stats['supplement_skipped_covered']} | {en_stats['merged_total']} |",
        f"| zh → ja | {ja_stats['official_count']} | {ja_stats['supplement_added']} | {ja_stats['supplement_skipped_covered']} | {ja_stats['merged_total']} |",
        "",
    ]
    if conflicts:
        lines += [
            "## 冲突清单（仅保留首次出现的译法）",
            "",
            "前 20 条预览，完整版见 `official/conflicts.json`：",
            "",
            "| 中文 | 语向 | 保留 | 忽略 | 来源 |",
            "|---|---|---|---|---|",
        ]
        for c in conflicts[:20]:
            lines.append(f"| {c['zh']} | {c['lang']} | {c['kept']} | {c['ignored']} | {c['source']} |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync official glossary CSV → JSON")
    parser.add_argument("--dry-run", action="store_true", help="不写文件，只输出诊断")
    parser.add_argument("--source", help="只解析指定 csv（默认扫 import/*.csv）")
    args = parser.parse_args()

    if args.source:
        csv_files = [Path(args.source)]
    else:
        if not IMPORT_DIR.exists():
            print(f"错误：{IMPORT_DIR} 不存在", file=sys.stderr)
            return 1
        csv_files = sorted(IMPORT_DIR.glob("*.csv"))

    if not csv_files:
        print(f"错误：未找到 csv 文件于 {IMPORT_DIR}", file=sys.stderr)
        return 1

    print(f"[*] 解析 {len(csv_files)} 个 csv …")
    for p in csv_files:
        print(f"    - {p.name}")

    official_en, official_ja, official_id, conflicts = parse_official_csvs(csv_files)
    official_en = sort_by_key_len_desc(official_en)
    official_ja = sort_by_key_len_desc(official_ja)
    official_id = sort_by_key_len_desc(official_id)
    print(
        f"[*] official: zh-en {len(official_en)} 条 / zh-ja {len(official_ja)} 条 / "
        f"zh-id {len(official_id)} 条 / 冲突 {len(conflicts)} 条"
    )

    supp_en, supp_ja = parse_supplements_md(LOCAL_SUPPLEMENTS_MD)
    print(f"[*] supplements: zh-en {len(supp_en)} 条 / zh-ja {len(supp_ja)} 条")

    merged_en, en_stats = merge_with_official(official_en, supp_en)
    merged_ja, ja_stats = merge_with_official(official_ja, supp_ja)
    # id 暂无本地补充，直接用 official
    merged_id = sort_by_key_len_desc(dict(official_id))
    merged_en = sort_by_key_len_desc(merged_en)
    merged_ja = sort_by_key_len_desc(merged_ja)
    print(f"[*] merged: zh-en {len(merged_en)} 条 / zh-ja {len(merged_ja)} 条 / zh-id {len(merged_id)} 条")

    print(write_json(OFFICIAL_DIR / "zh-en.json", official_en, dry_run=args.dry_run))
    print(write_json(OFFICIAL_DIR / "zh-ja.json", official_ja, dry_run=args.dry_run))
    print(write_json(OFFICIAL_DIR / "zh-id.json", official_id, dry_run=args.dry_run))
    print(write_json(OFFICIAL_DIR / "conflicts.json", conflicts, dry_run=args.dry_run))
    print(write_json(FINAL_ZH_EN, merged_en, dry_run=args.dry_run))
    print(write_json(FINAL_ZH_JA, merged_ja, dry_run=args.dry_run))
    print(write_json(FINAL_ZH_ID, merged_id, dry_run=args.dry_run))

    report = render_report(
        csv_files, official_en, official_ja, conflicts,
        supp_en, supp_ja, en_stats, ja_stats,
    )
    if args.dry_run:
        print(f"(dry-run) would write {MERGE_REPORT.relative_to(GLOSSARY_DIR.parent)}")
    else:
        MERGE_REPORT.write_text(report, encoding="utf-8")
        print(f"wrote {MERGE_REPORT.relative_to(GLOSSARY_DIR.parent)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
