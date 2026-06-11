#!/usr/bin/env python3
"""
Apply the 16 mechanical content constraints from the guide md to raw markdown.

The guide md (~/Downloads/dingtalk-open-service-api-docs.md) defines 20+ content
constraints. This script implements the 16 that can be applied mechanically:
  - 2 domain rewrites (low risk, always on)
  - 9 keyword-paragraph deletions (mixed risk; 3 default-off)
  - 3 SDK / debug-tool deletions (mostly high-risk; 1 default-off)
  - 2 pricing / credential deletions (1 default-off)

Two constraints from the guide are NOT implemented here:
  - A3 "Cross-site links → in-doc anchors" (needs semantic analysis)
  - E1 "API permission list trimmed to curated modules" (cross-document)

Defaults are dry-run: writes preview.md + changes.json + per-file diffs only.
Use --apply to actually write clean/{ns}/{slug}.md (never touches raw/).
Use --enable RULE_ID,... to turn on high-risk rules for this run.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
OUT_DIR = HERE / "output" / "open_platform"
RAW_DIR = OUT_DIR / "raw"
CLEAN_DIR = OUT_DIR / "clean"
CONS_DIR = OUT_DIR / "constraints"

RISK_LOW, RISK_MED, RISK_HIGH = "low", "medium", "high"


@dataclasses.dataclass
class Constraint:
    id: str
    name: str
    rule_type: str   # global_replace | paragraph_delete | section_delete
    pattern: str     # raw regex
    risk: str        # low | medium | high
    replacement: str = ""
    note: str = ""
    default_on: bool = True

    def compiled(self) -> re.Pattern:
        return re.compile(self.pattern)


CONSTRAINTS: list[Constraint] = [
    # ===== A: domain rewrites (always safe) =====
    Constraint("A1", "开发者后台域名 open-dev.dingtalk.com → open-dev.dingtalk.io",
        "global_replace", r"open-dev\.dingtalk\.com", RISK_LOW,
        replacement="open-dev.dingtalk.io"),
    Constraint("A2", "管理后台域名 oa.dingtalk.com → oa.dingtalk.io",
        "global_replace", r"\boa\.dingtalk\.com\b", RISK_LOW,
        replacement="oa.dingtalk.io"),

    # ===== B: keyword-paragraph deletions =====
    Constraint("B1", "删第三方企业应用 / 第三方个人应用相关段落",
        "paragraph_delete", r"第三方(企业|个人)应用", RISK_MED,
        note="多见于「适用对象」段，建议保留人工 spot check"),
    Constraint("B2", "删小程序段落（同段含「微应用」则保留）",
        "paragraph_delete", r"小程序", RISK_HIGH,
        note="同段含「微应用」时本规则会跳过该段；但海外仍可能误删；默认 OFF",
        default_on=False),
    Constraint("B3", "删委托商服务 / 委托应用",
        "paragraph_delete", r"委托(商服务|应用)", RISK_LOW),
    Constraint("B4", "删互动卡片 / 场景群",
        "paragraph_delete", r"(互动卡片|场景群)", RISK_MED,
        note="「互动卡片」是消息卡片新形态，海外不开放；命中段落整删"),
    Constraint("B5", "删行业通讯录 / 上下游组织 / 上下级组织",
        "paragraph_delete", r"(行业通讯录|上下游组织|上下级组织)", RISK_LOW),
    Constraint("B6", "删定制应用",
        "paragraph_delete", r"定制应用", RISK_LOW),
    Constraint("B7", "删直播",
        "paragraph_delete", r"直播", RISK_HIGH,
        note="「直播间」「直播课」等也会命中；默认 OFF",
        default_on=False),
    Constraint("B8", "删 AI 助理 / Agoal",
        "paragraph_delete", r"(AI\s*助理|Agoal)", RISK_LOW),
    Constraint("B9", "删工作台相关章节（H1-H6 标题含「工作台」）",
        "section_delete", r"工作台", RISK_MED,
        note="从段落级降级到章节级 — 只删标题含「工作台」的整节；段落 / 列表 / 表格里的「工作台」token 不再误删；默认 ON"),

    # ===== C: SDK / debug tool =====
    Constraint("C1", "删服务端 SDK 章节（H1-H6 标题含语言名 + SDK/示例/集成）",
        "section_delete",
        r"\b(Java|Python|PHP|Go|Node\.?\s*JS|Node\.?js|C#|\.NET|Ruby|Kotlin|Scala)\b.*?(SDK|示例|集成|调用|入门|快速接入|安装|示例代码|demo)|\b(SDK)\s*(示例|集成|调用|快速接入)|(Java|Python|PHP|Go|Node|C#)\s*(SDK)",
        RISK_MED,
        note="精准化：只在 H1-H6 标题里匹配；保留段落里的 HTTP 调用方式；改默认 ON"),
    Constraint("C1b", "删服务端 SDK 代码块（lang ∈ java/python/php/go/js/ts/csharp/ruby/kotlin/scala/node）",
        "code_block_delete",
        r"^(java|python|php|go|golang|javascript|js|typescript|ts|csharp|c#|cs|ruby|kotlin|scala|node|nodejs)$",
        RISK_MED,
        note="按 fenced code 的语言标签 ```lang 整块删；保留指导 md 要求的 HTTP/curl/shell 块；默认 ON"),
    Constraint("C2", "删 SDK 开发环境安装（IDE / Maven / JDK / Gradle / IntelliJ / Eclipse）",
        "paragraph_delete",
        r"\b(IntelliJ\s*IDEA|Eclipse(?!\s*Foundation)|Maven|Gradle|JDK\s*[0-9]+|Apache\s*Maven)\b",
        RISK_MED),
    Constraint("C3", "删服务端调试工具 API Explorer",
        "paragraph_delete", r"API\s*Explorer", RISK_LOW),

    # ===== D: pricing / credential =====
    Constraint("D1", "删收费 / 计费 / 套餐版本（基础/标准/企业/旗舰/高级版）",
        "paragraph_delete",
        r"(收费|计费|计量|套餐版本|基础版|标准版|旗舰版|高级版)",
        RISK_HIGH,
        note="「企业版」单独不算，会和应用类型冲突；当前模式只匹配套餐场景关键词；默认 OFF",
        default_on=False),
    Constraint("D2", "删获取微应用后台免登 accessToken（『微应用 + 免登 + accessToken』20 字内共现）",
        "paragraph_delete",
        r"微应用(后台)?.{0,20}免登.{0,20}access[_-]?[Tt]oken|access[_-]?[Tt]oken.{0,20}微应用(后台)?.{0,20}免登|(获取)?微应用(后台)?免登.{0,5}access[_-]?[Tt]oken",
        RISK_LOW,
        note="放宽：原 pattern 仅同段紧邻匹配 0 命中，现在三关键词只要 20 字范围内即触发"),
]


# --------------- markdown helpers ---------------

FENCE_RE = re.compile(r"^```")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
FM_END_RE = re.compile(r"^---\s*$")


def split_frontmatter(text: str) -> tuple[str, str]:
    """Return (frontmatter_with_trailing_blank, body)."""
    if not text.startswith("---\n"):
        return "", text
    lines = text.splitlines(keepends=True)
    for i in range(1, len(lines)):
        if FM_END_RE.match(lines[i].rstrip("\n")):
            fm = "".join(lines[: i + 1])
            # Consume one trailing blank line if present
            j = i + 1
            if j < len(lines) and lines[j].strip() == "":
                fm += lines[j]
                j += 1
            body = "".join(lines[j:])
            return fm, body
    return "", text


def split_paragraphs(body: str) -> list[tuple[int, str, bool]]:
    """Split body into (start_line, text, in_code_block) chunks.

    A 'paragraph' here = a run of consecutive non-blank lines.
    Lines inside ``` fenced code are flagged in_code_block=True at the whole-
    paragraph level (if any line of the paragraph is inside a fence).
    Fence delimiter lines themselves belong to the paragraph they start/end.
    """
    lines = body.splitlines()
    paragraphs: list[tuple[int, str, bool]] = []
    cur: list[str] = []
    cur_start = 0
    in_code = False
    para_has_code_line = False

    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            # Toggle code state; the fence delimiter line is part of the para
            if not cur:
                cur_start = i
            cur.append(line)
            in_code = not in_code
            para_has_code_line = True
            continue
        if not line.strip() and not in_code:
            if cur:
                paragraphs.append((cur_start, "\n".join(cur), para_has_code_line))
                cur = []
                para_has_code_line = False
            continue
        if not cur:
            cur_start = i
        cur.append(line)
        if in_code:
            para_has_code_line = True
    if cur:
        paragraphs.append((cur_start, "\n".join(cur), para_has_code_line))
    return paragraphs


# --------------- rule application ---------------


def _snippet(text: str, max_len: int = 240) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[:max_len] + " … (truncated)"


def apply_global_replace(body: str, rule: Constraint) -> tuple[str, list[dict]]:
    rx = rule.compiled()
    matches = list(rx.finditer(body))
    if not matches:
        return body, []
    # Group adjacent matches per line for nicer reporting
    line_offsets: list[int] = [0]
    for i, ch in enumerate(body):
        if ch == "\n":
            line_offsets.append(i + 1)
    def line_of(off: int) -> int:
        # Binary search
        lo, hi = 0, len(line_offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_offsets[mid] <= off:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1  # 1-indexed
    changes: list[dict] = []
    for m in matches:
        changes.append({
            "line_no": line_of(m.start()),
            "match": m.group(0),
            "replacement": rule.replacement,
        })
    new_body = rx.sub(rule.replacement, body)
    return new_body, changes


def is_table_block(para: str) -> bool:
    """A GFM table starts with a `|` row followed by a `| --- |` separator row."""
    lines = para.splitlines()
    if len(lines) < 2:
        return False
    first = lines[0].lstrip()
    second = lines[1].lstrip()
    return first.startswith("|") and second.startswith("|") and "---" in second


_LIST_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s")


def is_list_block(para: str) -> bool:
    """All non-blank lines start with a list marker (`- `, `* `, `1.`, etc).

    Continuation lines (indented under a list item) are also accepted as long
    as at least one true list marker appears.
    """
    non_blank = [l for l in para.splitlines() if l.strip()]
    if not non_blank:
        return False
    marker_count = sum(1 for l in non_blank if _LIST_RE.match(l))
    if marker_count == 0:
        return False
    # Allow continuation/nested lines (indented) — but at least one marker per item ratio
    return marker_count >= max(1, len(non_blank) // 4)


def apply_paragraph_delete(body: str, rule: Constraint) -> tuple[str, list[dict]]:
    """Delete paragraphs matching pattern, but SKIP (keep + flag) table blocks
    to avoid wiping API reference tables when a keyword appears in any cell."""
    rx = rule.compiled()
    paragraphs = split_paragraphs(body)
    out: list[str] = []
    changes: list[dict] = []
    for start, para, in_code in paragraphs:
        # B2: keep paragraph if "微应用" co-occurs in same paragraph
        if rule.id == "B2" and "微应用" in para:
            out.append(para)
            continue
        if not in_code and rx.search(para):
            ctx = "text"
            stripped = para.lstrip()
            if is_table_block(para):
                ctx = "table"
            elif stripped.startswith("#"):
                ctx = "heading"
            elif stripped.startswith("|"):  # table row outside of recognized block
                ctx = "table_row"
            elif is_list_block(para):
                ctx = "list"

            change = {
                "line_no": start + 1,
                "snippet": _snippet(para),
                "context": ctx,
            }
            if ctx in ("table", "table_row", "list"):
                # Flag only; don't auto-delete (would wipe API tables / mixed lists)
                change["action"] = "skip_manual_review"
                changes.append(change)
                out.append(para)
                continue
            change["action"] = "delete"
            changes.append(change)
            continue
        out.append(para)
    new_body = "\n\n".join(out)
    if not new_body.endswith("\n"):
        new_body += "\n"
    return new_body, changes


_FENCE_OPEN_RE = re.compile(r"^```(.*)$")


