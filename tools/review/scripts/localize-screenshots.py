#!/usr/bin/env python3
"""Offline Chinese-to-English screenshot localizer for ordinary product UI images."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont


CHINESE_RE = re.compile(r"[\u3400-\u9fff]")
EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
LONG_ID_RE = re.compile(r"(?i)\b(?:[a-z0-9_-]{24,}|\d{12,})\b")
TOKEN_RE = re.compile(r"(?i)(token|secret|access[_ -]?key|authorization)\s*[:=]\s*\S+")
URL_RE = re.compile(r"(?i)https?://[^\s\])}>\"']+")
ACCOUNT_VALUE_RE = re.compile(r"(?i)\b(uid|user[_ -]?id|account[_ -]?id)\s*[:=]\s*\S+")

COMMON_TERMS = {
    "宜搭": "Yida",
    "新建应用": "New Application",
    "创建应用": "Create Application",
    "应用管理": "Application Management",
    "应用设置": "Application Settings",
    "表单管理": "Form Management",
    "新建表单": "New Form",
    "流程表单": "Process Form",
    "普通表单": "Standard Form",
    "数据管理": "Data Management",
    "权限管理": "Permission Management",
    "集成自动化": "Integration & Automation",
    "连接器": "Connector",
    "报表": "Report",
    "工作台": "Workspace",
    "提交": "Submit",
    "取消": "Cancel",
    "确定": "OK",
    "保存": "Save",
    "编辑": "Edit",
    "删除": "Delete",
    "发布": "Publish",
    "预览": "Preview",
    "搜索": "Search",
    "设置": "Settings",
    "详情": "Details",
    "成功": "Success",
    "失败": "Failed",
    "返回": "Back",
    "下一步": "Next",
    "上一步": "Previous",
    "开始": "Home",
    "我的应用": "My Apps",
    "应用中心": "App Center",
    "模板中心": "Template Center",
    "插件中心": "Plugin Center",
    "解决方案": "Solutions",
    "学习&帮助": "Learn & Help",
    "学习＆帮助": "Learn & Help",
    "宜搭平台": "Yida Platform",
    "基础": "Basic",
    "基本信息": "Basic Information",
    "企业效能": "Enterprise Performance",
    "组织管理": "Organization Management",
    "账号授权管理": "Account Authorization",
    "平台权限管理": "Platform Permissions",
    "角色管理": "Role Management",
    "权限矩阵管理": "Permission Matrix",
    "开发者": "Developer",
    "插件管理": "Plugin Management",
    "服务注册": "Service Registration",
    "连接器工厂": "Connector Factory",
    "邮箱管理": "Mailbox Management",
    "消息通知模板": "Message Notification Templates",
    "服务商": "Service Provider",
    "订单中心": "Order Center",
    "应用": "Applications",
    "新建邮箱账号": "New Mailbox Account",
    "邮箱账号": "Mailbox Account",
    "邮箱名称": "Mailbox Name",
    "邮箱类型": "Mailbox Type",
    "测试邮箱": "Test Mailbox",
    "查看文档": "View Documentation",
    "修改时间": "Modified Time",
    "操作": "Actions",
    "密码/授权码": "Password/Authorization Code",
    "搜索": "Search",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parents[3]))
    parser.add_argument("--scope", default="yida")
    parser.add_argument("--source")
    parser.add_argument("--output")
    parser.add_argument("--max-images", type=int, default=0)
    parser.add_argument("--ocr-workers", type=int, default=6)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--repair-quality-failed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def compile_ocr(repo: Path) -> Path:
    source = repo / "tools/review/scripts/ocr-layout.swift"
    binary = repo / "tools/review/.cache/bin/ocr-layout"
    binary.parent.mkdir(parents=True, exist_ok=True)
    if not binary.exists() or binary.stat().st_mtime < source.stat().st_mtime:
        subprocess.run(
            ["swiftc", str(source), "-o", str(binary)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
    return binary


def load_tasks(args: argparse.Namespace, repo: Path) -> list[dict[str, str]]:
    if args.source:
        if not args.output:
            raise SystemExit("--output is required with --source")
        return [{"id": Path(args.source).stem, "source": args.source, "output": args.output}]
    state_path = repo / f"tools/review/.cache/image-automation/{args.scope}.json"
    state = json.loads(state_path.read_text())
    tasks = []
    for item in state["items"]:
        source = item.get("sourcePath")
        output = item.get("outputPath")
        if args.repair_quality_failed:
            if item.get("status") != "quality_failed" or not output or not Path(output).exists():
                continue
            tasks.append({"id": item["id"], "source": output, "output": output})
            continue
        if item.get("status") not in {"prepared", "failed", "generating"} or not source or not output:
            continue
        if not Path(source).exists():
            continue
        if Path(output).exists() and not args.overwrite:
            continue
        tasks.append({"id": item["id"], "source": source, "output": output})
    return tasks[: args.max_images or None]


def scan_chunk(binary: Path, tasks: list[dict[str, str]]) -> list[dict[str, Any]]:
    result = subprocess.run(
        [str(binary), *[task["source"] for task in tasks]],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def scan_all(
    binary: Path,
    tasks: list[dict[str, str]],
    workers: int,
    cache_path: Path,
) -> dict[str, dict[str, Any]]:
    scanned: dict[str, dict[str, Any]] = {}
    if cache_path.exists():
        try:
            scanned = json.loads(cache_path.read_text())
        except (OSError, json.JSONDecodeError):
            scanned = {}
    def cache_matches(task: dict[str, str]) -> bool:
        entry = scanned.get(task["source"])
        if not entry:
            return False
        try:
            stat = Path(task["source"]).stat()
        except OSError:
            return False
        return entry.get("_mtimeNs") == stat.st_mtime_ns and entry.get("_size") == stat.st_size

    pending = [task for task in tasks if not cache_matches(task)]
    chunks = [pending[index : index + 8] for index in range(0, len(pending), 8)]
    if not chunks:
        print(f"OCR cache {len(tasks)}/{len(tasks)}", file=sys.stderr, flush=True)
        return scanned
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(scan_chunk, binary, chunk) for chunk in chunks]
        for index, future in enumerate(as_completed(futures), 1):
            for result in future.result():
                try:
                    stat = Path(result["path"]).stat()
                    result["_mtimeNs"] = stat.st_mtime_ns
                    result["_size"] = stat.st_size
                except OSError:
                    pass
                scanned[result["path"]] = result
            if index % 20 == 0 or index == len(futures):
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache_path.with_suffix(f"{cache_path.suffix}.tmp")
                temporary.write_text(json.dumps(scanned, ensure_ascii=False))
                os.replace(temporary, cache_path)
                print(f"OCR {min(len(scanned), len(tasks))}/{len(tasks)}", file=sys.stderr, flush=True)
    return scanned


def sanitize_text(text: str) -> str:
    text = EMAIL_RE.sub("test@example.com", text)
    text = PHONE_RE.sub("00000000000", text)
    text = TOKEN_RE.sub(lambda match: f"{match.group(1)}: TEST_VALUE", text)
    text = ACCOUNT_VALUE_RE.sub(lambda match: f"{match.group(1)}: TEST_ID", text)
    text = URL_RE.sub("https://example.invalid", text)
    return LONG_ID_RE.sub("TEST_ID", text)


def is_sensitive(text: str) -> bool:
    return bool(
        EMAIL_RE.search(text)
        or PHONE_RE.search(text)
        or LONG_ID_RE.search(text)
        or TOKEN_RE.search(text)
        or URL_RE.search(text)
        or ACCOUNT_VALUE_RE.search(text)
    )


def load_glossary(repo: Path) -> dict[str, str]:
    path = repo / "scripts/glossary/zh-en.json"
    glossary = json.loads(path.read_text())
    return {
        source.strip(): target.strip()
        for source, target in glossary.items()
        if CHINESE_RE.search(source) and len(source) <= 80
    }


def translate_texts(texts: list[str], repo: Path) -> dict[str, str]:
    glossary = load_glossary(repo)
    mapping: dict[str, str] = {}
    pending: list[str] = []
    for original in texts:
        clean = sanitize_text(original).strip()
        required = clean.startswith("*")
        core = clean.lstrip("* ").strip()
        pieces = core.split()
        if core in COMMON_TERMS:
            mapping[original] = ("* " if required else "") + COMMON_TERMS[core]
        elif len(pieces) > 1 and all(piece in COMMON_TERMS for piece in pieces):
            mapping[original] = ("* " if required else "") + "   ".join(COMMON_TERMS[piece] for piece in pieces)
        elif clean in glossary:
            mapping[original] = glossary[clean]
        else:
            pending.append(original)
    if not pending:
        return mapping

    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    model_cache = repo / "tools/review/.cache/huggingface/hub/models--Helsinki-NLP--opus-mt-zh-en"
    revision = (model_cache / "refs/main").read_text().strip()
    model_path = model_cache / "snapshots" / revision
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_path, local_files_only=True)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model.to(device)
    model.eval()
    for offset in range(0, len(pending), 48):
        batch_original = pending[offset : offset + 48]
        batch = [sanitize_text(text) for text in batch_original]
        encoded = tokenizer(batch, return_tensors="pt", padding=True, truncation=True, max_length=256)
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.inference_mode():
            generated = model.generate(**encoded, max_new_tokens=96, num_beams=1)
        outputs = tokenizer.batch_decode(generated, skip_special_tokens=True)
        for original, translated in zip(batch_original, outputs):
            translated = translated.strip() or "Test"
            translated = re.sub(r"(?i)yi\s*-?\s*da", "Yida", translated)
            if CHINESE_RE.search(translated):
                translated = "Test"
            source_core = sanitize_text(original).strip().lstrip("* ").strip()
            if (
                re.fullmatch(r"[\u3400-\u9fff]{2,4}", source_core)
                and source_core not in COMMON_TERMS
                and re.fullmatch(r"[A-Z][A-Za-z-]{2,}!?", translated)
            ):
                translated = "Test User"
            mapping[original] = translated
        print(
            f"Translate {min(offset + len(batch_original), len(pending))}/{len(pending)}",
            file=sys.stderr,
            flush=True,
        )
    return mapping


def font_path() -> str:
    candidates = [
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    return next(path for path in candidates if Path(path).exists())


def rect_pixels(box: dict[str, float], width: int, height: int, pad: int = 2) -> tuple[int, int, int, int]:
    left = max(0, int(box["x"] * width) - pad)
    top = max(0, int((1 - box["y"] - box["height"]) * height) - pad)
    right = min(width, int((box["x"] + box["width"]) * width) + pad)
    bottom = min(height, int((1 - box["y"]) * height) + pad)
    return left, top, max(left + 1, right), max(top + 1, bottom)


def colors_for_box(array: np.ndarray, rect: tuple[int, int, int, int]) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    left, top, right, bottom = rect
    pad = max(3, min(right - left, bottom - top) // 4)
    outer = array[max(0, top - pad) : min(array.shape[0], bottom + pad), max(0, left - pad) : min(array.shape[1], right + pad), :3]
    inner = array[top:bottom, left:right, :3]
    if outer.size == 0:
        background = np.array([255, 255, 255], dtype=float)
    else:
        background = np.median(outer.reshape(-1, 3), axis=0)
    if inner.size == 0:
        foreground = np.array([0, 0, 0], dtype=float)
    else:
        pixels = inner.reshape(-1, 3).astype(float)
        distance = np.linalg.norm(pixels - background, axis=1)
        cutoff = np.quantile(distance, 0.85) if len(distance) > 5 else 0
        candidates = pixels[distance >= cutoff]
        foreground = np.median(candidates, axis=0) if len(candidates) else np.array([0, 0, 0])
    if np.linalg.norm(foreground - background) < 60:
        foreground = np.array([20, 20, 20]) if background.mean() > 145 else np.array([245, 245, 245])
    return tuple(background.astype(np.uint8)), tuple(foreground.astype(np.uint8))


def fit_font(draw: ImageDraw.ImageDraw, text: str, width: int, height: int, path: str) -> ImageFont.FreeTypeFont:
    size = max(7, int(height * 0.78))
    while size > 6:
        font = ImageFont.truetype(path, size=size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= width and box[3] - box[1] <= height:
            return font
        size -= 1
    return ImageFont.truetype(path, size=6)


def render(task: dict[str, str], layout: dict[str, Any], translations: dict[str, str], dry_run: bool) -> dict[str, Any]:
    source = Path(task["source"])
    output = Path(task["output"])
    image = Image.open(source).convert("RGBA")
    work = image.convert("RGB")
    array = np.asarray(work)
    draw = ImageDraw.Draw(work)
    replaced = 0
    font_file = font_path()
    for observation in layout.get("texts", []):
        original = observation["text"].strip()
        if not CHINESE_RE.search(original) and not is_sensitive(original):
            continue
        translated = translations.get(original, sanitize_text(original))
        rect = rect_pixels(observation["box"], work.width, work.height)
        background, foreground = colors_for_box(array, rect)
        draw.rectangle(rect, fill=background)
        left, top, right, bottom = rect
        font = fit_font(draw, translated, right - left, bottom - top, font_file)
        text_box = draw.textbbox((0, 0), translated, font=font)
        y = top + max(0, ((bottom - top) - (text_box[3] - text_box[1])) // 2 - text_box[1])
        draw.text((left, y), translated, fill=foreground, font=font)
        replaced += 1
    for qr in layout.get("qrCodes", []):
        rect = rect_pixels(qr, work.width, work.height, pad=4)
        draw.rectangle(rect, fill=(245, 245, 245), outline=(160, 160, 160), width=2)
        left, top, right, bottom = rect
        label = "TEST"
        font = fit_font(draw, label, right - left, bottom - top, font_file)
        draw.text((left + 3, top + 3), label, fill=(80, 80, 80), font=font)
    if not dry_run:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".png", dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
        try:
            work.save(temporary, format="PNG", optimize=True)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    return {"id": task["id"], "replaced": replaced, "qr": len(layout.get("qrCodes", []))}


def complexity_reason(task: dict[str, str], layout: dict[str, Any]) -> str | None:
    with Image.open(task["source"]) as image:
        width, height = image.size
    texts = [item["text"].strip() for item in layout.get("texts", []) if item.get("text", "").strip()]
    groups: dict[str, list[dict[str, Any]]] = {}
    for observation in layout.get("texts", []):
        normalized = re.sub(r"\d+", "#", observation.get("text", "").strip())
        if normalized:
            groups.setdefault(normalized, []).append(observation)
    if width > 6000 or height > 5000 or max(width / max(height, 1), height / max(width, 1)) > 3.4:
        return "long-image"
    for observations in groups.values():
        if len(observations) < 6:
            continue
        centers_x = [item["box"]["x"] + item["box"]["width"] / 2 for item in observations]
        centers_y = [item["box"]["y"] + item["box"]["height"] / 2 for item in observations]
        if max(centers_x) - min(centers_x) > 0.28 and max(centers_y) - min(centers_y) > 0.28:
            return "repeated-watermark"
    if len(texts) > 110:
        return "dense-text"
    if min(width, height) < 600 and len(texts) > 24:
        return "small-diagram"
    return None


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    tasks = load_tasks(args, repo)
    if not tasks:
        print(json.dumps({"total": 0, "completed": 0, "failed": []}))
        return 0
    binary = compile_ocr(repo)
    cache_name = "image-localizer-layouts-repair.json" if args.repair_quality_failed else "image-localizer-layouts.json"
    layouts = scan_all(binary, tasks, args.ocr_workers, repo / "tools/review/.cache" / cache_name)
    skipped = []
    eligible = []
    for task in tasks:
        layout = layouts.get(task["source"])
        if not layout or layout.get("error"):
            skipped.append({"id": task["id"], "reason": (layout or {}).get("error", "missing-ocr")})
            continue
        reason = None if args.repair_quality_failed else complexity_reason(task, layout)
        if reason:
            skipped.append({"id": task["id"], "reason": reason})
        else:
            eligible.append(task)
    texts = sorted(
        {
            observation["text"].strip()
            for task in eligible
            for layout in [layouts[task["source"]]]
            for observation in layout.get("texts", [])
            if CHINESE_RE.search(observation["text"])
        }
    )
    translations = translate_texts(texts, repo)
    completed = []
    failed = []
    for index, task in enumerate(eligible, 1):
        try:
            layout = layouts.get(task["source"])
            if not layout or layout.get("error"):
                raise RuntimeError((layout or {}).get("error", "missing OCR result"))
            completed.append(render(task, layout, translations, args.dry_run))
        except Exception as error:
            failed.append({"id": task["id"], "error": str(error)[:200]})
        if index % 50 == 0 or index == len(eligible):
            print(f"Render {index}/{len(eligible)}", file=sys.stderr, flush=True)
    report = {
        "total": len(tasks),
        "eligible": len(eligible),
        "completed": len(completed),
        "skipped": skipped,
        "failed": failed,
        "details": completed,
    }
    report_path = repo / "tools/review/.cache/image-localizer-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"total": len(tasks), "eligible": len(eligible), "completed": len(completed), "skipped": len(skipped), "failed": failed}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
