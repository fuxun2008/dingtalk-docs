#!/usr/bin/env python3
"""批量下载主循环。

用法:
    python3 download.py                 # 跑所有 pending/failed
    python3 download.py --limit 5       # 只跑前 5 篇（调试）
    python3 download.py --headed        # 可见浏览器（默认 headless）
    python3 download.py --retry-failed  # 重置 failed 状态后重试

设计:
  - 单一长寿命浏览器 context，每篇文档新开 page 处理
  - UI 驱动：模拟点击「更多 → 导出 → Markdown」，等待 download 事件
  - 每篇下载后立即更新 manifest.json → 断点续传
  - 限速 1-2s/篇，避免风控
  - 单篇连续失败 ≥ 3 次标记 permanent_failed
  - 登录态过期立即中断，提示重跑 auth_bootstrap.py
"""
from __future__ import annotations
import argparse
import asyncio
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Download,
    Frame,
    Page,
    TimeoutError as PWTimeout,
)

HERE = Path(__file__).parent
MANIFEST_PATH = HERE / 'manifest.json'   # 默认；可被 --manifest 覆盖（用于三产品并发）
STATE_PATH = HERE / 'storage_state.json'
LOG_DIR = Path.home() / 'Downloads' / 'dingtalk-docs-archive' / '.log'

MAX_ATTEMPTS = 3
PAGE_TIMEOUT_MS = 30_000
DOWNLOAD_TIMEOUT_MS = 30_000
MENU_PROBE_TIMEOUT_MS = 3_000
DOC_READY_TIMEOUT_MS = 20_000  # 等更多按钮渲染出来的最大时间（SPA 慢加载）

# 启发式 selector 候选（按优先级，首个能命中即用）
# 钉钉文档实测稳定属性：data-testid="doc-header-more-button" + data-role="headerMoreMenu"
# 注：[title*="更多"] 等过宽 selector 已删除，改用 _LOCATE_HEADER_MORE_JS 兜底（按位置过滤）
MORE_BUTTON_SELECTORS = [
    'button[data-testid="doc-header-more-button"]',
    '[data-role="headerMoreMenu"]',
    'button[data-testid*="more-button"]',
]


# 兜底用 JS 在右上角文档头部定位 ⋮ 按钮（避开工具栏的"更多格式"）
_LOCATE_HEADER_MORE_JS = """() => {
    const W = window.innerWidth;
    const candidates = Array.from(document.querySelectorAll(
        'button, [role="button"], [class*="icon-button"], svg'
    ));
    for (const el of candidates) {
        const r = el.getBoundingClientRect();
        // 必须在页面顶部 0~70px 之间（文档 header bar 高度），且靠右
        if (r.top < 0 || r.top > 70 || r.right < W - 200 || r.right > W - 20) continue;
        if (r.width < 16 || r.height < 16 || r.width > 60) continue;
        const title = (el.getAttribute('title') || el.getAttribute('aria-label') || '').toLowerCase();
        const cls = (el.getAttribute('class') || '').toLowerCase();
        if (title.includes('更多') || title.includes('more') || cls.includes('more')) {
            // 标记并返回 css selector
            el.setAttribute('data-pw-header-more', 'yes');
            return '[data-pw-header-more="yes"]';
        }
    }
    return null;
}"""

# 「下载到本地」入口（菜单项 = <div>，data-role/data-item-key 稳定）
EXPORT_MENU_SELECTORS = [
    '[data-role="operationBar_export"]',
    '[data-item-key="export"]',
    'div.wd3-listitem:has-text("下载到本地")',
    'div:has-text("下载到本地"):not(:has(div))',  # 叶子 div，文本即"下载到本地"
]

# Markdown 子菜单项
MARKDOWN_OPTION_SELECTORS = [
    '[data-role="operationBar__export_exportAsMd"]',
    '[data-item-key="exportAsMd"]',
    'div.wd3-listitem:has-text("Markdown(.md)")',
    'div.wd3-listitem:has-text("Markdown")',
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def load_manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))


def save_manifest(manifest: list[dict]) -> None:
    tmp = MANIFEST_PATH.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(MANIFEST_PATH)


class AuthExpiredError(RuntimeError):
    pass


class NotADocumentError(RuntimeError):
    """节点是文件夹/索引页，不是可导出的文档。"""
    pass