def apply_code_block_delete(body: str, rule: Constraint) -> tuple[str, list[dict]]:
    """Delete fenced code blocks whose language label matches the pattern.

    Lang = string immediately after ``` (before any space). Match is case-insensitive
    (pattern itself handles via lower()).
    """
    rx = rule.compiled()
    lines = body.splitlines()
    out: list[str] = []
    changes: list[dict] = []
    in_target = False
    in_any_fence = False
    block_start = 0
    current_lang = ""
    for i, line in enumerate(lines):
        m = _FENCE_OPEN_RE.match(line)
        if m:
            if not in_any_fence:
                lang = m.group(1).strip().lower()
                in_any_fence = True
                if rx.search(lang):
                    in_target = True
                    block_start = i
                    current_lang = lang or "(no-lang)"
                    continue
                out.append(line)
                continue
            # Closing fence
            in_any_fence = False
            if in_target:
                changes.append({
                    "line_no": block_start + 1,
                    "snippet": f"```{current_lang}…``` ({i - block_start} 行)",
                    "context": "code_block",
                    "action": "delete",
                })
                in_target = False
                current_lang = ""
            else:
                out.append(line)
            continue
        if in_target:
            continue
        out.append(line)
    new_body = "\n".join(out)
    if not new_body.endswith("\n"):
        new_body += "\n"
    return new_body, changes


