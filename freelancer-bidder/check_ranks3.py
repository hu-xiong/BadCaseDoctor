from playwright.sync_api import sync_playwright
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JOBS = [
    (40622729, "Excel Data Cleaning & ML"),
    (40608599, "Pincode Stock Tracker"),
    (40612616, "Nifty Options Backtesting"),
]
MY = 47254643


def rep_score(rep):
    if not isinstance(rep, dict):
        return 0.0, 0
    overall = 0.0
    reviews = 0
    eh = rep.get("entire_history") or {}
    if isinstance(eh, dict):
        overall = float(eh.get("overall") or 0)
        reviews = int(eh.get("reviews") or eh.get("total_reviews") or 0)
    emp = rep.get("employer") or {}
    if isinstance(emp, dict) and not overall:
        overall = float(emp.get("overall") or 0)
        reviews = int(emp.get("reviews_total") or emp.get("total") or reviews)
    if not overall and "overall" in rep:
        overall = float(rep.get("overall") or 0)
    return overall, reviews


with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=r"C:\Users\h2629\AppData\Local\Temp\freelancer-bid-profile",
        channel="chrome",
        headless=True,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.freelancer.com/manage/", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(1500)

    for pid, name in JOBS:
        u = f"https://www.freelancer.com/api/projects/0.1/bids/?projects[]={pid}&limit=100"
        data = page.evaluate("(u) => fetch(u, {credentials:'include'}).then(r => r.json())", u)
        bids = (data.get("result") or {}).get("bids") or []
        if isinstance(bids, dict):
            bids = list(bids.values())

        enriched = []
        for b in bids:
            overall, reviews = rep_score(b.get("reputation"))
            enriched.append(
                {
                    "bidder_id": b.get("bidder_id"),
                    "amount": float(b.get("amount") or 0),
                    "period": b.get("period"),
                    "time": int(b.get("submitdate") or 0),
                    "overall": overall,
                    "reviews": reviews,
                    "highlighted": bool(b.get("highlighted")),
                    "me": b.get("bidder_id") == MY,
                    "rep": b.get("reputation"),
                }
            )

        mine = next(x for x in enriched if x["me"])
        print("\n" + "=" * 60)
        print(name)
        print("my_rep_raw", json.dumps(mine["rep"], ensure_ascii=False)[:400])
        other = next((x for x in enriched if not x["me"] and x["rep"]), None)
        print("other_rep_raw", json.dumps(other["rep"] if other else None, ensure_ascii=False)[:400])

        # Freelancer listing heuristic: highlight -> reviews/reputation -> earlier time
        ordered = sorted(
            enriched,
            key=lambda x: (-int(x["highlighted"]), -x["reviews"], -x["overall"], x["time"]),
        )
        my_rank = next(i for i, x in enumerate(ordered, 1) if x["me"])
        priced = [x for x in enriched if x["amount"] > 0]
        by_price = sorted(priced, key=lambda x: x["amount"])
        price_rank = next(i for i, x in enumerate(by_price, 1) if x["me"])

        print(f"estimated_client_list_rank: {my_rank}/{len(ordered)}")
        print(f"price_rank_among_visible: {price_rank}/{len(by_price)} (my INR {mine['amount']:.0f})")
        print("top_list:", [(x["bidder_id"], x["amount"], x["reviews"], x["overall"], "ME" if x["me"] else "") for x in ordered[:8]])
        print("cheaper_than_me:", [(x["bidder_id"], x["amount"]) for x in by_price if x["amount"] < mine["amount"]][:8])

    ctx.close()
