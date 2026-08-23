"""阶段 1：扫描全仓 mdx，提取并分类所有图/媒体引用 → occurrences.json + 摘要。

用法：
    python scripts/cdn_migrate/discover.py            # 全量扫描
    python scripts/cdn_migrate/discover.py --summary  # 只打印摘要（复用已有 occurrences.json）
"""
from __future__ import annotations

import argparse
from collections import Counter

import common as C


def scan() -> dict:
    occurrences: list[dict] = []
    for path in C.iter_mdx_files():
        rel = str(path.relative_to(C.REPO_ROOT))
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        for kind, raw in C.extract_refs(text):
            klass = C.classify(raw)
            occurrences.append({
                "file": rel,
                "ref_kind": kind,          # md | img | frame
                "raw": raw,
                "class": klass,            # migrate | local | skip | video | leave | other | local-video
                "host": C.host_of(raw),
                "ext": C.ext_of(raw),
                "signed": C.is_signed(raw),
            })
    return {"occurrences": occurrences, "counts": summarize(occurrences)}


def summarize(occ: list[dict]) -> dict:
    by_class = Counter(o["class"] for o in occ)
    migrate = [o for o in occ if o["class"] == "migrate"]
    local = [o for o in occ if o["class"] == "local"]
    return {
        "total_occurrences": len(occ),
        "by_class": dict(by_class),
        "migrate_unique": len({o["raw"] for o in migrate}),
        "migrate_signed_unique": len({o["raw"] for o in migrate if o["signed"]}),
        "local_unique": len({C.strip_query(o["raw"]) for o in local}),
        "migrate_by_host": dict(Counter(o["host"] for o in migrate)),
        "files_touched": len({o["file"] for o in occ if o["class"] in ("migrate", "local")}),
    }


def print_summary(counts: dict) -> None:
    print("=" * 60)
    print("图/媒体引用发现摘要")
    print("=" * 60)
    print(f"总引用数：{counts['total_occurrences']}")
    print("\n按分类：")
    for k, v in sorted(counts["by_class"].items(), key=lambda x: -x[1]):
        print(f"  {k:14s} {v}")
    print(f"\n待迁远程唯一 URL：{counts['migrate_unique']}"
          f"（其中签名 {counts['migrate_signed_unique']}，Phase A 优先）")
    print(f"待迁本地唯一文件：{counts['local_unique']}")
    print(f"涉及 mdx 文件：{counts['files_touched']}")
    print("\n待迁远程按 host：")
    for h, v in sorted(counts["migrate_by_host"].items(), key=lambda x: -x[1]):
        print(f"  {h:45s} {v}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--summary", action="store_true", help="仅读已有 occurrences.json 打印摘要")
    args = ap.parse_args()

    out_path = C.OUT_DIR / "occurrences.json"
    if args.summary:
        data = C.load_json(out_path, None)
        if not data:
            print("无 occurrences.json，请先跑 discover。")
            return
        print_summary(data["counts"])
        return

    data = scan()
    C.save_json(out_path, data)
    print_summary(data["counts"])
    print(f"\n已写入 {out_path.relative_to(C.REPO_ROOT)}")


if __name__ == "__main__":
    main()