def apply_section_delete(body: str, rule: Constraint) -> tuple[str, list[dict]]:
    rx = rule.compiled()
    lines = body.splitlines()
    out: list[str] = []
    changes: list[dict] = []
    skip_until_level: int | None = None
    in_code = False
    for i, line in enumerate(lines):
        if FENCE_RE.match(line):
            in_code = not in_code
            if skip_until_level is None:
                out.append(line)
            continue
        if in_code:
            if skip_until_level is None:
                out.append(line)
            continue
        m = HEAD_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2)
            # Did we just exit the skipped section?
            if skip_until_level is not None and level <= skip_until_level:
                skip_until_level = None
            if skip_until_level is None and rx.search(title):
                skip_until_level = level
                changes.append({"line_no": i + 1, "snippet": line.strip()})
                continue
        if skip_until_level is None:
            out.append(line)
    new_body = "\n".join(out)
    if not new_body.endswith("\n"):
        new_body += "\n"
    return new_body, changes


def process_file(path: Path, active: list[Constraint]) -> tuple[str, dict, int, int]:
    """Return (new_text, per_rule_changes, raw_body_bytes, new_body_bytes).

    The two size numbers are body-only (excludes frontmatter) so the size ratio
    reflects real content shrinkage from the rules.
    """
    text = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)
    raw_body_size = len(body.encode("utf-8"))
    per_rule: dict[str, list[dict]] = {}
    for rule in active:
        if rule.rule_type == "global_replace":
            body, ch = apply_global_replace(body, rule)
        elif rule.rule_type == "paragraph_delete":
            body, ch = apply_paragraph_delete(body, rule)
        elif rule.rule_type == "section_delete":
            body, ch = apply_section_delete(body, rule)
        elif rule.rule_type == "code_block_delete":
            body, ch = apply_code_block_delete(body, rule)
        else:
            ch = []
        if ch:
            per_rule[rule.id] = ch
    new_body_size = len(body.encode("utf-8"))
    return fm + body, per_rule, raw_body_size, new_body_size


