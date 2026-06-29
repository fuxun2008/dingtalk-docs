#!/usr/bin/env python3
"""一次性脚本：统一帮助文档图片排版。

规则：
  1) 单图（横图 / 桌面截图）：去缩进 → 顶层块级、满宽页面居中。
  2) 移动端竖图（手机截图，h/w ≥ 1.6）：不论 1/2/3 张，一律 flex 画廊
     `<div flex><img width:32% minWidth:180px>`，并排居中、间距统一 12px、超 3 张换行；
     单张时宽度也与三图行的单图一致（32%）。
  3) 同行多图：始终走画廊（并排居中）。
  4) 段落隔离：图片块与相邻正文/`2.` 间补空行（居中 + 让 `2.` 重起 <ol start=N> 不丢编号），
     绝不在相邻图片间插空行。

移动端判定靠真实像素长宽比（crop 参数 → 本地文件头 → 远程 Range GET，结果缓存）。
取不到尺寸的图按横图处理（满宽，安全）。

排除：代码块 / 既有 <img> / 表格单元格内图 / 行内夹正文的图标 / blockquote / 列表标记开头。

用法：
  python3 scripts/normalize_image_lines.py            # dry-run
  python3 scripts/normalize_image_lines.py --apply     # 写回
"""
import re
import sys
import json
import struct
import urllib.request
import concurrent.futures
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path("/tmp/dt_img_dims.json")
MOBILE_RATIO = 1.6  # h/w ≥ 此值视为手机竖图

IMG = r"!\[[^\]]*\]\([^)]*\)"
IMG_LINE = re.compile(r"\s*(?:" + IMG + r"\s*)+")
IMG_PAIR = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")
CROP = re.compile(r"[/,](?:crop|resize)[^?]*?w_(\d+),h_(\d+)")
SKIP_DIRS = {".git", "node_modules", "scripts", ".claude"}

# 单图竖图缩成 32% 仅限「移动端为主」的产品 —— 在这些产品里竖图=手机截图。
# 桌面产品（aitable/docs/open）里竖图多为窄高的桌面侧栏/长截图，缩成 32% 会糊，故排除。
MOBILE_PRODUCTS = {"calendar", "meetings", "mail", "im", "ai-minutes", "contacts", "drive"}


def _product(relpath):
    parts = relpath.split("/")
    if parts and parts[0] in ("zh", "ja"):
        parts = parts[1:]
    return parts[0] if parts else ""

GALLERY_OPEN = ("<div style={{display: 'flex', gap: '12px', justifyContent: 'center', "
                "flexWrap: 'wrap', margin: '16px 0'}}>")
GALLERY_CLOSE = "</div>"
_IMG_STYLE = ("{{width: '32%', minWidth: '180px', borderRadius: '8px', "
              "boxShadow: '0 2px 12px rgba(0,0,0,0.08)'}}")


def _img_html(alt, url):
    alt = alt.replace('"', "&quot;")
    return '  <img src="' + url + '" alt="' + alt + '" style=' + _IMG_STYLE + " />"


# ----------------------------- 尺寸解析 -----------------------------
def _parse_dims(b):
    if len(b) >= 24 and b[:8] == b"\x89PNG\r\n\x1a\n" and b[12:16] == b"IHDR":
        w, h = struct.unpack(">II", b[16:24])
        return w, h
    if len(b) >= 10 and b[:6] in (b"GIF87a", b"GIF89a"):
        w, h = struct.unpack("<HH", b[6:10])
        return w, h
    if len(b) >= 4 and b[:2] == b"\xff\xd8":  # JPEG：扫 SOF 段
        i = 2
        while i < len(b) - 9:
            if b[i] != 0xFF:
                i += 1
                continue
            m = b[i + 1]
            if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", b[i + 5:i + 9])
                return w, h
            if m == 0xD8 or m == 0xD9 or 0xD0 <= m <= 0xD7:
                i += 2
                continue
            if i + 4 > len(b):
                break
            i += 2 + struct.unpack(">H", b[i + 2:i + 4])[0]
    if len(b) >= 30 and b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        fmt = b[12:16]
        try:
            if fmt == b"VP8X":
                wm1 = b[24] | (b[25] << 8) | (b[26] << 16)
                hm1 = b[27] | (b[28] << 8) | (b[29] << 16)
                return wm1 + 1, hm1 + 1
            if fmt == b"VP8 ":
                w = struct.unpack("<H", b[26:28])[0] & 0x3FFF
                h = struct.unpack("<H", b[28:30])[0] & 0x3FFF
                return w, h
        except Exception:
            pass
    return None


def _local_dims(url):
    try:
        return _parse_dims((ROOT / url.lstrip("/")).read_bytes()[:65536])
    except Exception:
        return None


