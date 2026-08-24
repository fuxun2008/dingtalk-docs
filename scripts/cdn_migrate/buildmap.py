"""阶段 4：join manifest-origin.json + upload-results.json → url-map.json（old→new）。

upload-results.json 来自 tools/review/scripts/cdn-api-upload.mjs，格式：
    {"ok": bool, "total": N, "completed": N, "items": [{"id": <key>, "cdnUrl": <url>} | {"id": <key>, "error": <msg>}]}

每个 origin.source（远程原始 URL 或本地 /... 引用字符串）映射到其 sha256 对应的 CDN URL。

用法：
    python scripts/cdn_migrate/buildmap.py
"""
from __future__ import annotations

import common as C


def main() -> None:
    origin_manifest = C.load_json(C.OUT_DIR / "manifest-origin.json", {})
    upload_result = C.load_json(C.OUT_DIR / "upload-results.json", {})
    results_by_id = {r["id"]: r for r in upload_result.get("items", [])}

    items: list[dict] = []
    missing_upload = 0
    for it in origin_manifest.get("items", []):
        r = results_by_id.get(it["key"])
        if not r or not r.get("cdnUrl"):
            missing_upload += 1
            continue
        new = r["cdnUrl"]
        kind = "both" if len(it["origin"]["types"]) > 1 else it["origin"]["types"][0]
        for src in it["origin"]["sources"]:
            items.append({"old": src, "new": new, "key": it["key"], "kind": kind})

    # old 去重（同一字符串只留一条）
    seen: dict[str, dict] = {}
    for m in items:
        seen.setdefault(m["old"], m)
    final = sorted(seen.values(), key=lambda x: x["old"])

    url_map = {
        "product": "cdn-migrate",
        "counts": {
            "manifest_items": len(origin_manifest.get("items", [])),
            "uploaded_ok": len(origin_manifest.get("items", [])) - missing_upload,
            "missing_upload": missing_upload,
            "map_entries": len(final),
        },
        "items": final,
    }
    C.save_json(C.OUT_DIR / "url-map.json", url_map)
    print(f"[buildmap] 映射条目 {len(final)}（未上传 {missing_upload} 条 manifest item 跳过）")
    print(f"[buildmap] → url-map.json")


if __name__ == "__main__":
    main()
