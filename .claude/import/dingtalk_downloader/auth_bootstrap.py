#!/usr/bin/env python3
"""首次登录引导：打开浏览器，等用户扫码登录后保存 storage_state.json。

用法:
    python3 auth_bootstrap.py

流程:
    1. Chromium 可见模式打开 alidocs.dingtalk.com
    2. 用户在浏览器中完成扫码登录 / 账号密码登录
    3. 用户回到终端按 Enter 确认
    4. 脚本保存 storage_state.json（含 cookie + localStorage）
    5. 后续 download.py 复用该 state 跑 headless
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

ENTRY_URL = 'https://alidocs.dingtalk.com/'
STATE_PATH = Path(__file__).parent / 'storage_state.json'


async def main() -> int:
    print('=' * 60)
    print('钉钉文档登录引导')
    print('=' * 60)
    print(f'1. 浏览器即将打开 {ENTRY_URL}')
    print('2. 请在浏览器中完成扫码 / 账号密码登录')
    print('3. 登录成功后，回到此终端按 Enter 保存登录态')
    print('=' * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context(
            viewport={'width': 1440, 'height': 900},
            locale='zh-CN',
        )
        page = await ctx.new_page()
        await page.goto(ENTRY_URL, wait_until='domcontentloaded')

        # 阻塞等待用户输入（异步上下文中用 to_thread）
        await asyncio.to_thread(input, '\n>>> 登录完成后按 Enter 继续（Ctrl+C 取消）: ')

        # 简单健全性检查：当前 URL 不应在登录页
        current = page.url
        if 'login' in current.lower():
            print(f'⚠️  当前仍在登录页 ({current})，未保存 state。请重试。', file=sys.stderr)
            await browser.close()
            return 1

        await ctx.storage_state(path=str(STATE_PATH))
        print(f'\n✅ 登录态已保存到: {STATE_PATH}')
        print(f'   当前 URL: {current}')

        await browser.close()
    return 0


if __name__ == '__main__':
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print('\n已取消')
        sys.exit(130)
