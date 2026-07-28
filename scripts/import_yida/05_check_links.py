#!/usr/bin/env python3
"""05_check_links.py — 宜搭中文文档外链清点 + 死链探测。

扫描 zh/yida/**/*.mdx 的 markdown 链接与 JSX href 属性，去重后并发探测，
产出 output/linkcheck.json（url → {status, final, verdict, files}）。

判定规则:
  dead  : DNS/连接失败、超时(重试后)、404/410、语雀 404 页
  alive : 2xx/3xx、403/405/429（反爬类，视为可访问）
"""
import json
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE = Path(__file__).parent
REPO = BASE.parent.parent

MD_LINK = re.compile(r"(?<!!)\[([^\]]*)\]\((https?://[^)\s]+)\)")
HREF = re.compile(r'href="(https?://[^"]+)"')

occurrences = {}  # url -> [(file, text)]
for f in sorted((REPO / "zh/yida").rglob("*.mdx")):
    rel = str(f.relative_to(REPO))
    t = f.read_text()
    for m in MD_LINK.finditer(t):
        occurrences.setdefault(m.group(2), []).append((rel, m.group(1)[:60]))
    for m in HREF.finditer(t):
        occurrences.setdefault(m.group(1), []).append((rel, "(href attr)"))

print(f"unique urls: {len(occurrences)}")

session = requests.Session()
session.trust_env = False
session.headers["User-Agent"] = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"
)

ALIVE_CODES = {403, 405, 429, 999}


def probe(url):
    last_err = None
    for _ in range(2):
        try:
            r = session.get(url, timeout=(6, 14), allow_redirects=True, stream=True)
            body_head = ""
            try:
                body_head = next(r.iter_content(4096, decode_unicode=True), "") or ""
            except Exception:
                pass
            r.close()
            status = r.status_code
            final = r.url
            if status in (404, 410):
                return {"status": status, "final": final, "verdict": "dead"}
            # 语雀删除页返回 200 但正文是 404 提示
            if "yuque.com" in final and ("页面没有找到" in body_head or "404" in final):
                return {"status": status, "final": final, "verdict": "dead"}
            if status >= 400 and status not in ALIVE_CODES:
                return {"status": status, "final": final, "verdict": "dead"}
            return {"status": status, "final": final, "verdict": "alive"}
        except (requests.exceptions.ConnectionError, socket.gaierror) as e:
            last_err = f"conn:{type(e).__name__}"
        except requests.exceptions.Timeout:
            last_err = "timeout"
        except Exception as e:
            last_err = f"err:{type(e).__name__}"
    return {"status": None, "final": None, "verdict": "dead", "error": last_err}


results = {}
with ThreadPoolExecutor(max_workers=20) as ex:
    futs = {ex.submit(probe, u): u for u in occurrences}
    done = 0
    for fut in as_completed(futs):
        u = futs[fut]
        results[u] = fut.result()
        results[u]["files"] = occurrences[u]
        done += 1
        if done % 100 == 0:
            print(f"  probed {done}/{len(occurrences)}")

dead = {u: r for u, r in results.items() if r["verdict"] == "dead"}
print(f"alive: {len(results) - len(dead)}, dead: {len(dead)}")
for u, r in sorted(dead.items()):
    print(f"  DEAD [{r.get('status')}] {r.get('error', '')} {u[:110]}")

(BASE / "output" / "linkcheck.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=1)
)
print("written output/linkcheck.json")
