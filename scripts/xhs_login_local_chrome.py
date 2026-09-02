# -*- coding: utf-8 -*-
"""One-shot Xiaohongshu login using local Chrome; save sau cookie file."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from patchright.async_api import async_playwright

COOKIE = Path(
    r"C:\Users\h2629\.cursor\skills\social-media-publish\engines\social-auto-upload\cookies\xiaohongshu_default.json"
)
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
if not CHROME.exists():
    CHROME = Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")

LOGIN_URL = "https://creator.xiaohongshu.com/login"
LOGIN_BOX = "div[class*='login-box']"


async def login_done(page) -> bool:
    if page.url.startswith("https://creator.xiaohongshu.com/login"):
        return False
    box = page.locator(LOGIN_BOX).first
    if await box.count() == 0:
        return True
    try:
        return not await box.is_visible()
    except Exception:
        return True


async def main() -> int:
    if not CHROME.exists():
        print(f"NO_BROWSER {CHROME}")
        return 1
    COOKIE.parent.mkdir(parents=True, exist_ok=True)
    print(f"browser={CHROME}")
    print(f"cookie_out={COOKIE}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            executable_path=str(CHROME),
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context()
        page = await context.new_page()
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        print("OPENED_LOGIN_PAGE: 请在弹出的浏览器窗口里扫码登录（约 5 分钟内）")
        for i in range(120):
            if await login_done(page):
                await asyncio.sleep(2)
                await context.storage_state(path=str(COOKIE))
                print(f"LOGIN_OK saved={COOKIE} url={page.url}")
                await context.close()
                await browser.close()
                return 0
            if i % 10 == 0:
                print(f"waiting_scan... {i*3}s url={page.url}")
            await asyncio.sleep(3)
        print("LOGIN_TIMEOUT")
        await context.close()
        await browser.close()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