class MarkdownNotSupportedError(RuntimeError):
    """文档类型不支持 Markdown 导出（如 AI 表格 / 多维表格）。"""
    pass


def is_login_page(html: str | None, url: str) -> bool:
    if 'login' in url.lower() or 'sso' in url.lower():
        return True
    if html and any(k in html for k in ('请登录', '扫码登录', 'login-form', 'dt-login')):
        return True
    return False


async def try_click_one(scope, selectors: list[str], timeout_ms: int) -> str | None:
    """按优先级尝试 selector，第一个能命中并点击的返回该 selector，全失败返回 None。
    scope 可以是 Page 或 Frame。"""
    for sel in selectors:
        try:
            loc = scope.locator(sel).first
            await loc.wait_for(state='visible', timeout=timeout_ms)
            await loc.click(timeout=timeout_ms)
            return sel
        except PWTimeout:
            continue
        except Exception:
            continue
    return None


async def try_hover_one(scope, selectors: list[str], timeout_ms: int) -> str | None:
    """同 try_click_one 但用 hover（适用于 hover 触发的级联菜单）。"""
    for sel in selectors:
        try:
            loc = scope.locator(sel).first
            await loc.wait_for(state='visible', timeout=timeout_ms)
            await loc.hover(timeout=timeout_ms)
            return sel
        except PWTimeout:
            continue
        except Exception:
            continue
    return None


async def find_more_button_scope(page: Page, timeout_ms: int) -> tuple[Page | Frame, str] | None:
    """在 page 与所有子 frame 内并发等待"更多"按钮出现，谁先出现返回 (scope, selector)。
    标准 selector 全失败时，用 JS 兜底（按位置过滤右上角 ⋮）。"""
    # 收集所有候选 scope：主页面 + 所有 iframe
    scopes: list[Page | Frame] = [page] + list(page.frames)

    async def watch(scope, sel):
        try:
            await scope.locator(sel).first.wait_for(state='visible', timeout=timeout_ms)
            return scope, sel
        except Exception:
            return None

    tasks = []
    for scope in scopes:
        for sel in MORE_BUTTON_SELECTORS:
            tasks.append(asyncio.create_task(watch(scope, sel)))
    try:
        for coro in asyncio.as_completed(tasks):
            result = await coro
            if result:
                # 取消其余任务
                for t in tasks:
                    if not t.done():
                        t.cancel()
                return result
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()

    # 兜底：用 JS 在右上角 header 区域找 ⋮ 按钮（编辑视图下 standard selector 都不命中时走这里）
    for scope in scopes:
        try:
            sel = await scope.evaluate(_LOCATE_HEADER_MORE_JS)
            if sel:
                return scope, sel
        except Exception:
            continue
    return None


_DUMP_JS = """() => {
    const out = [];
    const nodes = document.querySelectorAll(
        'button, [role="button"], [role="menuitem"], [class*="icon-button"]'
    );
    for (const el of nodes) {
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        out.push({
            tag: el.tagName.toLowerCase(),
            title: el.getAttribute('title') || '',
            ariaLabel: el.getAttribute('aria-label') || '',
            cls: (el.getAttribute('class') || '').slice(0, 80),
            text: (el.innerText || '').trim().slice(0, 40),
            dataTestId: el.getAttribute('data-test-id') || el.getAttribute('data-testid') || '',
            dataRole: el.getAttribute('data-role') || '',
            x: Math.round(r.left),
            y: Math.round(r.top),
        });
    }
    return out.slice(0, 60);
}"""


async def dump_all_candidates(page: Page) -> list[dict]:
    """selector 全挂时调用：dump 主 page + 所有 frame 内可点击元素的关键属性。"""
    all_cands: list[dict] = []
    scopes: list[tuple[str, Page | Frame]] = [('main', page)]
    for i, fr in enumerate(page.frames):
        if fr == page.main_frame:
            continue
        scopes.append((f'frame[{i}]:{fr.url[:60]}', fr))
    for label, sc in scopes:
        try:
            items = await sc.evaluate(_DUMP_JS)
            for it in items:
                it['_scope'] = label
            all_cands.extend(items)
        except Exception as e:
            all_cands.append({'_scope': label, 'dump_error': str(e)})
    return all_cands


