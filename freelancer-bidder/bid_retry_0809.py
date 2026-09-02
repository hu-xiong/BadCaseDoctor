from playwright.sync_api import sync_playwright
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PDF = {
    "url": "https://www.freelancer.com/projects/pdf/Extract-PDF-Text-into-Excel",
    "pid": 40634618,
    "amount": "900",
    "days": "2",
    "proposal": (
        "Hi - I can extract plain text from your PDF batch into a clean Excel file, "
        "line-by-line and in source order.\n\n"
        "Plan:\n"
        "1) Python pipeline with pdfplumber/pypdf; OCR only if a page is scanned\n"
        "2) Keep file/page mapping columns so every row is traceable\n"
        "3) Deliver one structured xlsx plus a short field note\n"
        "4) Send a small sample sheet first for your confirmation\n\n"
        "INR 900 / 2 days. Roughly how many PDFs, and are they text-based or scanned?"
    ),
}

AMAZON = {
    "url": "https://www.freelancer.com/projects/electronics/Amazon-India-Product-Research",
    "pid": 40635432,
    "amount": "3500",
    "days": "4",
    "proposal": (
        "Hi - I can deliver a data-backed Amazon India electronics shortlist for FBA launch decisions.\n\n"
        "Plan:\n"
        "1) Compile product candidates with price, reviews, ratings, category signals\n"
        "2) Score demand vs competition with a simple transparent rubric\n"
        "3) Deliver Excel shortlist plus top picks with clear reasons\n"
        "4) Short note on assumptions and next validation steps\n\n"
        "INR 3500 / 4 days. Any subcategory focus and target price band?"
    ),
    "skills": [
        "Data Analysis",
        "Data Analytics",
        "Market Research",
        "Product Research",
        "eCommerce",
        "Amazon FBA",
    ],
}

OPTIONS = {
    "url": "https://www.freelancer.com/projects/data-analysis/Optimize-Options-Trading-Strategy",
    "pid": 40632505,
    "amount": "4500",
    "days": "5",
    "proposal": (
        "Hi - I can optimize your rules-based equity-options strategy with a clean Python "
        "backtest and analysis workflow.\n\n"
        "Plan:\n"
        "1) Reproduce your current rules on historical data\n"
        "2) Parameter sweeps for entry/exit, SL/target and filters\n"
        "3) Report win rate, avg R:R, drawdown and trade log in Excel/CSV\n"
        "4) Recommend 2-3 improved rule sets with before/after metrics\n\n"
        "INR 4500 / 5 days. Please share your current rules and sample data format."
    ),
    "skills": ["Data Analysis", "Python", "Financial Analysis", "Excel"],
}


def already_bid(page, pid, my=47254643):
    data = page.evaluate(
        "(pid)=>fetch('https://www.freelancer.com/api/projects/0.1/bids/?projects[]='+pid+'&limit=50',{credentials:'include'}).then(r=>r.json())",
        str(pid),
    )
    bids = (data.get("result") or {}).get("bids") or []
    if isinstance(bids, dict):
        bids = list(bids.values())
    return next((b for b in bids if b.get("bidder_id") == my), None)


def complete_steps(page, skills):
    body = page.inner_text("body")
    if "3 steps before bidding" not in body and "Update your skills" not in body:
        return False
    print("completing 3 steps...")
    # select skills
    for sk in skills:
        try:
            loc = page.get_by_text(sk, exact=True)
            if loc.count():
                loc.first.click(timeout=1500)
                page.wait_for_timeout(300)
                print("skill", sk)
        except Exception as e:
            print("skill fail", sk, e)
    # Next buttons through wizard
    for _ in range(5):
        clicked = False
        for name in [r"^Next$", r"^Continue$", r"^Save$", r"^Finish$", r"^Done$", r"^Submit$"]:
            btn = page.get_by_role("button", name=re.compile(name, re.I))
            if btn.count() and btn.first.is_visible():
                try:
                    btn.first.click(timeout=2000)
                    page.wait_for_timeout(1500)
                    print("wizard", name)
                    clicked = True
                    break
                except Exception:
                    pass
        if not clicked:
            break
    # profile text fields if shown
    try:
        # fill empty visible text inputs with minimal profile bits
        page.evaluate(
            """() => {
              const inputs=[...document.querySelectorAll('input[type=text],textarea')].filter(e=>e.offsetParent && !e.value);
              for (const el of inputs.slice(0,3)) {
                const lab=((el.getAttribute('aria-label')||'')+(el.placeholder||'')+(el.name||'')).toLowerCase();
                if (/tagline|title|headline/.test(lab)) el.value='Python developer for data, Excel and scraping';
                else if (/about|description|bio|summary/.test(lab)) el.value='I build Python tools for Excel automation, scraping and data cleaning with clear delivery.';
                el.dispatchEvent(new Event('input',{bubbles:true}));
              }
            }"""
        )
    except Exception:
        pass
    for name in [r"^Next$", r"^Save$", r"^Finish$", r"^Done$", r"^Continue$"]:
        btn = page.get_by_role("button", name=re.compile(name, re.I))
        if btn.count() and btn.first.is_visible():
            try:
                btn.first.click(timeout=2000)
                page.wait_for_timeout(1500)
            except Exception:
                pass
    return True


