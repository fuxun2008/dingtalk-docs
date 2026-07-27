#!/usr/bin/env python3
"""02_crawl.py — 按 toc.json 抓取宜搭用户手册静态 HTML 到 staging 目录。

用法: python3 scripts/import_yida/02_crawl.py [--force]
产物: scripts/import_yida/staging/html/<slug>.html + crawl-report.json
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

BASE = Path(__file__).parent
TOC = json.loads((BASE / "output" / "toc.json").read_text())
STAGING = BASE / "staging" / "html"
STAGING.mkdir(parents=True, exist_ok=True)
FORCE = "--force" in sys.argv

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) dingtalk-docs-importer"}
SITE = "https://docs.aliwork.com/docs/yida_support/"
# 环境里可能残留失效的本地代理配置，直连目标站
SESSION = requests.Session()
SESSION.trust_env = False


def fetch(entry):
    slug = entry["slug"]
    # slug 可能含层级路径，落盘文件名用末段（已验证全局唯一）
    out = STAGING / f"{slug.split('/')[-1]}.html"
    if out.exists() and not FORCE:
        return slug, "cached", out.stat().st_size
    url = SITE + slug
    last_err = None
    for attempt in range(3):
        try:
            r = SESSION.get(url, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                out.write_text(r.text)
                return slug, "ok", len(r.text)
            last_err = f"HTTP {r.status_code}"
            if r.status_code == 404:
                break
        except Exception as e:  # noqa: BLE001
            last_err = str(e)
        time.sleep(2 * (attempt + 1))
    return slug, f"fail: {last_err}", 0


def main():
    results = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futs = {pool.submit(fetch, e): e for e in TOC}
        done = 0
        for fut in as_completed(futs):
            slug, status, size = fut.result()
            results[slug] = {"status": status, "size": size}
            done += 1
            if done % 50 == 0 or status.startswith("fail"):
                print(f"[{done}/{len(TOC)}] {slug}: {status}")
    fails = {k: v for k, v in results.items() if v["status"].startswith("fail")}
    report = {
        "total": len(TOC),
        "ok": sum(1 for v in results.values() if v["status"] == "ok"),
        "cached": sum(1 for v in results.values() if v["status"] == "cached"),
        "failed": fails,
    }
    (BASE / "output" / "crawl-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "failed"}, ensure_ascii=False))
    if fails:
        print("FAILED:", list(fails)[:20])


if __name__ == "__main__":
    main()
