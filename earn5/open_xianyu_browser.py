from playwright.sync_api import sync_playwright
import time

PROFILE = r"earn5\xianyu-browser-profile"
URL = "https://www.goofish.com/publish"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE,
        headless=False,
        viewport={"width": 1280, "height": 900},
        args=["--remote-debugging-port=9333"],
        locale="zh-CN",
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    print("BROWSER_READY port=9333 url=" + page.url)
    # keep open until killed
    while True:
        time.sleep(5)
