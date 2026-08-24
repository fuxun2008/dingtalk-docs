"""阶段 6：把 staging/ 下改写好的 mdx 覆盖到 live（在人工过完 migrate-report.md 之后）。

用法：
    python scripts/cdn_migrate/apply.py [--yes]
"""
from __future__ import annotations

import argparse
import shutil

import common as C


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="跳过确认")
    args = ap.parse_args()

    if not C.STAGING_DIR.exists():
        print("[apply] 无 staging，先跑 rewrite（dry-run）。")
        return
    staged = sorted(C.STAGING_DIR.rglob("*.mdx"))
    if not staged:
        print("[apply] staging 为空。")
        return

    print(f"[apply] 将用 staging 覆盖 {len(staged)} 个 live mdx。")
    if not args.yes:
        ans = input("确认覆盖？(yes/no) ").strip().lower()
        if ans not in ("y", "yes"):
            print("[apply] 已取消。")
            return

    for sp in staged:
        rel = sp.relative_to(C.STAGING_DIR)
        dest = C.REPO_ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sp, dest)
    print(f"[apply] 已覆盖 {len(staged)} 个文件。建议随后跑 verify + mint broken-links。")


if __name__ == "__main__":
    main()