async def dump_menu_candidates(page: Page) -> list[dict]:
    """菜单弹出后专用 dump：聚焦 role=menu / role=menuitem。"""
    try:
        return await page.evaluate(
            """() => {
                const out = [];
                const nodes = document.querySelectorAll(
                    '[role="menuitem"], [role="menu"] li, [class*="menu-item"], [class*="dropdown"] li'
                );
                for (const el of nodes) {
                    const r = el.getBoundingClientRect();
                    if (r.width === 0 || r.height === 0) continue;
                    out.push({
                        tag: el.tagName.toLowerCase(),
                        text: (el.innerText || '').trim().slice(0, 60),
                        cls: (el.getAttribute('class') || '').slice(0, 60),
                        role: el.getAttribute('role') || '',
                    });
                }
                return out.slice(0, 50);
            }"""
        )
    except Exception as e:
        return [{'dump_error': str(e)}]


async def export_markdown(page: Page, entry: dict) -> bytes:
    """对当前 page 模拟「更多 → 导出 → Markdown」并返回下载的字节。"""
    url = entry['url']
    await page.goto(url, wait_until='domcontentloaded', timeout=PAGE_TIMEOUT_MS)

    # 等待主体内容渲染（启发式：等任何含"导出"或"更多"的按钮出现，或 1.5s 短延时）
    try:
        await page.wait_for_load_state('networkidle', timeout=10_000)
    except PWTimeout:
        pass
    await page.wait_for_timeout(500)

    # 登录态过期检测
    if is_login_page(None, page.url):
        raise AuthExpiredError(f'redirected to login: {page.url}')

    # Step 1: 跨 page + iframe 等待「更多」按钮出现并点击
    found = await find_more_button_scope(page, DOC_READY_TIMEOUT_MS)
    if not found:
        cands = await dump_all_candidates(page)
        sample = json.dumps(cands[:25], ensure_ascii=False)
        raise RuntimeError(
            f'未找到「更多」按钮（page + {len(page.frames)} 个 frame 均无）；'
            f'候选元素 dump: {sample}'
        )
    scope, more_sel = found
    await scope.locator(more_sel).first.click(timeout=MENU_PROBE_TIMEOUT_MS)

    # Step 2: hover「下载到本地」展开级联子菜单（不是 click，因为右侧有 ▶ 表示 hover 触发）
    # scope 优先（more button 与子菜单同 frame），page 兜底。
    # 反序的代价：page 兜底 12s timeout 期间子菜单已因鼠标离开而关闭，frame fallback 必失败。
    await page.wait_for_timeout(300)
    export_sel = None
    if scope is not page:
        export_sel = await try_hover_one(scope, EXPORT_MENU_SELECTORS, MENU_PROBE_TIMEOUT_MS)
    if not export_sel:
        export_sel = await try_hover_one(page, EXPORT_MENU_SELECTORS, MENU_PROBE_TIMEOUT_MS)
    if not export_sel:
        cands = await dump_menu_candidates(page)
        # 失败时存截图便于诊断
        try:
            shot_dir = Path.home() / 'Downloads' / 'dingtalk-docs-archive' / '.log' / 'shots'
            shot_dir.mkdir(parents=True, exist_ok=True)
            safe_name = entry['rel_path'].replace('/', '_')[:80]
            shot_path = shot_dir / f'{safe_name}-{int(time.time())}.png'
            await page.screenshot(path=str(shot_path), full_page=False)
            extra = f' [截图: {shot_path.name}; 触发的 more 选择器: {more_sel}]'
        except Exception:
            extra = f' [截图失败; more 选择器: {more_sel}]'
        raise RuntimeError(f'未找到「下载到本地」入口{extra}；当前菜单项 dump: {json.dumps(cands[:30], ensure_ascii=False)}')

    # Step 3: 定位「Markdown(.md)」（scope 优先，page 兜底），再 hover+click 一气呵成
    await page.wait_for_timeout(500)  # 等子菜单弹出动画
    md_loc = None
    md_sel = None
    scopes_try = ([scope] if scope is not page else []) + [page]
    for s in scopes_try:
        for sel in MARKDOWN_OPTION_SELECTORS:
            try:
                loc = s.locator(sel).first
                await loc.wait_for(state='visible', timeout=MENU_PROBE_TIMEOUT_MS)
                md_loc = loc
                md_sel = sel
                break
            except Exception:
                continue
        if md_loc:
            break
    if not md_loc:
        cands = await dump_menu_candidates(page)
        # 子菜单里没有 Markdown 文本 → 此文档类型不支持 md 导出（AI 表格 / 多维表格）
        has_md_text = any('markdown' in (c.get('text') or '').lower() for c in cands)
        if not has_md_text:
            raise MarkdownNotSupportedError(
                f'子菜单中无 Markdown 选项（疑似 AI 表格/多维表格类型）'
            )
        raise RuntimeError(f'未找到「Markdown(.md)」选项；当前菜单项 dump: {json.dumps(cands[:30], ensure_ascii=False)}')

    async with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as dl_info:
        # hover → 100ms → click：保持鼠标在子菜单内，避免子菜单在 click 前关闭
        await md_loc.hover()
        await page.wait_for_timeout(100)
        await md_loc.click()
    download: Download = await dl_info.value

    # 把下载流读到临时文件再读出 bytes
    tmp_path = Path('/tmp') / f'dt-download-{int(time.time()*1000)}.md'
    await download.save_as(str(tmp_path))
    data = tmp_path.read_bytes()
    tmp_path.unlink(missing_ok=True)
    return data


