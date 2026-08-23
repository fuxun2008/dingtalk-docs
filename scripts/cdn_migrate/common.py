"""图片全量转存 CDN — 共享工具：路径 / 分类 / 图引用提取。

小工具（is_image_url / save_json / load_json / split_code_blocks / short_hash）与
scripts/import_archive.py 语义一致，此处以 stdlib 独立实现，避免 import_archive 在
模块加载期引入 requests 依赖（本仓无 venv）。HTTP 探活/下载在 download.py/verify.py
内按需 lazy-import。
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

# ---------- 路径 ----------
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = _SCRIPTS_DIR.parent
OUT_DIR = REPO_ROOT / "scripts" / "output" / "cdn-migrate"
DOWNLOADS_DIR = OUT_DIR / "downloads"
STAGING_DIR = OUT_DIR / "staging"
CONFIG_PATH = REPO_ROOT / "scripts" / "cdn_migrate" / "config.local.json"

# 三语镜像根：en 在仓库根，zh/ ja/ id/ 为子目录
LANG_ROOTS = ["", "zh", "ja", "id"]

# ---------- stdlib 小工具（语义同 import_archive） ----------
_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
_CODE_FENCE = re.compile(r"^[ \t]{0,3}```", re.MULTILINE)


def is_image_url(url: str) -> bool:
    return strip_query(url).lower().endswith(_IMAGE_EXTS)


def short_hash(text: str, length: int = 6) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return default
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def split_code_blocks(text: str) -> list[tuple[bool, str]]:
    """切分为 [(is_code, chunk), ...]，code 块不动（同 import_archive.split_code_blocks）。"""
    parts: list[tuple[bool, str]] = []
    pos = 0
    in_code = False
    while True:
        m = _CODE_FENCE.search(text, pos)
        if not m:
            parts.append((in_code, text[pos:]))
            return parts
        parts.append((in_code, text[pos:m.start()]))
        end = text.find("\n", m.end())
        if end < 0:
            parts.append((True, text[m.start():]))
            return parts
        parts.append((True, text[m.start():end + 1]))
        in_code = not in_code
        pos = end + 1


# ---------- host 分类 ----------
# 需要迁移的临时 OSS host（钉钉文档导出残留）
MIGRATE_HOSTS = {
    "alidocs.oss-cn-zhangjiakou.aliyuncs.com",
    "alidocs2.oss-cn-zhangjiakou.aliyuncs.com",
    "alidocs.oss-accelerate.aliyuncs.com",
    "yida-support.oss-cn-shanghai.aliyuncs.com",
    "tianshu-vpc.oss-cn-shanghai.aliyuncs.com",
}
# 已是永久 CDN，跳过
SKIP_HOSTS = {
    "g.alicdn.com",
    "img.alicdn.com",
    "gw.alicdn.com",
    "dev.g.alicdn.com",
}
# 阿里官方 host：默认保留不迁（可按需并入 MIGRATE_HOSTS）
LEAVE_HOSTS = {
    "help-static-aliyun-doc.aliyuncs.com",
    "www.aliwork.com",
    "aliwork.com",
}
# 视频 host（TPS 无法托管）
VIDEO_HOSTS = {
    "cloud.video.taobao.com",
    "v.qq.com",
    "player.youku.com",
    "tv.sohu.com",
}
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".avi", ".mkv")

# ---------- 图 / 媒体引用正则 ----------
# markdown 图片：![alt](url "title")  —— url 不含空格与右括号
MD_IMAGE_RE = re.compile(r'!\[[^\]]*\]\(\s*(<?)([^)\s"\'<>]+)\1?(?:\s+"[^"]*")?\s*\)')
# HTML <img src="...">（含单双引号）
IMG_SRC_RE = re.compile(r'<img\b[^>]*?\bsrc\s*=\s*(["\'])(.*?)\1', re.IGNORECASE | re.DOTALL)
# <Frame src="...">（Frame 多为包 <img>，此为防御性直匹配）
FRAME_SRC_RE = re.compile(r'<Frame\b[^>]*?\bsrc\s*=\s*(["\'])(.*?)\1', re.IGNORECASE | re.DOTALL)


def host_of(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower()
    except Exception:
        return ""


def strip_query(url: str) -> str:
    return url.split("#", 1)[0].split("?", 1)[0]


def is_signed(url: str) -> bool:
    return any(k in url for k in ("Expires=", "OSSAccessKeyId", "Signature="))


def is_video_url(url: str) -> bool:
    bare = strip_query(url).lower()
    return host_of(url) in VIDEO_HOSTS or bare.endswith(VIDEO_EXTS)


def is_local_ref(url: str) -> bool:
    """站点根相对路径：以单 / 开头（排除协议相对 //host）。"""
    return url.startswith("/") and not url.startswith("//")


def ext_of(url: str) -> str:
    bare = strip_query(url).lower()
    m = re.search(r"\.([a-z0-9]{1,5})$", bare)
    return m.group(1) if m else ""


def classify(url: str) -> str:
    """→ 'skip' | 'migrate' | 'video' | 'leave' | 'local' | 'other'"""
    if is_local_ref(url):
        # 本地资源里视频不迁（保留），图片才迁
        return "local-video" if strip_query(url).lower().endswith(VIDEO_EXTS) else "local"
    if is_video_url(url):
        return "video"
    host = host_of(url)
    if host in SKIP_HOSTS:
        return "skip"
    if host in MIGRATE_HOSTS:
        return "migrate" if is_image_url(strip_query(url)) else "video"
    if host in LEAVE_HOSTS:
        return "leave"
    return "other"


def iter_mdx_files() -> list[Path]:
    """全仓所有 .mdx（en 根 + zh/ ja/ id/ 镜像 + 各产品目录）。"""
    files: list[Path] = []
    for p in REPO_ROOT.rglob("*.mdx"):
        rel = p.relative_to(REPO_ROOT)
        parts = rel.parts
        if parts and parts[0] in {"node_modules", ".git", "scripts", "tools", ".claude"}:
            continue
        files.append(p)
    return files


def extract_refs(text: str) -> list[tuple[str, str]]:
    """返回 [(kind, raw_url), ...]，kind ∈ {md, img, frame}；跳过代码围栏。"""
    refs: list[tuple[str, str]] = []
    for is_code, chunk in split_code_blocks(text):
        if is_code:
            continue
        for m in MD_IMAGE_RE.finditer(chunk):
            refs.append(("md", m.group(2)))
        for m in IMG_SRC_RE.finditer(chunk):
            refs.append(("img", m.group(2)))
        for m in FRAME_SRC_RE.finditer(chunk):
            refs.append(("frame", m.group(2)))
    return refs


def local_ref_to_path(url: str) -> Path | None:
    """站点根路径 → 磁盘绝对路径（去 query，URL 解码）。"""
    from urllib.parse import unquote

    bare = unquote(strip_query(url)).lstrip("/")
    p = (REPO_ROOT / bare).resolve()
    return p if p.exists() and p.is_file() else None


__all__ = [
    "REPO_ROOT", "OUT_DIR", "DOWNLOADS_DIR", "STAGING_DIR", "CONFIG_PATH", "LANG_ROOTS",
    "MIGRATE_HOSTS", "SKIP_HOSTS", "LEAVE_HOSTS", "VIDEO_HOSTS", "VIDEO_EXTS",
    "is_image_url", "save_json", "load_json", "split_code_blocks", "short_hash",
    "host_of", "strip_query", "is_signed", "is_video_url", "is_local_ref", "ext_of",
    "classify", "iter_mdx_files", "extract_refs", "local_ref_to_path",
]
