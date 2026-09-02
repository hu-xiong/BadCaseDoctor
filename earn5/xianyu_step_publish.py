# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    page = ctx.pages[0]

    clicked = False
    for sel in ['text=发布', 'a:has-text("发布")', 'text=卖闲置']:
        loc = page.locator(sel).first
        try:
            if loc.count() and loc.is_visible():
                loc.click(timeout=5000)
                clicked = True
                print("clicked", sel)
                break
        except Exception as e:
            print("fail", sel, type(e).__name__, e)

    if not clicked:
        page.goto("https://www.goofish.com/publish", wait_until="domcontentloaded", timeout=60000)
        print("navigated publish")

    time.sleep(3)
    print("URL:", page.url)
    page.screenshot(path=r"earn5\xianyu_publish.png", full_page=False)
    body = page.inner_text("body")[:2000]
    print("BODY_SNIP:", body.replace("\n", " | ")[:1500])