def write_atomic(path: Path, data: bytes) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_bytes(data)
    tmp.replace(path)
    return len(data)


async def process_one(ctx: BrowserContext, entry: dict, log_fp) -> tuple[bool, str | None]:
    """处理单篇下载。返回 (是否成功, 错误消息)。"""
    page = await ctx.new_page()
    try:
        data = await export_markdown(page, entry)
        # 内容污染检测
        if len(data) < 50:
            raise RuntimeError(f'下载文件过小 ({len(data)} bytes)，疑似导出失败')
        try:
            txt = data.decode('utf-8', errors='ignore')
            if 'login' in page.url.lower() or 'sso' in page.url.lower():
                raise AuthExpiredError(f'redirected to login: {page.url}')
            if any(k in txt for k in ('login-form', 'dt-login', '<!DOCTYPE html', '<html')):
                raise AuthExpiredError('downloaded content looks like login HTML page')
        except UnicodeDecodeError:
            pass

        size = write_atomic(Path(entry['output_path']), data)
        entry.update(
            status='success',
            size_bytes=size,
            downloaded_at=now_iso(),
            error=None,
        )
        log_fp.write(json.dumps({'ts': now_iso(), 'level': 'INFO', 'rel': entry['rel_path'], 'size': size}, ensure_ascii=False) + '\n')
        log_fp.flush()
        return True, None
    except AuthExpiredError as e:
        raise
    except NotADocumentError as e:
        entry['status'] = 'not_a_document'
        entry['error'] = str(e)
        log_fp.write(json.dumps({'ts': now_iso(), 'level': 'INFO', 'rel': entry['rel_path'], 'msg': 'skipped: not a document'}, ensure_ascii=False) + '\n')
        log_fp.flush()
        return False, 'not_a_document (跳过)'
    except MarkdownNotSupportedError as e:
        entry['status'] = 'markdown_not_supported'
        entry['error'] = str(e)
        log_fp.write(json.dumps({'ts': now_iso(), 'level': 'INFO', 'rel': entry['rel_path'], 'msg': 'skipped: markdown not supported'}, ensure_ascii=False) + '\n')
        log_fp.flush()
        return False, 'markdown_not_supported (跳过)'
    except Exception as e:
        msg = f'{type(e).__name__}: {e}'
        entry['attempts'] = entry.get('attempts', 0) + 1
        entry['error'] = msg
        if entry['attempts'] >= MAX_ATTEMPTS:
            entry['status'] = 'permanent_failed'
        else:
            entry['status'] = 'failed'
        log_fp.write(json.dumps({'ts': now_iso(), 'level': 'ERROR', 'rel': entry['rel_path'], 'attempts': entry['attempts'], 'err': msg}, ensure_ascii=False) + '\n')
        log_fp.flush()
        return False, msg
    finally:
        try:
            await page.close()
        except Exception:
            pass


