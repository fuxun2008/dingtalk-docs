#!/usr/bin/env python3
"""
Crawl open.dingtalk.com developer docs to local raw markdown.

Subcommands:
  menu    - Build fetch_list.json from guide md (development) + dingstart meta.json
  fetch   - Batch fetch raw markdown for everything in fetch_list.json
  report  - Generate report.md from report.json

Endpoints (anonymous, no cookie/referer needed):
  meta:  https://icms-document.oss-cn-beijing.aliyuncs.com/zh-CN/dingtalk/{ns}/meta.json
  doc:   https://icms-document.oss-cn-beijing.aliyuncs.com/zh-CN/dingtalk/{ns}/topics/{slug}.html
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import httpx
from markdownify import markdownify as md_convert

HERE = Path(__file__).parent
OUT_DIR = HERE / "output" / "open_platform"
MENU_DIR = OUT_DIR / "menu"
DEFAULT_GUIDE = Path.home() / "Downloads" / "dingtalk-open-service-api-docs.md"

OSS_BASE = "https://icms-document.oss-cn-beijing.aliyuncs.com/zh-CN/dingtalk"
META_URL = f"{OSS_BASE}/{{ns}}/meta.json"
DOC_URL = f"{OSS_BASE}/{{ns}}/topics/{{slug}}.html"
SITE_URL = "https://open.dingtalk.com/document/{ns}/{slug}"

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://open.dingtalk.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


# --------------- menu subcommand ---------------

# Headings to skip when building module_path (they are not real grouping)
SKIP_HEADINGS = {
    "约束", "模块映射说明", "模块容量汇总",
    "钉钉开放平台 - 服务端 API 文档清单",
}

LINK_RE = re.compile(
    r"\[([^\]]+)\]\(https://open\.dingtalk\.com/document/development/([^)\s#?]+)(?:[#?][^)]*)?\)"
)
HEAD_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LIST_RE = re.compile(r"^\s*[-*]\s+(.+)$")


def parse_guide_md(path: Path) -> list[dict]:
    """Parse guide markdown -> list of dev items.

    Tracks a heading stack so each link inherits its module_path
    (e.g. "三、通讯录管理 / 3.5 角色管理").
    """
    text = path.read_text(encoding="utf-8")
    heading_stack: list[tuple[int, str]] = []  # (level, title)
    items: list[dict] = []
    seen_slugs: set[str] = set()

    for line in text.splitlines():
        m = HEAD_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if title in SKIP_HEADINGS:
                # Drop everything at level >= this
                heading_stack = [(l, t) for (l, t) in heading_stack if l < level]
                continue
            heading_stack = [(l, t) for (l, t) in heading_stack if l < level]
            heading_stack.append((level, title))
            continue

        lm = LIST_RE.match(line)
        if not lm:
            continue
        link_m = LINK_RE.search(lm.group(1))
        if not link_m:
            continue
        title = link_m.group(1).strip()
        slug = link_m.group(2).strip()
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        items.append({
            "namespace": "development",
            "slug": slug,
            "title": title,
            "module_path": " / ".join(t for (_, t) in heading_stack),
            "url": DOC_URL.format(ns="development", slug=slug),
            "source_url": SITE_URL.format(ns="development", slug=slug),
            "source": "guide_md",
        })
    return items


def fetch_meta(namespace: str) -> dict:
    url = META_URL.format(ns=namespace)
    req = urllib.request.Request(url, headers=DEFAULT_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def walk_meta(topics: list, namespace: str, path: list[str] | None = None) -> list[dict]:
    """Recursively walk meta.json topics tree -> flat list of doc items."""
    items: list[dict] = []
    path = path or []
    for t in topics or []:
        if not t:
            continue
        title = (t.get("title") or "").strip()
        node_type = t.get("type")
        if node_type == "doc":
            slug = t.get("slug")
            if slug:
                items.append({
                    "namespace": namespace,
                    "slug": slug,
                    "title": title,
                    "module_path": " / ".join(path),
                    "url": DOC_URL.format(ns=namespace, slug=slug),
                    "source_url": SITE_URL.format(ns=namespace, slug=slug),
                    "source": f"{namespace}_meta",
                    "short_description": t.get("shortDescription"),
                    "labels": t.get("labels"),
                })
        # Recurse into children regardless of node_type (directory may host docs)
        children = t.get("children")
        if children:
            new_path = path + [title] if title else path
            items.extend(walk_meta(children, namespace, new_path))
    return items


def cmd_menu(args) -> int:
    MENU_DIR.mkdir(parents=True, exist_ok=True)

    guide_path = Path(args.guide_md).expanduser()
    if not guide_path.exists():
        print(f"ERROR: guide md not found: {guide_path}", file=sys.stderr)
        return 2

    print(f"[1/3] parsing guide md: {guide_path}")
    dev_items = parse_guide_md(guide_path)
    print(f"      → {len(dev_items)} development items")
    (MENU_DIR / "development_index.json").write_text(
        json.dumps(dev_items, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[2/3] fetching dingstart meta.json...")
    ds_meta = fetch_meta("dingstart")
    (MENU_DIR / "dingstart_meta.json").write_text(
        json.dumps(ds_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    ds_items = walk_meta(ds_meta.get("topics", []), namespace="dingstart")
    print(f"      → {len(ds_items)} dingstart items")
    (MENU_DIR / "dingstart_tree.json").write_text(
        json.dumps(ds_items, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[3/3] merging into fetch_list.json")
    fetch_list = dev_items + ds_items
    # Dedupe by (namespace, slug); first one wins
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for it in fetch_list:
        key = (it["namespace"], it["slug"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)
    (MENU_DIR / "fetch_list.json").write_text(
        json.dumps(deduped, ensure_ascii=False, indent=2), encoding="utf-8")

    by_ns: dict[str, int] = {}
    for it in deduped:
        by_ns[it["namespace"]] = by_ns.get(it["namespace"], 0) + 1
    print()
    print(f"=== fetch_list.json: {len(deduped)} total ===")
    for ns, n in by_ns.items():
        print(f"  {ns}: {n}")

    # Sanity check vs guide md "模块容量汇总" table (410 expected)
    if by_ns.get("development", 0) != 410:
        print(
            f"  ⚠️  development count {by_ns.get('development', 0)} != expected 410. "
            f"Check guide md or LINK_RE."
        )
    return 0


# --------------- fetch subcommand ---------------

RAW_DIR = OUT_DIR / "raw"
REPORT_JSON = OUT_DIR / "report.json"
FAILED_JSON = OUT_DIR / "failed.json"
FETCH_LIST = MENU_DIR / "fetch_list.json"

# Headers for actual GET — match browser to avoid 403
FETCH_HEADERS = {
    "User-Agent": UA,
    "Referer": "https://open.dingtalk.com/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Origin": "https://open.dingtalk.com",
}

# markdownify options — keep tables/code, strip script/style
MD_OPTS = dict(
    heading_style="ATX",
    bullets="-",
    strip=["script", "style"],
    code_language="",
)


def _yaml_str(v) -> str:
    """Render a value as a safe YAML scalar (JSON-quoted for strings, raw for others)."""
    if v is None:
        return '""'
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        # Inline JSON array — safe for primitives
        return json.dumps(v, ensure_ascii=False)
    return json.dumps(str(v), ensure_ascii=False)


def build_frontmatter(item: dict, html_bytes: int, image_count: int) -> str:
    fields = {
        "title": item.get("title"),
        "slug": item.get("slug"),
        "namespace": item.get("namespace"),
        "module_path": item.get("module_path"),
        "source_url": item.get("source_url"),
        "source": item.get("source"),
        "html_bytes": html_bytes,
        "image_count": image_count,
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if item.get("short_description"):
        fields["short_description"] = item["short_description"]
    if item.get("labels"):
        fields["labels"] = item["labels"]
    lines = ["---"]
    for k, v in fields.items():
        lines.append(f"{k}: {_yaml_str(v)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


_IMG_RE = re.compile(r"<img\s[^>]*src=", re.IGNORECASE)
_HEAD_RE = re.compile(r"<head\b[^>]*>.*?</head>", re.IGNORECASE | re.DOTALL)


def html_to_md(html: str) -> tuple[str, int]:
    """Convert HTML to markdown; return (md, image_count)."""
    # Drop <head>...</head> first so <title> doesn't become leading text
    html = _HEAD_RE.sub("", html)
    image_count = len(_IMG_RE.findall(html))
    md = md_convert(html, **MD_OPTS)
    # Collapse excessive blank lines (markdownify can produce 3+)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    return md, image_count


async def fetch_one(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    item: dict,
    raw_dir: Path,
    retry: int,
    delay: float,
) -> dict:
    """Fetch + convert + write one doc. Returns a report record."""
    url = item["url"]
    ns = item["namespace"]
    slug = item["slug"]
    out_path = raw_dir / ns / f"{slug}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    last_err: str | None = None
    for attempt in range(1, retry + 2):
        async with sem:
            try:
                r = await client.get(url, headers=FETCH_HEADERS, timeout=30.0)
                if r.status_code == 200:
                    html = r.text
                    md, img_count = html_to_md(html)
                    fm = build_frontmatter(item, len(r.content), img_count)
                    out_path.write_text(fm + md, encoding="utf-8")
                    elapsed_ms = int((time.perf_counter() - start) * 1000)
                    await asyncio.sleep(delay)
                    return {
                        "namespace": ns,
                        "slug": slug,
                        "title": item.get("title"),
                        "module_path": item.get("module_path"),
                        "status": "ok",
                        "http_code": 200,
                        "elapsed_ms": elapsed_ms,
                        "html_bytes": len(r.content),
                        "md_bytes": len((fm + md).encode("utf-8")),
                        "image_count": img_count,
                        "attempts": attempt,
                    }
                if r.status_code in (404, 410):
                    elapsed_ms = int((time.perf_counter() - start) * 1000)
                    return {
                        "namespace": ns,
                        "slug": slug,
                        "title": item.get("title"),
                        "status": "not_found",
                        "http_code": r.status_code,
                        "elapsed_ms": elapsed_ms,
                        "attempts": attempt,
                    }
                # Retryable
                last_err = f"HTTP {r.status_code}"
            except (httpx.RequestError, httpx.HTTPError) as e:
                last_err = f"{type(e).__name__}: {e}"
            except Exception as e:
                last_err = f"parse_error: {type(e).__name__}: {e}"
        # Backoff outside the semaphore (don't hold capacity while sleeping)
        if attempt <= retry:
            backoff = min(30.0, delay * (2 ** attempt))
            await asyncio.sleep(backoff)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return {
        "namespace": ns,
        "slug": slug,
        "title": item.get("title"),
        "status": "failed",
        "elapsed_ms": elapsed_ms,
        "attempts": attempt,
        "error": last_err,
    }


def _load_existing_report() -> dict[tuple[str, str], dict]:
    if not REPORT_JSON.exists():
        return {}
    data = json.loads(REPORT_JSON.read_text())
    return {(r["namespace"], r["slug"]): r for r in data}


async def fetch_all(items: list[dict], args) -> None:
    raw_dir = RAW_DIR
    raw_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(args.concurrency)
    delay = args.delay
    retry = args.retry

    # Existing report — preserve unchanged entries on partial runs
    existing = _load_existing_report()

    total = len(items)
    if args.limit:
        items = items[: args.limit]
        print(f"--limit {args.limit}: fetching {len(items)} of {total} items")
    else:
        print(f"fetching {total} items (concurrency={args.concurrency}, retry={retry}, delay={delay}s)")

    results: dict[tuple[str, str], dict] = dict(existing)
    done_count = 0
    ok_count = 0
    fail_count = 0
    nf_count = 0

    async with httpx.AsyncClient(http2=False, limits=httpx.Limits(max_connections=args.concurrency * 2)) as client:
        tasks = [
            asyncio.create_task(fetch_one(client, sem, it, raw_dir, retry, delay))
            for it in items
        ]
        for fut in asyncio.as_completed(tasks):
            rec = await fut
            results[(rec["namespace"], rec["slug"])] = rec
            done_count += 1
            if rec["status"] == "ok":
                ok_count += 1
            elif rec["status"] == "not_found":
                nf_count += 1
            else:
                fail_count += 1
            if done_count % 20 == 0 or done_count == len(items):
                pct = done_count * 100 // len(items)
                marker = "✓" if rec["status"] == "ok" else ("∅" if rec["status"] == "not_found" else "✗")
                print(
                    f"  [{done_count:>3}/{len(items)} {pct:>3}%] "
                    f"ok={ok_count} fail={fail_count} 404={nf_count}  "
                    f"{marker} {rec['namespace']}/{rec['slug']}"
                )
                # Periodic flush
                _flush_report(results)

    _flush_report(results)
    _flush_failed(results)
    print()
    print(f"=== fetch complete ===")
    print(f"  total processed: {done_count}")
    print(f"  ok:        {ok_count}")
    print(f"  not_found: {nf_count}")
    print(f"  failed:    {fail_count}")
    print(f"  report:    {REPORT_JSON}")
    if fail_count:
        print(f"  failed list: {FAILED_JSON} (use --resume to retry)")


def _flush_report(results: dict[tuple[str, str], dict]) -> None:
    records = sorted(results.values(), key=lambda r: (r["namespace"], r["slug"]))
    REPORT_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _flush_failed(results: dict[tuple[str, str], dict]) -> None:
    failed = [r for r in results.values() if r["status"] not in ("ok", "not_found")]
    FAILED_JSON.write_text(json.dumps(failed, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_fetch(args) -> int:
    if not FETCH_LIST.exists():
        print(f"ERROR: {FETCH_LIST} missing. Run `menu` first.", file=sys.stderr)
        return 2
    items = json.loads(FETCH_LIST.read_text())
    if args.resume:
        if not FAILED_JSON.exists():
            print(f"ERROR: --resume requires {FAILED_JSON}", file=sys.stderr)
            return 2
        failed_keys = {(r["namespace"], r["slug"]) for r in json.loads(FAILED_JSON.read_text())}
        items = [it for it in items if (it["namespace"], it["slug"]) in failed_keys]
        print(f"--resume: {len(items)} previously failed items")
    asyncio.run(fetch_all(items, args))
    return 0


# --------------- report subcommand ---------------


def cmd_report(args) -> int:
    if not REPORT_JSON.exists():
        print(f"ERROR: {REPORT_JSON} missing. Run `fetch` first.", file=sys.stderr)
        return 2
    records = json.loads(REPORT_JSON.read_text())
    fetch_list = json.loads(FETCH_LIST.read_text())
    expected_by_ns: dict[str, int] = {}
    for it in fetch_list:
        expected_by_ns[it["namespace"]] = expected_by_ns.get(it["namespace"], 0) + 1

    ok = [r for r in records if r["status"] == "ok"]
    nf = [r for r in records if r["status"] == "not_found"]
    failed = [r for r in records if r["status"] not in ("ok", "not_found")]

    by_ns_ok: dict[str, int] = {}
    by_ns_total: dict[str, int] = {}
    by_module_ok: dict[str, int] = {}
    for r in records:
        ns = r["namespace"]
        by_ns_total[ns] = by_ns_total.get(ns, 0) + 1
        if r["status"] == "ok":
            by_ns_ok[ns] = by_ns_ok.get(ns, 0) + 1
            mp = r.get("module_path") or "(root)"
            top = mp.split(" / ")[0] if mp else "(root)"
            by_module_ok[top] = by_module_ok.get(top, 0) + 1

    total_html = sum(r.get("html_bytes", 0) for r in ok)
    total_md = sum(r.get("md_bytes", 0) for r in ok)
    total_imgs = sum(r.get("image_count", 0) for r in ok)
    avg_elapsed = (sum(r.get("elapsed_ms", 0) for r in ok) // max(1, len(ok)))

    # Failure reason top-N
    from collections import Counter
    err_counter = Counter()
    for r in failed:
        e = r.get("error") or "unknown"
        err_counter[e.split(":")[0]] += 1

    lines: list[str] = []
    lines.append("# open.dingtalk.com 抓取报告\n")
    lines.append(f"> 生成时间：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    lines.append("")
    lines.append("## 汇总\n")
    lines.append(f"- 处理总数：**{len(records)}** / 清单 {sum(expected_by_ns.values())}")
    lines.append(f"- ✅ 成功：**{len(ok)}**")
    lines.append(f"- ∅ 404 / 410（slug 已失效）：{len(nf)}")
    lines.append(f"- ❌ 失败：{len(failed)}")
    lines.append("")
    lines.append(f"- HTML 总下载：{total_html / 1024 / 1024:.2f} MB")
    lines.append(f"- Markdown 总产出：{total_md / 1024 / 1024:.2f} MB")
    lines.append(f"- 远端图片引用：{total_imgs}")
    lines.append(f"- 平均单篇耗时：{avg_elapsed} ms")
    lines.append("")
    lines.append("## 按 namespace 对账\n")
    lines.append("| namespace | 期望 | 成功 | 偏差 |")
    lines.append("|---|---:|---:|---:|")
    for ns in sorted(expected_by_ns):
        exp = expected_by_ns[ns]
        got = by_ns_ok.get(ns, 0)
        diff = got - exp
        marker = "✅" if diff == 0 else ("⚠️" if abs(diff) / exp <= 0.02 else "🚨")
        lines.append(f"| {ns} | {exp} | {got} | {marker} {diff:+d} |")
    lines.append("")
    lines.append("## 按顶级模块（成功篇数）\n")
    for m, n in sorted(by_module_ok.items(), key=lambda x: -x[1]):
        lines.append(f"- {m}: **{n}**")
    lines.append("")
    if failed:
        lines.append("## 失败原因 top-N\n")
        for err, n in err_counter.most_common(10):
            lines.append(f"- `{err}`: {n}")
        lines.append("")
        lines.append("## 失败明细（前 20 条）\n")
        for r in failed[:20]:
            lines.append(f"- `{r['namespace']}/{r['slug']}` — {r.get('error', '?')}")
        lines.append("")
    if nf:
        lines.append("## slug 失效（404/410）\n")
        for r in nf[:30]:
            lines.append(f"- `{r['namespace']}/{r['slug']}` ({r.get('title', '')})")
        if len(nf) > 30:
            lines.append(f"- … 共 {len(nf)} 条，详见 report.json")
        lines.append("")
    report_md = OUT_DIR / "report.md"
    report_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"report → {report_md}")
    print(f"  ok={len(ok)} not_found={len(nf)} failed={len(failed)}")
    return 0


# --------------- entry ---------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    sp = p.add_subparsers(dest="cmd", required=True)

    pm = sp.add_parser("menu", help="Build fetch_list.json")
    pm.add_argument("--guide-md", default=str(DEFAULT_GUIDE),
                    help=f"Path to guide markdown (default: {DEFAULT_GUIDE})")
    pm.set_defaults(func=cmd_menu)

    pf = sp.add_parser("fetch", help="Batch fetch raw markdown")
    pf.add_argument("--concurrency", type=int, default=4)
    pf.add_argument("--retry", type=int, default=3)
    pf.add_argument("--delay", type=float, default=0.5,
                    help="Sleep seconds after each request (default 0.5)")
    pf.add_argument("--resume", action="store_true",
                    help="Re-fetch only items in failed.json from previous run")
    pf.add_argument("--limit", type=int, default=0,
                    help="Stop after first N items in fetch_list (0 = all)")
    pf.set_defaults(func=cmd_fetch)

    pr = sp.add_parser("report", help="Generate report.md from report.json")
    pr.set_defaults(func=cmd_report)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