# --------------- preview / apply driver ---------------


def select_rules(args) -> list[Constraint]:
    active: list[Constraint] = []
    enable_set = set(s.strip() for s in (args.enable or "").split(",") if s.strip())
    disable_set = set(s.strip() for s in (args.disable or "").split(",") if s.strip())
    for c in CONSTRAINTS:
        on = c.default_on
        if c.id in enable_set:
            on = True
        if c.id in disable_set:
            on = False
        if on:
            active.append(c)
    return active


def iter_raw_files() -> list[Path]:
    files: list[Path] = []
    for ns_dir in sorted(RAW_DIR.iterdir()) if RAW_DIR.exists() else []:
        if ns_dir.is_dir():
            for p in sorted(ns_dir.glob("*.md")):
                files.append(p)
    return files


def write_per_file_diff(rel: str, per_rule: dict, raw_text: str, new_text: str) -> None:
    out_path = CONS_DIR / "preview" / f"{rel}.diff.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# {rel}", ""]
    for rule_id in sorted(per_rule.keys()):
        rule = next(c for c in CONSTRAINTS if c.id == rule_id)
        changes = per_rule[rule_id]
        lines.append(f"## {rule_id} — {rule.name} [{rule.risk}] ({len(changes)} 处)")
        lines.append("")
        for ch in changes[:25]:
            ln = ch.get("line_no", "?")
            if rule.rule_type == "global_replace":
                lines.append(f"- L{ln}: `{ch['match']}` → `{ch['replacement']}`")
            else:
                snip = ch.get("snippet", "")
                lines.append(f"- L{ln}:")
                lines.append("  ```")
                for line in snip.splitlines():
                    lines.append(f"  {line}")
                lines.append("  ```")
        if len(changes) > 25:
            lines.append(f"- … 还有 {len(changes) - 25} 处")
        lines.append("")
    raw_bytes = len(raw_text.encode("utf-8"))
    new_bytes = len(new_text.encode("utf-8"))
    delta = new_bytes - raw_bytes
    lines.append("---")
    lines.append(f"raw: {raw_bytes:,} B | post-rules: {new_bytes:,} B | Δ: {delta:+,} B")
    out_path.write_text("\n".join(lines), encoding="utf-8")


