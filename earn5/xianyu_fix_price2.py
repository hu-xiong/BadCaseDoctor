# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    page = next((pg for pg in ctx.pages if "publish" in pg.url), ctx.pages[-1])
    page.bring_to_front()

    price_inputs = page.locator('input.ant-input[placeholder="0.00"]')
    print("price inputs", price_inputs.count())
    # first = 价格, second = 原价
    price_inputs.nth(0).click()
    price_inputs.nth(0).fill("")
    price_inputs.nth(0).type("35", delay=50)
    print("price value", price_inputs.nth(0).input_value())

    # optional original price leave empty / 0
    time.sleep(0.5)

    # ensure 无需邮寄 if visible
    loc = page.locator("text=无需邮寄").first
    try:
        if loc.count() and loc.is_visible():
            loc.click(timeout=2000)
            print("clicked no shipping")
    except Exception as e:
        print("ship", e)

    page.screenshot(path="earn5/xianyu_price_fixed.png", full_page=False)
    print("done")
