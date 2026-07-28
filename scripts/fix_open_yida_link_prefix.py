#!/usr/bin/env python3
"""
open/yida 三语译文链接后处理（阶段 4）：

1. 新译文内链前缀切换（open/yida、ja/open/yida、id/open/yida）：
   - /zh/open/yida/... → /open/yida/...（en）/ /ja/open/yida/...（ja）/ /id/open/yida/...（id）
   - /zh/yida/...、/zh/open/development/...、/zh/open/dingstart/... 同理按语向切换
   - 覆盖 markdown [text](url) 与 JSX href="url" 两种形态；替换前校验目标 mdx 存在
2. 跨页锚点治理：zh 与译文 heading 结构 1:1 镜像，按 heading 序号映射
   slug(zh_heading[i]) → slug(tgt_heading[i])；无法映射的锚点降级为纯页面链接
3. 存量译文遗留链接切换：yida/、ja/yida/、id/yida/ 下指向 /zh/open/yida 的链接

用法：
  python3 scripts/fix_open_yida_link_prefix.py            # 预演
  python3 scripts/fix_open_yida_link_prefix.py --write    # 写入
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

LANG_PREFIX = {"en": "", "ja": "ja/", "id": "id/"}
# (待处理译文目录, 语言)
NEW_DIRS = [("open/yida", "en"), ("ja/open/yida", "ja"), ("id/open/yida", "id")]
LEGACY_DIRS = [("yida", "en"), ("ja/yida", "ja"), ("id/yida", "id")]

# 可切换的 zh 前缀（去掉 /zh/ 后目标 mdx 必须存在于对应语向）
SWITCHABLE = ("/zh/open/yida/", "/zh/yida/", "/zh/open/development/", "/zh/open/dingstart/")

LINK_RE = re.compile(r"(\]\(|href=\")(/zh/[^)\"#\s]+)(#[^)\"\s]*)?([)\"])")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.M)


def slugify(h: str) -> str:
    """近似 github-slugger：去 md 修饰、去标点（保留字母数字/CJK/空格/连字符）、空格→-、小写。"""
    h = re.sub(r"[`*_]", "", h).strip()
    h = re.sub(r"[^\w\u4e00-\u9fff\u3040-\u30ff\- ]", "", h)
    return re.sub(r"\s+", "-", h).lower()


def headings_of(path: Path) -> list[str]:
    try:
        return [slugify(m) for m in HEADING_RE.findall(path.read_text(encoding="utf-8"))]
    except FileNotFoundError:
        return []


def map_anchor(zh_path: Path, tgt_path: Path, anchor: str) -> str | None:
    """zh 锚点 → 译文锚点。返回 None 表示无法映射（应降级去锚）。返回 '' 不可能。"""
    zh_slugs = headings_of(zh_path)
    tgt_slugs = headings_of(tgt_path)
    a = anchor.lstrip("#")
    a_slug = slugify(a)
    # 先在译文中直接命中（英文 heading 未变等场景）
    if a_slug in tgt_slugs or a in tgt_slugs:
        return a_slug if a_slug in tgt_slugs else a
    # 序号镜像映射（heading 数量一致时才可靠）
    if len(zh_slugs) == len(tgt_slugs):
        for i, zs in enumerate(zh_slugs):
            if zs == a_slug or zs == a:
                return tgt_slugs[i]
    return None


def process_file(path: Path, lang: str, write: bool, stats: dict) -> None:
    text = path.read_text(encoding="utf-8")
    changed = False

    def repl(m: re.Match) -> str:
        nonlocal changed
        head, url, anchor, tail = m.group(1), m.group(2), m.group(3) or "", m.group(4)
        if not any(url.startswith(p) or (url + "/") == p or (url + "/").startswith(p) for p in SWITCHABLE):
            stats.setdefault("skip_other_zh", []).append(f"{path}: {url}")
            return m.group(0)
        rest = url[len("/zh/"):]  # open/yida/... 或 yida/...
        new_rel = LANG_PREFIX[lang] + rest
        tgt = REPO_ROOT / (new_rel + ".mdx")
        if not tgt.exists():
            stats.setdefault("missing_target", []).append(f"{path}: {url}")
            return m.group(0)
        new_anchor = ""
        if anchor and anchor != "#":
            zh_src = REPO_ROOT / ("zh/" + rest + ".mdx")
            mapped = map_anchor(zh_src, tgt, anchor)
            if mapped is None:
                stats.setdefault("anchor_dropped", []).append(f"{path}: {url}{anchor}")
            else:
                new_anchor = "#" + mapped
                if new_anchor != anchor:
                    stats.setdefault("anchor_mapped", []).append(f"{path}: {anchor} -> {new_anchor}")
        changed = True
        stats["links"] = stats.get("links", 0) + 1
        return f"{head}/{new_rel}{new_anchor}{tail}"

    new_text = LINK_RE.sub(repl, text)
    if changed and write:
        path.write_text(new_text, encoding="utf-8")
    if changed:
        stats["files"] = stats.get("files", 0) + 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--legacy-only", action="store_true", help="只处理存量 yida/ 遗留链接")
    ap.add_argument("--new-only", action="store_true", help="只处理新译文 open/yida")
    args = ap.parse_args()

    dirs = []
    if not args.legacy_only:
        dirs += NEW_DIRS
    if not args.new_only:
        dirs += LEGACY_DIRS

    grand = {}
    for rel_dir, lang in dirs:
        base = REPO_ROOT / rel_dir
        if not base.exists():
            print(f"[skip] {rel_dir} 不存在")
            continue
        stats: dict = {}
        for mdx in sorted(base.rglob("*.mdx")):
            process_file(mdx, lang, args.write, stats)
        print(f"[{rel_dir}] 改链接 {stats.get('links', 0)} 处 / {stats.get('files', 0)} 文件"
              f"  锚点映射 {len(stats.get('anchor_mapped', []))}  去锚 {len(stats.get('anchor_dropped', []))}"
              f"  目标缺失保留 {len(stats.get('missing_target', []))}")
        for k in ("missing_target", "anchor_dropped", "anchor_mapped", "skip_other_zh"):
            for line in stats.get(k, [])[:15]:
                print(f"    [{k}] {line}")
        for k, v in stats.items():
            if isinstance(v, list):
                grand.setdefault(k, []).extend(v)
            else:
                grand[k] = grand.get(k, 0) + v

    print(f"\n[total] 链接 {grand.get('links', 0)} / 文件 {grand.get('files', 0)}"
          f" / 目标缺失 {len(grand.get('missing_target', []))} / 去锚 {len(grand.get('anchor_dropped', []))}")
    if not args.write:
        print("[dry-run] 未写入。加 --write 生效")
    return 0


if __name__ == "__main__":
    sys.exit(main())
