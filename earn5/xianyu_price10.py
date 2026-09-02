# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    page = next((pg for pg in ctx.pages if "publish" in pg.url), ctx.pages[-1])
    page.bring_to_front()

    # price -> 10
    price_inputs = page.locator('input.ant-input[placeholder="0.00"]')
    print("price inputs", price_inputs.count())
    price_inputs.nth(0).click()
    price_inputs.nth(0).fill("")
    price_inputs.nth(0).type("10", delay=40)
    print("price", price_inputs.nth(0).input_value())

    # 工期 -> 面议
    page.keyboard.press("Escape")
    time.sleep(0.2)
    page.locator("#rc_select_2").click(force=True)
    time.sleep(0.5)
    picked = False
    for name in ["面议", "待议", "15天以上"]:
        loc = page.locator(".ant-select-item-option-content", has_text=name)
        if loc.count():
            loc.first.click(force=True)
            print("工期", name)
            picked = True
            break
    if not picked:
        opts = page.locator(".ant-select-item-option-content")
        print("工期 options", [opts.nth(i).inner_text() for i in range(opts.count())])
        if opts.count():
            opts.last.click(force=True)
            print("工期 last", opts.last.inner_text())

    # patch description: 35 -> 10
    edited = page.evaluate(
        """() => {
      const el = document.querySelector('[contenteditable=true], .editor--MtHPS94K, [class*=editor]');
      if (!el) return {ok:false, reason:'no editor'};
      const html = el.innerHTML || '';
      const text = el.innerText || '';
      if (!text.includes('35') && !text.includes('¥35') && !text.includes('本页')) {
        // still rewrite key line if present
      }
      let next = text
        .replaceAll('¥35', '¥10')
        .replaceAll('本页 ¥35', '本页 ¥10')
        .replaceAll('本页¥35', '本页¥10')
        .replaceAll('仅为沟通/评估占位', '仅为沟通意向占位，正式项目另报，工期待议');
      if (next === text) {
        next = text.replace(/35/g, '10');
      }
      el.focus();
      // prefer textContent set + input events for react-ish editors
      el.innerText = next;
      el.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data: next}));
      return {ok:true, len: next.length, has10: next.includes('10'), snippet: next.slice(next.findIndex?.(()=>false) ?? Math.max(0, next.indexOf('购买说明')), Math.max(0, next.indexOf('购买说明'))+80)};
    }"""
    )
    print("desc", edited)

    # stronger desc replace via keyboard if needed
    area = page.locator('[contenteditable="true"]').first
    if area.count():
        txt = area.inner_text()
        if "¥35" in txt or "本页 ¥35" in txt or "35 仅为" in txt or "¥35" in txt:
            new_txt = (
                txt.replace("¥35", "¥10")
                .replace("本页 ¥35", "本页 ¥10")
                .replace("35 仅为", "10 仅为")
            )
            area.click()
            page.keyboard.press("Control+A")
            # use fill via evaluate insert
            page.evaluate(
                """(t) => {
                  const el = document.querySelector('[contenteditable=true]');
                  el.focus();
                  document.execCommand('selectAll');
                  document.execCommand('insertText', false, t);
                }""",
                new_txt,
            )
            print("desc keyboard patched")
        else:
            # ensure line about 10 exists
            if "本页 ¥10" not in txt and "¥10" not in txt:
                page.evaluate(
                    """() => {
                      const el = document.querySelector('[contenteditable=true]');
                      const t = el.innerText.replaceAll('35', '10');
                      el.focus();
                      document.execCommand('selectAll');
                      document.execCommand('insertText', false, t);
                      return t.includes('10');
                    }"""
                )
                print("desc 35->10 fallback")

    time.sleep(0.8)
    page.screenshot(path="earn5/xianyu_price10.png", full_page=False)
    print("DONE")
