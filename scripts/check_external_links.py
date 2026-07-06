#!/usr/bin/env python3
"""
钉钉外链死链探针：扫所有 mdx 里指向钉钉文档系统的链接，HTTP 实测死活。

死链判定（三类均自动 fix：`[label](dead)` → `label`）：
1. 最终 URL path 含 `/exception` 或 query 含 `type=notfound` → `dead_redirect`
2. 响应 body 含 `Wiki not found` / `The Wiki you accessed does not exist`
   / `这个 Wiki 找不到` / `The link is no longer accessible` / `链接已失效`
   → `dead_body`（注意：钉钉文档站是 SPA，多数 body 文案由 JS 渲染，此项实测命中率极低）
3. 服务端渲染的 `<meta property="og:title" content="">` 为空 → `dead_empty_title`
   实测：活公开文档 og:title 是真实标题；死/受限/exception 页面均空。
   2026-06-02 batch 抽样 8/8 验证 docs.dingtalk.io 上 og:title 空的 URL 全部在
   alidocs.dingtalk.com 上活着——即"没镜像到国际 .io 域名"。用户决策：按原 spec 去链留文。

网络错误（超时/连接拒绝/SSL/5xx）单独归类 `network_error`，**不**自动判死，列报告人审。

白名单域（其它外链不动）：
- docs.dingtalk.io
- alidocs.dingtalk.com
- alidocs.dingtalk.io

CLI:
  python3 scripts/check_external_links.py                 # dry-run，全部 mdx
  python3 scripts/check_external_links.py --apply         # 实际写盘（死链去链留文）
  python3 scripts/check_external_links.py --limit 20      # 只扫前 20 个 mdx
  python3 scripts/check_external_links.py --no-cache      # 跳过缓存，重跑全量
  python3 scripts/check_external_links.py --concurrency 4 # 并发降到 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

import httpx


REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "scripts" / "output" / "check_links"
CACHE_PATH = OUTPUT_DIR / "url-cache.json"

EXCLUDE_DIRS = {"node_modules", ".next", ".mintlify", "scripts", ".claude", ".git"}

WHITELIST_DOMAINS = {
    "docs.dingtalk.io",
    "alidocs.dingtalk.com",
    "alidocs.dingtalk.io",
}

# 死链 body 标记（中日英语种全打）
DEAD_BODY_MARKERS = [
    "Wiki not found",
    "The Wiki you accessed does not exist",
    "这个 Wiki 找不到",
    "这个Wiki找不到",
    "The link is no longer accessible",
    "链接已失效",
    "リンクは既に無効になっています",
    "Wikiが見つかりません",
]

# 死链 URL path / query 标记
DEAD_URL_MARKERS = [
    "/exception",
    "type=notfound",
]

# SSR meta tag：og:title 为空判为弱信号死链
RE_OG_TITLE = re.compile(r'<meta\s+property=["\']og:title["\']\s+content=["\']([^"\']*)["\']', re.I)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CACHE_TTL_SECONDS = 24 * 3600  # 24h

# mdx 链接捕获：[label](url) —— 不抓 ![label](url)（图片）
RE_LINK = re.compile(r'(?<!\!)\[([^\]]+)\]\((https?://[^)]+)\)')


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class ProbeResult:
    url: str
    status: str          # alive / dead_redirect / dead_body / dead_empty_title / network_error
    final_url: str = ""
    http_status: int = 0
    reason: str = ""
    checked_at: float = 0.0  # epoch seconds

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LinkOccurrence:
    file: str
    line: int
    label: str
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# 收集 mdx 链接
# ---------------------------------------------------------------------------

def discover_mdx(root: Optional[str], lang: str) -> list[Path]:
    files: list[Path] = []
    for p in REPO_ROOT.rglob("*.mdx"):
        rel = p.relative_to(REPO_ROOT)
        parts = rel.parts
        if any(part in EXCLUDE_DIRS for part in parts):
            continue
        first = parts[0]
        if lang == "en" and first in ("zh", "ja", "id"):
            continue
        if lang == "zh" and first != "zh":
            continue
        if lang == "ja" and first != "ja":
            continue
        if lang == "id" and first != "id":
            continue
        if root:
            if first in ("zh", "ja", "id"):
                if len(parts) < 2 or parts[1] != root:
                    continue
            else:
                if first != root:
                    continue
        files.append(p)
    files.sort()
    return files


def url_in_whitelist(url: str) -> bool:
    for d in WHITELIST_DOMAINS:
        if f"//{d}/" in url or f"//{d}?" in url or url.rstrip("/").endswith(f"//{d}"):
            return True
    return False


def collect_occurrences(files: list[Path]) -> tuple[list[LinkOccurrence], dict[str, list[int]]]:
    """返回 (所有命中链接的 occurrences, {url: [occurrence_idx,...]})。"""
    occurrences: list[LinkOccurrence] = []
    by_url: dict[str, list[int]] = {}
    for p in files:
        try:
            src = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        rel = str(p.relative_to(REPO_ROOT))
        for m in RE_LINK.finditer(src):
            label, url = m.group(1), m.group(2)
            # 去 url 末尾的 markdown title 部分 `"xxx"`
            url = url.split(' "')[0].strip()
            if not url_in_whitelist(url):
                continue
            line = src.count("\n", 0, m.start()) + 1
            idx = len(occurrences)
            occurrences.append(LinkOccurrence(file=rel, line=line, label=label, url=url))
            by_url.setdefault(url, []).append(idx)
    return occurrences, by_url


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
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
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
        return ProbeResult(
            url=url, status="network_error", reason=f"{type(e).__name__}: {e}",
            checked_at=now,
        )
    except Exception as e:
        return ProbeResult(
            url=url, status="network_error", reason=f"unexpected: {type(e).__name__}: {e}",
            checked_at=now,
        )

    final_url = str(resp.url)
    http_status = resp.status_code

    # 死链判定 1：URL marker
    for mark in DEAD_URL_MARKERS:
        if mark in final_url:
            return ProbeResult(
                url=url, status="dead_redirect", final_url=final_url,
                http_status=http_status, reason=f"redirect→{mark}", checked_at=now,
            )

    # HTTP 状态非 2xx：5xx 不判死（服务端波动），4xx 也单独归类
    if http_status >= 500:
        return ProbeResult(
            url=url, status="network_error", final_url=final_url,
            http_status=http_status, reason=f"HTTP {http_status}", checked_at=now,
        )
    if http_status == 404:
        return ProbeResult(
            url=url, status="dead_redirect", final_url=final_url,
            http_status=http_status, reason="HTTP 404", checked_at=now,
        )

    # 死链判定 2：body marker（SPA 站点几乎抓不到）
    try:
        body = resp.text
    except Exception:
        body = ""
    for mark in DEAD_BODY_MARKERS:
        if mark in body:
            return ProbeResult(
                url=url, status="dead_body", final_url=final_url,
                http_status=http_status, reason=f"body⊃'{mark}'", checked_at=now,
            )

    # 死链判定 3：SSR og:title 为空（弱信号，default 不自动修，列报告）
    # 仅对钉钉文档 `/i/p/` 和 `/i/nodes/` 路径下的链接生效；
    # 其它路径（如 /notable/share/form/...）SSR 不一定保证有 og:title
    if "/i/p/" in final_url or "/i/nodes/" in final_url:
        m = RE_OG_TITLE.search(body)
        if m and not m.group(1).strip():
            return ProbeResult(
                url=url, status="dead_empty_title", final_url=final_url,
                http_status=http_status, reason="og:title=''",  checked_at=now,
            )

    return ProbeResult(
        url=url, status="alive", final_url=final_url, http_status=http_status,
        checked_at=now,
    )


async def probe_all(urls: list[str], concurrency: int, cache: dict[str, dict],
                    use_cache: bool) -> dict[str, ProbeResult]:
    """并发探针；缓存命中跳过。返回 {url: ProbeResult}。"""
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
# 修复（--apply）
# ---------------------------------------------------------------------------

def is_dead(r: ProbeResult) -> bool:
    return r.status in ("dead_redirect", "dead_body", "dead_empty_title")


def apply_fixes(occurrences: list[LinkOccurrence], by_url: dict[str, list[int]],
                results: dict[str, ProbeResult]) -> dict[str, int]:
    """对所有引用了死链的 mdx，把 `[label](dead)` 替换为 `label`。返回 {file: 改动数}。"""
    dead_urls = {u for u, r in results.items() if is_dead(r)}
    if not dead_urls:
        return {}

    files_to_patch: dict[str, list[LinkOccurrence]] = {}
    for url in dead_urls:
        for idx in by_url.get(url, []):
            occ = occurrences[idx]
            files_to_patch.setdefault(occ.file, []).append(occ)

    applied: dict[str, int] = {}
    for rel, occs in files_to_patch.items():
        path = REPO_ROOT / rel
        src = path.read_text(encoding="utf-8")
        new_src = src
        count = 0
        # 对每个死 URL 做就地替换：把 [label](url) 替换为 label
        # 一个 mdx 可能多次引用同 URL，全替
        for url in {o.url for o in occs}:
            # 同 URL 可能有不同 label，逐个 escape
            pat = re.compile(
                r'(?<!\!)\[([^\]]+)\]\(' + re.escape(url) +
                r'(?: "[^"]*")?\)'
            )
            new_src, n = pat.subn(lambda m: m.group(1), new_src)
            count += n
        if count and new_src != src:
            path.write_text(new_src, encoding="utf-8")
            applied[rel] = count
    return applied


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------

STATUS_LABEL = {
    "alive": "✅ 存活",
    "dead_redirect": "❌ 死链（URL 重定向）",
    "dead_body": "❌ 死链（页面内容）",
    "dead_empty_title": "❌ 死链（og:title 空）",
    "network_error": "⚠️ 网络异常（人审）",
}


def write_reports(occurrences: list[LinkOccurrence], by_url: dict[str, list[int]],
                  results: dict[str, ProbeResult], applied: dict[str, int],
                  mode: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    by_status: dict[str, list[ProbeResult]] = {}
    for r in results.values():
        by_status.setdefault(r.status, []).append(r)

    dead_payload = []
    for url, r in sorted(results.items()):
        if r.status == "alive":
            continue
        refs = [occurrences[i].to_dict() for i in by_url.get(url, [])]
        dead_payload.append({"probe": r.to_dict(), "refs": refs})

    summary = {
        "mode": mode,
        "total_urls": len(results),
        "by_status": {k: len(v) for k, v in by_status.items()},
        "total_occurrences": len(occurrences),
        "files_applied": len(applied),
        "applied_changes_per_file": applied,
    }

    (OUTPUT_DIR / "dead-links.json").write_text(
        json.dumps({"summary": summary, "issues": dead_payload},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md = ["# 外链死链报告", "",
          f"- 模式：**{mode}**",
          f"- 探针 URL 总数：{len(results)}",
          f"- 引用 occurrence 总数：{len(occurrences)}"]
    if mode == "apply":
        md.append(f"- 已修改文件数：{len(applied)}")
        md.append(f"- 已修改链接占位数：{sum(applied.values())}")
    md.append("")
    md.append("## 按状态统计")
    md.append("")
    md.append("| 状态 | URL 数 |")
    md.append("|---|---|")
    for status, label in STATUS_LABEL.items():
        md.append(f"| {label} | {len(by_status.get(status, []))} |")
    md.append("")

    for status in ("dead_redirect", "dead_body", "dead_empty_title", "network_error"):
        items = by_status.get(status, [])
        if not items:
            continue
        md.append(f"## {STATUS_LABEL[status]}（前 30 例）")
        md.append("")
        md.append("| URL | 原因 | 引用次数 | HTTP |")
        md.append("|---|---|---|---|")
        items_sorted = sorted(items, key=lambda r: -len(by_url.get(r.url, [])))
        for r in items_sorted[:30]:
            refs = len(by_url.get(r.url, []))
            url_disp = r.url if len(r.url) <= 80 else r.url[:77] + "…"
            md.append(f"| `{url_disp}` | {r.reason} | {refs} | {r.http_status or '-'} |")
        if len(items) > 30:
            md.append(f"\n_（共 {len(items)} 例，余见 dead-links.json）_")
        md.append("")

    (OUTPUT_DIR / "dead-links.md").write_text("\n".join(md), encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="钉钉外链死链探针（asyncio + httpx）")
    p.add_argument("--root", default=None, help="限定单产品根，如 docs / aitable")
    p.add_argument("--lang", default="all", choices=["all", "en", "zh", "ja", "id"])
    p.add_argument("--apply", action="store_true", help="实际写盘修复（默认 dry-run）")
    p.add_argument("--limit", type=int, default=0, help="只扫前 N 个 mdx")
    p.add_argument("--concurrency", type=int, default=8, help="并发请求数（默认 8）")
    p.add_argument("--no-cache", action="store_true", help="跳过 URL 缓存，全量重探")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    files = discover_mdx(args.root, args.lang)
    if args.limit:
        files = files[: args.limit]

    mode = "apply" if args.apply else "dry-run"
    print(f"[info] 模式={mode} root={args.root or 'all'} lang={args.lang} 文件数={len(files)}")

    occurrences, by_url = collect_occurrences(files)
    print(f"[info] 命中钉钉链接 occurrence={len(occurrences)} unique_url={len(by_url)}")
    if not by_url:
        print("[done] 无白名单域链接，无事可做")
        return 0

    cache = load_cache()
    results = asyncio.run(
        probe_all(list(by_url.keys()), args.concurrency, cache, use_cache=not args.no_cache)
    )
    save_cache(cache)

    applied: dict[str, int] = {}
    if args.apply:
        applied = apply_fixes(occurrences, by_url, results)
        print(f"[done] 已修改 {len(applied)} 文件 / 共 {sum(applied.values())} 处链接占位")

    write_reports(occurrences, by_url, results, applied, mode)

    dead_n = sum(1 for r in results.values() if is_dead(r))
    redirect_n = sum(1 for r in results.values() if r.status == "dead_redirect")
    body_n = sum(1 for r in results.values() if r.status == "dead_body")
    empty_n = sum(1 for r in results.values() if r.status == "dead_empty_title")
    err_n = sum(1 for r in results.values() if r.status == "network_error")
    alive_n = len(results) - dead_n - err_n
    print(f"[done] 死链 {dead_n}（redirect {redirect_n} / body {body_n} / og:title 空 {empty_n}）"
          f" / 网络异常 {err_n} / 存活 {alive_n}")
    print(f"[done] 报告：{OUTPUT_DIR / 'dead-links.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
