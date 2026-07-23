#!/usr/bin/env python3
"""按 title-mapping.json 批量更新「文档」子产品四语 mdx 的 frontmatter title。

- 仅替换 frontmatter 内第一个 `title:` 行，其余内容不动
- 统一写成 title: "..."（英文双引号包裹）
- 幂等：新旧一致则跳过

用法：python3 scripts/apply_docs_titles.py [--dry-run]
"""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAPPING = ROOT / "scripts" / "output" / "docs-titles" / "title-mapping.json"

LANG_PREFIX = {"en": "", "zh": "zh/", "ja": "ja/", "id": "id/"}
FM_RE = re.compile(r"^---\n(.*?)\n---", re.S)
TITLE_LINE_RE = re.compile(r"^title:.*$", re.M)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    mapping = json.loads(MAPPING.read_text(encoding="utf-8"))
    changed, skipped, errors = 0, 0, []
    for slug, titles in sorted(mapping.items()):
        for lang, new_title in titles.items():
            path = ROOT / f"{LANG_PREFIX[lang]}{slug}.mdx"
            if not path.is_file():
                errors.append(f"缺文件: {path}")
                continue
            src = path.read_text(encoding="utf-8")
            fm = FM_RE.match(src)
            if not fm:
                errors.append(f"无 frontmatter: {path}")
                continue
            block = fm.group(1)
            m = TITLE_LINE_RE.search(block)
            if not m:
                errors.append(f"frontmatter 无 title: {path}")
                continue
            new_line = f'title: "{new_title}"'
            if m.group(0) == new_line:
                skipped += 1
                continue
            new_block = block[:m.start()] + new_line + block[m.end():]
            new_src = src[:fm.start(1)] + new_block + src[fm.end(1):]
            if not args.dry_run:
                path.write_text(new_src, encoding="utf-8")
            changed += 1

    mode = "dry-run" if args.dry_run else "apply"
    print(f"[{mode}] 更新 {changed} / 跳过(已一致) {skipped} / 异常 {len(errors)}")
    for e in errors:
        print("  ", e)


if __name__ == "__main__":
    main()
