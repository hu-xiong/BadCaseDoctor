# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time
from pathlib import Path

out = Path("earn5")
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    print("pages:", len(ctx.pages))
    for i, page in enumerate(ctx.pages):
        print(f"[{i}] {page.url}")
        page.screenshot(path=str(out / f"xianyu_tab_{i}.png"), full_page=False)

    page = ctx.pages[-1]
    # try open publish via known routes
    for url in [
        "https://www.goofish.com/publish",
        "https://www.goofish.com/sell",
        "https://2.taobao.com/auction/item/item_edit.htm",
    ]:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(2)
            print("GOTO", url, "->", page.url)
            page.screenshot(path=str(out / "xianyu_after_goto.png"), full_page=False)
            # write text safe
            text = page.inner_text("body")
            (out / "xianyu_body.txt").write_text(text[:4000], encoding="utf-8")
            break
        except Exception as e:
            print("fail goto", url, type(e).__name__, str(e)[:200])
