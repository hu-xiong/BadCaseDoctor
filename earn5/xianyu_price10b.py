# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time
from pathlib import Path

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    page = next((pg for pg in ctx.pages if "publish" in pg.url), ctx.pages[-1])
    page.bring_to_front()

    price_inputs = page.locator('input.ant-input[placeholder="0.00"]')
    price_inputs.nth(0).click()
    price_inputs.nth(0).fill("")
    price_inputs.nth(0).type("10", delay=40)
    val = price_inputs.nth(0).input_value()

    # ensure duration 面议
    page.keyboard.press("Escape")
    time.sleep(0.2)
    page.locator("#rc_select_2").click(force=True)
    time.sleep(0.5)
    page.locator(".ant-select-item-option-content", has_text="面议").first.click(force=True)

    # fix desc 35 -> 10 without printing unicode
    area = page.locator('[contenteditable="true"]').first
    txt = area.inner_text()
    new_txt = (
        txt.replace("¥35", "¥10")
        .replace("本页 ¥35", "本页 ¥10")
        .replace("本页¥35", "本页¥10")
    )
    # also bare 35 in purchase note
    new_txt = new_txt.replace("本页 35", "本页 ¥10").replace("仅为沟通/评估占位", "仅为沟通意向占位，正式项目另报，工期待议")
    if "35" in new_txt and "本页" in new_txt:
        new_txt = new_txt.replace("35", "10", 1)
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
        f"price={val}\nhas35={'35' in final}\nhas10={'10' in final}\n", encoding="utf-8"
    )
    print("OK")
