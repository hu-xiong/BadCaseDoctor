# -*- coding: utf-8 -*-
from playwright.sync_api import sync_playwright
import time
from pathlib import Path

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9333")
    ctx = browser.contexts[0]
    page = next((pg for pg in ctx.pages if "publish" in pg.url), ctx.pages[-1])
    page.bring_to_front()

    # dump inputs
    info = page.evaluate(
        """() => {
      const nodes = [...document.querySelectorAll('input, textarea, [contenteditable=true]')];
      return nodes.map((el, i) => ({
        i,
        tag: el.tagName,
        type: el.getAttribute('type'),
        name: el.getAttribute('name'),
        placeholder: el.getAttribute('placeholder'),
        className: (el.className || '').toString().slice(0, 80),
        value: (el.value || el.innerText || '').toString().slice(0, 40),
        aria: el.getAttribute('aria-label'),
      }));
    }"""
    )
    Path("earn5/xianyu_inputs.json").write_text(
        __import__("json").dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("inputs", len(info))

    # Try set price via JS on likely fields near 价格
    result = page.evaluate(
        """() => {
      const labels = [...document.querySelectorAll('*')].filter(el => el.childNodes.length && [...el.childNodes].some(n => n.nodeType===3 && n.textContent.trim()==='价格'));
      let filled = [];
      for (const lab of labels.slice(0, 8)) {
        let root = lab.parentElement;
        for (let k=0;k<4 && root;k++) {
          const inputs = root.querySelectorAll('input');
          for (const inp of inputs) {
            const ph = (inp.placeholder||'') + (inp.getAttribute('aria-label')||'');
            if (ph.includes('原价')) continue;
            inp.focus();
            inp.value = '';
            inp.dispatchEvent(new Event('input', {bubbles:true}));
            inp.value = '35';
            inp.dispatchEvent(new Event('input', {bubbles:true}));
            inp.dispatchEvent(new Event('change', {bubbles:true}));
            filled.push({ph, value: inp.value, className: (inp.className||'').toString().slice(0,60)});
          }
          root = root.parentElement;
        }
      }
      return filled;
    }"""
    )
    print("js fill", result)

    # Also try React-like native setter
    result2 = page.evaluate(
        """() => {
      function setNative(el, val) {
        const proto = window.HTMLInputElement.prototype;
        const desc = Object.getOwnPropertyDescriptor(proto, 'value');
        desc.set.call(el, val);
        el.dispatchEvent(new Event('input', {bubbles:true}));
        el.dispatchEvent(new Event('change', {bubbles:true}));
      }
      const inputs = [...document.querySelectorAll('input')].filter(i => {
        const t = (i.type||'').toLowerCase();
        return t === 'text' || t === 'number' || t === '' || t === 'tel';
      });
      const out = [];
      for (const inp of inputs) {
        const box = inp.closest('div');
        const txt = (box && box.innerText || '').slice(0, 30);
        if (txt.includes('价格') && !txt.includes('原价')) {
          setNative(inp, '35');
          out.push({txt, value: inp.value});
        }
      }
      // fallback: any input currently showing 0.00 near currency
      if (!out.length) {
        for (const inp of inputs) {
          if ((inp.value === '0.00' || inp.value === '0' || inp.value === '') && (inp.parentElement?.innerText||'').includes('￥')) {
            setNative(inp, '35');
            out.push({fallback: true, value: inp.value, parent: (inp.parentElement?.innerText||'').slice(0,40)});
            break;
          }
        }
      }
      return out;
    }"""
    )
    print("native fill", result2)

    time.sleep(1)
    page.screenshot(path="earn5/xianyu_price_fixed.png", full_page=False)
    print("shot ok")
