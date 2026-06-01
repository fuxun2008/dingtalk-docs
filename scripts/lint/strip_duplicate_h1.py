"""
strip_duplicate_h1.py

针对 zh/docs 中 32 个"正文首行重复写 H1"的文件做处理。en/ja 对应文件均无 H1，
说明规范是 frontmatter.title 即唯一页头。

按 H1 内容分类:
  - NOISE  → H1 是工具粘贴的噪音 ([魔法棒挥动] / [举手] / 仅产品名等) → 删除 H1
  - SAME   → H1 与 title 高度等价 → 删除 H1
  - DEMOTE → H1 是有意义的章节标题 → `# ` 降级为 `## `

用法:
  python3 scripts/lint/strip_duplicate_h1.py             # 报告分类
  python3 scripts/lint/strip_duplicate_h1.py --apply     # 应用
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

TARGETS = [
    "zh/docs/dingtalk-docs/flash-plugin.mdx",
    "zh/docs/admin-guide/permission-overview.mdx",
    "zh/docs/admin-guide/permission-restrictions.mdx",
    "zh/docs/knowledge-group/yuque-sheet-mapping.mdx",
    "zh/docs/release-notes/2024-11-12-content-finalize.mdx",
    "zh/docs/release-notes/2024-07-base-button-field.mdx",
    "zh/docs/release-notes/2025-03-kb-automation.mdx",
    "zh/docs/release-notes/2021-08-30-pivot-table.mdx",
    "zh/docs/release-notes/2025-01-ai-dashboard.mdx",
    "zh/docs/release-notes/2024-09-10-ai-digital-human-video.mdx",
    "zh/docs/release-notes/2024-04-base-free-tier.mdx",
    "zh/docs/release-notes/2024-06-ai-ppt-launch.mdx",
    "zh/docs/release-notes/2024-08-base-advanced-permission.mdx",
    "zh/docs/release-notes/2021-01-26-data-portal.mdx",
    "zh/docs/getting-started/intro-docs.mdx",
    "zh/docs/getting-started/intro-ai-table.mdx",
    "zh/docs/knowledge-base/unified-management.mdx",
    "zh/docs/knowledge-base/about.mdx",
    "zh/docs/templates/index.mdx",
    "zh/docs/best-practices/index.mdx",
    "zh/docs/sheets/formulas/lookup-match.mdx",
    "zh/docs/sheets/formulas/dynamic-reference.mdx",
    "zh/docs/dingtalk-docs/collaboration/invite-collaborators.mdx",
    "zh/docs/dingtalk-docs/faq/cannot-copy-download-print.mdx",
    "zh/docs/dingtalk-docs/faq/feature-limits.mdx",
    "zh/docs/dingtalk-docs/shortcuts-input/edit-markdown.mdx",
    "zh/docs/dingtalk-docs/shortcuts-input/import-markdown.mdx",
    "zh/docs/dingtalk-docs/shortcuts-input/markdown-guide.mdx",
    "zh/docs/dingtalk-docs/shortcuts-input/export-markdown.mdx",
    "zh/docs/doc-ai/advanced/prompt-basics.mdx",
    "zh/docs/doc-ai/more-apps/smart-correction.mdx",
    "zh/docs/doc-ai/getting-started/assistant-kb-qa/group-qa-assistant.mdx",
]

NOISE_PATTERNS = [
    r"^\[[^\]]+\]",                       # [魔法棒挥动] / [举手] 等
    r"^[「\"\"]?钉钉(文档|知识库|表格|多维表|AI)?[」\"\"]?$",   # 仅"钉钉文档"等
    r"^文档\s*AI$",
]


def normalize(s: str) -> str:
    s = s.replace("\xa0", " ")
    s = re.sub(r"[\s　]+", "", s)
    s = re.sub(r"[，,。.!?！？:：;；\"\"''「」｜|（）()【】\[\]、/／\\-–—~×&]+", "", s)
    return s.lower()


def classify(title: str, h1: str) -> str:
    h1_clean = h1.replace("\xa0", " ").strip()
    h1_squeezed = re.sub(r'[\s「」""\'\']+', '', h1_clean)
    # 噪音
    for pat in NOISE_PATTERNS:
        if re.match(pat, h1_clean):
            return "NOISE"
    if re.match(r"^钉钉(文档|知识库|表格|多维表|AI)?$", h1_squeezed):
        return "NOISE"
    if normalize(h1) == normalize(title):
        return "SAME"
    # 内容型 → 降级为 H2
    return "DEMOTE"


def process(path: Path, apply: bool) -> str:
    text = path.read_text(encoding="utf-8")
    fm_m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not fm_m:
        return "NO_FM"
    title_m = re.search(r'^title:\s*"?([^"\n]+?)"?\s*$', fm_m.group(1), re.M)
    if not title_m:
        return "NO_TITLE"
    title = title_m.group(1).strip()

    body_start = fm_m.end()
    body = text[body_start:]
    body_lines = body.split("\n")
    idx = 0
    while idx < len(body_lines) and not body_lines[idx].strip():
        idx += 1
    if idx >= len(body_lines) or not body_lines[idx].startswith("# "):
        return "NO_H1"

    h1 = body_lines[idx][2:].strip()
    cls = classify(title, h1)

    if apply:
        if cls in ("NOISE", "SAME"):
            # 删除 H1 行 + 紧跟空行
            del_count = 1
            if idx + 1 < len(body_lines) and not body_lines[idx + 1].strip():
                del_count = 2
            new_body_lines = body_lines[:idx] + body_lines[idx + del_count:]
            new_body = "\n".join(new_body_lines)
            path.write_text(text[:body_start] + new_body, encoding="utf-8")
        elif cls == "DEMOTE":
            body_lines[idx] = "## " + h1
            new_body = "\n".join(body_lines)
            path.write_text(text[:body_start] + new_body, encoding="utf-8")

    return f"{cls}  title={title!r}  h1={h1!r}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    counts = {"NOISE": 0, "SAME": 0, "DEMOTE": 0, "NO_H1": 0, "OTHER": 0}
    for rel in TARGETS:
        p = REPO / rel
        if not p.exists():
            print(f"  MISSING: {rel}")
            counts["OTHER"] += 1
            continue
        r = process(p, args.apply)
        cls = r.split()[0] if r else "OTHER"
        counts[cls] = counts.get(cls, 0) + 1
        print(f"  {r}  ({rel})")
    print()
    mode = "APPLIED" if args.apply else "DRY-RUN"
    print(f"[{mode}]  " + "  ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
