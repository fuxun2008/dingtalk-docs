#!/usr/bin/env python3
"""
将 zh/open/ 下所有 mdx 文件中的 `dingtalk.com` 字面值统一替换为 `dingtalk.io`。

约束（来自用户决策）：
- 不区分子域名 / 不挑剔目标 .io 是否真实存在
- 不区分上下文（URL / 邮箱举例 / URL-encoded 全部一并改）
- 仅作用域 zh/open/，不动 docs.json / en/ / ja/ / 其他 product

产出：
  scripts/output/open_platform/nav/rename_dingtalk_io_report.md
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TARGET_DIR = REPO / "zh/open"
OUT_REPORT = REPO / "scripts/output/open_platform/nav/rename_dingtalk_io_report.md"

OLD = "dingtalk.com"
NEW = "dingtalk.io"


def main() -> None:
    total_hits = 0
    changed_files: list[tuple[str, int]] = []  # (relpath, hits)

    for path in sorted(TARGET_DIR.rglob("*.mdx")):
        text = path.read_text()
        hits = text.count(OLD)
        if hits == 0:
            continue
        new_text = text.replace(OLD, NEW)
        path.write_text(new_text)
        total_hits += hits
        changed_files.append((str(path.relative_to(REPO)), hits))

    # 报告
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# 开放平台 mdx `dingtalk.com` → `dingtalk.io` 全量替换报告\n")
    lines.append(f"- 总替换次数：**{total_hits}**")
    lines.append(f"- 涉及文件数：**{len(changed_files)}**")
    lines.append(f"- 作用域：`zh/open/**/*.mdx`")
    lines.append("- 范围说明：不区分子域名 / 不区分上下文，所有 `dingtalk.com` 字面值一律改为 `dingtalk.io`")
    lines.append("- 死链处理：用户已确认死链 OK，等 `*.dingtalk.io` 子域陆续上线后自然恢复\n")
    lines.append("## 文件级替换次数（倒序前 30）\n")
    for rel, hits in sorted(changed_files, key=lambda x: -x[1])[:30]:
        lines.append(f"- {hits:>4}  {rel}")
    if len(changed_files) > 30:
        lines.append(f"- ... 共 {len(changed_files)} 个文件")
    OUT_REPORT.write_text("\n".join(lines) + "\n")

    print(f"OK. 总替换 {total_hits} 处，{len(changed_files)} 个文件改动")
    print(f"报告：{OUT_REPORT}")


if __name__ == "__main__":
    main()
