#!/usr/bin/env python3
"""
translate-image.py — UI screenshot text translator (Chinese → English).

Two-phase workflow:

  1. extract    Run PaddleOCR on a (or directory of) image(s); emit a JSON
                with detected bbox + Chinese text + an empty `en` field.
                Claude fills the `en` fields by hand for terminology accuracy.

  2. render     Read filled JSON; for each bbox where `en` is non-empty,
                erase the original Chinese pixels by sampling the surrounding
                edge color and rewriting the English at an auto-scaled font
                size that fits the bbox. Resolution is preserved.

Examples:
  ./translate-image.py extract input.png        --out input.json
  ./translate-image.py render  input.png input.json --out output.png

Single-image first; batch later.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter


# --- Font discovery (macOS-first, with sensible fallbacks) -------------------

CANDIDATE_FONTS = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/SFNS.ttf",
    "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in CANDIDATE_FONTS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


# --- OCR (PaddleOCR) ---------------------------------------------------------


def run_ocr(image_path: Path) -> list[dict]:
    """Return list of {box: [[x,y]*4], text: str, score: float}."""
    from paddleocr import PaddleOCR  # lazy: avoid import cost in render mode

    ocr = PaddleOCR(use_textline_orientation=True, lang="ch")
    raw = ocr.predict(str(image_path))
    items: list[dict] = []
    for page in raw or []:
        # New API returns dict-like objects with rec_polys/rec_texts/rec_scores
        polys = page.get("rec_polys", []) or page.get("dt_polys", [])
        texts = page.get("rec_texts", [])
        scores = page.get("rec_scores", [])
        for i in range(len(texts)):
            box = polys[i] if i < len(polys) else []
            items.append({
                "box": [[float(p[0]), float(p[1])] for p in box],
                "text": texts[i],
                "score": float(scores[i]) if i < len(scores) else 0.0,
            })
    return items


# --- Geometry helpers --------------------------------------------------------


def bbox_rect(box: list[list[float]]) -> tuple[int, int, int, int]:
    xs = [p[0] for p in box]
    ys = [p[1] for p in box]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def median_edge_color(img: Image.Image, rect: tuple[int, int, int, int], pad: int = 3) -> tuple[int, int, int]:
    """Sample a thin frame outside the rect and return the median RGB."""
    x0, y0, x1, y1 = rect
    W, H = img.size
    fx0 = max(0, x0 - pad)
    fy0 = max(0, y0 - pad)
    fx1 = min(W, x1 + pad)
    fy1 = min(H, y1 + pad)
    region = img.crop((fx0, fy0, fx1, fy1)).convert("RGB")
    px = region.load()
    samples: list[tuple[int, int, int]] = []
    rw, rh = region.size
    for x in range(rw):
        for y in range(rh):
            inner_x = x + fx0
            inner_y = y + fy0
            if x0 <= inner_x < x1 and y0 <= inner_y < y1:
                continue
            samples.append(px[x, y])
    if not samples:
        return (255, 255, 255)
    samples.sort()
    return samples[len(samples) // 2]


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


# --- Render ------------------------------------------------------------------


def fit_font_size(text: str, max_w: int, max_h: int) -> ImageFont.FreeTypeFont:
    """Pick a font size where text fits within (max_w, max_h)."""
    lo, hi = 8, max(10, int(max_h * 1.2))
    best = load_font(lo)
    while lo <= hi:
        mid = (lo + hi) // 2
        f = load_font(mid)
        bbox = f.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        if tw <= max_w and th <= max_h:
            best = f
            lo = mid + 1
        else:
            hi = mid - 1
    return best


def render_translations(image_path: Path, json_path: Path, out_path: Path) -> None:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    rendered = 0
    skipped = 0
    for item in items:
        en = (item.get("en") or "").strip()
        if not en:
            skipped += 1
            continue
        box = item["box"]
        rect = bbox_rect(box)
        x0, y0, x1, y1 = rect
        bw, bh = max(1, x1 - x0), max(1, y1 - y0)

        bg = median_edge_color(img, rect, pad=3)
        draw.rectangle([x0, y0, x1, y1], fill=bg)

        # Target ~80% of bbox width to avoid edge-kissing
        target_w = int(bw * 0.95)
        target_h = int(bh * 0.95)
        font = fit_font_size(en, target_w, target_h)

        tb = font.getbbox(en)
        tw = tb[2] - tb[0]
        th = tb[3] - tb[1]
        cx = x0 + (bw - tw) // 2 - tb[0]
        cy = y0 + (bh - th) // 2 - tb[1]

        # Pick text color contrasting with background
        fg = (23, 26, 29) if luminance(bg) > 140 else (250, 250, 250)
        draw.text((cx, cy), en, font=font, fill=fg)
        rendered += 1

    img.save(out_path)
    print(f"rendered={rendered} skipped={skipped} → {out_path}")


# --- Extract -----------------------------------------------------------------


def extract_image(image_path: Path, out_path: Path) -> None:
    items = run_ocr(image_path)
    payload = {
        "image": str(image_path),
        "items": [
            {"id": i, "box": it["box"], "zh": it["text"], "score": it["score"], "en": ""}
            for i, it in enumerate(items)
        ],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"extracted {len(items)} text blocks → {out_path}")


# --- CLI ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Translate text inside UI screenshots.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="Run OCR and dump JSON template.")
    e.add_argument("image", type=Path)
    e.add_argument("--out", type=Path, required=True)

    r = sub.add_parser("render", help="Apply translations from JSON to image.")
    r.add_argument("image", type=Path)
    r.add_argument("json", type=Path)
    r.add_argument("--out", type=Path, required=True)

    args = ap.parse_args(argv)

    if args.cmd == "extract":
        extract_image(args.image, args.out)
    elif args.cmd == "render":
        render_translations(args.image, args.json, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
