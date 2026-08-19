#!/usr/bin/env python3
"""按语言对显式文件清单抽取 frontmatter title，报告撞车分组。

只报告，不自动改——标题消歧义需要读正文内容手写，不是可机械判定的问题。

用法:
    python3 scripts/lint/find_duplicate_titles.py --files-from <list.txt>
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def parse_title(text: str) -> str | None:
    m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
    if not m:
        return None
    fm = m.group(1)
    tm = re.search(r'^title:\s*"?(.*?)"?\s*$', fm, re.MULTILINE)
    return tm.group(1).strip() if tm else None


def lang_of(rel: str) -> str:
    first = rel.split("/", 1)[0]
    return first if first in ("zh", "ja", "id") else "en"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--files-from", required=True)
    args = parser.parse_args()

    rel_paths = [l.strip() for l in Path(args.files_from).read_text(encoding="utf-8").splitlines() if l.strip()]

    by_lang: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for rel in rel_paths:
        path = REPO_ROOT / rel
        title = parse_title(path.read_text(encoding="utf-8"))
        by_lang[lang_of(rel)][title or ""].append(rel)

    total_groups = 0
    for lang in ("en", "zh", "ja", "id"):
        groups = {t: paths for t, paths in by_lang[lang].items() if len(paths) > 1}
        print(f"=== {lang}: {len(groups)} 组撞车 ===")
        for t, paths in groups.items():
            total_groups += 1
            print(f"  '{t}' x{len(paths)}")
            for p in paths:
                print(f"      {p}")
    print(f"\n总撞车组数: {total_groups}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
