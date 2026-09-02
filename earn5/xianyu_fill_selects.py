# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    page = next((pg for pg in ctx.pages if "publish" in pg.url), ctx.pages[-1])
    page.bring_to_front()

    # 计价方式
    try:
        page.get_by_text("请选择", exact=True).nth(0).click(timeout=3000)
        time.sleep(0.5)
        # prefer 一口价 / 按次 / 面议
        for opt in ["一口价", "按次收费", "按次", "面议", "其他"]:
            loc = page.locator(f"text={opt}").first
            if loc.count() and loc.is_visible():
                loc.click(timeout=2000)
                print("计价方式 ->", opt)
                break
        else:
            # pick first dropdown option
            opts = page.locator(".ant-select-item-option")
            if opts.count():
                txt = opts.first.inner_text()
                opts.first.click()
                print("计价方式 first ->", txt)
    except Exception as e:
        print("计价方式 fail", type(e).__name__, e)

    time.sleep(0.5)

    # 预计工期 - second 请选择
    try:
        # reopen if needed
        remains = page.get_by_text("请选择", exact=True)
        if remains.count():
            remains.first.click(timeout=3000)
            time.sleep(0.5)
            for opt in ["1天内", "3天内", "7天内", "1周内", "面议"]:
                loc = page.locator(f".ant-select-item-option:has-text('{opt}')").first
                if loc.count():
                    loc.click(timeout=2000)
                    print("工期 ->", opt)
                    break
            else:
                opts = page.locator(".ant-select-item-option")
                if opts.count():
                    txt = opts.first.inner_text()
                    opts.first.click()
                    print("工期 first ->", txt)
    except Exception as e:
        print("工期 fail", type(e).__name__, e)

    time.sleep(1)
    page.screenshot(path="earn5/xianyu_ready.png", full_page=True)
    print("READY")
