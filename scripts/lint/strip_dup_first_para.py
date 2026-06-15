#!/usr/bin/env python3
"""删除 mdx 中与 frontmatter description 重复的正文首段。

钉钉文档导出器对部分页签把"描述段落"既塞进 frontmatter.description（mintlify
用作 SEO meta + 标题下副标题）又原样保留在正文首段，导致页面顶部「标题 →
副标题 → 首段」连读两遍同一句话。

归一化处理 `_` ↔ `\\_` 转义差异（如 frontmatter `jsapi\\ticket` vs 正文
`jsapi_ticket`）后比较。命中即删除正文里的重复段（保留 frontmatter）。

用法:
    python3 scripts/lint/strip_dup_first_para.py --root zh/open            # dry-run
    python3 scripts/lint/strip_dup_first_para.py --root zh/open --apply    # 实际写盘
"""
import argparse
import re
import sys
from pathlib import Path


def normalize(s: str) -> str:
    """归一化：去 _/\\_/反斜杠/markdown 强调符号/空白，便于跨转义与样式差异比较。"""
    s = s.strip()
    s = s.replace("\\_", "")
    s = s.replace("_", "")
    s = s.replace("\\\\", "")
    s = s.replace("\\", "")
    s = re.sub(r"[*`~]", "", s)
    s = re.sub(r"\s+", "", s)
    return s


def parse_description(fm_text: str):
    m = re.search(r'^description:\s*"((?:[^"\\]|\\.)*)"\s*$', fm_text, re.MULTILINE)
    if m:
        return m.group(1)
    m = re.search(r'^description:\s*(.+)$', fm_text, re.MULTILINE)
    if m:
        return m.group(1).strip()
    return None


def process(path: Path):
    """返回 (new_text, removed_lines) 或 None（未命中）。"""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    fm_end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            fm_end = i
            break
    if fm_end is None:
        return None
    fm_text = "\n".join(lines[1:fm_end])
    desc = parse_description(fm_text)
    if not desc:
        return None
    n_desc = normalize(desc)
    if not n_desc:
        return None

    i = fm_end + 1
    while i < len(lines):
        s = lines[i].strip()
        if s == "" or s.startswith("import ") or s.startswith("#"):
            i += 1
            continue
        break
    if i >= len(lines):
        return None
    para_start = i
    para_end = i
    while para_end < len(lines):
        s = lines[para_end].strip()
        if s == "" or s.startswith("#"):
            break
        para_end += 1
    para_text = " ".join(ln.strip() for ln in lines[para_start:para_end])
    n_para = normalize(para_text)
    # 完全相等 或 description 是 body 段落的前缀（description 被截断到 160 chars 时 import 端的常见形态）
    if n_para != n_desc and not n_para.startswith(n_desc):
        return None

    delete_to = para_end
    if delete_to < len(lines) and lines[delete_to].strip() == "":
        delete_to += 1
    # 顺手清掉紧跟的 `---` 水平线 + 其后空行
    # 钉钉文档导出常在描述段后插一条 hr 分隔；删段后裸露的 hr 紧贴 frontmatter 关闭定界符，
    # mintlify 会误判为第二段 frontmatter 起始 → 500 错
    if delete_to < len(lines) and lines[delete_to].strip() == "---":
        delete_to += 1
        if delete_to < len(lines) and lines[delete_to].strip() == "":
            delete_to += 1
    new_lines = lines[:para_start] + lines[delete_to:]
    return "\n".join(new_lines), lines[para_start:para_end]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True, help="扫描根目录（如 zh/open）")
    parser.add_argument("--apply", action="store_true", help="实际写盘（默认 dry-run）")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"目录不存在: {root}", file=sys.stderr)
        sys.exit(1)

    changed = []
    total = 0
    for mdx in sorted(root.rglob("*.mdx")):
        total += 1
        result = process(mdx)
        if result is None:
            continue
        new_text, removed = result
        changed.append((mdx, removed))
        if args.apply:
            mdx.write_text(new_text, encoding="utf-8")

    verb = "已修改" if args.apply else "将修改"
    print(f"扫描 {total} 篇，{verb} {len(changed)} 篇\n")
    for mdx, removed in changed:
        try:
            rel = mdx.relative_to(Path.cwd())
        except ValueError:
            rel = mdx
        snippet = removed[0][:60] if removed else ""
        print(f"  - {rel}    -> 删: {snippet}")


if __name__ == "__main__":
    main()