def _remote_dims(url):
    try:
        req = urllib.request.Request(
            url, headers={"Range": "bytes=0-65535", "User-Agent": "dim/1"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return _parse_dims(r.read(65536))
    except Exception:
        return None


def resolve_dims(urls):
    cache = {}
    if CACHE.exists():
        try:
            cache = json.loads(CACHE.read_text())
        except Exception:
            cache = {}
    net = []
    for u in urls:
        if u in cache:
            continue
        m = CROP.search(u)
        if m:
            cache[u] = [int(m.group(1)), int(m.group(2))]
        elif u.startswith("/"):
            cache[u] = _local_dims(u)
        else:
            net.append(u)
    if net:
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
            for u, d in zip(net, ex.map(_remote_dims, net)):
                cache[u] = d
    CACHE.write_text(json.dumps(cache))
    return cache


def _is_mobile(url, dims):
    d = dims.get(url)
    if not d:
        return False
    w, h = d
    return w > 0 and h >= w * MOBILE_RATIO


def _is_blank(s):
    return s.strip() == ""


def _is_image_line(s):
    return bool(IMG_LINE.fullmatch(s))


# ----------------------------- 收集 / 变换 -----------------------------
def collect_single_urls(lines):
    """收集需要判定移动端的「单图行」URL。"""
    urls = []
    in_fence = False
    for line in lines:
        s = line.rstrip("\n")
        if FENCE.match(s):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if _is_image_line(s):
            pairs = IMG_PAIR.findall(s)
            if len(pairs) == 1:
                urls.append(pairs[0][1])
    return urls


def transform_lines(lines, dims, mobile_product):
    """返回 (new_lines, deindent, gallery_multi, gallery_single)。

    mobile_product: 该文件是否属移动端产品（决定单竖图是否缩成 32%）。
    """
    out = []
    in_fence = False
    prev_img = False
    deindent = gallery_multi = gallery_single = 0
    n = len(lines)
    for i, line in enumerate(lines):
        s = line.rstrip("\n")
        if FENCE.match(s):
            in_fence = not in_fence
            out.append(line)
            prev_img = False
            continue
        if in_fence:
            out.append(line)
            prev_img = False
            continue

        if _is_image_line(s):
            pairs = IMG_PAIR.findall(s)
            single_mobile = (len(pairs) == 1 and mobile_product
                             and _is_mobile(pairs[0][1], dims))
            is_gallery = len(pairs) >= 2 or single_mobile
            # 段前补空行：画廊总是隔离；单（横）图仅当上一行非空且非图片行时
            if out and not _is_blank(out[-1].rstrip("\n")) and (is_gallery or not prev_img):
                out.append("\n")
            if is_gallery:
                out.append(GALLERY_OPEN + "\n")
                for alt, url in pairs:
                    out.append(_img_html(alt, url) + "\n")
                out.append(GALLERY_CLOSE + "\n")
                if len(pairs) >= 2:
                    gallery_multi += 1
                else:
                    gallery_single += 1
            else:
                deindented = s.strip()
                out.append(deindented + "\n")
                if s != deindented:
                    deindent += 1
            nxt = lines[i + 1].rstrip("\n") if i + 1 < n else None
            if (nxt is not None and not _is_blank(nxt)
                    and not _is_image_line(nxt) and not FENCE.match(nxt)):
                out.append("\n")
            prev_img = True
            continue

        out.append(line)
        prev_img = False
    return out, deindent, gallery_multi, gallery_single


def main():
    apply = "--apply" in sys.argv
    files = [p for p in sorted(ROOT.rglob("*.mdx"))
             if not any(x in p.relative_to(ROOT).parts for x in SKIP_DIRS)]

    # 第一遍：收集单图 URL → 解析尺寸（带缓存）
    all_urls = set()
    parsed = {}
    for p in files:
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        parsed[p] = lines
        all_urls.update(collect_single_urls(lines))
    dims = resolve_dims(sorted(all_urls))

    # 第二遍：变换
    changed = []
    tot = [0, 0, 0]
    for p in files:
        rel = str(p.relative_to(ROOT))
        mobile_product = _product(rel) in MOBILE_PRODUCTS
        new_lines, d, gm, gs = transform_lines(parsed[p], dims, mobile_product)
        if new_lines == parsed[p]:
            continue
        changed.append((rel, d, gm, gs))
        tot[0] += d
        tot[1] += gm
        tot[2] += gs
        if apply:
            p.write_text("".join(new_lines), encoding="utf-8")

    mode = "APPLIED" if apply else "DRY-RUN"
    print(f"[{mode}] files={len(changed)} de-indent={tot[0]} "
          f"gallery_multi={tot[1]} gallery_single_mobile={tot[2]}")
    for rel, d, gm, gs in changed:
        print(f"  {rel}  de-indent={d} multi={gm} single-mobile={gs}")


if __name__ == "__main__":
    main()
