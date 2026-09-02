# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    page = next((pg for pg in ctx.pages if "publish" in pg.url), ctx.pages[-1])
    page.bring_to_front()

    # 计价方式 = rc_select_1
    page.locator("#rc_select_1").click(force=True)
    time.sleep(0.6)
    opts = page.locator(".ant-select-item-option-content")
    print("options1", opts.count())
    texts = [opts.nth(i).inner_text() for i in range(opts.count())]
    print(texts)
    pick = None
    for name in texts:
        if any(k in name for k in ("一口", "按次", "面议", "固定")):
            pick = name
            break
    if pick is None and texts:
        pick = texts[0]
    if pick:
        page.locator(".ant-select-item-option-content", has_text=pick).first.click()
        print("chose1", pick)

    time.sleep(0.4)
    # 预计工期 = rc_select_2 likely
    page.locator("#rc_select_2").click(force=True)
    time.sleep(0.6)
    opts = page.locator(".ant-select-item-option-content")
    print("options2", opts.count())
    texts = [opts.nth(i).inner_text() for i in range(opts.count())]
    print(texts)
    pick = None
    for name in texts:
        if any(k in name for k in ("3天", "7天", "1天", "周")):
            pick = name
            break
    if pick is None and texts:
        pick = texts[0]
    if pick:
        page.locator(".ant-select-item-option-content", has_text=pick).first.click()
        print("chose2", pick)

    time.sleep(0.5)
    page.screenshot(path="earn5/xianyu_ready2.png", full_page=False)
    print("OK")
