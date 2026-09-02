"""Submit Freelancer bids via headed Chrome. Login once if needed, then auto-fill."""
from __future__ import annotations

import re
import time
from playwright.sync_api import sync_playwright

BIDS = [
    {
        "name": "Excel Data Cleaning & ML",
        "url": "https://www.freelancer.com/projects/data-analysis/Excel-Data-Cleaning-40622729",
        "amount": "5500",
        "days": "4",
        "proposal": (
            "Hi - I can turn your messy Excel into a model-ready workbook, then wire a lightweight ML workflow you can re-run.\n\n"
            "Plan:\n"
            "1) Profile columns, duplicates, formats, missing values\n"
            "2) Clean + reshape with Power Query (steps saved) and/or Python-in-Excel / small external script\n"
            "3) Train a simple classification or regression model with clear inputs/outputs + refresh steps\n"
            "4) Short walkthrough so you can repeat on new files\n\n"
            "Delivery: cleaned workbook + working model + 1-2 page guide in 4 days.\n"
            "Quick question: roughly how many rows/sheets, and is the target classification or regression?"
        ),
    },
    {
        "name": "Pincode Stock Tracker",
        "url": "https://www.freelancer.com/projects/web-scraping/Pincode-Stock-Tracker-Needed",
        "amount": "900",
        "days": "3",
        "proposal": (
            "Hi - I can build a small Windows/VPS tool that checks Bigbasket + Flipkart electronics for each pincode: "
            "in-stock flag and current price, with CSV/Sheet output and 15-30 min refresh.\n\n"
            "Approach:\n"
            "1) Requests/Selenium scrapers with throttling + rotating headers\n"
            "2) Pincode input list -> stock + price rows\n"
            "3) CSV export (optional light dashboard)\n"
            "4) Full source + setup guide + sample run for 3 pincodes\n\n"
            "Delivery in 3 days. One question: do you have product URLs/ASINs already, or should the tool also search by keyword?"
        ),
    },
    {
        "name": "Nifty Options Backtesting",
        "url": "https://www.freelancer.com/projects/backtesting/Nifty-Options-Backtesting-Strategy",
        "amount": "900",
        "days": "4",
        "proposal": (
            "Hi - I can deliver a clean Python (pandas) backtest framework for your Nifty option-buying rules: "
            "entry/exit params, P/L + R:R, chart markers, and CSV/Excel trade log that reconciles to the equity curve.\n\n"
            "Plan:\n"
            "1) Ingest 1y+ historical Nifty options (handle weekly/monthly expiries)\n"
            "2) Config-driven entry/exit/risk-reward\n"
            "3) Plot trades + export trade-by-trade log + summary (win rate, avg R:R, total P/L)\n"
            "4) Install notes so you can re-run with new parameters\n\n"
            "4 days delivery. Please share a sample of your data format and rough trade logic so I can map rules before coding."
        ),
    },
    {
        "name": "BigQuery & Looker Studio",
        "url": "https://www.freelancer.com/projects/bigquery/BigQuery-Looker-Studio-Setup",
        "amount": "7500",
        "days": "5",
        "proposal": (
            "Hi - I can set up BigQuery tables for your CSVs, automate a weekly load, connect Looker Studio, "
            "and build sales + operations dashboards with filters and export.\n\n"
            "Plan:\n"
            "1) Dataset + schema for incoming CSVs\n"
            "2) Weekly refresh (Cloud Function / scheduled load)\n"
            "3) Looker Studio connection documented\n"
            "4) Two interactive dashboards: sales + ops performance\n"
            "5) Short hand-off guide for maintenance\n\n"
            "5 days. Quick question: roughly how many CSV files and do you already have a GCP project I can use?"
        ),
    },
]


def dismiss_noise(page):
    for text in ["Accept", "Accept all", "Got it", "Close", "No thanks", "Not now"]:
        try:
            loc = page.get_by_role("button", name=re.compile(text, re.I))
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=1500)
                page.wait_for_timeout(500)
        except Exception:
            pass


def logged_in(page) -> bool:
    try:
        html = page.content()
        text = page.inner_text("body")
    except Exception:
        return False
    if "@huxiong" in text or "@huxiong" in html:
        return True
    # logged-in chrome often shows avatar / My Projects / Post a Project in nav
    if re.search(r"href=\"/u/[^\"]+\"", html) and "Log In" not in text[:800]:
        # weak signal; require bid capability
        pass
    # Strong: bid form visible without email signup field for guests
    if page.locator("textarea").count() > 0 and "Place Bid" in text:
        # guest pages sometimes still show place bid with email
        if "Email address" in text and "Log In" in text and "@" not in text[:1500]:
            return False
        return "Log In" not in page.locator("header").inner_text() if page.locator("header").count() else True
    return False


