"""阶段 3：由 download-cache（远程）+ 本地文件构建 manifest.json，按内容 sha256 去重。

相同字节的图（不同 URL、或 remote==local）只保留一个上传条目；其所有原始引用字符串
汇入 origin.sources，供 buildmap 时统一映射到同一 CDN URL。

输出格式对接 tools/review/scripts/cdn-api-upload.mjs 的消费契约：
    {"version": 1, "items": [{"id": <sha256 key>, "path": <绝对路径>, "filename": <文件名>}, ...]}
origin/sources 元数据额外落一份 manifest-origin.json，供 buildmap.py 使用。

用法：
    python scripts/cdn_migrate/dedup.py --kind remote|local|all
"""
from __future__ import annotations

import argparse
import hashlib
import os

import common as C


def _basename_from_url(url: str) -> str:
    bare = C.strip_query(url)
    name = bare.rsplit("/", 1)[-1] or "image"
    return name


def gather_remote(items: dict) -> None:
    """把远程下载成功的图并入 items（key=sha256）。"""
    cache = C.load_json(C.OUT_DIR / "download-cache.json", {})
    occ = C.load_json(C.OUT_DIR / "occurrences.json", {}).get("occurrences", [])
    remote_urls = {o["raw"] for o in occ if o["class"] == "migrate"}
    for url in sorted(remote_urls):
        c = cache.get(url)
        if not c or c.get("status") != "ok":
            continue
        key = c["sha256"]
        it = items.setdefault(key, _new_item(key, c["path"], _basename_from_url(url), c["bytes"]))
        it["origin"]["sources"].append(url)
        if "remote" not in it["origin"]["types"]:
            it["origin"]["types"].append("remote")


def gather_local(items: dict) -> None:
    """把本地图并入 items（key=sha256）。登记所有 /... 引用变体。"""
    occ = C.load_json(C.OUT_DIR / "occurrences.json", {}).get("occurrences", [])
    # raw 引用字符串 → 磁盘文件（去重）
    ref_to_file: dict[str, str] = {}
    for o in occ:
        if o["class"] != "local":
            continue
        p = C.local_ref_to_path(o["raw"])
        if p:
            ref_to_file[o["raw"]] = str(p)
    # 按磁盘文件分组算 sha256
    file_hash: dict[str, str] = {}
    for path in sorted(set(ref_to_file.values())):
        data = open(path, "rb").read()
        file_hash[path] = "sha256:" + hashlib.sha256(data).hexdigest()
    for raw, path in ref_to_file.items():
        key = file_hash[path]
        it = items.setdefault(key, _new_item(key, path, os.path.basename(path), os.path.getsize(path)))
        it["origin"]["sources"].append(raw)
        if "local" not in it["origin"]["types"]:
            it["origin"]["types"].append("local")


def _new_item(key: str, path: str, filename: str, nbytes: int) -> dict:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return {
        "key": key,
        "localPath": os.path.abspath(path),
        "filename": filename,
        "ext": ext,
        "bytes": nbytes,
        "origin": {"types": [], "sources": []},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["remote", "local", "all"], default="all")
    args = ap.parse_args()

    items: dict[str, dict] = {}
    if args.kind in ("remote", "all"):
        gather_remote(items)
    if args.kind in ("local", "all"):
        gather_local(items)

    # 每个 item 的 sources 去重排序
    for it in items.values():
        it["origin"]["sources"] = sorted(set(it["origin"]["sources"]))

    ordered = sorted(items.values(), key=lambda x: x["key"])

    # cdn-api-upload.mjs 消费的上传清单：{version:1, items:[{id,path,filename}]}
    upload_manifest = {
        "version": 1,
        "items": [
            {"id": it["key"], "path": it["localPath"], "filename": it["filename"]}
            for it in ordered
        ],
    }
    C.save_json(C.OUT_DIR / "manifest.json", upload_manifest)

    # origin/sources 元数据另存一份，供 buildmap.py 关联映射
    origin_manifest = {"items": ordered}
    C.save_json(C.OUT_DIR / "manifest-origin.json", origin_manifest)

    n_remote = sum(1 for it in items.values() if "remote" in it["origin"]["types"])
    n_local = sum(1 for it in items.values() if "local" in it["origin"]["types"])
    n_both = sum(1 for it in items.values() if len(it["origin"]["types"]) > 1)
    total_sources = sum(len(it["origin"]["sources"]) for it in items.values())
    print(f"[dedup] 唯一上传条目 {len(items)}（remote {n_remote} / local {n_local} / 重合 {n_both}）")
    print(f"[dedup] 覆盖原始引用字符串 {total_sources} 个")
    print("[dedup] → manifest.json（供 cdn-api-upload.mjs 上传）+ manifest-origin.json（供 buildmap.py）")


if __name__ == "__main__":
    main()
