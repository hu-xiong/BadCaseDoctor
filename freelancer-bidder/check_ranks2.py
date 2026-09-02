from playwright.sync_api import sync_playwright
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JOBS = [
    (40622729, "Excel Data Cleaning & ML"),
    (40608599, "Pincode Stock Tracker"),
    (40612616, "Nifty Options Backtesting"),
]


with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=r"C:\Users\h2629\AppData\Local\Temp\freelancer-bid-profile",
        channel="chrome",
        headless=True,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto("https://www.freelancer.com/manage/", wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(2000)

    # discover my user id from profile
    me = page.evaluate(
        """() => fetch('https://www.freelancer.com/api/users/0.1/self/', {credentials:'include'}).then(r=>r.json())"""
    )
    self = ((me.get("result") or {}).get("users") or {})
    if not self and isinstance(me.get("result"), dict):
        self = me["result"]
    print("self_keys", list((me.get("result") or {}).keys())[:20])
    print("self_raw", json.dumps(me, ensure_ascii=False)[:800])
    my_id = None
    users_map = (me.get("result") or {}).get("users") or {}
    if users_map:
        my_id = list(users_map.keys())[0]
        print("my_id", my_id, users_map[my_id].get("username"))
    elif (me.get("result") or {}).get("id"):
        my_id = str(me["result"]["id"])
        print("my_id", my_id)

    for pid, name in JOBS:
        print("\n" + "=" * 60)
        print(name)
        u = f"https://www.freelancer.com/api/projects/0.1/bids/?projects[]={pid}&limit=100&bidder_details=true"
        data = page.evaluate(
            """(u) => fetch(u, {credentials:'include'}).then(r=>r.json())""",
            u,
        )
        res = data.get("result") or {}
        bids = res.get("bids") or []
        if isinstance(bids, dict):
            bids = list(bids.values())
        users = {str(k): v for k, v in (res.get("users") or {}).items()}
        print("bids", len(bids), "users", len(users))
        if bids and not users:
            print("sample_bid", json.dumps(bids[0], ensure_ascii=False)[:900])

        # attach usernames
        for b in bids:
            uid = str(b.get("bidder_id") or "")
            b["_user"] = (users.get(uid) or {}).get("username") or ""
            b["_amount"] = float(b.get("amount") or 0)
            b["_time"] = int(b.get("submitdate") or 0)
            b["_score"] = float(b.get("score") or 0)

        # identify mine
        mine = None
        for b in bids:
            if my_id and str(b.get("bidder_id")) == str(my_id):
                mine = b
                break
            if b["_user"].lower() == "huxiong":
                mine = b
                break
        if mine is None:
            # fallback: amount+recent from manage knowledge
            cands = [b for b in bids if abs(b["_amount"] - (5500 if pid == 40622729 else 900)) < 0.01]
            print("cand_by_amount", [(b["_amount"], b.get("bidder_id"), b["_time"]) for b in cands])
            if len(cands) == 1:
                mine = cands[0]

        by_score = sorted(bids, key=lambda x: (-x["_score"], x["_time"]))
        by_time = sorted(bids, key=lambda x: x["_time"])
        by_amt = sorted(bids, key=lambda x: x["_amount"] if x["_amount"] > 0 else 1e18)

        def rank_of(lst):
            if not mine:
                return None
            for i, b in enumerate(lst, 1):
                if b.get("id") == mine.get("id"):
                    return i
            return None

        print(
            "MY",
            {
                "bidder_id": mine.get("bidder_id") if mine else None,
                "user": mine.get("_user") if mine else None,
                "amount": mine.get("_amount") if mine else None,
                "period": mine.get("period") if mine else None,
                "score": mine.get("_score") if mine else None,
            },
        )
        print(
            "RANKS",
            {
                "total": len(bids),
                "by_score": rank_of(by_score),
                "by_earliest": rank_of(by_time),
                "by_lowest_price": rank_of(by_amt),
            },
        )
        print("score_order", [(b["_user"] or b.get("bidder_id"), round(b["_score"], 3), b["_amount"]) for b in by_score[:10]])
        print("price_order", [(b["_user"] or b.get("bidder_id"), b["_amount"]) for b in by_amt[:10]])

    ctx.close()
