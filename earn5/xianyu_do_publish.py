# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time
from pathlib import Path

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    page = next((pg for pg in ctx.pages if "publish" in pg.url), None)
    if page is None:
        # fallback: any goofish page
        page = next((pg for pg in ctx.pages if "goofish" in pg.url), ctx.pages[-1])
        page.goto("https://www.goofish.com/publish", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

    page.bring_to_front()
    print("url", page.url)

    # click yellow 发布 button at bottom (not header)
    clicked = False
    # prefer button role
    candidates = [
        page.get_by_role("button", name="\u53d1\u5e03"),  # 发布
        page.locator("button:has-text('\u53d1\u5e03')"),
        page.locator("text='\u53d1\u5e03'"),
    ]
    for loc in candidates:
        try:
            n = loc.count()
            print("cand", n)
            if n == 0:
                continue
            # click the last visible one (bottom CTA)
            target = loc.nth(n - 1)
            target.scroll_into_view_if_needed()
            target.click(timeout=5000, force=True)
            clicked = True
            print("clicked publish")
            break
        except Exception as e:
            print("fail", type(e).__name__, str(e)[:120])

    if not clicked:
        raise SystemExit("PUBLISH_BTN_NOT_FOUND")

    time.sleep(3)
    # handle confirm dialog if any
    for name in ["\u786e\u5b9a", "\u77e5\u9053\u4e86", "\u7ee7\u7eed\u53d1\u5e03", "\u786e\u8ba4\u53d1\u5e03"]:
        loc = page.get_by_role("button", name=name)
        try:
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=2000)
                print("confirm", name)
                time.sleep(1)
        except Exception:
            pass

    time.sleep(2)
    page.screenshot(path="earn5/xianyu_after_publish.png", full_page=False)
    Path("earn5/xianyu_after_publish.txt").write_text(
        f"url={page.url}\nbody={page.inner_text('body')[:2000]}",
        encoding="utf-8",
    )
    print("DONE")
