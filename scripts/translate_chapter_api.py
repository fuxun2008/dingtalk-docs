"""translate_chapter_api.py — 跑一个章节，调 Fluxion API 翻译所有 PNG（不处理 GIF）。

用法:
  python scripts/translate_chapter_api.py aitable/forms/form-basics --langs en
  python scripts/translate_chapter_api.py aitable/forms/form-basics --langs en --limit 2
  python scripts/translate_chapter_api.py aitable/forms/form-basics --langs en --skip-existing
  python scripts/translate_chapter_api.py aitable/forms/form-basics --langs en --only image_xxx.png

行为:
  - 源: zh/<slug>/images/*.png（**不**碰 *.gif）
  - 目标: en → <slug>/images/<name>.png; ja → ja/<slug>/images/<name>.png
  - 失败: log + 报告里记 fail，继续下一张（不中断批次）
  - --skip-existing: 目标 PNG 与 zh 同源（md5 同）则视为未译，重译；否则跳过
  - 串行；每次调用之间 sleep 1s 防 rate-limit
  - 报告路径: scripts/output/<flat-slug>/report_v3.json
  - 对照图: scripts/output/v3_visual/<lang>/<name>.compare.png（zh / 目标 横向拼接）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image

# 允许 from-script 直接运行
sys.path.insert(0, str(Path(__file__).parent))
from translate_image_api import (  # noqa: E402
    download_to,
    require_api_key,
    translate_image,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_LANGS = ("en", "ja")
SLEEP_BETWEEN_CALLS_S = 1.0


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def target_path(slug: str, lang: str, image_name: str) -> Path:
    if lang == "en":
        return REPO_ROOT / slug / "images" / image_name
    return REPO_ROOT / lang / slug / "images" / image_name


def list_zh_pngs(slug: str) -> list[Path]:
    src_dir = REPO_ROOT / "zh" / slug / "images"
    if not src_dir.is_dir():
        raise SystemExit(f"Source dir not found: {src_dir}")
    return sorted(p for p in src_dir.iterdir() if p.suffix.lower() == ".png")


def make_compare(zh_png: Path, target_png: Path, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    a = Image.open(zh_png).convert("RGB")
    b = Image.open(target_png).convert("RGB")
    h = max(a.height, b.height)
    canvas = Image.new("RGB", (a.width + b.width + 12, h), (240, 240, 240))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (a.width + 12, 0))
    canvas.save(out_path, "PNG", optimize=True)


def report_path(slug: str) -> Path:
    flat = slug.replace("/", "_")
    return REPO_ROOT / "scripts" / "output" / flat / "report_v3.json"


def visual_dir(lang: str) -> Path:
    return REPO_ROOT / "scripts" / "output" / "v3_visual" / lang


def process_one(
    zh_png: Path,
    slug: str,
    lang: str,
    api_key: str,
    *,
    storage: str,
    skip_existing: bool,
) -> dict:
    name = zh_png.name
    target = target_path(slug, lang, name)
    record: dict = {
        "image": name,
        "lang": lang,
        "src": str(zh_png.relative_to(REPO_ROOT)),
        "target": str(target.relative_to(REPO_ROOT)) if target.is_relative_to(REPO_ROOT) else str(target),
    }

    if skip_existing and target.exists():
        if md5_of(target) != md5_of(zh_png):
            record.update(status="skipped_existing", ok=True)
            return record

    started = time.time()
    api_result = translate_image(zh_png, lang, api_key=api_key, storage=storage)
    record["api_elapsed_s"] = api_result.get("elapsed_s")
    record["api_status"] = api_result.get("status")

    if not api_result.get("ok"):
        record.update(status="fail_api", ok=False, error=api_result.get("error"))
        return record

    url = api_result["url"]
    record["url"] = url

    try:
        bytes_written = download_to(url, target)
        record["bytes"] = bytes_written
    except Exception as e:
        record.update(status="fail_download", ok=False, error=f"{type(e).__name__}: {e}")
        return record

    try:
        src_size = Image.open(zh_png).size
        out_size = Image.open(target).size
        record["src_size"] = list(src_size)
        record["out_size"] = list(out_size)
        if src_size != out_size:
            record["warn_size_mismatch"] = True
    except Exception as e:
        record["warn_size_check"] = f"{type(e).__name__}: {e}"

    try:
        compare_path = visual_dir(lang) / f"{zh_png.stem}.compare.png"
        make_compare(zh_png, target, compare_path)
        record["compare"] = str(compare_path.relative_to(REPO_ROOT))
    except Exception as e:
        record["warn_compare"] = f"{type(e).__name__}: {e}"

    record["total_elapsed_s"] = round(time.time() - started, 2)
    record.update(status="ok", ok=True)
    return record


def run(
    slug: str,
    langs: Iterable[str],
    *,
    limit: int | None,
    only: list[str] | None,
    skip_existing: bool,
    storage: str,
) -> int:
    api_key = require_api_key()
    zh_pngs = list_zh_pngs(slug)
    if only:
        only_set = set(only)
        zh_pngs = [p for p in zh_pngs if p.name in only_set]
    if limit is not None:
        zh_pngs = zh_pngs[:limit]
    if not zh_pngs:
        print("[!] no PNGs match selection")
        return 1

    print(f"[*] chapter={slug}  langs={list(langs)}  count={len(zh_pngs)}  storage={storage}")
    records: list[dict] = []
    started_at = datetime.now().isoformat(timespec="seconds")
    overall_start = time.time()

    fail_n = 0
    for lang in langs:
        if lang not in SUPPORTED_LANGS:
            print(f"[!] skip unsupported lang: {lang}")
            continue
        print(f"\n=== lang={lang} ===")
        for idx, zh_png in enumerate(zh_pngs, 1):
            print(f"  [{idx:02d}/{len(zh_pngs)}] {zh_png.name} ... ", end="", flush=True)
            rec = process_one(
                zh_png,
                slug,
                lang,
                api_key,
                storage=storage,
                skip_existing=skip_existing,
            )
            records.append(rec)
            if rec.get("ok"):
                tag = "skip" if rec.get("status") == "skipped_existing" else "ok"
                print(f"{tag}  ({rec.get('total_elapsed_s', rec.get('api_elapsed_s'))}s)")
            else:
                fail_n += 1
                print(f"FAIL  {rec.get('error')}")
            time.sleep(SLEEP_BETWEEN_CALLS_S)

    out = report_path(slug)
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "version": "v3",
        "slug": slug,
        "langs": list(langs),
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
        "total_elapsed_s": round(time.time() - overall_start, 2),
        "ok_count": sum(1 for r in records if r.get("ok")),
        "fail_count": fail_n,
        "skip_count": sum(1 for r in records if r.get("status") == "skipped_existing"),
        "records": records,
    }
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[*] report: {out.relative_to(REPO_ROOT)}")
    print(f"[*] ok={summary['ok_count']}  fail={summary['fail_count']}  skip={summary['skip_count']}")
    return 0 if fail_n == 0 else 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate a chapter's PNGs via Fluxion API")
    parser.add_argument("slug", help="chapter slug under zh/, e.g. aitable/forms/form-basics")
    parser.add_argument("--langs", nargs="+", default=["en"], choices=list(SUPPORTED_LANGS))
    parser.add_argument("--limit", type=int, default=None, help="only process first N PNGs")
    parser.add_argument("--only", nargs="+", default=None, help="filter by file name(s)")
    parser.add_argument("--skip-existing", action="store_true", help="skip targets that already differ from zh source")
    parser.add_argument("--storage", default="dingtalk", choices=["dingtalk", "raw", "cdn"])
    args = parser.parse_args()
    rc = run(
        slug=args.slug.strip("/"),
        langs=args.langs,
        limit=args.limit,
        only=args.only,
        skip_existing=args.skip_existing,
        storage=args.storage,
    )
    sys.exit(rc)


if __name__ == "__main__":
    main()
