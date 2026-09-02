from playwright.sync_api import sync_playwright
import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JOBS = [
    (40622729, "Excel Data Cleaning & ML", "https://www.freelancer.com/projects/data-analysis/Excel-Data-Cleaning-40622729/details"),
    (40608599, "Pincode Stock Tracker", "https://www.freelancer.com/projects/web-scraping/Pincode-Stock-Tracker-Needed/details"),
    (40612616, "Nifty Options Backtesting", "https://www.freelancer.com/projects/backtesting/Nifty-Options-Backtesting-Strategy/details"),
]


def summarize(bids, users):
    for b in bids:
        uid = str(b.get("bidder_id") or "")
        u = users.get(uid) or {}
        b["_user"] = (u.get("username") or "").lower()
        b["_amount"] = float(b.get("amount") or 0)
        b["_time"] = int(b.get("submitdate") or 0)
        b["_score"] = float(b.get("score") or 0)

    mine = next((b for b in bids if b["_user"] == "huxiong"), None)
    by_time = sorted(bids, key=lambda x: x["_time"])  # earlier first
    by_amt = sorted(bids, key=lambda x: x["_amount"])
    by_score = sorted(bids, key=lambda x: (-x["_score"], x["_time"]))

    def idx(lst):
        if not mine:
            return None
        for i, b in enumerate(lst, 1):
            if b.get("id") == mine.get("id"):
                return i
        return None

    return {
        "total": len(bids),
        "my_amount": mine["_amount"] if mine else None,
        "my_period": mine.get("period") if mine else None,
        "my_score": mine["_score"] if mine else None,
        "rank_earliest_bid": idx(by_time),
        "rank_lowest_price": idx(by_amt),
        "rank_by_score": idx(by_score),
        "top_score_users": [b["_user"] or "?" for b in by_score[:8]],
        "price_ladder": [round(b["_amount"], 2) for b in by_amt[:8]],
    }


with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=r"C:\Users\h2629\AppData\Local\Temp\freelancer-bid-profile",
        channel="chrome",
        headless=True,
        viewport={"width": 1400, "height": 1000},
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.freelancer.com/manage/", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)

    for pid, name, url in JOBS:
        print("\n" + "=" * 60)
        print(name, "id=", pid)
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(3000)

        au = f"https://www.freelancer.com/api/projects/0.1/bids/?projects[]={pid}&limit=100"
        data = page.evaluate(
            """(u) => fetch(u, {credentials:'include'}).then(r => r.json()).catch(e => ({error:String(e)}))""",
            au,
        )
        if not isinstance(data, dict) or data.get("status") != "success":
            print("API fail", data)
            # try alternate
            au2 = f"https://www.freelancer.com/api/projects/0.1/bids?projects[]={pid}&limit=100"
            data = page.evaluate(
                """(u) => fetch(u, {credentials:'include'}).then(r => r.json()).catch(e => ({error:String(e)}))""",
                au2,
            )
        if not isinstance(data, dict) or data.get("status") != "success":
            print("API fail2", str(data)[:300])
            continue

        result = data.get("result") or {}
        bids = result.get("bids") or []
        if isinstance(bids, dict):
            bids = list(bids.values())
        users = result.get("users") or {}
        # users keys may be str
        users = {str(k): v for k, v in users.items()}
        print("bids", len(bids), "users", len(users))
        s = summarize(bids, users)
        print(json.dumps(s, ensure_ascii=False, indent=2))

        # page ranking line if any
        t = page.inner_text("body")
        m = re.search(r"You are ranked[^\n]{0,60}", t, re.I)
        print("page:", m.group(0) if m else "(no on-page rank text)")

    ctx.close()
