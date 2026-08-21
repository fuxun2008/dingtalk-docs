#!/usr/bin/env python3
"""文档站隐私安全扫描 — mdx / json / scripts/*.py 多类敏感数据检测。

13 类 detector（CRITICAL / HIGH / MEDIUM / LOW），上下文白名单过滤，产报告。

CLI:
  python3 scripts/security_scan_docs.py                   # 全仓 dry-run
  python3 scripts/security_scan_docs.py --root open       # 单产品
  python3 scripts/security_scan_docs.py --lang en         # 单语言
  python3 scripts/security_scan_docs.py --severity HIGH   # 只看 HIGH+
  python3 scripts/security_scan_docs.py --no-py           # 跳过 py

退码:
  0 — 0 命中（或全在白名单）
  1 — HIGH 命中
  2 — CRITICAL 命中
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "security_scan"
WHITELIST_PATH = REPO_ROOT / "scripts" / "security_scan_docs_whitelist.yaml"

EXCLUDE_DIRS = {
    ".git", "node_modules", ".next", ".mintlify",
    ".claude/import",  # 钉钉下载器敏感产物（gitignore 已覆盖，提前排）
    "scripts/output",  # 自己的产物，避免自扫
    "scripts/__pycache__",
    ".qoder",  # gitignore 覆盖：repowiki 元数据 hash 子串被误报手机号，不部署
    "scripts/pdf_export",  # gitignore 覆盖：venv 第三方库 idna 十六进制码点误报，不部署
    "scripts/import_yida/output",  # gitignore 覆盖：宜搭导入中间产物 json，不部署
}

SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


# ---------------------------------------------------------------------------
# Detector 定义
# ---------------------------------------------------------------------------

@dataclass
class Detector:
    name: str
    severity: str
    pattern: re.Pattern
    description: str
    # 命中后看周边 ±60 字符上下文是否含这些 pattern，含则跳过（false positive）
    context_skip: list[re.Pattern] = field(default_factory=list)


def _re(p: str, flags: int = 0) -> re.Pattern:
    return re.compile(p, flags)


DETECTORS: list[Detector] = [
    # ============ CRITICAL ============
    Detector(
        name="api_key_prefix",
        severity="CRITICAL",
        pattern=_re(r"\b(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[A-Za-z0-9_-]{35}|xoxb-[0-9]{10,}-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|gho_[A-Za-z0-9]{30,}|glpat-[A-Za-z0-9_-]{20,})\b"),
        description="API key/token 已知前缀（OpenAI/AWS/Google/Slack/GitHub/GitLab）",
    ),
    Detector(
        name="jwt",
        severity="CRITICAL",
        pattern=_re(r"\beyJ[A-Za-z0-9_-]{15,}\.eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}\b"),
        description="三段式 JWT token",
    ),
    Detector(
        name="db_conn_string",
        severity="CRITICAL",
        pattern=_re(r"\b(mysql|postgres|postgresql|mongodb|redis)://[^@\s]+:[^@\s]+@\S+"),
        description="含密码的数据库连接串",
    ),
    Detector(
        name="private_key_block",
        severity="CRITICAL",
        pattern=_re(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"),
        description="PEM 格式私钥起始标记",
    ),

    # ============ HIGH ============
    Detector(
        name="dingtalk_corpid",
        severity="HIGH",
        # ding 开头 + 16-32 位 hex（小写）
        pattern=_re(r"\bding[a-f0-9]{16,32}\b"),
        description="钉钉企业 corpId（疑似真实企业 ID）",
        context_skip=[
            _re(r"dingxxxxxxxxxxxxx"),       # 全 x 占位
            _re(r"ding[a-f0-9]*x{3,}"),       # 含连续 x 的占位
            _re(r"YOUR_CORP_ID|your_corp_id|<corpid>"),
        ],
    ),
    Detector(
        name="dingtalk_access_token",
        severity="HIGH",
        # x-acs-dingtalk-access-token: <20+ alnum/=/+/>
        pattern=_re(r"(?i)x-acs-dingtalk-access-token[:\s]+[A-Za-z0-9+/=]{20,}"),
        description="钉钉 access_token 头部赋值（疑似真实 token）",
        context_skip=[
            # 含 placeholder 关键词：xxx 占位 / example / YOUR_/your_ / asdasd 等
            _re(r"(?i)x{3,}|example|your[_-]?token|<token>|YOUR_TOKEN|asdasd|String|qkops"),
        ],
    ),
    Detector(
        name="chinese_phone",
        severity="HIGH",
        # 中国大陆 11 位手机号（1[3-9]xxxx）
        pattern=_re(r"(?<![\d-])1[3-9]\d{9}(?![\d-])"),
        description="11 位中国大陆手机号（白名单过滤测试号）",
        context_skip=[
            _re(r"x{3,}"),  # 上下文含 xxx 占位说明
            # URL query 里的长数字 ID 误报（postId / articleCode / goodsId / spm 等）
            _re(r"(?i)(postId|articleCode|goodsId|productId|spm[=]?)[%=]"),
            # 阿里云 OSS / CDN URL 里的哈希文件名常含 11 位数字段
            _re(r"(?i)(aliyuncs|alicdn|alidocs\.oss|x-oss-process)"),
        ],
    ),
    Detector(
        name="id_card_china",
        severity="HIGH",
        # 中国身份证：6 位行政区码 + YYYYMMDD + 3 位序号 + 1 位校验
        pattern=_re(r"\b[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[0-9Xx]\b"),
        description="18 位中国身份证号",
    ),
    Detector(
        name="bank_card_unionpay",
        severity="HIGH",
        # 银联卡 BIN 62 开头，16-19 位
        pattern=_re(r"\b62\d{14,17}\b"),
        description="银联卡号（62 开头 16-19 位）",
        context_skip=[
            _re(r"alidocs\.oss|alicdn|aliyuncs|spm=|article|product"),  # 阿里云 OSS / CDN URL 里的数字串
        ],
    ),
    Detector(
        name="email_internal",
        severity="HIGH",
        pattern=_re(r"\b[\w.+-]+@(?:alibaba-inc|alibaba|alipay-inc|antgroup)\.com\b"),
        description="阿里系内部员工邮箱",
    ),

    # ============ MEDIUM ============
    Detector(
        name="internal_domain",
        severity="MEDIUM",
        pattern=_re(r"\b[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.(?:alibaba-inc\.com|aone\.alibaba|alipay-inc\.com|antgroup\.com|alibaba\.net)\b"),
        description="阿里内网域名（应改对外域名或脱敏）",
    ),
    Detector(
        name="internal_system_url",
        severity="MEDIUM",
        # aone / yida / teambition / atomic / ... 子域形态
        pattern=_re(r"\b(?:aone|teambition|atomic|alimei|gitlab\.alibaba|code\.alibaba)\.[a-z0-9.-]+\.(?:com|net|org)\b"),
        description="阿里内部系统 URL",
    ),

    # ============ LOW ============
    Detector(
        name="private_ipv4",
        severity="LOW",
        pattern=_re(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"),
        description="RFC1918 私有 IP",
        context_skip=[_re(r"192\.168\.1\.1|10\.0\.0\.1")],  # 路由器示例
    ),
]


# ---------------------------------------------------------------------------
# Finding 数据
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    detector: str
    severity: str
    file: str       # 相对 REPO_ROOT
    line: int
    match: str      # 命中的具体串
    context: str    # ±40 字符上下文
    whitelisted: bool = False
    whitelist_reason: str = ""


# ---------------------------------------------------------------------------
# 白名单
# ---------------------------------------------------------------------------

def load_whitelist() -> dict:
    """白名单格式 (YAML)：

    chinese_phone:
      - "13800138000"
    dingtalk_corpid:
      - "dingxxxxxxxxxxxx"
    """
    if not WHITELIST_PATH.exists():
        return {}
    try:
        with WHITELIST_PATH.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {k: set(v or []) for k, v in data.items()}
    except Exception as e:
        print(f"[warn] 白名单加载失败 {WHITELIST_PATH}: {e}", file=sys.stderr)
        return {}


def is_whitelisted(detector_name: str, match_text: str, whitelist: dict) -> tuple[bool, str]:
    """精确匹配白名单值。"""
    if detector_name not in whitelist:
        return False, ""
    if match_text in whitelist[detector_name]:
        return True, "exact match in whitelist"
    return False, ""


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------

def is_excluded(path: Path) -> bool:
    rel = path.relative_to(REPO_ROOT).as_posix()
    for ex in EXCLUDE_DIRS:
        if rel.startswith(ex + "/") or rel == ex:
            return True
        if "/" + ex + "/" in "/" + rel:
            return True
    return False


def context_snippet(line_text: str, start: int, end: int, radius: int = 40) -> str:
    """命中位置 ±radius 上下文，单行。"""
    s = max(0, start - radius)
    e = min(len(line_text), end + radius)
    snippet = line_text[s:e].replace("\t", " ").replace("\n", "")
    if s > 0:
        snippet = "..." + snippet
    if e < len(line_text):
        snippet = snippet + "..."
    return snippet


def scan_file(path: Path, detectors: list[Detector], whitelist: dict) -> list[Finding]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"[warn] 读不了 {path}: {e}", file=sys.stderr)
        return []

    findings: list[Finding] = []
    rel = path.relative_to(REPO_ROOT).as_posix()
    lines = text.splitlines()

    for line_no, line in enumerate(lines, 1):
        for d in detectors:
            for m in d.pattern.finditer(line):
                matched = m.group(0)
                ctx = context_snippet(line, m.start(), m.end())
                # context_skip：命中条件，则跳
                skip = False
                for skip_re in d.context_skip:
                    if skip_re.search(ctx):
                        skip = True
                        break
                if skip:
                    continue
                wl, reason = is_whitelisted(d.name, matched, whitelist)
                findings.append(Finding(
                    detector=d.name,
                    severity=d.severity,
                    file=rel,
                    line=line_no,
                    match=matched,
                    context=ctx,
                    whitelisted=wl,
                    whitelist_reason=reason,
                ))
    return findings


def discover_files(root: str | None, lang: str, include_py: bool) -> list[Path]:
    """扫范围：mdx + json + scripts/*.py。"""
    files: list[Path] = []
    for p in REPO_ROOT.rglob("*.mdx"):
        if is_excluded(p):
            continue
        # --root 过滤
        if root:
            top = p.relative_to(REPO_ROOT).parts[0]
            top_after_lang = p.relative_to(REPO_ROOT).parts[1] if top in ("zh", "ja") and len(p.relative_to(REPO_ROOT).parts) > 1 else top
            if top != root and top_after_lang != root:
                continue
        # --lang 过滤
        if lang != "all":
            top = p.relative_to(REPO_ROOT).parts[0]
            if lang == "en" and top in ("zh", "ja"):
                continue
            if lang in ("zh", "ja") and top != lang:
                continue
        files.append(p)

    for p in REPO_ROOT.rglob("*.json"):
        if is_excluded(p):
            continue
        files.append(p)

    if include_py:
        for p in (REPO_ROOT / "scripts").rglob("*.py"):
            if is_excluded(p):
                continue
            files.append(p)

    return sorted(set(files))


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

def build_report(findings: list[Finding], scanned: int, args) -> str:
    findings_active = [f for f in findings if not f.whitelisted]
    findings_wl = [f for f in findings if f.whitelisted]

    by_sev: dict[str, list[Finding]] = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": []}
    for f in findings_active:
        by_sev[f.severity].append(f)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Security Scan Report (Docs)",
        "",
        f"- 扫描时间：{now}",
        f"- 文件数：{scanned}",
        f"- 命中合计（已扣白名单）：**{len(findings_active)}**",
        f"  - CRITICAL: **{len(by_sev['CRITICAL'])}**",
        f"  - HIGH:     **{len(by_sev['HIGH'])}**",
        f"  - MEDIUM:   **{len(by_sev['MEDIUM'])}**",
        f"  - LOW:      **{len(by_sev['LOW'])}**",
        f"- 白名单跳过：{len(findings_wl)}",
        f"- CLI: `{' '.join(['scripts/security_scan_docs.py'] + sys.argv[1:])}`",
        "",
        "## 检测维度",
        "",
        "| Detector | Severity | 说明 |",
        "|---|---|---|",
    ]
    for d in DETECTORS:
        lines.append(f"| `{d.name}` | {d.severity} | {d.description} |")
    lines.append("")

    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        flist = by_sev[sev]
        if not flist:
            continue
        lines.append(f"## {sev} ({len(flist)})")
        lines.append("")
        # 按 detector 再分组
        by_det: dict[str, list[Finding]] = {}
        for f in flist:
            by_det.setdefault(f.detector, []).append(f)
        for det_name in sorted(by_det.keys()):
            det_findings = by_det[det_name]
            lines.append(f"### `{det_name}` — {len(det_findings)} 处")
            lines.append("")
            # 按 unique match 聚合
            by_match: dict[str, list[Finding]] = {}
            for f in det_findings:
                by_match.setdefault(f.match, []).append(f)
            for m, occurs in sorted(by_match.items(), key=lambda kv: -len(kv[1])):
                lines.append(f"**`{m}`** — {len(occurs)} 处")
                # 列前 3 个 occurrence
                for f in occurs[:3]:
                    lines.append(f"- `{f.file}:{f.line}` — {f.context}")
                if len(occurs) > 3:
                    lines.append(f"- ... 还有 {len(occurs) - 3} 处")
                lines.append("")
            lines.append("")

    if findings_wl:
        lines.append("## 白名单已跳过")
        lines.append("")
        by_det_wl: dict[str, list[Finding]] = {}
        for f in findings_wl:
            by_det_wl.setdefault(f.detector, []).append(f)
        for det_name, occurs in by_det_wl.items():
            lines.append(f"- `{det_name}`: {len(occurs)} 处（白名单 hit）")
        lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="文档站隐私安全扫描")
    p.add_argument("--root", help="限单产品（aitable / docs / open / mail / im 等）")
    p.add_argument("--lang", default="all", choices=["all", "en", "zh", "ja"])
    p.add_argument("--severity", default="LOW", choices=["CRITICAL", "HIGH", "MEDIUM", "LOW"],
                   help="只显示 >= 该 severity")
    p.add_argument("--no-py", action="store_true", help="跳过 scripts/*.py")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    threshold = SEVERITY_ORDER[args.severity]
    detectors = [d for d in DETECTORS if SEVERITY_ORDER[d.severity] <= threshold]

    print(f"[info] detectors: {len(detectors)} / {len(DETECTORS)}（severity >= {args.severity}）")
    whitelist = load_whitelist()
    if whitelist:
        wl_summary = ", ".join(f"{k}={len(v)}" for k, v in whitelist.items())
        print(f"[info] whitelist 加载: {wl_summary}")

    files = discover_files(args.root, args.lang, not args.no_py)
    print(f"[info] 扫描文件: {len(files)}（root={args.root} lang={args.lang} include_py={not args.no_py}）")

    all_findings: list[Finding] = []
    for fp in files:
        all_findings.extend(scan_file(fp, detectors, whitelist))

    report = build_report(all_findings, len(files), args)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / "report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"[done] 报告: {report_path}")

    active = [f for f in all_findings if not f.whitelisted]
    by_sev: dict[str, int] = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in active:
        by_sev[f.severity] += 1
    print(f"[summary] CRITICAL={by_sev['CRITICAL']} HIGH={by_sev['HIGH']} MEDIUM={by_sev['MEDIUM']} LOW={by_sev['LOW']} (白名单跳过 {len(all_findings) - len(active)})")

    if by_sev["CRITICAL"] > 0:
        return 2
    if by_sev["HIGH"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
