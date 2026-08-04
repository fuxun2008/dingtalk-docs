#!/usr/bin/env python3
"""宜搭（YiDA）非中文文档外链三分类：转内链 / 去死链 / 汇总人审。

背景：en/ja/id 三语 yida/ 目录下混入大量指向纯中文站点（docs.aliwork.com、
yuque.com、open.dingtalk.com 等）的外链，翻译时锚文本译了但 href 没换。
本脚本只扫 yida/、ja/yida/、id/yida/（zh/yida/ 永远不碰）。

三分类：
1. 内链候选（internal candidate）：锚文本能匹配到站内已有同主题页 —— 只生成候选，
   人工在 internal-candidates.json 里回填 approved 后用 --apply-internal 落盘。
2. 死链（dead）：HTTP 404/410 判死，直接可信；og:title 空 / 中文"页面不存在"类
   body marker / 重定向落首页，均归"待验证"，不自动 apply。
3. 其余（review-needed）：活链接 + 无内链对应，汇总进 review-needed.md 供人工过。

CLI:
  python3 scripts/fix_yida_cn_links.py                          # dry-run 扫描+分类+出报告
  python3 scripts/fix_yida_cn_links.py --limit 20                # 调试：只扫前 N 个 mdx（每语言）
  python3 scripts/fix_yida_cn_links.py --no-cache                # 跳过 24h 探针缓存
  python3 scripts/fix_yida_cn_links.py --concurrency 8            # 并发数
  python3 scripts/fix_yida_cn_links.py --apply-dead                # 落盘：strip 可信死链
  python3 scripts/fix_yida_cn_links.py --apply-internal <path>      # 落盘：应用已确认内链改写
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "fix_yida_links"
CACHE_PATH = OUTPUT_DIR / "url-cache.json"
TITLE_INVENTORY_PATH = REPO_ROOT / "scripts" / "output" / "docs-titles" / "yida-inventory.json"

LANG_ROOTS = {"en": "yida", "ja": "ja/yida", "id": "id/yida"}

# ---------------------------------------------------------------------------
# 域名判定
# ---------------------------------------------------------------------------

# dingtalk.com / dingtalk.io 家族用精确匹配——避免 suffix 规则误伤已在
# check_external_links.py 白名单里的 docs.dingtalk.io / alidocs.dingtalk.com /
# alidocs.dingtalk.io（那三个域名的死链判定交给现有工具，不在本脚本重复处理）。
EXACT_CN_HOSTS = {
    "open.dingtalk.com", "developers.dingtalk.com", "oa.dingtalk.io",
    "notes.dingtalk.com", "standard.dingtalk.com", "page.dingtalk.com",
    "static.dingtalk.com", "api.dingtalk.com", "open-dev.dingtalk.com",
    "dingtalk.io",
}

# 其余域名用 suffix 匹配（无竞争白名单子域需要排除）
SUFFIX_CN_DOMAINS = {
    "aliwork.com", "yuque.com", "yidaapps.com", "aliyun.com", "alicdn.com",
    "w3school.com.cn", "sohu.com", "itc.cn", "csdn.net", "baidu.com",
    "taobao.com", "ruanyifeng.com", "runoob.com", "w3cschool.cn",
    "miit.gov.cn", "inspur.com",
}

# 资产类域名：图片/视频/CDN，不算"跳转链接"
ASSET_HOSTS = {"img.alicdn.com", "g.alicdn.com", "dev.g.alicdn.com", "cloud.video.taobao.com"}
MEDIA_EXTS = (".mov", ".mp4", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")


def normalize_host(host: str) -> str:
    host = (host or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def match_cn_domain(url: str) -> Optional[str]:
    """返回命中的域名标记，或 None（不在范围内）。"""
    parts = urlsplit(url)
    host = normalize_host(parts.hostname or "")
    path = (parts.path or "").lower()

    if host in ASSET_HOSTS:
        return None
    if path.endswith(MEDIA_EXTS):
        return None
    if host == "javascript.info":
        return host if path.startswith("/zh") else None
    if host in EXACT_CN_HOSTS:
        return host
    for d in SUFFIX_CN_DOMAINS:
        if host == d or host.endswith("." + d):
            return d
    return None


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class LinkOccurrence:
    file: str
    line: int
    lang: str            # en / ja / id
    label: str
    url: str
    domain: str
    kind: str             # md_link / card_href

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProbeResult:
    url: str
    status: str           # alive / dead_http404 / dead_http410 / weak_signal_review /
                           # dead_body_unverified / dead_redirect_to_home_unverified / network_error
    final_url: str = ""
    http_status: int = 0
    reason: str = ""
    checked_at: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


TRUSTED_DEAD_STATUSES = {"dead_http404", "dead_http410"}
REVIEW_STATUSES = {"weak_signal_review", "dead_body_unverified", "dead_redirect_to_home_unverified", "network_error"}

DEAD_BODY_MARKERS_CN = [
    "页面不存在", "你访问的页面不存在", "抱歉，该文档不存在或已被删除",
    "文档不存在", "该文档不存在", "页面走丢了", "该链接已失效或被删除",
    "Wiki not found", "The Wiki you accessed does not exist",
]

RE_OG_TITLE = re.compile(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']*)["\']', re.I)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CACHE_TTL_SECONDS = 24 * 3600

RE_LINK = re.compile(r'(?<!\!)\[([^\]]+)\]\((https?://[^)\s]+)\)')
RE_CARD = re.compile(
    r'<Card\b[^>]*\btitle=(?P<tq>["\'])(?P<title>(?:(?!(?P=tq)).)*)(?P=tq)'
    r'[^>]*\bhref=(?P<hq>["\'])(?P<href>https?://[^"\']+)(?P=hq)[^>]*/?>'
)
RE_CARD_HREF_ONLY = re.compile(
    r'<Card\b[^>]*\bhref=(?P<hq>["\'])(?P<href>https?://[^"\']+)(?P=hq)[^>]*/?>'
)


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------

def discover_mdx(lang: str, limit: int) -> list[Path]:
    base = REPO_ROOT / LANG_ROOTS[lang]
    files = sorted(base.rglob("*.mdx")) if base.is_dir() else []
    if limit:
        files = files[:limit]
    return files


def fenced_line_indices(lines: list[str]) -> set[int]:
    fenced: set[int] = set()
    in_fence = False
    for i, line in enumerate(lines):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            fenced.add(i)
    return fenced


def collect_occurrences(files: list[Path], lang: str) -> list[LinkOccurrence]:
    occurrences: list[LinkOccurrence] = []
    for p in files:
        try:
            src = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = str(p.relative_to(REPO_ROOT))
        lines = src.split("\n")
        fenced = fenced_line_indices(lines)

        for i, line in enumerate(lines):
            if i in fenced:
                continue

            for m in RE_LINK.finditer(line):
                label, url = m.group(1), m.group(2).split(' "')[0].strip()
                domain = match_cn_domain(url)
                if domain:
                    occurrences.append(LinkOccurrence(
                        file=rel, line=i + 1, lang=lang, label=label,
                        url=url, domain=domain, kind="md_link",
                    ))

            cm = RE_CARD.search(line) or RE_CARD_HREF_ONLY.search(line)
            if cm:
                href = cm.group("href")
                domain = match_cn_domain(href)
                if domain:
                    label = cm.groupdict().get("title") or href
                    occurrences.append(LinkOccurrence(
                        file=rel, line=i + 1, lang=lang, label=label,
                        url=href, domain=domain, kind="card_href",
                    ))
    return occurrences


def build_by_url(occurrences: list[LinkOccurrence]) -> dict[str, list[LinkOccurrence]]:
    by_url: dict[str, list[LinkOccurrence]] = {}
    for o in occurrences:
        by_url.setdefault(o.url, []).append(o)
    return by_url


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------

def load_cache() -> dict[str, dict]:
    if not CACHE_PATH.exists():
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache: dict[str, dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8",
    )


def cache_fresh(entry: dict, now: float) -> bool:
    return now - entry.get("checked_at", 0) < CACHE_TTL_SECONDS


# ---------------------------------------------------------------------------
# 探针
# ---------------------------------------------------------------------------

async def probe_url(client: httpx.AsyncClient, url: str) -> ProbeResult:
    now = time.time()
    try:
        resp = await client.get(url, follow_redirects=True, timeout=10.0)
    except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError,
            httpx.RemoteProtocolError, httpx.ReadError) as e:
        return ProbeResult(url=url, status="network_error", reason=f"{type(e).__name__}: {e}", checked_at=now)
    except Exception as e:
        return ProbeResult(url=url, status="network_error", reason=f"unexpected: {type(e).__name__}: {e}", checked_at=now)

    final_url = str(resp.url)
    http_status = resp.status_code

    if http_status == 404:
        return ProbeResult(url=url, status="dead_http404", final_url=final_url, http_status=http_status, reason="HTTP 404", checked_at=now)
    if http_status == 410:
        return ProbeResult(url=url, status="dead_http410", final_url=final_url, http_status=http_status, reason="HTTP 410", checked_at=now)
    if http_status >= 500:
        return ProbeResult(url=url, status="network_error", final_url=final_url, http_status=http_status, reason=f"HTTP {http_status}", checked_at=now)

    try:
        body = resp.text
    except Exception:
        body = ""

    for mark in DEAD_BODY_MARKERS_CN:
        if mark in body:
            return ProbeResult(url=url, status="dead_body_unverified", final_url=final_url, http_status=http_status, reason=f"body⊃'{mark}'（未验证信号，先人审）", checked_at=now)

    m = RE_OG_TITLE.search(body)
    if m and not m.group(1).strip():
        return ProbeResult(url=url, status="weak_signal_review", final_url=final_url, http_status=http_status, reason="og:title=''（该信号只在 docs.dingtalk.io 验证过，此处未验证）", checked_at=now)

    orig_path = (urlsplit(url).path or "").rstrip("/")
    final_path = (urlsplit(final_url).path or "").rstrip("/")
    if orig_path and not final_path:
        return ProbeResult(url=url, status="dead_redirect_to_home_unverified", final_url=final_url, http_status=http_status, reason="重定向落到域名首页（未验证信号，先人审）", checked_at=now)

    return ProbeResult(url=url, status="alive", final_url=final_url, http_status=http_status, checked_at=now)


async def probe_all(urls: list[str], concurrency: int, cache: dict[str, dict], use_cache: bool) -> dict[str, ProbeResult]:
    now = time.time()
    results: dict[str, ProbeResult] = {}
    todo: list[str] = []
    for url in urls:
        entry = cache.get(url)
        if use_cache and entry and cache_fresh(entry, now):
            results[url] = ProbeResult(**entry)
        else:
            todo.append(url)

    if not todo:
        return results

    print(f"[info] cache 命中 {len(results)} / 待探 {len(todo)}（并发 {concurrency}）")
    sem = asyncio.Semaphore(concurrency)
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,en;q=0.8,ja;q=0.6"}

    async with httpx.AsyncClient(headers=headers, http2=False) as client:
        async def bound(u: str) -> ProbeResult:
            async with sem:
                return await probe_url(client, u)

        done = 0
        tasks = [asyncio.create_task(bound(u)) for u in todo]
        for coro in asyncio.as_completed(tasks):
            r = await coro
            results[r.url] = r
            cache[r.url] = r.to_dict()
            done += 1
            if done % 20 == 0 or done == len(todo):
                print(f"[info]   探针进度 {done}/{len(todo)}")

    return results


# ---------------------------------------------------------------------------
# 内链候选匹配
# ---------------------------------------------------------------------------

STOPWORDS = {
    "a", "an", "the", "to", "for", "of", "and", "in", "on", "see", "more",
    "information", "learn", "about", "with", "your", "you", "how", "is",
    # "yida" 是品牌名，几乎每个页面标题都含它，不去掉会导致任意含 "YiDA" 的锚文本
    # 和任意 yida 页面标题都有虚假 overlap（如 "YiDA Workbench" 误配到无关页面）
    "yida",
}


def tokenize(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower())) - STOPWORDS


def ensure_title_inventory() -> dict:
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "extract_docs_titles.py"), "--root", "yida"],
        cwd=REPO_ROOT, check=True,
    )
    return json.loads(TITLE_INVENTORY_PATH.read_text(encoding="utf-8"))


def match_internal_candidates(en_occurrences: list[LinkOccurrence], inventory: dict) -> list[dict]:
    candidates: list[dict] = []
    title_index = [
        (slug, entry["titles"].get("en"))
        for slug, entry in inventory.items()
        if entry["titles"].get("en")
    ]
    for o in en_occurrences:
        # 排除"自己匹配自己"——链接所在页面的标题天然和页面内文字有词面重叠，
        # 但转成指向自身的内链毫无意义
        own_slug = o.file[:-4] if o.file.endswith(".mdx") else o.file
        label_tokens = tokenize(o.label)
        if not label_tokens:
            continue
        scored = []
        for slug, title_en in title_index:
            if slug == own_slug:
                continue
            title_tokens = tokenize(title_en)
            if not title_tokens:
                continue
            inter = label_tokens & title_tokens
            if not inter:
                continue
            # 至少 2 个词重叠，或唯一重叠词足够具体（长度 >=6）——排除
            # "OSS"/"Sort"/"Use cases" 这类靠单个短泛词就能凑出 0.5 分的虚假匹配
            if len(inter) < 2 and max(len(t) for t in inter) < 6:
                continue
            score = len(inter) / len(label_tokens)
            if score < 0.5:
                continue
            confidence = "high" if (score >= 0.8 and abs(len(title_tokens) - len(label_tokens)) <= 2) else "medium"
            scored.append({"slug": slug, "title_en": title_en, "score": round(score, 2), "confidence": confidence})
        if not scored:
            continue
        scored.sort(key=lambda c: -c["score"])
        for c in scored:
            c["suggested"] = c is scored[0] and c["confidence"] == "high"
        candidates.append({
            "en_file": o.file, "en_line": o.line, "label": o.label, "url": o.url,
            "candidates": scored[:5], "approved": False, "approved_slug": None,
        })
    return candidates


def merge_existing_approvals(candidates: list[dict]) -> list[dict]:
    """重新生成 internal-candidates.json 时，保留人工已回填的 approved/approved_slug，
    不然每次重跑（比如脚本改了打分逻辑）都会把人工审核结果冲掉。"""
    existing_path = OUTPUT_DIR / "internal-candidates.json"
    if not existing_path.exists():
        return candidates
    try:
        existing = json.loads(existing_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return candidates
    prior = {(e["en_file"], e["en_line"], e["url"]): e for e in existing}
    for c in candidates:
        key = (c["en_file"], c["en_line"], c["url"])
        old = prior.get(key)
        if old and old.get("approved"):
            c["approved"] = True
            c["approved_slug"] = old.get("approved_slug")
    return candidates


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

STATUS_LABEL = {
    "alive": "✅ 存活",
    "dead_http404": "❌ 死链（HTTP 404，可信）",
    "dead_http410": "❌ 死链（HTTP 410，可信）",
    "weak_signal_review": "⚠️ og:title 空（未验证信号，人审）",
    "dead_body_unverified": "⚠️ body 命中『页面不存在』类文案（未验证信号，人审）",
    "dead_redirect_to_home_unverified": "⚠️ 重定向落首页（未验证信号，人审）",
    "network_error": "⚠️ 网络异常（人审）",
}


def write_dead_links_report(occurrences: list[LinkOccurrence], by_url: dict, results: dict[str, ProbeResult]) -> None:
    by_status: dict[str, list[ProbeResult]] = {}
    for r in results.values():
        by_status.setdefault(r.status, []).append(r)

    payload = []
    for url, r in sorted(results.items()):
        if r.status == "alive":
            continue
        refs = [o.to_dict() for o in by_url.get(url, [])]
        payload.append({"probe": r.to_dict(), "refs": refs})

    summary = {
        "total_urls": len(results),
        "by_status": {k: len(v) for k, v in by_status.items()},
        "trusted_dead_urls": sum(len(v) for k, v in by_status.items() if k in TRUSTED_DEAD_STATUSES),
        "needs_human_review_urls": sum(len(v) for k, v in by_status.items() if k in REVIEW_STATUSES),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "dead-links.json").write_text(
        json.dumps({"summary": summary, "issues": payload}, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    md = ["# 宜搭外链死链报告", "", f"- 探针 URL 总数：{len(results)}",
          f"- 可信死链（自动 apply）：{summary['trusted_dead_urls']}",
          f"- 待人审（不自动 apply）：{summary['needs_human_review_urls']}", ""]
    md.append("## 按状态统计")
    md.append("")
    md.append("| 状态 | URL 数 |")
    md.append("|---|---|")
    for status, label in STATUS_LABEL.items():
        if status == "alive":
            continue
        md.append(f"| {label} | {len(by_status.get(status, []))} |")
    md.append("")

    md.append("## 可信死链（HTTP 404/410）——将被 --apply-dead 处理")
    md.append("")
    md.append("| URL | 状态 | 引用次数 |")
    md.append("|---|---|---|")
    for status in ("dead_http404", "dead_http410"):
        for r in by_status.get(status, []):
            refs = len(by_url.get(r.url, []))
            md.append(f"| `{r.url}` | {status} | {refs} |")
    md.append("")

    for status in ("weak_signal_review", "dead_body_unverified", "dead_redirect_to_home_unverified", "network_error"):
        items = by_status.get(status, [])
        if not items:
            continue
        md.append(f"## {STATUS_LABEL[status]}（前 30 例）")
        md.append("")
        md.append("| URL | 原因 | 引用次数 |")
        md.append("|---|---|---|")
        items_sorted = sorted(items, key=lambda r: -len(by_url.get(r.url, [])))
        for r in items_sorted[:30]:
            refs = len(by_url.get(r.url, []))
            url_disp = r.url if len(r.url) <= 90 else r.url[:87] + "…"
            md.append(f"| `{url_disp}` | {r.reason} | {refs} |")
        if len(items) > 30:
            md.append(f"\n_（共 {len(items)} 例，余见 dead-links.json）_")
        md.append("")

    (OUTPUT_DIR / "dead-links.md").write_text("\n".join(md), encoding="utf-8")


def write_internal_candidates_report(candidates: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "internal-candidates.json").write_text(
        json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    md = ["# 宜搭内链候选确认队列", "",
          f"- 候选总数：{len(candidates)}",
          "- 使用方法：人工逐条打开 en_file 原页 + candidates 里的目标页核对主题是否真对应，",
          "  确认后在 internal-candidates.json 里把该条目的 `approved` 置 `true`、",
          "  `approved_slug` 填成最终采用的 slug（一般就是 candidates[0].slug），",
          "  再跑 `--apply-internal scripts/output/fix_yida_links/internal-candidates.json`。",
          ""]
    md.append("| EN 文件:行 | 锚文本 | 目标 URL | 首选候选 slug | 置信度 | 分数 |")
    md.append("|---|---|---|---|---|---|")
    for c in candidates:
        top = c["candidates"][0]
        url_disp = c["url"] if len(c["url"]) <= 60 else c["url"][:57] + "…"
        md.append(
            f"| `{c['en_file']}:{c['en_line']}` | {c['label']} | `{url_disp}` | "
            f"`{top['slug']}` | {top['confidence']} | {top['score']} |"
        )
    (OUTPUT_DIR / "internal-candidates.md").write_text("\n".join(md), encoding="utf-8")


def write_review_needed_report(occurrences: list[LinkOccurrence], by_url: dict,
                                results: dict[str, ProbeResult], internal_urls: set[str]) -> None:
    """按唯一 URL 分组的人审汇总——用户要的最终交付物。"""
    help_aliyun_zh = re.compile(r"^https?://help\.aliyun\.com/zh/")

    rows = []
    for url, occs in sorted(by_url.items()):
        if url in internal_urls:
            continue
        r = results.get(url)
        status = r.status if r else "unknown"
        if status == "alive" or status in REVIEW_STATUSES:
            refs = sorted({f"{o.lang}:{o.file}:{o.line}" for o in occs})
            suggested_fix = ""
            if help_aliyun_zh.match(url):
                suggested_fix = url.replace("/zh/", "/en/", 1) + "（aliyun 官方英文变体，未验证，建议人工确认后手动替换）"
            rows.append({
                "url": url, "domain": occs[0].domain, "status": status,
                "refs": refs, "ref_count": len(refs), "suggested_fix": suggested_fix,
            })

    rows.sort(key=lambda x: (-x["ref_count"], x["url"]))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "review-needed.json").write_text(
        json.dumps({"total": len(rows), "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    md = ["# 宜搭外链人审汇总", "",
          "本文档汇总所有指向中文专属内容、且既非可信死链也无站内内链对应的外链，",
          "按唯一 URL 去重展示。请逐条人工判断：保留 / 找中文站以外的等价来源改写 / 其它处理。",
          "",
          f"- 唯一 URL 总数：{len(rows)}", ""]
    md.append("| URL | 域名 | 状态 | 引用次数 | 引用位置（前 5） | 建议 |")
    md.append("|---|---|---|---|---|---|")
    for row in rows:
        url_disp = row["url"] if len(row["url"]) <= 70 else row["url"][:67] + "…"
        refs_disp = "<br>".join(row["refs"][:5])
        if len(row["refs"]) > 5:
            refs_disp += f"<br>…共 {len(row['refs'])} 处"
        md.append(
            f"| `{url_disp}` | {row['domain']} | {row['status']} | {row['ref_count']} | "
            f"{refs_disp} | {row['suggested_fix']} |"
        )
    (OUTPUT_DIR / "review-needed.md").write_text("\n".join(md), encoding="utf-8")


# ---------------------------------------------------------------------------
# 应用：死链 strip
# ---------------------------------------------------------------------------

def apply_dead(occurrences: list[LinkOccurrence], results: dict[str, ProbeResult]) -> tuple[dict[str, int], dict[str, int]]:
    trusted_dead = {u for u, r in results.items() if r.status in TRUSTED_DEAD_STATUSES}
    if not trusted_dead:
        return {}, {}

    by_file: dict[str, list[LinkOccurrence]] = {}
    for o in occurrences:
        if o.url in trusted_dead:
            by_file.setdefault(o.file, []).append(o)

    applied: dict[str, int] = {}
    card_removed: dict[str, int] = {}
    for rel, occs in by_file.items():
        path = REPO_ROOT / rel
        src = path.read_text(encoding="utf-8")
        new_src = src
        count = 0

        md_urls = {o.url for o in occs if o.kind == "md_link"}
        for url in md_urls:
            pat = re.compile(r'(?<!\!)\[([^\]]+)\]\(' + re.escape(url) + r'(?: "[^"]*")?\)')
            new_src, n = pat.subn(lambda m: m.group(1), new_src)
            count += n

        card_urls = {o.url for o in occs if o.kind == "card_href"}
        if card_urls:
            lines = new_src.split("\n")
            kept = []
            removed_here = 0
            for line in lines:
                stripped = line.strip()
                hit = stripped.startswith("<Card") and any(
                    f'href="{u}"' in line or f"href='{u}'" in line for u in card_urls
                )
                if hit:
                    removed_here += 1
                    continue
                kept.append(line)
            if removed_here:
                new_src = "\n".join(kept)
                count += removed_here
                card_removed[rel] = removed_here

        if count and new_src != src:
            path.write_text(new_src, encoding="utf-8")
            applied[rel] = count

    return applied, card_removed


# ---------------------------------------------------------------------------
# 应用：内链改写
# ---------------------------------------------------------------------------

def rewrite_link(rel_file: str, url: str, new_target: str) -> bool:
    path = REPO_ROOT / rel_file
    src = path.read_text(encoding="utf-8")
    pat = re.compile(r'(\[[^\]]+\]\()' + re.escape(url) + r'(\))')
    new_src, n = pat.subn(lambda m: m.group(1) + new_target + m.group(2), src)
    if n == 0:
        pat2 = re.compile(r'(href=(["\']))' + re.escape(url) + r'(\2)')
        new_src, n = pat2.subn(lambda m: m.group(1) + new_target + m.group(3), src)
    if n:
        path.write_text(new_src, encoding="utf-8")
        return True
    return False


def apply_internal(confirm_path: Path, by_url: dict[str, list[LinkOccurrence]]) -> dict:
    entries = json.loads(confirm_path.read_text(encoding="utf-8"))
    applied = []
    mismatches = []

    for entry in entries:
        if not entry.get("approved"):
            continue
        url = entry["url"]
        slug = entry.get("approved_slug")
        if not slug:
            mismatches.append({"url": url, "reason": "approved=true 但缺 approved_slug"})
            continue

        en_ok = rewrite_link(entry["en_file"], url, f"/{slug}")
        if en_ok:
            applied.append({"file": entry["en_file"], "url": url, "target": f"/{slug}"})
        else:
            mismatches.append({"url": url, "file": entry["en_file"], "reason": "EN 文件里没找到原 URL，跳过"})

        for lang in ("ja", "id"):
            # 镜像文件路径固定推导（en_file: "yida/x.mdx" -> "ja/yida/x.mdx" /
            # "id/yida/x.mdx"），而不是在同 URL 的全部 occurrence 里瞎找——
            # 同一个 URL 可能在很多不同文件里出现（如 21 篇都引用同一条
            # Integration & Automation 说明），必须先按镜像文件路径过滤，
            # 再在该文件内按 URL 定位，否则会把"该语言全站命中数"误判成歧义
            mirror_file = f"{lang}/{entry['en_file']}"
            cands = [o for o in by_url.get(url, []) if o.lang == lang and o.file == mirror_file]
            if len(cands) == 0:
                continue
            # 同一镜像文件内该 URL 出现多次也不算歧义——rewrite_link 按 URL 做
            # 全文件正则替换，本就会把该文件里所有该 URL 的出现一并改成同一目标
            target = f"/{lang}/{slug}"
            ok = rewrite_link(mirror_file, url, target)
            if ok:
                applied.append({"file": mirror_file, "url": url, "target": target})
            else:
                mismatches.append({"url": url, "lang": lang, "file": mirror_file, "reason": "改写失败"})

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result = {"applied": applied, "mismatches": mismatches}
    (OUTPUT_DIR / "apply-internal-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="宜搭非中文文档外链三分类（转内链 / 去死链 / 人审汇总）")
    p.add_argument("--limit", type=int, default=0, help="调试：每语言只扫前 N 个 mdx")
    p.add_argument("--concurrency", type=int, default=8, help="探针并发数")
    p.add_argument("--no-cache", action="store_true", help="跳过 24h 探针缓存")
    p.add_argument("--apply-dead", action="store_true", help="落盘：strip 可信死链（HTTP 404/410）")
    p.add_argument("--apply-internal", metavar="PATH", help="落盘：应用 internal-candidates.json 里 approved=true 的内链改写")
    return p.parse_args()


def main() -> int:
    args = parse_args()

    all_occurrences: list[LinkOccurrence] = []
    for lang in ("en", "ja", "id"):
        files = discover_mdx(lang, args.limit)
        occs = collect_occurrences(files, lang)
        print(f"[info] {lang}: {len(files)} mdx / {len(occs)} 中文域名链接命中")
        all_occurrences.extend(occs)

    by_url = build_by_url(all_occurrences)
    print(f"[info] 总占用 occurrence={len(all_occurrences)} / 唯一 URL={len(by_url)}")

    if args.apply_internal:
        result = apply_internal(Path(args.apply_internal), by_url)
        print(f"[done] 内链改写：已应用 {len(result['applied'])} 处 / 跳过 {len(result['mismatches'])} 处（见 apply-internal-result.json）")
        return 0

    cache = load_cache()
    results = asyncio.run(probe_all(list(by_url.keys()), args.concurrency, cache, use_cache=not args.no_cache))
    save_cache(cache)

    if args.apply_dead:
        applied, card_removed = apply_dead(all_occurrences, results)
        print(f"[done] 死链 strip：已改 {len(applied)} 文件 / {sum(applied.values())} 处占位（其中整块删除 Card {sum(card_removed.values())} 处）")
        write_dead_links_report(all_occurrences, by_url, results)
        return 0

    en_occurrences = [o for o in all_occurrences if o.lang == "en"]
    inventory = ensure_title_inventory()
    candidates = match_internal_candidates(en_occurrences, inventory)
    candidates = merge_existing_approvals(candidates)
    # 只有已批准的内链候选才从人审汇总里排除；未批准的（不管置信度多高）
    # 必须继续出现在 review-needed.md，不然会随着候选列表"静默消失"
    internal_urls = {c["url"] for c in candidates if c.get("approved")}

    write_dead_links_report(all_occurrences, by_url, results)
    write_internal_candidates_report(candidates)
    write_review_needed_report(all_occurrences, by_url, results, internal_urls)

    dead_n = sum(1 for r in results.values() if r.status in TRUSTED_DEAD_STATUSES)
    review_n = sum(1 for r in results.values() if r.status in REVIEW_STATUSES)
    alive_n = sum(1 for r in results.values() if r.status == "alive")
    print(f"[done] 可信死链 {dead_n} / 待人审 {review_n} / 存活 {alive_n} / 内链候选 {len(candidates)}")
    print(f"[done] 报告：{OUTPUT_DIR / 'dead-links.md'}")
    print(f"[done] 报告：{OUTPUT_DIR / 'internal-candidates.md'}")
    print(f"[done] 报告：{OUTPUT_DIR / 'review-needed.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
