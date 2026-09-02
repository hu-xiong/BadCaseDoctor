# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time
from pathlib import Path

MIAN_YI = "\u9762\u8bae"  # 面议
YUAN_CI = "\u5143/\u6b21"  # 元/次

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    page = next((pg for pg in ctx.pages if "publish" in pg.url), ctx.pages[-1])
    page.bring_to_front()

    # price 10
    price_inputs = page.locator('input.ant-input[placeholder="0.00"]')
    price_inputs.nth(0).click()
    price_inputs.nth(0).fill("")
    price_inputs.nth(0).type("10", delay=40)
    val = price_inputs.nth(0).input_value()

    page.keyboard.press("Escape")
    time.sleep(0.2)

    # pricing method keep 元/次
    page.locator("#rc_select_1").click(force=True)
    time.sleep(0.4)
    page.locator(".ant-select-item-option-content", has_text=YUAN_CI).first.click(force=True)
    time.sleep(0.3)

    # duration 面议
    page.locator("#rc_select_2").click(force=True)
    time.sleep(0.5)
    opts = page.locator(".ant-select-item-option-content")
    texts = [opts.nth(i).inner_text() for i in range(opts.count())]
    Path("earn5/xianyu_opts.txt").write_text("\n".join(texts), encoding="utf-8")
    target = None
    for t in texts:
        if MIAN_YI in t or "\u5f85\u8bae" in t:  # 待议
            target = t
            break
    if target is None:
        for t in texts:
            if "15" in t:
                target = t
                break
    if target is None and texts:
        target = texts[-1]
    page.locator(".ant-select-item-option-content", has_text=target).first.click(force=True)

    # desc replace 35->10
    area = page.locator('[contenteditable="true"]').first
    txt = area.inner_text()
    new_txt = txt.replace("\uffe535", "\uffe510").replace("35", "10")
    # careful: don't wreck other numbers if any - listing mainly has 35
    new_txt = (
        txt.replace("¥35", "¥10")
        .replace("￥35", "￥10")
        .replace("本页 ¥35", "本页 ¥10")
        .replace("本页¥35", "本页¥10")
    )
    if "¥35" in txt or "35" in txt:
        # only replace purchase-note style 35
        new_txt = txt
        new_txt = new_txt.replace("¥35", "¥10").replace("￥35", "￥10")
        if "本页" in new_txt and "35" in new_txt:
            new_txt = new_txt.replace("35", "10")
    page.evaluate(
        """(t) => {
          const el = document.querySelector('[contenteditable=true]');
          el.focus();
          document.execCommand('selectAll');
          document.execCommand('insertText', false, t);
        }""",
        new_txt,
    )
    time.sleep(0.5)
    final = area.inner_text()
    Path("earn5/xianyu_desc_check.txt").write_text(final, encoding="utf-8")
    page.screenshot(path="earn5/xianyu_price10.png", full_page=False)
    Path("earn5/xianyu_status.txt").write_text(
        f"price={val}\nduration={target}\nhas35={'35' in final}\nhas10price_line={'10' in final}\n",
        encoding="utf-8",
    )
    print("OK")
