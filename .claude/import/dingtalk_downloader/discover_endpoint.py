#!/usr/bin/env python3
"""导出端点探测 / 录制模式。

用法:
    python3 discover_endpoint.py

流程:
    1. 用 storage_state.json 启动可见浏览器
    2. 打开 manifest 中第一篇文档（cover 页）
    3. 后台监听所有 network request + page download 事件
    4. 用户在 UI 中手动操作"更多 → 导出 → Markdown"
    5. 脚本捕获 download 事件，保存到 ./endpoint_capture/
    6. 把请求 trace 与 download 元数据写入 endpoint.json
    7. 用户按 Enter 结束

产物:
    endpoint.json        — 录制到的 API 端点 + 关键 header
    endpoint_capture/    — 捕获的下载 markdown 原文（用于 sanity check）

这一步是 download.py 的依赖：我们用录制结果验证"导出 markdown"流程
可行，并提取批量重放需要的信息。如果发现 download 直接来自 UI 按钮触发的
单个 API 调用，则 download.py 可以直接 replay 该 API；否则退回到 UI 驱动模式
（每篇文档都模拟同样的点击序列）。
"""
from __future__ import annotations
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Download, Request

HERE = Path(__file__).parent
MANIFEST_PATH = HERE / 'manifest.json'
STATE_PATH = HERE / 'storage_state.json'
ENDPOINT_PATH = HERE / 'endpoint.json'
CAPTURE_DIR = HERE / 'endpoint_capture'

# 只记录这些主机的请求，避免 noise
INTERESTING_HOSTS = ('alidocs.dingtalk.com', 'docs.dingtalk.com', 'dingtalk.com')


async def main() -> int:
    if not STATE_PATH.exists():
        print(f'❌ {STATE_PATH} 不存在；请先跑 auth_bootstrap.py', file=sys.stderr)
        return 1
    if not MANIFEST_PATH.exists():
        print(f'❌ {MANIFEST_PATH} 不存在；请先跑 build_manifest.py', file=sys.stderr)
        return 1

    manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    if not manifest:
        print('❌ manifest 为空', file=sys.stderr)
        return 1

    target = manifest[0]
    print('=' * 60)
    print('导出端点录制模式')
    print('=' * 60)
    print(f'目标文档: {target["title"]}')
    print(f'URL: {target["url"]}')
    print('=' * 60)
    print('请在浏览器中找到「更多」按钮 → 「导出」 → 「Markdown」')
    print('脚本会捕获该次下载与对应 API 请求，存入 endpoint.json')
    print('=' * 60)

    CAPTURE_DIR.mkdir(exist_ok=True)
    requests: list[dict] = []
    downloads: list[dict] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(
            storage_state=str(STATE_PATH),
            viewport={'width': 1440, 'height': 900},
            locale='zh-CN',
            accept_downloads=True,
        )
        page = await ctx.new_page()

        # 监听所有请求
        def on_request(req: Request) -> None:
            host = req.url.split('/')[2] if '://' in req.url else ''
            if not any(h in host for h in INTERESTING_HOSTS):
                return
            # 过滤静态资源
            if any(req.url.endswith(ext) for ext in ('.js', '.css', '.png', '.jpg', '.jpeg', '.svg', '.woff', '.woff2', '.ico')):
                return
            requests.append({
                'ts': datetime.now().isoformat(timespec='milliseconds'),
                'method': req.method,
                'url': req.url,
                'resource_type': req.resource_type,
                'headers': dict(req.headers),
                'post_data': req.post_data,
            })

        # 监听下载
        async def on_download(dl: Download) -> None:
            suggested = dl.suggested_filename or f'capture-{len(downloads)}.bin'
            save_to = CAPTURE_DIR / f'{datetime.now():%H%M%S}-{suggested}'
            await dl.save_as(str(save_to))
            meta = {
                'ts': datetime.now().isoformat(timespec='milliseconds'),
                'suggested_filename': suggested,
                'url': dl.url,
                'saved_to': str(save_to),
                'size_bytes': save_to.stat().st_size if save_to.exists() else 0,
            }
            downloads.append(meta)
            print(f'\n📥 捕获下载: {suggested} → {save_to.name} ({meta["size_bytes"]} bytes)')

        page.on('request', on_request)
        page.on('download', lambda dl: asyncio.create_task(on_download(dl)))

        print(f'\n打开 {target["url"]} ...')
        await page.goto(target['url'], wait_until='domcontentloaded')

        await asyncio.to_thread(input, '\n>>> 完成"导出 → Markdown"操作后按 Enter 收尾: ')

        # 写出录制结果
        endpoint_data = {
            'recorded_at': datetime.now().isoformat(),
            'target_url': target['url'],
            'target_node_id': target['node_id'],
            'downloads': downloads,
            'request_count': len(requests),
            'requests_tail': requests[-50:],  # 只保留末 50 条避免文件爆炸
        }
        ENDPOINT_PATH.write_text(
            json.dumps(endpoint_data, indent=2, ensure_ascii=False),
            encoding='utf-8',
        )

        print(f'\n✅ 录制完成')
        print(f'   下载捕获: {len(downloads)} 个')
        print(f'   总请求数: {len(requests)} 条（记录末 50 条到 endpoint.json）')
        print(f'   {ENDPOINT_PATH}')
        print(f'   {CAPTURE_DIR}/')

        if not downloads:
            print('\n⚠️  未捕获到下载事件。可能原因：')
            print('   - 没有点击「导出 → Markdown」')
            print('   - 导出走 blob URL 而非下载事件（需切换到 fetch API 录制）')
            print('   请重试或反馈给开发者调整 download.py 策略。')

        await browser.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print('\n已取消')
        sys.exit(130)
