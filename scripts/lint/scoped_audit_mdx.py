#!/usr/bin/env python3
"""对显式文件清单跑 audit_mdx_quality 的检测/修复逻辑，不触碰清单外的文件。

复用 scripts/audit_mdx_quality.py 的 scan_file()/write_reports()，只是把
discover_files() 的目录通配换成一份显式路径清单——用于只处理某一批新增
文档而不误碰同目录下已经清理过的旧文件。

用法:
    python3 scripts/lint/scoped_audit_mdx.py --files-from <list.txt>            # dry-run
    python3 scripts/lint/scoped_audit_mdx.py --files-from <list.txt> --apply    # 实际写盘
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import audit_mdx_quality as amq  # noqa: E402

REPORT_ONLY = {
    "url_as_label", "card_candidate", "mobile_screenshot_group",
    "dingtalk_mp4_link", "bold_cjk_punct", "caption_candidate",
}

# class A (`++text++`) 的正则不感知围栏代码块：当代码示例里出现字面 `++`
# （如 base64/加密串 `HJ+q6tp1qhl9L1++j74xxxx`），会把两处不相关的 `++`
# 跨越整个文档中段当成一对"下划线"标记，产出巨型误判、apply 会腰斩正文。
# 本批已核实 4 处命中全部是这一个已知假阳性（configure-synchttp-push.mdx
# 四语），故这里跳过 fix_underline，其余 fix 函数原样复用、顺序不变。
SKIP_UNDERLINE_FIX = True


def apply_fixes(rel: str, src: str) -> str:
    fixed = src
    if not SKIP_UNDERLINE_FIX:
        fixed = amq.fix_underline(fixed)
    fixed = amq.fix_nested_bold(fixed)
    fixed = amq.fix_bold_cjk_boundary(fixed)
    fixed = amq.fix_bold_whitespace(fixed)
    fixed = amq.fix_bad_url_placeholder(fixed)
    fixed = amq.fix_empty_note(fixed)
    if amq.is_release_notes(rel):
        fixed = amq.fix_strip_note_tags(fixed)
    if amq.is_release_notes_index(rel):
        fixed = amq.fix_four_space_indent(fixed)
    return fixed


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

    mode = "apply" if args.apply else "dry-run"
    print(f"[info] 模式={mode} 文件数={len(files)} (class A underline fix {'已跳过' if SKIP_UNDERLINE_FIX else '启用'})")

    all_issues = []
    applied = {}
    for path in files:
        issues, _ = amq.scan_file(path)
        all_issues.extend(issues)
        actionable = [i for i in issues if i.pattern not in REPORT_ONLY and not (SKIP_UNDERLINE_FIX and i.pattern == "underline")]
        if args.apply and actionable:
            rel = str(path.relative_to(REPO_ROOT))
            src = path.read_text(encoding="utf-8")
            fixed = apply_fixes(rel, src)
            if fixed != src:
                path.write_text(fixed, encoding="utf-8")
                applied[rel] = len(actionable)

    amq.write_reports(all_issues, applied, len(files), mode)

    print(f"[done] 命中 {len(all_issues)} 处 / {len({i.file for i in all_issues})} 文件")
    if args.apply:
        print(f"[done] 已修改 {len(applied)} 文件")
    print(f"[done] 报告：{amq.OUTPUT_DIR / 'syntax-report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