def wait_for_login(page, timeout_sec: int = 300) -> bool:
    print(f"Please log in as @huxiong in the Chrome window (up to {timeout_sec}s)...")
    print("After login, open any project or stay on the site - script will continue.")
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            text = page.inner_text("body")
            html = page.content()
            if "@huxiong" in text or "@huxiong" in html:
                print("Login detected (@huxiong).")
                return True
            # also accept generic logged-in markers
            if page.locator('a[href*="/dashboard"]').count() or page.locator('a[href*="/manage"]').count():
                if "Log In" not in text[:1200]:
                    print("Login detected (dashboard link).")
                    return True
        except Exception:
            pass
        time.sleep(2)
    return False


def set_native_value(page, selector_or_el, value: str) -> bool:
    return page.evaluate(
        """([sel, val]) => {
          const el = typeof sel === 'string' ? document.querySelector(sel) : sel;
          if (!el) return false;
          const proto = el instanceof HTMLTextAreaElement
            ? window.HTMLTextAreaElement.prototype
            : window.HTMLInputElement.prototype;
          const desc = Object.getOwnPropertyDescriptor(proto, 'value');
          desc.set.call(el, val);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
          return true;
        }""",
        [selector_or_el, value],
    )


def fill_bid(page, amount: str, days: str, proposal: str) -> dict:
    dismiss_noise(page)
    page.wait_for_timeout(2000)

    # Scroll toward bid form
    for _ in range(6):
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(400)
        if page.locator("textarea").count():
            break

    body = page.inner_text("body")
    # Avoid matching "Place your bid" — require Edit/Retract or "Your bid:" panel
    already = bool(
        page.get_by_role("button", name=re.compile(r"^\s*Edit Bid\s*$", re.I)).count()
        or page.get_by_role("button", name=re.compile(r"Retract", re.I)).count()
        or re.search(r"Your bid:\s*₹|Your bid:\s*\$|Edit Bid", body)
    )
    if already and not page.locator("textarea").count():
        return {"ok": True, "reason": "already_bid"}
    if already and "Place Bid" not in body and "Place a Bid" not in body:
        return {"ok": True, "reason": "already_bid"}

    # Wait for textarea up to 20s
    try:
        page.wait_for_selector("textarea", timeout=20000)
    except Exception:
        # maybe need click "Place a Bid" to expand
        for label in ["Place a Bid", "Place Bid", "Bid on this project"]:
            try:
                loc = page.get_by_text(label, exact=False)
                if loc.count():
                    loc.first.click(timeout=2000)
                    page.wait_for_timeout(1500)
            except Exception:
                pass
        try:
            page.wait_for_selector("textarea", timeout=10000)
        except Exception:
            snippet = body[:400].replace("\n", " ")
            return {"ok": False, "reason": "no_textarea", "snippet": snippet}

    # Fill amount / days via JS heuristics
    filled = page.evaluate(
        """([amount, days]) => {
          const inputs = [...document.querySelectorAll('input')].filter(el => {
            const st = getComputedStyle(el);
            return st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null;
          });
          const meta = inputs.map((el, i) => {
            const label = (
              (el.getAttribute('aria-label') || '') + ' ' +
              (el.name || '') + ' ' +
              (el.placeholder || '') + ' ' +
              (el.id || '')
            ).toLowerCase();
            return { i, label, type: el.type, inputMode: el.inputMode };
          });
          const setVal = (el, val) => {
            const proto = window.HTMLInputElement.prototype;
            const desc = Object.getOwnPropertyDescriptor(proto, 'value');
            desc.set.call(el, val);
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
          };
          let amountOk = false, daysOk = false;
          for (const m of meta) {
            const el = inputs[m.i];
            if (/day|period|duration|delivery/.test(m.label) && !daysOk) {
              setVal(el, days); daysOk = true; continue;
            }
            if (/bid|amount|budget|price/.test(m.label) && !amountOk) {
              setVal(el, amount); amountOk = true; continue;
            }
          }
          // fallback: number-like inputs near proposal
          const nums = inputs.filter(el => el.type === 'number' || el.inputMode === 'decimal' || el.inputMode === 'numeric' || /\\d/.test(el.placeholder||''));
          if (!amountOk && nums[0]) { setVal(nums[0], amount); amountOk = true; }
          if (!daysOk && nums[1]) { setVal(nums[1], days); daysOk = true; }
          if (!daysOk && nums[0] && amountOk && nums.length === 1) {
            // only one number field - leave days
          }
          return { amountOk, daysOk, meta: meta.slice(0, 12) };
        }""",
        [amount, days],
    )

    # Proposal
    ta = page.locator("textarea").first
    ta.scroll_into_view_if_needed()
    ta.click()
    # Clear and type via fill + native setter
    page.evaluate(
        """(text) => {
          const ta = document.querySelector('textarea');
          if (!ta) return false;
          const desc = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
          desc.set.call(ta, text);
          ta.dispatchEvent(new Event('input', { bubbles: true }));
          ta.dispatchEvent(new Event('change', { bubbles: true }));
          return ta.value.length;
        }""",
        proposal,
    )
    page.wait_for_timeout(500)
    prop_len = page.evaluate("document.querySelector('textarea')?.value?.length || 0")

    # Click Place Bid
    clicked = False
    for name in [r"Place Bid", r"Place a Bid", r"Submit", r"Update Bid"]:
        try:
            btn = page.get_by_role("button", name=re.compile(name, re.I))
            if btn.count():
                btn.first.scroll_into_view_if_needed()
                btn.first.click(timeout=4000)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        clicked = page.evaluate(
            """() => {
              const buttons = [...document.querySelectorAll('button, a, [role=button]')];
              const btn = buttons.find(b => /place\\s*a?\\s*bid|submit bid/i.test(b.innerText || ''));
              if (!btn) return false;
              btn.click();
              return true;
            }"""
        )

    page.wait_for_timeout(4000)
    body2 = page.inner_text("body")
    success = bool(
        page.get_by_role("button", name=re.compile(r"Edit Bid", re.I)).count()
        or re.search(r"Your bid:\s*[₹$]|Bid placed|successfully placed", body2, re.I)
    )
    return {
        "ok": bool(success),
        "reason": "submitted" if success else ("clicked_uncertain" if clicked else "click_failed"),
        "amountOk": filled.get("amountOk"),
        "daysOk": filled.get("daysOk"),
        "prop_len": prop_len,
        "meta": filled.get("meta"),
    }


