#!/usr/bin/env python3
"""
跨语言链接污染清理：扫所有 mdx，把指向"别的语言"的链接修正回当前语言。

背景：zh→en 翻译流水线保留了正文 label 但漏了 URL 前缀 `/zh/` 的清理，
导致英文文档大量内链 `](/zh/docs/foo)` 跳到中文站。三语应独立。

规则：
- EN 文件（根 docs/ aitable/ 等）：链接前缀不应含 `/zh/` 或 `/ja/`
- ZH 文件（zh/...）：链接前缀不应含 `/ja/`；不应是裸 `/docs/`（无 lang 前缀）
- JA 文件（ja/...）：链接前缀不应含 `/zh/`；不应是裸 `/docs/`

形态：
- 相对绝对：`](/zh/docs/foo)`
- 完整 URL：`](https://help.dingtalk.io/zh/docs/foo)`
- 链接 title：`](/zh/docs/foo "标题")`

修复策略：
- EN 文件：剥前缀 `/zh/` / `/ja/`，得到 `/docs/foo`；完整 URL 同理
- ZH 文件：把 `/ja/` 替换为 `/zh/`；裸 `/docs/` 添加 `/zh/` 前缀（需谨慎，目标存在性校验）
- JA 文件：把 `/zh/` 替换为 `/ja/`；裸 `/docs/` 添加 `/ja/` 前缀

目标文件存在性校验：替换后路径在仓库内可解析为 mdx 才执行；否则列入报告人审。

CLI:
  python3 scripts/fix_cross_lang_links.py                # dry-run，全部
  python3 scripts/fix_cross_lang_links.py --lang en      # 只扫 EN（最常用）
  python3 scripts/fix_cross_lang_links.py --apply        # 实际写盘
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "fix_cross_lang"

EXCLUDE_DIRS = {"node_modules", ".next", ".mintlify", "scripts", ".claude", ".git"}

# 仅在 site domain 检测
SITE_HOST = "help.dingtalk.io"

# 链接形态：](path) 或 ](path "title")
# path 内不能含 ) 或 空格（除非进入 title 段）
RE_LINK = re.compile(r'\]\((?P<path>[^)\s]+)(?:\s+"(?P<title>[^"]*)")?\)')


@dataclass
class Issue:
    file: str
    line: int
    before: str
    after: str
    kind: str            # zh_in_en / ja_in_en / ja_in_zh / zh_in_ja / bare_in_zh / bare_in_ja
    target_exists: bool  # 修复后路径是否能在仓库找到 mdx
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def file_lang(rel: Path) -> str:
    """返回 'en' / 'zh' / 'ja'。"""
    first = rel.parts[0] if rel.parts else ""
    if first in ("zh", "ja"):
        return first
    return "en"


def normalize_to_relative(url: str) -> str:
    """把 https://help.dingtalk.io/X 改为 /X；其它保持。"""
    prefix = f"https://{SITE_HOST}"
    if url.startswith(prefix):
        rest = url[len(prefix):]
        return rest if rest.startswith("/") else "/" + rest
    return url


