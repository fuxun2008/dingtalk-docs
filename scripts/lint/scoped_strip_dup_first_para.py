#!/usr/bin/env python3
"""对显式文件清单跑 strip_dup_first_para 的检测/修复逻辑，不触碰清单外的文件。

复用 scripts/lint/strip_dup_first_para.py 的 process()，只是把 --root 目录
通配换成一份显式路径清单。

用法:
    python3 scripts/lint/scoped_strip_dup_first_para.py --files-from <list.txt>            # dry-run
    python3 scripts/lint/scoped_strip_dup_first_para.py --files-from <list.txt> --apply     # 实际写盘
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import strip_dup_first_para as sdfp  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--files-from", required=True, help="每行一个相对仓库根的路径")
    parser.add_argument("--apply", action="store_true", help="实际写盘（默认 dry-run）")
    args = parser.parse_args()

    rel_paths = [l.strip() for l in Path(args.files_from).read_text(encoding="utf-8").splitlines() if l.strip()]
    files = [REPO_ROOT / p for p in rel_paths]
    missing = [p for p in files if not p.is_file()]
    if missing:
        print(f"[error] {len(missing)} 个文件不存在，例如 {missing[0]}", file=sys.stderr)
        return 1

    changed = []
    for mdx in files:
        result = sdfp.process(mdx)
        if result is None:
            continue
        new_text, removed = result
        changed.append((mdx, removed))
        if args.apply:
            mdx.write_text(new_text, encoding="utf-8")

    verb = "已修改" if args.apply else "将修改"
    print(f"扫描 {len(files)} 篇，{verb} {len(changed)} 篇\n")
    for mdx, removed in changed:
        rel = mdx.relative_to(REPO_ROOT)
        snippet = removed[0][:60] if removed else ""
        print(f"  - {rel}    -> 删: {snippet}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