async def main(args) -> int:
    if not STATE_PATH.exists():
        print(f'❌ {STATE_PATH} 不存在；请先跑 auth_bootstrap.py', file=sys.stderr)
        return 1
    if not MANIFEST_PATH.exists():
        print(f'❌ {MANIFEST_PATH} 不存在；请先跑 build_manifest.py', file=sys.stderr)
        return 1

    manifest = load_manifest()
    if args.retry_failed:
        for e in manifest:
            if e.get('status') in ('failed', 'permanent_failed'):
                e['status'] = 'pending'
                e['attempts'] = 0
                e['error'] = None
        save_manifest(manifest)

    pending = [e for e in manifest if e.get('status') not in ('success', 'not_a_document', 'markdown_not_supported', 'export_unavailable')]
    if args.skip:
        pending = pending[args.skip:]
    if args.limit:
        pending = pending[:args.limit]

    total = len(pending)
    if total == 0:
        print('✅ 没有待下载的条目')
        return 0

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f'download-{datetime.now():%Y-%m-%dT%H-%M-%S}.log'
    log_fp = log_path.open('w', encoding='utf-8')
    log_fp.write(json.dumps({'ts': now_iso(), 'level': 'INFO', 'msg': f'start; pending={total}; limit={args.limit}; headed={args.headed}'}, ensure_ascii=False) + '\n')

    print(f'待下载: {total} 篇')
    print(f'日志: {log_path}')
    print('=' * 60)

    success, failed, auth_expired = 0, 0, False
    started = time.time()

    async with async_playwright() as p:
        browser: Browser = await p.chromium.launch(headless=not args.headed)
        ctx: BrowserContext = await browser.new_context(
            storage_state=str(STATE_PATH),
            viewport={'width': 1440, 'height': 900},
            locale=args.locale,
            extra_http_headers={'Accept-Language': f'{args.locale},en;q=0.9'},
            accept_downloads=True,
        )

        for i, entry in enumerate(pending, 1):
            label = f'[{i}/{total}] {entry["rel_path"]}'
            print(f'  {label} ...', end='', flush=True)
            try:
                ok, err = await process_one(ctx, entry, log_fp)
            except AuthExpiredError as e:
                print(f' ❌ 登录态过期: {e}')
                log_fp.write(json.dumps({'ts': now_iso(), 'level': 'FATAL', 'msg': str(e)}, ensure_ascii=False) + '\n')
                auth_expired = True
                break

            # 立即写 manifest（断点续传）
            save_manifest(manifest)

            if ok:
                success += 1
                print(f' ✅ {entry["size_bytes"]} bytes')
            else:
                failed += 1
                print(f' ❌ {err}')

            # 限速
            if i < total:
                await asyncio.sleep(random.uniform(1.0, 2.0))

        await ctx.close()
        await browser.close()

    log_fp.close()
    elapsed = time.time() - started
    print('=' * 60)
    print(f'完成: success={success} failed={failed} elapsed={elapsed:.1f}s')
    if auth_expired:
        print('⚠️  登录态过期，请重跑 auth_bootstrap.py 后续跑此脚本')
        return 2
    return 0 if failed == 0 else 1


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0, help='只跑前 N 篇（调试）')
    ap.add_argument('--skip', type=int, default=0, help='跳过前 N 条 pending（调试时绕过文件夹节点）')
    ap.add_argument('--headed', action='store_true', help='显示浏览器（默认 headless）')
    ap.add_argument('--retry-failed', action='store_true', help='把 failed/permanent_failed 重置为 pending 后跑')
    ap.add_argument('--locale', default='zh-CN', help='浏览器 locale（默认 zh-CN；EN 文档抓取用 en-US）')
    ap.add_argument('--manifest', default=None, help='manifest.json 路径（默认 dingtalk_downloader/manifest.json；多产品并发各自传一份）')
    ap.add_argument('--timeout-ms', type=int, default=None, help='单篇下载等待事件超时（ms）；默认 30000；retry-failed 时建议 120000')
    return ap.parse_args()


if __name__ == '__main__':
    args = parse_args()
    if args.manifest:
        MANIFEST_PATH = Path(args.manifest).resolve()
    if args.timeout_ms:
        DOWNLOAD_TIMEOUT_MS = args.timeout_ms
    try:
        sys.exit(asyncio.run(main(args)))
    except KeyboardInterrupt:
        print('\n已中断；进度已保存到 manifest.json，下次跑可继续')
        sys.exit(130)
