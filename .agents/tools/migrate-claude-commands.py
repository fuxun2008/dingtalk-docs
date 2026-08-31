#!/usr/bin/env python3
"""把 .claude/commands/ 下的仓库专属命令迁移为 Qoder 技能（.agents/skills/<name>/SKILL.md）。

设计要点：
- 正文原样保留（这些命令里写死了大量历史踩坑，不能改写语义）
- 只做「平台工具名」适配：Claude 的 Edit 工具 → Qoder 的 SearchReplace 工具
  这一步是功能性的：Qoder 没有 Edit 工具，若不改写，代理可能退化成用 Write
  整份覆盖 docs.json —— 正是这批技能反复警告的灾难性操作
- 补齐 Qoder 技能必需的 frontmatter（name / description），否则技能无法被触发
- 幂等：可重复执行，覆盖生成结果

用法：
    python3 .agents/tools/migrate-claude-commands.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / ".claude" / "commands"
DST = REPO / ".agents" / "skills"

# name -> (description_en, description_zh, argument_hint)
METADATA: dict[str, tuple[str, str, str]] = {
    "docs-dingtalk-onboard": (
        "Nine-stage orchestration pipeline that turns a raw DingTalk zh MDX export into a "
        "push-ready, mint-renderable, trilingual (en/zh/ja) help-center sub-product. Use when "
        "onboarding a new DingTalk sub-product, re-importing a product wholesale, or refreshing "
        "a single group.",
        "钉钉文档子产品导入流水线（9 阶段编排）：把钉钉原始 zh mdx 导出树做成可 push、可渲染、可三语切换的最终态。",
        "<slug> [--only <group>] [--from-stage N]",
    ),
    "docs-import-archive": (
        "Stage 0 data acquisition: download all MDX of one DingTalk help-center product into a "
        "local archive using the 5-script downloader (build_manifest, auth_bootstrap, "
        "discover_endpoint, download, verify). Use before docs-dingtalk-onboard stage 1.",
        "阶段 0 钉钉文档归档自动下载：5 个脚本串起来，拿到一个产品的全部原始 mdx，供 import_archive.py 消费。",
        "<product> [--force-redownload]",
    ),
    "docs-import-hub-en": (
        "EN-direct import route: import a DingTalk English hub into the help center in one pass "
        "(hub crawl, download, template-mirrored import, register the en tab) and skip translation. "
        "Use when the English master already exists upstream.",
        "EN-direct 导入路线 — 钉钉文档英文 hub 一键导入帮助中心子产品（hub crawl → download → 仿模板 import → 注册 en tab，跳过翻译）。",
        "<hub-url> <slug>",
    ),
    "docs-add-page": (
        "Create one new doc page mirrored across en/zh/ja and append it to all three docs.json "
        "navigation blocks, then verify links. Use when adding a single page to an existing "
        "product tab and group.",
        "三语镜像建页 + docs.json 三处 navigation 同步：建 3 个 mdx、追加三语 pages[]、跑死链。",
        "<product>/<group>/<slug> [--title-en ...]",
    ),
    "docs-nav-edit": (
        "Atomic, SearchReplace-only safe editor for the strictly order-synced trilingual docs.json "
        "navigation. Operations: add-product, add-group, add-page, reorder, verify. Use for any "
        "navigation structure change; never overwrite docs.json wholesale.",
        "docs.json 三语 navigation 安全编辑器：add-product / add-group / add-page / reorder / verify 原子操作，强制精确替换，禁止整份覆盖。",
        "<add-product|add-group|add-page|reorder|verify> [args]",
    ),
    "docs-reorder-by-official-menu": (
        "Reorder the pages array of one or more docs.json groups to match the official alidocs "
        "left-side menu order, synced across languages. Handles deeply nested groups and flat "
        "leaf pages.",
        "按官方左侧菜单重排 docs.json 顺序：指定 group 的 pages 数组按 alidocs 官方菜单顺序重排，三语同步。",
        "<group-title> [<group-title> ...]",
    ),
    "docs-translate": (
        "Translate a single English master MDX into zh and ja with the project glossary injected "
        "as hard terminology constraints. Use for one-off page translation or re-reviewing an "
        "existing translation against the latest glossary.",
        "单篇文档翻译（带词库强约束）：把一篇英文 mdx 母版翻成中文 / 日文，自动注入项目词库作为术语强约束。",
        "<path/to/file.mdx> [--force]",
    ),
    "docs-translate-batch": (
        "Batch-translate a whole zh/<root>/ product directory into English and Japanese with "
        "glossary constraints, image/video stripping, link-prefix correction and dead-link "
        "verification. Supports resume and force retranslation.",
        "产品目录级批量翻译（zh → en + ja）：整个产品目录批量翻译，含词库约束、图视频剥离、链接前缀修正、死链验证。",
        "<root> [--force] [--limit N]",
    ),
    "docs-translate-polish": (
        "Polish existing en/ja translations for language quality only — terminology consistency, "
        "sentence length, active voice, punctuation, list parallelism, tense — while keeping "
        "semantics, links, components and frontmatter unchanged.",
        "翻译润色（en / ja 已译文件二次打磨）：只改语言质量（术语一致性 / 句长 / 主动语态 / 标点），绝不改动语义。",
        "<root> [--lang en|ja] [--limit N]",
    ),
    "docs-glossary-sync": (
        "Merge the official zh-en-ja glossary CSV exports maintained by the language team into "
        "scripts/glossary/zh-en.json and zh-ja.json consumed by the translation pipeline, and "
        "report the merge diff and conflicts.",
        "翻译词库同步：把官方「中文-英文-日文」词库 csv 合并进项目，生成 scripts/glossary/zh-en.json 与 zh-ja.json。",
        "[--dry-run] [--source <csv-path>]",
    ),
    "docs-audit-mdx": (
        "Audit MDX quality (broken bold, ++text++ residue, syntax defects) and probe DingTalk "
        "external dead links in one pass, producing a report or applying fixes. Use before "
        "committing a translation batch or as a periodic health check.",
        "MDX 质量审计 + 外链死链清理：串起 audit_mdx_quality.py 与 check_external_links.py，一次性出报告或落盘修复。",
        "[--root <name>] [--apply]",
    ),
    "docs-open-platform-cleanup": (
        "Batch-clean the 8 classes of residual defects specific to DingTalk Open Platform API "
        "docs (API reference, SDK, overview, FAQ) after import into zh/open/. Complements "
        "docs-audit-mdx, which covers generic MDX rendering defects.",
        "开放平台开发者文档批量清洗：专治钉钉开放平台 API 文档形态的 8 类残留瑕疵（zh/open/ 416 篇已验证）。",
        "[--root zh/open] [--apply]",
    ),
    "docs-prune-orphan-images": (
        "Scan local image assets and physically delete images no longer referenced by any MDX "
        "file. Use after deleting MDX sections, after trimming one language mirror, or to slim "
        "the repository.",
        "文档孤儿图清理：找出不再被任何 mdx 引用的本地图片并物理删除。",
        "[<scope>] [--dry-run]",
    ),
    "docs-preview": (
        "Local visual smoke test: start mint dev, run mint broken-links to catch newly introduced "
        "dead links, and screenshot the three language homepages. Use after a batch translation, "
        "a bulk cleanup, or a docs.json navigation change.",
        "本地预览 + 死链验证 + 三语首页截图：mint dev 起服务、mint broken-links 查死链、三语首页视觉冒烟。",
        "[--port 3333] [--pages <path>]",
    ),
    "security-scan-docs": (
        "Privacy and security scan tailored to the MDX docs site: corpId, real phone numbers and "
        "emails, tokens, internal domains, QR codes and employee IDs. Use before a new product "
        "lands, as a monthly health check, or as a pre-push gate. Distinct from the generic "
        "TS/JS security-scan.",
        "文档站隐私安全扫描：扫 corpId / 真手机号 / 内网域名 / token / 二维码是否漏出（区别于通用 TS/JS 的 security-scan）。",
        "[--root <name>]",
    ),
    "docs-release": (
        "Release flow for this docs repo: merge the feature branch into main and push both "
        "branches to both remotes (GitHub + Alibaba internal GitLab). Pushing main to GitHub "
        "triggers the Mintlify production build of help.dingtalk.io. Requires explicit user "
        "authorization before pushing.",
        "发布流程 — 把 feat/docs 合并进 main 并双推 github + gitlab（推 main 到 github 会触发 Mintlify 线上发布）。",
        "[source-branch] [target-branch]",
    ),
    "commit-flow": (
        "Commit flow for this docs repo: resolve the aoneId, check git status, run lint, generate "
        "a conventional commit message with the `to #<aone-id>` suffix, and commit. Never pushes "
        "automatically — this repo has two remotes and push is fully user-driven.",
        "提交流程（本仓库版）— 解析 aoneId → lint 检查 → 生成带 to #<aone-id> 的 commit message → 提交；绝不自动 push。",
        "[commit description]",
    ),
}

# 平台工具名适配：Claude 的 Edit → Qoder 的 SearchReplace。
# 用词边界 + 大小写敏感，避免误伤 "Editor" / 文件名里的小写 "edit"。
TOOL_RENAMES: list[tuple[str, str]] = [
    (r"\bEdit\b", "SearchReplace"),
]

# 逐条精确改写的平台专属引用（Claude 私有路径 → Qoder 等价机制）
REFERENCE_REWRITES: list[tuple[str, str]] = [
    (
        "读 user memory：`~/.claude/projects/<slug>/memory/user_aone_id.md` 是否存在；若存在，取里面的 ID 作为兜底默认",
        "查 Qoder 记忆（SearchMemory，关键词 `aoneId`）里是否存过本项目的 aoneId；若有，取它作为兜底默认",
    ),
    (
        "按 `~/.claude/rules/typescript-coding-style.md` 的 prompt caching 约定缓存系统 prompt",
        "系统 prompt 走 prompt caching 复用，避免每篇重复计费",
    ),
]

FRONTMATTER_RE = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)


def strip_claude_frontmatter(text: str) -> str:
    """仅当文件真的以 frontmatter 开头时剥离；正文里的 MDX frontmatter 示例不受影响。"""
    if not text.startswith("---"):
        return text
    return FRONTMATTER_RE.sub("", text, count=1)


def adapt_body(text: str) -> tuple[str, int]:
    changes = 0
    for pattern, repl in TOOL_RENAMES:
        text, n = re.subn(pattern, repl, text)
        changes += n
    for old, new in REFERENCE_REWRITES:
        if old in text:
            text = text.replace(old, new)
            changes += 1
    return text, changes


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_skill(name: str, body: str) -> str:
    desc_en, desc_zh, arg_hint = METADATA[name]
    lines = [
        "---",
        f"name: {name}",
        "version: 1.0.0",
        f"description: {yaml_quote(desc_en)}",
        f"description_zh: {yaml_quote(desc_zh)}",
        "user-invocable: true",
    ]
    if arg_hint:
        lines.append(f"argument-hint: {yaml_quote(arg_hint)}")
    lines += ["---", ""]
    return "\n".join(lines) + body.lstrip("\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not SRC.is_dir():
        print(f"source not found: {SRC}", file=sys.stderr)
        return 1

    missing = [n for n in METADATA if not (SRC / f"{n}.md").is_file()]
    if missing:
        print(f"missing source commands: {missing}", file=sys.stderr)
        return 1

    total_adapt = 0
    for name in sorted(METADATA):
        raw = (SRC / f"{name}.md").read_text(encoding="utf-8")
        body = strip_claude_frontmatter(raw)
        body, n = adapt_body(body)
        total_adapt += n
        out = build_skill(name, body)

        target = DST / name / "SKILL.md"
        if args.dry_run:
            print(f"[dry-run] {target.relative_to(REPO)}  ({len(out)} bytes, {n} adaptations)")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(out, encoding="utf-8")
        print(f"wrote {target.relative_to(REPO)}  ({len(out)} bytes, {n} adaptations)")

    print(f"\n{len(METADATA)} skills, {total_adapt} platform adaptations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