def target_mdx_path(url: str) -> Path | None:
    """把站内绝对 URL（如 /zh/docs/foo）映射到仓库内 mdx 路径。
    返回存在的 Path 或 None。"""
    if not url.startswith("/"):
        return None
    rel = url.lstrip("/")
    # 剥 anchor / query
    rel = rel.split("#", 1)[0].split("?", 1)[0]
    if not rel:
        return None
    candidates = [
        REPO_ROOT / f"{rel}.mdx",
        REPO_ROOT / rel / "index.mdx",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def fix_url_for_lang(url: str, lang: str) -> tuple[str | None, str]:
    """根据当前文件语言，返回 (修复后 URL, 修复类型) 或 (None, '')。
    None 表示无需修复。"""
    norm = normalize_to_relative(url)
    is_full = url != norm  # 原本是完整 URL

    if lang == "en":
        # EN 文件：剥 /zh/ /ja/
        if norm.startswith("/zh/"):
            new = "/" + norm[len("/zh/"):]
            return new, "zh_in_en"
        if norm.startswith("/ja/"):
            new = "/" + norm[len("/ja/"):]
            return new, "ja_in_en"
        # 完整 URL 但路径正确：仍然把 https:// 形式改为相对
        if is_full and norm.startswith("/"):
            return norm, "full_to_relative_en"
        return None, ""

    if lang == "zh":
        # ZH 文件：/ja/ → /zh/；裸 /docs/ /aitable/ → /zh/docs/ /zh/aitable/
        if norm.startswith("/ja/"):
            new = "/zh/" + norm[len("/ja/"):]
            return new, "ja_in_zh"
        # 仅当裸 /docs/* /aitable/* 等（未带语言前缀）且目标在 zh/ 下存在
        if norm.startswith("/") and not norm.startswith(("/zh/", "/ja/")):
            stripped = norm.lstrip("/")
            first_seg = stripped.split("/", 1)[0]
            if first_seg in ("docs", "aitable", "guides", "quickstart"):
                new = "/zh" + norm
                return new, "bare_in_zh"
        if is_full and norm.startswith("/zh/"):
            return norm, "full_to_relative_zh"
        return None, ""

    if lang == "ja":
        if norm.startswith("/zh/"):
            new = "/ja/" + norm[len("/zh/"):]
            return new, "zh_in_ja"
        if norm.startswith("/") and not norm.startswith(("/zh/", "/ja/")):
            stripped = norm.lstrip("/")
            first_seg = stripped.split("/", 1)[0]
            if first_seg in ("docs", "aitable", "guides", "quickstart"):
                new = "/ja" + norm
                return new, "bare_in_ja"
        if is_full and norm.startswith("/ja/"):
            return norm, "full_to_relative_ja"
        return None, ""

    return None, ""


def find_line(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def scan_file(path: Path) -> tuple[list[Issue], str | None]:
    rel = path.relative_to(REPO_ROOT)
    lang = file_lang(rel)
    try:
        src = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [], None

    issues: list[Issue] = []
    replacements: list[tuple[int, int, str]] = []

    for m in RE_LINK.finditer(src):
        url = m.group("path")
        title = m.group("title")
        fixed_url, kind = fix_url_for_lang(url, lang)
        if not fixed_url or fixed_url == url:
            continue

        # 校验目标存在
        target = target_mdx_path(fixed_url)
        exists = target is not None

        # 构造新 link 形态
        if title is not None:
            new_link = f']({fixed_url} "{title}")'
        else:
            new_link = f']({fixed_url})'

        before = m.group(0)
        issues.append(Issue(
            file=str(rel),
            line=find_line(src, m.start()),
            before=before,
            after=new_link,
            kind=kind,
            target_exists=exists,
            note="" if exists else "目标 mdx 不存在，跳过自动修复",
        ))
        if exists:
            replacements.append((m.start(), m.end(), new_link))

    if not replacements:
        return issues, None

    # 从后往前替换
    fixed = src
    for start, end, new in reversed(replacements):
        fixed = fixed[:start] + new + fixed[end:]
    return issues, fixed


def discover_files(lang: str) -> list[Path]:
    files: list[Path] = []
    for p in REPO_ROOT.rglob("*.mdx"):
        rel = p.relative_to(REPO_ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        flang = file_lang(rel)
        if lang != "all" and flang != lang:
            continue
        files.append(p)
    files.sort()
    return files


def write_reports(issues: list[Issue], applied: dict[str, int], scanned: int, mode: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    by_kind: dict[str, list[Issue]] = {}
    for i in issues:
        by_kind.setdefault(i.kind, []).append(i)
    by_file: dict[str, int] = {}
    for i in issues:
        by_file[i.file] = by_file.get(i.file, 0) + 1
    unfixable = [i for i in issues if not i.target_exists]

    summary = {
        "mode": mode,
        "scanned_files": scanned,
        "total_issues": len(issues),
        "by_kind": {k: len(v) for k, v in by_kind.items()},
        "files_with_issues": len(by_file),
        "files_applied": len(applied),
        "applied_per_file": applied,
        "unfixable_count": len(unfixable),
    }

    (OUTPUT_DIR / "report.json").write_text(
        json.dumps({"summary": summary, "issues": [i.to_dict() for i in issues]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md = [
        "# 跨语言链接污染报告",
        "",
        f"- 模式：**{mode}**",
        f"- 扫描文件数：{scanned}",
        f"- 命中文件数：{len(by_file)}",
        f"- 命中总数：{len(issues)}",
        f"- 不可自动修复（目标不存在）：{len(unfixable)}",
    ]
    if mode == "apply":
        md.append(f"- 已修改文件数：{len(applied)}")
    md.append("")
    md.append("## 按类型统计")
    md.append("")
    md.append("| 类型 | 命中数 |")
    md.append("|---|---|")
    for k, items in sorted(by_kind.items()):
        md.append(f"| {k} | {len(items)} |")
    md.append("")

    md.append("## Top 20 命中文件")
    md.append("")
    for f, n in sorted(by_file.items(), key=lambda x: x[1], reverse=True)[:20]:
        md.append(f"- `{f}` — {n}")
    md.append("")

    for kind, items in sorted(by_kind.items()):
        md.append(f"## {kind}（前 30 例）")
        md.append("")
        md.append("| 文件 | 行 | 原链接 | 修复后 | 目标存在 |")
        md.append("|---|---|---|---|---|")
        for i in items[:30]:
            before = i.before.replace("|", "\\|")
            after = i.after.replace("|", "\\|")
            md.append(f"| `{i.file}` | {i.line} | `{before}` | `{after}` | {'✓' if i.target_exists else '✗'} |")
        if len(items) > 30:
            md.append(f"\n_（共 {len(items)} 例，余见 report.json）_")
        md.append("")

    if unfixable:
        md.append("## 不可自动修复（目标 mdx 不存在，需人审）")
        md.append("")
        md.append("| 文件 | 行 | 原链接 | 拟修复 | 说明 |")
        md.append("|---|---|---|---|---|")
        for i in unfixable[:50]:
            md.append(f"| `{i.file}` | {i.line} | `{i.before}` | `{i.after}` | {i.note} |")
        if len(unfixable) > 50:
            md.append(f"\n_（共 {len(unfixable)} 例，余见 report.json）_")

    (OUTPUT_DIR / "report.md").write_text("\n".join(md), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="跨语言链接污染清理")
    p.add_argument("--lang", default="all", choices=["all", "en", "zh", "ja"])
    p.add_argument("--apply", action="store_true", help="实际写盘修复（默认 dry-run）")
    p.add_argument("--limit", type=int, default=0)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    files = discover_files(args.lang)
    if args.limit:
        files = files[: args.limit]

    mode = "apply" if args.apply else "dry-run"
    print(f"[info] 模式={mode} lang={args.lang} 文件数={len(files)}")

    all_issues: list[Issue] = []
    applied: dict[str, int] = {}

    for path in files:
        issues, fixed = scan_file(path)
        all_issues.extend(issues)
        actionable = [i for i in issues if i.target_exists]
        if args.apply and fixed is not None and actionable:
            path.write_text(fixed, encoding="utf-8")
            applied[str(path.relative_to(REPO_ROOT))] = len(actionable)

    write_reports(all_issues, applied, len(files), mode)

    print(f"[done] 命中 {len(all_issues)} 处 / {len({i.file for i in all_issues})} 文件")
    if args.apply:
        print(f"[done] 已修改 {len(applied)} 文件")
    print(f"[done] 报告：{OUTPUT_DIR / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