def build_preview_md(summary: dict, active_ids: set[str], disabled_ids: set[str],
                     enabled_stats: dict, disabled_stats: dict, file_count: int,
                     hit_file_count: int,
                     near_empty: list[tuple[str, dict]] | None = None,
                     near_empty_threshold: float = 0.3) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []
    lines.append("# 约束规则预览（dry-run）\n")
    lines.append(f"> 生成时间：{now}")
    lines.append(f"> 输入：`scripts/output/open_platform/raw/` 共 {file_count} 篇")
    lines.append(f"> 启用规则：**{len(active_ids)} / 16 条**（高风险 5 条默认 OFF）")
    lines.append(f"> 受影响篇数：**{hit_file_count}** / {file_count}")
    lines.append("")
    lines.append("## 规则列表与启用状态\n")
    lines.append("> **删除** = 应用后真实删除的段；**跳过** = 命中但在表格里，需人工 review 不自动删")
    lines.append("")
    lines.append("| ID | 规则 | 风险 | 启用 | 命中篇数 | 删除 | 跳过(表格) |")
    lines.append("|---|---|:-:|:-:|---:|---:|---:|")
    for c in CONSTRAINTS:
        on = c.id in active_ids
        stats = enabled_stats if on else disabled_stats
        s = stats.get(c.id, {"files": 0, "ops": 0, "del_ops": 0, "skip_ops": 0})
        risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}[c.risk]
        on_icon = "✅" if on else "🚫"
        del_part = s.get("del_ops", s.get("ops", 0))
        skip_part = s.get("skip_ops", 0)
        # global_replace doesn't have skip; show as "—"
        if c.rule_type == "global_replace":
            del_str = str(s.get("ops", 0))
            skip_str = "—"
        else:
            del_str = str(del_part)
            skip_str = str(skip_part) if skip_part else "—"
        lines.append(
            f"| {c.id} | {c.name} | {risk_icon} {c.risk} | {on_icon} | {s['files']} | {del_str} | {skip_str} |"
        )
    lines.append("")
    if disabled_ids:
        lines.append("> 🚫 默认 OFF 规则（B2/B7/B9/C1/D1）也跑了 dry-run 计数，未真正影响 preview 文件；")
        lines.append("> 若审完想启用，加 `--enable B7,B9` 重跑 preview，或直接 `--apply --enable ...`。")
        lines.append("")

    def render_rule_block(c: Constraint, s: dict, prefix: str) -> None:
        lines.append(f"### {prefix} {c.id} — {c.name}")
        meta = [f"风险：{c.risk}", f"命中：{s['files']} 篇"]
        if c.rule_type == "global_replace":
            meta.append(f"替换：{s.get('ops', 0)} 处")
        else:
            meta.append(f"删除：{s.get('del_ops', 0)} 处")
            if s.get("skip_ops"):
                meta.append(f"跳过(表格)：{s['skip_ops']} 处")
        lines.append("- " + " | ".join(meta))
        if c.note:
            lines.append(f"- 备注：{c.note}")
        samples_del = s.get("samples_delete", [])
        if samples_del:
            lines.append(f"- 真正会删除（删除样例前 5）：")
            for sample in samples_del[:5]:
                ctx = f"[{sample.get('context', '?')}] " if sample.get("context") else ""
                lines.append(f"  - `{sample['file']}` L{sample['line_no']}: {ctx}{sample['snippet']}")
        samples_skip = s.get("samples_skip", [])
        if samples_skip:
            lines.append(f"- ⚠️ 跳过（含关键词但在表格中，需人工 review，前 3）：")
            for sample in samples_skip[:3]:
                ctx = f"[{sample.get('context', '?')}] " if sample.get("context") else ""
                lines.append(f"  - `{sample['file']}` L{sample['line_no']}: {ctx}{sample['snippet']}")
        # global_replace samples (no skip/del split — use ops fallback)
        if c.rule_type == "global_replace" and not samples_del:
            # Reconstitute samples from changes.json source instead — but for preview just show count
            pass
        lines.append("")

    lines.append("## 按规则详情（启用）\n")
    for c in CONSTRAINTS:
        if c.id not in active_ids:
            continue
        s = enabled_stats.get(c.id, {"files": 0, "ops": 0, "samples_delete": [], "samples_skip": []})
        if s["files"] == 0:
            continue
        render_rule_block(c, s, "✅")

    if disabled_ids:
        lines.append("## 按规则详情（默认 OFF，仅展示影响范围）\n")
        for c in CONSTRAINTS:
            if c.id in active_ids:
                continue
            s = disabled_stats.get(c.id, {"files": 0, "ops": 0, "samples_delete": [], "samples_skip": []})
            if s["files"] == 0:
                continue
            render_rule_block(c, s, "🚫")

    if near_empty:
        lines.append(f"## ⚠️ 整文删建议 — 体积剩 < {near_empty_threshold:.0%}\n")
        lines.append(
            "> 经过 rules 处理后正文剩余比例低于阈值，文档基本被掏空，建议 `--apply --drop-near-empty` "
            "时整文不写入 clean/，由人工决定是否入库。"
        )
        lines.append("")
        lines.append("| 文件 | 原 (B) | 后 (B) | 剩余比 |")
        lines.append("|---|---:|---:|---:|")
        for rel, sz in near_empty[:50]:
            lines.append(
                f"| `{rel}.md` | {sz['raw_size']:,} | {sz['new_size']:,} | {sz['ratio']:.1%} |"
            )
        if len(near_empty) > 50:
            lines.append(f"| … 还有 {len(near_empty) - 50} 条 | | | |")
        lines.append("")

    lines.append("## 按文件命中 Top 30\n")
    by_file = sorted(summary.get("by_file", {}).items(),
                     key=lambda kv: -sum(len(v) for v in kv[1].values()))
    for rel, per_rule in by_file[:30]:
        total = sum(len(v) for v in per_rule.values())
        rule_list = ", ".join(f"{rid}×{len(v)}" for rid, v in sorted(per_rule.items()))
        lines.append(f"- `{rel}.md` ({total} 处): {rule_list}")
    if len(by_file) > 30:
        lines.append(f"- … 还有 {len(by_file) - 30} 篇，详见 `changes.json` 或 `preview/{{ns}}/{{slug}}.diff.md`")
    lines.append("")
    return "\n".join(lines)


