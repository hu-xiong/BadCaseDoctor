# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    page = next((pg for pg in ctx.pages if "publish" in pg.url), ctx.pages[-1])
    page.bring_to_front()

    # close any open dropdown
    page.keyboard.press("Escape")
    time.sleep(0.3)

    page.locator("#rc_select_1").click(force=True)
    time.sleep(0.5)
    page.locator(".ant-select-item-option-content", has_text="元/次").first.click(force=True)
    print("计价=元/次")
    time.sleep(0.4)

    page.locator("#rc_select_2").click(force=True)
    time.sleep(0.5)
    page.locator(".ant-select-item-option-content", has_text="1-5天").first.click(force=True)
    print("工期=1-5天")
    time.sleep(0.5)

    page.screenshot(path="earn5/xianyu_ready2.png", full_page=False)
    print("OK")
