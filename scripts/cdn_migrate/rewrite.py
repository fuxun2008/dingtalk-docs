"""阶段 5：按 url-map.json 改写全仓 mdx 的图引用（md / <img> / <Frame>）。

逐条精确替换：只替换匹配到的 URL token 本身，其余字节不动；跳过代码围栏。
默认 dry-run 写 staging/ + migrate-report.md；--apply 直接覆盖 live 文件。

用法：
    python scripts/cdn_migrate/rewrite.py            # dry-run → staging
    python scripts/cdn_migrate/rewrite.py --apply    # 覆盖 live
"""
from __future__ import annotations

import argparse
from collections import Counter

import common as C


def _splice(m, url_group: int, mapping: dict[str, str]) -> tuple[str, str | None]:
    """把 match 内 url_group 处的 URL 换成映射值；返回 (新串, 命中的 old|None)。"""
    url = m.group(url_group)
    new = mapping.get(url)
    if not new:
        return m.group(0), None
    s = m.group(0)
    a = m.start(url_group) - m.start(0)
    b = m.end(url_group) - m.start(0)
    return s[:a] + new + s[b:], url


def rewrite_text(text: str, mapping: dict[str, str], hits: Counter) -> tuple[str, int]:
    out: list[str] = []
    n = 0
    for is_code, chunk in C.split_code_blocks(text):
        if is_code:
            out.append(chunk)
            continue
        for regex in (C.MD_IMAGE_RE, C.IMG_SRC_RE, C.FRAME_SRC_RE):
            def repl(m):
                nonlocal n
                new_s, old = _splice(m, 2, mapping)
                if old is not None:
                    n += 1
                    hits[old] += 1
                return new_s
            chunk = regex.sub(repl, chunk)
        out.append(chunk)
    return "".join(out), n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="覆盖 live 文件（默认 dry-run 写 staging）")
    args = ap.parse_args()

    url_map = C.load_json(C.OUT_DIR / "url-map.json", {})
    mapping = {m["old"]: m["new"] for m in url_map.get("items", [])}
    if not mapping:
        print("[rewrite] url-map.json 无条目，先跑 buildmap。")
        return

    hits: Counter = Counter()
    changed_files = 0
    total_changes = 0
    report_lines = ["# 图片转存 CDN — 改写报告\n", f"映射条目：{len(mapping)}\n"]

    for path in C.iter_mdx_files():
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        new_text, n = rewrite_text(text, mapping, hits)
        if n == 0 or new_text == text:
            continue
        changed_files += 1
        total_changes += n
        rel = path.relative_to(C.REPO_ROOT)
        report_lines.append(f"- {rel}：{n} 处")
        if args.apply:
            path.write_text(new_text, encoding="utf-8")
        else:
            dest = C.STAGING_DIR / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(new_text, encoding="utf-8")

    unused = [old for old in mapping if hits[old] == 0]
    report_lines.append(f"\n改写文件 {changed_files}，替换 {total_changes} 处；未命中映射 {len(unused)} 条。\n")
    if unused:
        report_lines.append("## 未命中映射（前 30）\n")
        report_lines += [f"- {u}" for u in unused[:30]]
    (C.OUT_DIR / "migrate-report.md").write_text("\n".join(report_lines), encoding="utf-8")

    mode = "APPLY(覆盖 live)" if args.apply else "DRY-RUN(写 staging)"
    print(f"[rewrite] {mode}：改写 {changed_files} 文件 / {total_changes} 处，未命中 {len(unused)} 条")
    print(f"[rewrite] 报告 → migrate-report.md" + ("" if args.apply else f"，staging → {C.STAGING_DIR.relative_to(C.REPO_ROOT)}"))


if __name__ == "__main__":
    main()