def stats_from_per_file(per_file_all: dict, rule_ids: set[str]) -> dict:
    """For each rule_id in rule_ids, return {files, ops, del_ops, skip_ops, samples_delete, samples_skip}."""
    out: dict[str, dict] = {}
    for rid in rule_ids:
        files = 0
        ops = 0
        del_ops = 0
        skip_ops = 0
        samples_delete: list[dict] = []
        samples_skip: list[dict] = []
        for rel, per_rule in per_file_all.items():
            ch = per_rule.get(rid, [])
            if not ch:
                continue
            files += 1
            ops += len(ch)
            for c in ch:
                action = c.get("action", "delete")
                if action == "delete":
                    del_ops += 1
                    if len(samples_delete) < 8:
                        snip = (c.get("snippet") or c.get("match", "")).replace("\n", " ⏎ ")
                        if len(snip) > 160:
                            snip = snip[:160] + "…"
                        samples_delete.append({
                            "file": rel + ".md",
                            "line_no": c.get("line_no"),
                            "snippet": snip,
                            "context": c.get("context"),
                        })
                else:
                    skip_ops += 1
                    if len(samples_skip) < 5:
                        snip = (c.get("snippet") or "").replace("\n", " ⏎ ")
                        if len(snip) > 160:
                            snip = snip[:160] + "…"
                        samples_skip.append({
                            "file": rel + ".md",
                            "line_no": c.get("line_no"),
                            "snippet": snip,
                            "context": c.get("context"),
                        })
        out[rid] = {
            "files": files, "ops": ops,
            "del_ops": del_ops, "skip_ops": skip_ops,
            "samples_delete": samples_delete,
            "samples_skip": samples_skip,
        }
    return out


