#!/usr/bin/env python3
"""
批量把连续 ≥2 张移动端截图包成 flex 容器。

启发式（复用 audit_mdx_quality.py 的 is_mobile_screenshot）：
- alt 文件名 lQDPKH / IMG_<digits> 前缀
- alt 内嵌尺寸 _<w>_<h>.png 且 h/w ≥ 1.5
- url crop 参数 w_<>,h_<> 且 h/w ≥ 1.5

替换规则：
- 2 张 → flex 单行 2 列（width 48%）
- 3 张 → flex 单行 3 列（width 32%）
- 4+ → flex + flex-wrap 自动换行（width 32%，按 3/行）

替换范围：从首张图行起，吃掉中间所有空白行，到末张图行（含）止。
非图非空行 → 终止组（不会跨过文本段）。
原本同一行内多个 inline 图也会被拆出来。

CLI:
  python3 scripts/wrap_mobile_screenshots.py                 # dry-run，全仓
  python3 scripts/wrap_mobile_screenshots.py --root drive    # 限定单产品
  python3 scripts/wrap_mobile_screenshots.py --apply         # 实际写盘
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "wrap_mobile"
EXCLUDE_DIRS = {"node_modules", ".next", ".mintlify", "scripts", ".claude", ".git"}

RE_IMG_INLINE = re.compile(r'!\[([^\]]*)\]\((https?://[^)\s]+?)(?:\s+"([^"]*)")?\)')


def is_mobile_screenshot(alt: str, url: str) -> bool:
    """启发式判定一张图是否移动端截图。与 audit_mdx_quality.py 保持一致。"""
    alt = alt or ""
    if re.match(r'(?:lQDPKH|IMG_\d+)', alt, re.I):
        return True
    name_match = re.search(r'_(\d{3,4})_(\d{3,4})\.(?:png|jpg|jpeg)', alt, re.I)
    if name_match:
        w, h = int(name_match.group(1)), int(name_match.group(2))
        if w > 0 and h > w * 1.5:
            return True
    crop_match = re.search(r'w_(\d+),h_(\d+)', url)
    if crop_match:
        w, h = int(crop_match.group(1)), int(crop_match.group(2))
        if w > 0 and h > w * 1.5:
            return True
    return False


@dataclass
class Group:
    file: str
    start_line: int            # 1-based, 首张图所在行
    end_line: int              # 1-based, 末张图所在行（含）
    images: list[tuple[str, str]] = field(default_factory=list)  # [(alt, url)]


def parse_image_line(line: str) -> list[tuple[str, str]]:
    """返回该行所有 image markdown 的 [(alt, url)]。"""
    return [(m.group(1), m.group(2)) for m in RE_IMG_INLINE.finditer(line)]


def find_groups(text: str, rel_path: str) -> list[Group]:
    """扫一个文件，返回所有连续 ≥2 张移动端截图组。"""
    lines = text.split("\n")
    n = len(lines)
    groups: list[Group] = []
    i = 0
    while i < n:
        line = lines[i]
        imgs = parse_image_line(line)
        if not imgs or not all(is_mobile_screenshot(a, u) for a, u in imgs):
            i += 1
            continue
        # 找连续段
        run_imgs: list[tuple[str, str]] = list(imgs)
        run_start = i
        run_end = i
        j = i + 1
        while j < n:
            line_j = lines[j]
            if line_j.strip() == "":
                k = j + 1
                while k < n and lines[k].strip() == "":
                    k += 1
                if k >= n:
                    break
                imgs_k = parse_image_line(lines[k])
                if not imgs_k or not all(is_mobile_screenshot(a, u) for a, u in imgs_k):
                    break
                run_imgs.extend(imgs_k)
                run_end = k
                j = k + 1
                continue
            imgs_j = parse_image_line(line_j)
            if not imgs_j or not all(is_mobile_screenshot(a, u) for a, u in imgs_j):
                break
            run_imgs.extend(imgs_j)
            run_end = j
            j += 1
        if len(run_imgs) >= 2:
            groups.append(Group(
                file=rel_path,
                start_line=run_start + 1,
                end_line=run_end + 1,
                images=run_imgs,
            ))
        i = max(j, i + 1)
    return groups


def render_flex(images: list[tuple[str, str]]) -> str:
    """按数量决定列宽：2→48% / 3→32% / 4+→32% + flex-wrap。"""
    n = len(images)
    if n == 2:
        width = "48%"
        min_width = "200px"
    else:
        width = "32%"
        min_width = "180px"
    img_lines = []
    for alt, url in images:
        safe_alt = (alt or "").replace('"', '&quot;')
        img_lines.append(
            f'  <img src="{url}" alt="{safe_alt}" '
            f'style={{{{width: \'{width}\', minWidth: \'{min_width}\', '
            f'borderRadius: \'8px\', boxShadow: \'0 2px 12px rgba(0,0,0,0.08)\'}}}} />'
        )
    return (
        "<div style={{display: 'flex', gap: '12px', justifyContent: 'center', "
        "flexWrap: 'wrap', margin: '16px 0'}}>\n"
        + "\n".join(img_lines)
        + "\n</div>"
    )


def apply_groups(text: str, groups: list[Group]) -> str:
    """从后往前替换避开行号漂移。"""
    lines = text.split("\n")
    for g in sorted(groups, key=lambda x: x.start_line, reverse=True):
        replacement = render_flex(g.images)
        lines[g.start_line - 1 : g.end_line] = [replacement]
    return "\n".join(lines)


def discover_files(root: str | None, lang: str) -> list[Path]:
    files: list[Path] = []
    for p in REPO_ROOT.rglob("*.mdx"):
        rel = p.relative_to(REPO_ROOT)
        parts = rel.parts
        if any(part in EXCLUDE_DIRS for part in parts):
            continue
        first = parts[0]
        if lang == "en" and first in ("zh", "ja"):
            continue
        if lang == "zh" and first != "zh":
            continue
        if lang == "ja" and first != "ja":
            continue
        if root:
            if first in ("zh", "ja"):
                if len(parts) < 2 or parts[1] != root:
                    continue
            else:
                if first != root:
                    continue
        files.append(p)
    files.sort()
    return files


def write_report(groups: list[Group], mode: str, applied_files: int) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    by_file: dict[str, int] = {}
    for g in groups:
        by_file[g.file] = by_file.get(g.file, 0) + 1
    by_count: dict[int, int] = {}
    for g in groups:
        n = len(g.images)
        by_count[n] = by_count.get(n, 0) + 1

    md = [
        "# 移动端截图组 flex 包装报告",
        "",
        f"- 模式：**{mode}**",
        f"- 命中组数：{len(groups)}",
        f"- 涉及文件数：{len(by_file)}",
    ]
    if mode == "apply":
        md.append(f"- 已修改文件数：{applied_files}")
    md.append("")
    md.append("## 按张数分布")
    md.append("")
    md.append("| 张数 | 组数 |")
    md.append("|---|---|")
    for n in sorted(by_count.keys()):
        md.append(f"| {n} | {by_count[n]} |")
    md.append("")
    md.append("## 按文件分布")
    md.append("")
    md.append("| 文件 | 组数 |")
    md.append("|---|---|")
    for f, n in sorted(by_file.items()):
        md.append(f"| `{f}` | {n} |")
    md.append("")
    md.append("## 全部组（前 50）")
    md.append("")
    md.append("| 文件 | 起始行 | 结束行 | 张数 |")
    md.append("|---|---|---|---|")
    for g in groups[:50]:
        md.append(f"| `{g.file}` | {g.start_line} | {g.end_line} | {len(g.images)} |")
    if len(groups) > 50:
        md.append(f"\n_共 {len(groups)} 组，余见 JSON_")
    (OUTPUT_DIR / "report.md").write_text("\n".join(md), encoding="utf-8")

    (OUTPUT_DIR / "report.json").write_text(
        json.dumps(
            {
                "mode": mode,
                "total_groups": len(groups),
                "by_file": by_file,
                "by_count": by_count,
                "groups": [
                    {
                        "file": g.file,
                        "start_line": g.start_line,
                        "end_line": g.end_line,
                        "image_count": len(g.images),
                        "images": [{"alt": a, "url": u} for a, u in g.images],
                    }
                    for g in groups
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="批量包装移动端截图组为 flex 容器")
    p.add_argument("--root", default=None, help="限定单产品根（如 drive / ai-minutes）")
    p.add_argument("--lang", default="all", choices=["all", "en", "zh", "ja"])
    p.add_argument("--apply", action="store_true", help="实际写盘（默认 dry-run）")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    files = discover_files(args.root, args.lang)
    mode = "apply" if args.apply else "dry-run"
    print(f"[info] 模式={mode} root={args.root or 'all'} lang={args.lang} 文件数={len(files)}")

    all_groups: list[Group] = []
    applied_files = 0
    for path in files:
        try:
            src = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = str(path.relative_to(REPO_ROOT))
        groups = find_groups(src, rel)
        if not groups:
            continue
        all_groups.extend(groups)
        if args.apply:
            fixed = apply_groups(src, groups)
            if fixed != src:
                path.write_text(fixed, encoding="utf-8")
                applied_files += 1

    write_report(all_groups, mode, applied_files)
    print(f"[done] 命中 {len(all_groups)} 组 / {len({g.file for g in all_groups})} 文件")
    if args.apply:
        print(f"[done] 已修改 {applied_files} 文件")
    print(f"[done] 报告：{OUTPUT_DIR / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
