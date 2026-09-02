# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    page = next((pg for pg in ctx.pages if "publish" in pg.url), ctx.pages[-1])
    page.bring_to_front()

    # scroll to selects
    page.locator("text=计价方式").first.scroll_into_view_if_needed()
    time.sleep(0.3)

    # open first select by placeholder-like text
    page.locator("text=请选择计价方式").first.click(timeout=5000)
    time.sleep(0.6)
    # list options
    opts = page.locator(".ant-select-item-option-content")
    print("options1", opts.count())
    for i in range(min(opts.count(), 10)):
        print(" -", opts.nth(i).inner_text())
    # choose something sensible
    chosen = False
    for name in ["一口价", "按次", "面议", "固定价格"]:
        o = page.locator(f".ant-select-item-option-content:text-is('{name}')")
        if o.count():
            o.first.click()
            print("chose", name)
            chosen = True
            break
    if not chosen and opts.count():
        print("chose first", opts.first.inner_text())
        opts.first.click()

    time.sleep(0.5)
    page.locator("text=请选择预计工期").first.click(timeout=5000)
    time.sleep(0.6)
    opts = page.locator(".ant-select-item-option-content")
    print("options2", opts.count())
    for i in range(min(opts.count(), 10)):
        print(" -", opts.nth(i).inner_text())
    chosen = False
    for name in ["3天内", "7天内", "1天内", "1周内"]:
        o = page.locator(f".ant-select-item-option-content:text-is('{name}')")
        if o.count():
            o.first.click()
            print("chose", name)
            chosen = True
            break
    if not chosen and opts.count():
        print("chose first", opts.first.inner_text())
        opts.first.click()

    time.sleep(0.5)
    page.screenshot(path="earn5/xianyu_ready2.png", full_page=False)
    print("OK")