def cmd_preview(args) -> int:
    if not RAW_DIR.exists():
        print(f"ERROR: {RAW_DIR} missing. Run `crawl_open_platform.py fetch` first.", file=sys.stderr)
        return 2
    active = select_rules(args)
    active_ids = {c.id for c in active}
    all_ids = {c.id for c in CONSTRAINTS}
    disabled_ids = all_ids - active_ids

    CONS_DIR.mkdir(parents=True, exist_ok=True)
    (CONS_DIR / "preview").mkdir(exist_ok=True)

    files = iter_raw_files()
    if args.limit:
        files = files[: args.limit]

    print(f"processing {len(files)} files with {len(active)} active rules ({len(disabled_ids)} disabled)")

    per_file_enabled: dict[str, dict] = {}
    per_file_disabled: dict[str, dict] = {}
    file_sizes: dict[str, dict] = {}  # rel -> {raw_size, new_size, ratio}

    for i, p in enumerate(files):
        rel = f"{p.parent.name}/{p.stem}"
        raw_text = p.read_text(encoding="utf-8")
        new_text, per_rule, raw_size, new_size = process_file(p, active)
        if per_rule:
            per_file_enabled[rel] = per_rule
            write_per_file_diff(rel, per_rule, raw_text, new_text)
        ratio = new_size / raw_size if raw_size else 1.0
        file_sizes[rel] = {"raw_size": raw_size, "new_size": new_size, "ratio": ratio}
        # Also dry-run disabled rules separately so we can show their potential
        # impact, but DO NOT cascade their changes (so each disabled rule is
        # evaluated against the ORIGINAL raw — gives a clean impact estimate).
        disabled_rules = [c for c in CONSTRAINTS if c.id in disabled_ids]
        _, per_rule_d, _, _ = process_file(p, disabled_rules)
        if per_rule_d:
            per_file_disabled[rel] = per_rule_d
        if (i + 1) % 50 == 0 or i + 1 == len(files):
            print(f"  [{i + 1}/{len(files)}]")

    enabled_stats = stats_from_per_file(per_file_enabled, active_ids)
    disabled_stats = stats_from_per_file(per_file_disabled, disabled_ids)
    hit_file_count = len(set(per_file_enabled.keys()) | set(per_file_disabled.keys()))

    # File-level near-empty detection: cascade left < 30% of original body
    near_empty_threshold = args.near_empty_threshold
    near_empty = sorted(
        ((rel, sz) for rel, sz in file_sizes.items()
         if sz["raw_size"] >= 500 and sz["ratio"] < near_empty_threshold),
        key=lambda kv: kv[1]["ratio"],
    )

    # Write changes.json
    changes_json = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "input_dir": str(RAW_DIR),
        "rules": {
            c.id: {
                "name": c.name, "rule_type": c.rule_type, "risk": c.risk,
                "pattern": c.pattern, "replacement": c.replacement,
                "default_on": c.default_on, "active_this_run": c.id in active_ids,
                "note": c.note,
            }
            for c in CONSTRAINTS
        },
        "summary": {
            "enabled": enabled_stats,
            "disabled": disabled_stats,
            "file_count": len(files),
            "hit_file_count": hit_file_count,
            "near_empty_threshold": near_empty_threshold,
            "near_empty_count": len(near_empty),
        },
        "by_file_enabled": per_file_enabled,
        "by_file_disabled": per_file_disabled,
        "file_sizes": file_sizes,
        "near_empty": [
            {"file": rel + ".md", **sz} for rel, sz in near_empty
        ],
    }
    (CONS_DIR / "changes.json").write_text(
        json.dumps(changes_json, ensure_ascii=False, indent=2), encoding="utf-8")

    # Write preview.md
    preview_md = build_preview_md(
        summary={"by_file": per_file_enabled},
        active_ids=active_ids,
        disabled_ids=disabled_ids,
        enabled_stats=enabled_stats,
        disabled_stats=disabled_stats,
        file_count=len(files),
        hit_file_count=hit_file_count,
        near_empty=near_empty,
        near_empty_threshold=near_empty_threshold,
    )
    (CONS_DIR / "preview.md").write_text(preview_md, encoding="utf-8")

    print()
    print(f"=== preview ready ===")
    print(f"  files processed: {len(files)}")
    print(f"  files with hits: {hit_file_count}")
    print(f"  preview:    {CONS_DIR / 'preview.md'}")
    print(f"  per-file:   {CONS_DIR / 'preview' / '<ns>' / '<slug>.diff.md'}")
    print(f"  json:       {CONS_DIR / 'changes.json'}")
    return 0


