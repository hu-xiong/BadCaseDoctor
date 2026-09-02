from playwright.sync_api import sync_playwright
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = "https://www.freelancer.com/projects/excel-macros/Excel-VBA-Based-Index-Option/details"
BID_AMT = "2000"
BID_DAYS = "5"
BID_TEXT = (
    "Hi - I can build a practical Excel VBA Index Option analysis workbook for NIFTY first, "
    "with structure ready to extend to SENSEX.\n\n"
    "MVP for INR 2000:\n"
    "1) Index selector dashboard (NIFTY now; SENSEX hook)\n"
    "2) Option-chain import (auto pull where stable + fallback import)\n"
    "3) Common analysis: ATM, 6 above/below, basic momentum/status, S/R style levels, simple signals\n"
    "4) Separate history area per index\n"
    "5) Short usage note\n\n"
    "Out of scope for this budget: full live 3-minute multi-index production bot, paid data feeds, web/mobile UI.\n"
    "Delivery in 5 days. Preferred expiry: nearest weekly or monthly?"
)


def click_first(page, names):
    for name in names:
        try:
            loc = page.get_by_role("button", name=re.compile(name, re.I))
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=2500)
                page.wait_for_timeout(1200)
                return name
        except Exception:
            pass
        try:
            loc = page.get_by_text(re.compile(r"^" + name + r"$", re.I))
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=2500)
                page.wait_for_timeout(1200)
                return name
        except Exception:
            pass
    return None


def sign_agreements(page):
    body = page.inner_text("body")
    print("need NDA", "Non-Disclosure Agreement" in body or "sign the Non-Disclosure" in body)
    print("need IP", "IP Agreement" in body or "sign the IP" in body)

    for label in ["NDA", "Non-Disclosure", "IP Agreement", "IP AGREEMENT"]:
        try:
            loc = page.get_by_text(label, exact=False)
            if loc.count():
                # click the actionable one near project sidebar
                for i in range(min(loc.count(), 4)):
                    try:
                        el = loc.nth(i)
                        if el.is_visible():
                            el.click(timeout=1500)
                            page.wait_for_timeout(1500)
                            print("opened", label, i)
                            # check all boxes
                            page.evaluate(
                                """() => {
                              [...document.querySelectorAll('input[type=checkbox]')].forEach(c => {
                                if (!c.checked && c.offsetParent !== null) c.click();
                              });
                            }"""
                            )
                            clicked = click_first(
                                page,
                                [
                                    r"I Agree",
                                    r"Agree",
                                    r"Accept",
                                    r"Sign",
                                    r"Continue",
                                    r"Submit",
                                    r"Confirm",
                                ],
                            )
                            print("confirm", clicked)
                            page.wait_for_timeout(2000)
                            break
                    except Exception as e:
                        print("open fail", label, e)
        except Exception as e:
            print("label fail", label, e)


def fill_bid(page):
    page.wait_for_timeout(2000)
    # scroll
    for _ in range(6):
        page.mouse.wheel(0, 700)
        page.wait_for_timeout(250)

    has = page.evaluate(
        """() => ({
          bidAmount: !!document.querySelector('#bidAmountInput, input[id*=bidAmount i], input[aria-label*=\"Bid\" i]'),
          textarea: [...document.querySelectorAll('textarea')].some(t => /proposal|describe|bid|write/i.test((t.placeholder||'')+(t.getAttribute('aria-label')||'')) || (t.offsetParent && t.placeholder !== 'Type a message')),
          anyNumber: [...document.querySelectorAll('input[type=number]')].filter(e=>e.offsetParent).length,
          anyTa: [...document.querySelectorAll('textarea')].filter(e=>e.offsetParent).map(t=>t.placeholder)
        })"""
    )
    print("form probe", has)
    if not has.get("bidAmount") and has.get("anyNumber", 0) == 0:
        return {"ok": False, "reason": "no_form"}

    info = page.evaluate(
        """(args) => {
          const a = args[0], d = args[1], text = args[2];
          const set = (el, v) => {
            const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
            Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
          };
          let amountOk=false, daysOk=false;
          for (const el of document.querySelectorAll('input')) {
            if (!el.offsetParent) continue;
            const lab = ((el.getAttribute('aria-label')||'')+' '+(el.id||'')+' '+(el.name||'')).toLowerCase();
            if (/bidamount|bid amount|amount/.test(lab)) { set(el, a); amountOk=true; }
            if (/period|day/.test(lab)) { set(el, d); daysOk=true; }
          }
          const tas = [...document.querySelectorAll('textarea')].filter(t => t.offsetParent && t.placeholder !== 'Type a message');
          const ta = tas[0] || null;
          if (ta) set(ta, text);
          const btn = [...document.querySelectorAll('button')].find(b => /place\\s*a?\\s*bid|update\\s*bid/i.test((b.innerText||'').trim()));
          if (btn) { btn.scrollIntoView({block:'center'}); btn.click(); }
          return {amountOk, daysOk, ta: ta && ta.value.length, btn: !!btn, btnText: btn && btn.innerText.trim()};
        }""",
        [BID_AMT, BID_DAYS, BID_TEXT],
    )
    return {"ok": True, **info}


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=r"C:\Users\h2629\AppData\Local\Temp\freelancer-bid-profile",
            channel="chrome",
            headless=False,
            viewport={"width": 1400, "height": 1100},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(4000)

        # Do signing twice (NDA + IP)
        for round_i in range(3):
            sign_agreements(page)
            page.goto(URL, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(3000)
            body = page.inner_text("body")
            still = ("must sign the Non-Disclosure" in body) or ("must sign the IP Agreement" in body)
            print("round", round_i, "still_blocked", still)
            if not still:
                break

        result = fill_bid(page)
        print("bid_result", result)
        page.wait_for_timeout(4000)

        page.goto("https://www.freelancer.com/manage/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(3500)
        row = page.evaluate(
            """() => {
              const tr=[...document.querySelectorAll('tr')].find(t=>/Index Option|VBA/i.test(t.innerText||''));
              return tr ? tr.innerText.replace(/\\s+/g,' ').trim() : null;
            }"""
        )
        print("MANAGE", row)
        # leftover blockers
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(2500)
        body = page.inner_text("body")
        for line in body.splitlines():
            if re.search(r"must sign|NDA|IP Agreement|Edit Bid|Your bid", line, re.I) and len(line.strip()) < 120:
                print(">", line.strip())
        time.sleep(6)
        ctx.close()


if __name__ == "__main__":
    main()