def main():
    results = []
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=r"C:\Users\h2629\AppData\Local\Temp\freelancer-bid-profile",
            channel="chrome",
            headless=False,
            viewport={"width": 1360, "height": 960},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.freelancer.com/login", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(1500)
        dismiss_noise(page)

        # If already logged in, login page may redirect
        text0 = page.inner_text("body")
        if "@huxiong" not in text0 and "@huxiong" not in page.content():
            if not wait_for_login(page, 300):
                print("LOGIN_TIMEOUT - please run again after logging in")
                print("Browser left open 60s...")
                time.sleep(60)
                context.close()
                return
        else:
            print("Already logged in as @huxiong")

        for job in BIDS:
            print(f"\n=== Bidding: {job['name']} ===")
            try:
                page.goto(job["url"], wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(3500)
                dismiss_noise(page)
                # Ensure still logged in
                if "@huxiong" not in page.content() and "Log In" in page.inner_text("body")[:2000]:
                    print("Session lost - go login")
                    page.goto("https://www.freelancer.com/login", wait_until="domcontentloaded")
                    if not wait_for_login(page, 180):
                        results.append({"name": job["name"], "ok": False, "reason": "lost_login"})
                        continue
                    page.goto(job["url"], wait_until="domcontentloaded", timeout=90000)
                    page.wait_for_timeout(3000)

                r = fill_bid(page, job["amount"], job["days"], job["proposal"])
                print({k: v for k, v in r.items() if k != "meta"})
                if r.get("meta"):
                    print("inputs:", r["meta"])
                results.append({"name": job["name"], "amount": job["amount"], "days": job["days"], **{k: v for k, v in r.items() if k != "meta"}})
            except Exception as e:
                print("ERROR", e)
                results.append({"name": job["name"], "ok": False, "reason": str(e)})

        print("\n=== SUMMARY ===")
        for r in results:
            print(r)
        print("Leaving browser open 45s for manual verify/fix...")
        time.sleep(45)
        context.close()


if __name__ == "__main__":
    main()