def place_bid(page, amount, days, proposal):
    for _ in range(8):
        page.mouse.wheel(0, 800)
        page.wait_for_timeout(200)
    if not page.locator("#bidAmountInput").count():
        return {"ok": False, "reason": "no_amount"}
    page.fill("#bidAmountInput", amount)
    if page.locator("#periodInput").count():
        page.fill("#periodInput", days)
    ta = page.locator("textarea").first
    ta.click()
    ta.fill(proposal)
    page.wait_for_timeout(500)
    # ensure length
    val = page.evaluate("document.querySelector('textarea')?.value?.length || 0")
    print("proposal_len", val)
    btn = page.get_by_role("button", name=re.compile(r"Place Bid", re.I))
    if not btn.count():
        return {"ok": False, "reason": "no_button", "proposal_len": val}
    btn.first.click()
    page.wait_for_timeout(5000)
    return {"ok": True, "reason": "clicked", "proposal_len": val}


def main():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=r"C:\Users\h2629\AppData\Local\Temp\freelancer-bid-profile",
            channel="chrome",
            headless=False,
            viewport={"width": 1360, "height": 1000},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://www.freelancer.com/manage/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(2000)

        # PDF
        print("\n=== PDF ===")
        if already_bid(page, PDF["pid"]):
            print("already")
        else:
            page.goto(PDF["url"], wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(3500)
            print(place_bid(page, PDF["amount"], PDF["days"], PDF["proposal"]))
            mine = already_bid(page, PDF["pid"])
            print("api", bool(mine), mine.get("amount") if mine else None)

        # Amazon with steps
        print("\n=== AMAZON ===")
        if already_bid(page, AMAZON["pid"]):
            print("already")
        else:
            page.goto(AMAZON["url"], wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(3500)
            complete_steps(page, AMAZON["skills"])
            page.goto(AMAZON["url"], wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(3500)
            if "3 steps before bidding" in page.inner_text("body"):
                complete_steps(page, AMAZON["skills"])
                page.wait_for_timeout(2000)
                page.goto(AMAZON["url"], wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(3500)
            print("gate_left", "3 steps before bidding" in page.inner_text("body"))
            if page.locator("#bidAmountInput").count():
                print(place_bid(page, AMAZON["amount"], AMAZON["days"], AMAZON["proposal"]))
            else:
                print("still no form")
            mine = already_bid(page, AMAZON["pid"])
            print("api", bool(mine), mine.get("amount") if mine else None)

        # Options
        print("\n=== OPTIONS ===")
        if already_bid(page, OPTIONS["pid"]):
            print("already")
        else:
            page.goto(OPTIONS["url"], wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(3500)
            if "3 steps before bidding" in page.inner_text("body") or "Update your skills" in page.inner_text("body"):
                complete_steps(page, OPTIONS["skills"])
                page.goto(OPTIONS["url"], wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(3500)
            print("gate_left", "3 steps before bidding" in page.inner_text("body"))
            if page.locator("#bidAmountInput").count():
                print(place_bid(page, OPTIONS["amount"], OPTIONS["days"], OPTIONS["proposal"]))
            else:
                print("still no form")
            mine = already_bid(page, OPTIONS["pid"])
            print("api", bool(mine), mine.get("amount") if mine else None)

        page.goto("https://www.freelancer.com/manage/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(3500)
        rows = page.evaluate(
            """() => [...document.querySelectorAll('tr')].slice(0,12).map(tr => tr.innerText.replace(/\\s+/g,' ').trim())"""
        )
        print("\n=== MANAGE ===")
        for r in rows:
            print(r[:240])
        time.sleep(6)
        ctx.close()


if __name__ == "__main__":
    main()
