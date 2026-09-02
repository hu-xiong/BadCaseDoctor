# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time
from pathlib import Path

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    page = next((pg for pg in ctx.pages if "publish" in pg.url), ctx.pages[-1])
    page.bring_to_front()

    # find yellow publish CTA via DOM
    info = page.evaluate(
        """() => {
      const nodes = [...document.querySelectorAll('button, div, span, a')];
      const hits = [];
      for (const el of nodes) {
        const t = (el.innerText || '').trim();
        if (t === '\u53d1\u5e03' || t === '\u786e\u8ba4\u53d1\u5e03') {
          const r = el.getBoundingClientRect();
          hits.push({
            tag: el.tagName,
            className: (el.className||'').toString().slice(0,100),
            text: t,
            w: Math.round(r.width), h: Math.round(r.height),
            y: Math.round(r.y), x: Math.round(r.x),
            disabled: !!(el.disabled || el.getAttribute('disabled') || el.getAttribute('aria-disabled')==='true'),
          });
        }
      }
      return hits;
    }"""
    )
    Path("earn5/xianyu_publish_btns.json").write_text(
        __import__("json").dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("hits", len(info))

    # click the largest bottom-ish 发布
    clicked = page.evaluate(
        """() => {
      const nodes = [...document.querySelectorAll('button, div[role=button], span, a')];
      let best = null;
      for (const el of nodes) {
        const t = (el.innerText || '').trim();
        if (t !== '\u53d1\u5e03') continue;
        const r = el.getBoundingClientRect();
        if (r.width < 80 || r.height < 30) continue;
        if (!best || r.y > best.r.y) best = {el, r};
      }
      if (!best) return {ok:false};
      best.el.scrollIntoView({block:'center'});
      best.el.click();
      return {ok:true, y: Math.round(best.r.y), w: Math.round(best.r.width), h: Math.round(best.r.height), cls:(best.el.className||'').toString().slice(0,80)};
    }"""
    )
    print("click", clicked)
    time.sleep(2)

    # confirm dialogs
    for name in [
        "\u786e\u5b9a",
        "\u786e\u8ba4\u53d1\u5e03",
        "\u7ee7\u7eed\u53d1\u5e03",
        "\u77e5\u9053\u4e86",
        "\u6211\u77e5\u9053\u4e86",
    ]:
        try:
            loc = page.get_by_text(name, exact=True)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=1500)
                print("dialog", name.encode("unicode_escape").decode())
                time.sleep(1)
        except Exception:
            pass

    time.sleep(3)
    # toast / message
    msgs = page.evaluate(
        """() => {
      const sels = ['.ant-message', '.ant-notification', '.ant-modal', '[class*=toast]', '[class*=Toast]', '[class*=message]'];
      const out = [];
      for (const s of sels) {
        for (const el of document.querySelectorAll(s)) {
          const t = (el.innerText||'').trim();
          if (t) out.push(t.slice(0,200));
        }
      }
      return out.slice(0,10);
    }"""
    )
    Path("earn5/xianyu_publish_msgs.txt").write_text(
        f"url={page.url}\nmsgs={msgs}\n", encoding="utf-8"
    )
    page.screenshot(path="earn5/xianyu_after_publish2.png", full_page=False)
    print("url", page.url)
    print("DONE")
