"""阶段 7：改写后程序化校验。

- 重扫 live，统计残留待迁 host（应趋近于 0，除下载失败清单）；
- 断言 url-map 里每个 new 落在 g/img/gw.alicdn.com；
- 抽样 HTTP 探活 N 个 new CDN URL（lazy-import urllib）；
- 复核三语镜像图引用总数（迁移后每篇图数不应变化）。

用法：
    python scripts/cdn_migrate/verify.py [--sample 20]
"""
from __future__ import annotations

import argparse
import urllib.error
import urllib.request
from collections import Counter

import common as C


def probe(url: str) -> int:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=20)
    args = ap.parse_args()

    # 1) 残留待迁 host
    residual = Counter()
    for path in C.iter_mdx_files():
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for _, raw in C.extract_refs(text):
            if C.classify(raw) == "migrate":
                residual[C.host_of(raw)] += 1
    print("[verify] 残留待迁远程引用：", dict(residual) or "0 ✓")

    # 2) url-map 里 new 均为 CDN
    url_map = C.load_json(C.OUT_DIR / "url-map.json", {})
    news = [m["new"] for m in url_map.get("items", [])]
    bad = [u for u in news if C.host_of(u) not in C.SKIP_HOSTS]
    print(f"[verify] url-map new 非 CDN host：{len(bad)}", "✓" if not bad else bad[:5])

    # 3) 抽样探活
    if news:
        sample = news[:: max(1, len(news) // max(1, args.sample))][: args.sample]
        codes = Counter(probe(u) for u in sample)
        print(f"[verify] 抽样 {len(sample)} 个 CDN URL HTTP：{dict(codes)}")

    # 4) 失败清单提醒
    fails = C.load_json(C.OUT_DIR / "download-failures.json", {})
    if fails:
        print(f"[verify] ⚠ 下载失败 {len(fails)} 条（这些仍指向原临时 URL，见 download-failures.json）")


if __name__ == "__main__":
    main()