def cmd_apply(args) -> int:
    """Write clean/{ns}/{slug}.md applying active rules. Never touches raw/."""
    if not RAW_DIR.exists():
        print(f"ERROR: {RAW_DIR} missing.", file=sys.stderr)
        return 2
    active = select_rules(args)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    files = iter_raw_files()
    if args.limit:
        files = files[: args.limit]
    print(f"applying {len(active)} rules to {len(files)} files → {CLEAN_DIR}")

    total_changed = 0
    total_dropped = 0
    threshold = args.near_empty_threshold
    drop_near_empty = args.drop_near_empty
    for i, p in enumerate(files):
        new_text, per_rule, raw_size, new_size = process_file(p, active)
        ratio = new_size / raw_size if raw_size else 1.0
        out_path = CLEAN_DIR / p.parent.name / p.name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if drop_near_empty and raw_size >= 500 and ratio < threshold:
            total_dropped += 1
            # Don't write — file is "dropped" (would be excluded from import)
            continue
        out_path.write_text(new_text, encoding="utf-8")
        if per_rule:
            total_changed += 1
        if (i + 1) % 50 == 0 or i + 1 == len(files):
            print(f"  [{i + 1}/{len(files)}]")
    print()
    print(f"=== apply done ===")
    print(f"  files processed: {len(files)}")
    print(f"  files written:   {len(files) - total_dropped}")
    print(f"  files changed:   {total_changed}")
    if drop_near_empty:
        print(f"  files dropped (near-empty, ratio < {threshold}): {total_dropped}")
    print(f"  output:          {CLEAN_DIR}")
    return 0


def cmd_rules(args) -> int:
    """Print rule list (--enable/--disable for what-if listing)."""
    active = {c.id for c in select_rules(args)}
    for c in CONSTRAINTS:
        on = "ON " if c.id in active else "OFF"
        risk_icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}[c.risk]
        print(f"  [{on}] {risk_icon} {c.id}  {c.name}")
        if c.note:
            print(f"          note: {c.note}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sp = p.add_subparsers(dest="cmd", required=True)

    common_rule_args = lambda sub: (
        sub.add_argument("--enable", help="Comma-separated rule IDs to enable (overrides default-off)"),
        sub.add_argument("--disable", help="Comma-separated rule IDs to disable (overrides default-on)"),
        sub.add_argument("--limit", type=int, default=0, help="Process at most N files (debug)"),
        sub.add_argument("--near-empty-threshold", type=float, default=0.3,
                         help="Ratio threshold below which a file is flagged as near-empty (default 0.3)"),
    )

    pp = sp.add_parser("preview", help="Dry-run: write preview.md + changes.json + per-file diffs")
    common_rule_args(pp)
    pp.set_defaults(func=cmd_preview)

    pa = sp.add_parser("apply", help="Write clean/{ns}/{slug}.md applying rules (never touches raw/)")
    common_rule_args(pa)
    pa.add_argument("--drop-near-empty", action="store_true",
                    help="Don't write clean/ for files where body shrinks below threshold")
    pa.set_defaults(func=cmd_apply)

    pr = sp.add_parser("rules", help="Print rule list with active/inactive flags")
    common_rule_args(pr)
    pr.set_defaults(func=cmd_rules)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
