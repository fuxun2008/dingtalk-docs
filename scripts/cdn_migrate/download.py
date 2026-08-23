"""阶段 2：把待迁远程图下载到本地临时目录 → download-cache.json（可断点续跑）。

按引用中的原始 URL（含 ?x-oss-process= 等 query）原样下载，使再托管的图与页面
当前显示一致。校验字节非空且非 HTML 错误页，计算内容 sha256 供后续去重。

用法：
    python scripts/cdn_migrate/download.py [--concurrency 8] [--limit N] [--retry-failed]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import urllib.request
import urllib.error

import common as C

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")
_IMG_MAGIC = (b"\x89PNG", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"RIFF", b"<svg", b"<?xml")


def _disk_name(url: str) -> str:
    ext = C.ext_of(url) or "bin"
    return f"{hashlib.sha1(url.encode()).hexdigest()[:20]}.{ext}"


def _looks_like_image(data: bytes) -> bool:
    if not data:
        return False
    head = data[:16].lstrip()
    if head[:5].lower() == b"<html" or head[:9].lower() == b"<!doctype":
        return False
    return True  # 宽松：OSS 常回 octet-stream；靠 magic 兜底但不强制


def download_one(url: str) -> dict:
    dest = C.DOWNLOADS_DIR / _disk_name(url)
    if dest.exists() and dest.stat().st_size > 0:
        data = dest.read_bytes()
        return {"status": "ok", "path": str(dest), "bytes": len(data),
                "sha256": "sha256:" + hashlib.sha256(data).hexdigest(), "httpCode": 200, "cached": True}
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            code = r.status
            data = r.read()
    except urllib.error.HTTPError as e:
        return {"status": "failed", "error": f"HTTP {e.code}", "httpCode": e.code}
    except Exception as e:
        return {"status": "failed", "error": str(e), "httpCode": 0}
    if not _looks_like_image(data):
        return {"status": "failed", "error": "非图片内容（疑似 HTML 错误页）", "httpCode": code, "bytes": len(data)}
    C.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"status": "ok", "path": str(dest), "bytes": len(data),
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest(), "httpCode": code}


def collect_remote_urls() -> list[str]:
    occ = C.load_json(C.OUT_DIR / "occurrences.json", {}).get("occurrences", [])
    return sorted({o["raw"] for o in occ if o["class"] == "migrate"})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--retry-failed", action="store_true", help="重试上次失败的 URL")
    args = ap.parse_args()

    cache_path = C.OUT_DIR / "download-cache.json"
    cache: dict[str, dict] = C.load_json(cache_path, {})
    urls = collect_remote_urls()
    if args.limit > 0:
        urls = urls[:args.limit]

    def pending(u: str) -> bool:
        c = cache.get(u)
        if c is None:
            return True
        if c.get("status") == "ok":
            return False
        return bool(args.retry_failed)

    todo = [u for u in urls if pending(u)]
    print(f"[download] 唯一远程 URL {len(urls)}，待下载 {len(todo)}，并发 {args.concurrency}")

    done = ok = fail = 0
    with cf.ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(download_one, u): u for u in todo}
        for fut in cf.as_completed(futs):
            u = futs[fut]
            cache[u] = fut.result()
            done += 1
            if cache[u]["status"] == "ok":
                ok += 1
            else:
                fail += 1
            if done % 100 == 0:
                print(f"  [{done}/{len(todo)}] ok={ok} fail={fail}")
                C.save_json(cache_path, cache)

    C.save_json(cache_path, cache)
    total_ok = sum(1 for c in cache.values() if c.get("status") == "ok")
    print(f"[download] 完成本轮 ok={ok} fail={fail}；累计成功 {total_ok}/{len(urls)}")
    if fail:
        fails = {u: cache[u] for u in cache if cache[u].get("status") != "ok"}
        C.save_json(C.OUT_DIR / "download-failures.json", fails)
        print(f"[download] 失败清单 → download-failures.json（{len(fails)} 条）")


if __name__ == "__main__":
    main()
