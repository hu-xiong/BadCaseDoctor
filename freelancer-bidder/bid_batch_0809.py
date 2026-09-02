from playwright.sync_api import sync_playwright
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JOBS = [
    {
        "name": "Amazon India Product Research",
        "url": "https://www.freelancer.com/projects/electronics/Amazon-India-Product-Research",
        "amount": "3500",
        "days": "4",
        "proposal": (
            "Hi - I can deliver a data-backed Amazon India electronics shortlist for FBA launch decisions.\n\n"
            "Plan:\n"
            "1) Pull/compile product candidates in your niche (price, reviews, ratings, category, fees signals where available)\n"
            "2) Score demand vs competition with a simple transparent rubric\n"
            "3) Deliver Excel/CSV shortlist + top picks with why they look promising\n"
            "4) Short note on assumptions and next validation steps\n\n"
            "INR 3500 / 4 days. Quick question: any subcategory focus (earphones, cables, smart home, etc.) and target price band?"
        ),
    },
    {
        "name": "Extract PDF Text into Excel",
        "url": "https://www.freelancer.com/projects/pdf/Extract-PDF-Text-into-Excel",
        "amount": "900",
        "days": "2",
        "proposal": (
            "Hi - I can extract plain text from your PDF batch into a clean Excel file, line-by-line and in source order.\n\n"
            "Plan:\n"
            "1) Process the PDF set with a Python pipeline (pdfplumber/pypdf; OCR only if a page is scanned)\n"
            "2) Keep page/file mapping columns so every row is traceable\n"
            "3) Deliver one structured .xlsx + quick field note\n"
            "4) Send a small sample sheet first for your confirmation\n\n"
            "INR 900 / 2 days. How many PDFs roughly, and text-based or scanned?"
        ),
    },
    {
        "name": "Optimize Options Trading Strategy",
        "url": "https://www.freelancer.com/projects/data-analysis/Optimize-Options-Trading-Strategy",
        "amount": "4500",
        "days": "5",
        "proposal": (
            "Hi - I can help optimize your rules-based equity-options strategy with a clean Python backtest/analysis workflow.\n\n"
            "Plan:\n"
            "1) Reproduce your current rules on historical data\n"
            "2) Parameter sweeps (entry/exit, SL/target, filters) with walk-forward style checks\n"
            "3) Report win rate, avg R:R, drawdown, and trade log in Excel/CSV\n"
            "4) Recommend 2-3 improved rule sets with clear before/after metrics\n\n"
            "INR 4500 / 5 days. Please share your current rules and a sample of the data format you use."
        ),
    },
    {
        "name": "Android Word-Search Wordlist",
        "url": "https://www.freelancer.com/projects/data-management/Android-Word-Search-Wordlist-Compilation",
        "amount": "900",
        "days": "3",
        "proposal": (
            "Hi - I can compile a clean wordlist package for your Android word-search app.\n\n"
            "Plan:\n"
            "1) Build word lists by length/difficulty as you specify\n"
            "2) Deduplicate, normalize case, remove invalid tokens\n"
            "3) Deliver CSV/JSON ready for app import + sample categories\n"
            "4) Short readme for how to regenerate/extend the lists\n\n"
            "INR 900 / 3 days. Target language(s) and approx word-count per difficulty tier?"
        ),
    },
]


def dismiss(page):
    for text in ["Accept", "Accept all", "Got it", "Close", "Not now"]:
        try:
            loc = page.get_by_role("button", name=re.compile(text, re.I))
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=1200)
                page.wait_for_timeout(400)
        except Exception:
            pass


def fill_and_submit(page, amount, days, proposal):
    dismiss(page)
    for _ in range(8):
        page.mouse.wheel(0, 850)
        page.wait_for_timeout(250)
        if page.locator("#bidAmountInput, input[id*=bidAmount i]").count():
            break

    body = page.inner_text("body")
    if re.search(r"must sign the (Non-Disclosure|IP Agreement)", body, re.I):
        return {"ok": False, "reason": "nda_ip_required"}
    if re.search(r"3 steps before bidding", body, re.I) and not page.locator(
        "#bidAmountInput, input[id*=bidAmount i]"
    ).count():
        return {"ok": False, "reason": "three_steps_gate"}
    if page.get_by_role("button", name=re.compile(r"Edit Bid", re.I)).count():
        return {"ok": True, "reason": "already_bid"}

    try:
        page.wait_for_selector("#bidAmountInput, input[id*=bidAmount i], textarea", timeout=12000)
    except Exception:
        return {"ok": False, "reason": "no_form", "snippet": body[:250].replace("\n", " ")}

    info = page.evaluate(
        """(args) => {
          const a=args[0], d=args[1], text=args[2];
          const set=(el,v)=>{const proto=el.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto,'value').set.call(el,v); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true}));};
          let amountOk=false, daysOk=false;
          for (const el of document.querySelectorAll('input')) {
            if (!el.offsetParent) continue;
            const lab=((el.getAttribute('aria-label')||'')+' '+(el.id||'')+' '+(el.name||'')).toLowerCase();
            if (/bidamount|bid amount|amount/.test(lab)) { set(el,a); amountOk=true; }
            if (/period|day/.test(lab)) { set(el,d); daysOk=true; }
          }
          const tas=[...document.querySelectorAll('textarea')].filter(t=>t.offsetParent && t.placeholder!=='Type a message');
          const ta=tas[0];
          if (ta) set(ta,text);
          const btn=[...document.querySelectorAll('button')].find(b=>/place\\s*a?\\s*bid|update\\s*bid/i.test((b.innerText||'').trim()));
          if (btn) { btn.scrollIntoView({block:'center'}); btn.click(); }
          return {amountOk, daysOk, ta: ta && ta.value.length, btn: !!btn, btnText: btn && btn.innerText.trim()};
        }""",
        [amount, days, proposal],
    )
    page.wait_for_timeout(4000)
    body2 = page.inner_text("body")
    success = bool(page.get_by_role("button", name=re.compile(r"Edit Bid", re.I)).count()) or bool(
        re.search(r"Your bid:\s*[₹$]", body2, re.I)
    )
    return {"ok": success, "reason": "submitted" if success else "clicked_uncertain", **info}


def main():
    results = []
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=r"C:\Users\h2629\AppData\Local\Temp\freelancer-bid-profile",
            channel="chrome",
            headless=False,
            viewport={"width": 1360, "height": 960},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.freelancer.com/manage/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(2500)
        print("logged", "@huxiong" in page.content())

        for job in JOBS:
            print("\n===", job["name"], "===")
            try:
                page.goto(job["url"], wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(3500)
                r = fill_and_submit(page, job["amount"], job["days"], job["proposal"])
                print(r)
                results.append({"name": job["name"], "amount": job["amount"], "days": job["days"], **r})
            except Exception as e:
                print("ERROR", e)
                results.append({"name": job["name"], "ok": False, "reason": str(e)})

        page.goto("https://www.freelancer.com/manage/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(3500)
        rows = page.evaluate(
            """() => [...document.querySelectorAll('tr')].slice(0,20).map(tr => tr.innerText.replace(/\\s+/g,' ').trim()).filter(Boolean)"""
        )
        print("\n=== MANAGE ===")
        for row in rows:
            print(row[:240])
        print("\n=== SUMMARY ===")
        for r in results:
            print(r)
        time.sleep(8)
        ctx.close()


if __name__ == "__main__":
    main()
