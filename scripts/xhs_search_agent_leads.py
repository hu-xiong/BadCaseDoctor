# -*- coding: utf-8 -*-
"""Search Xiaohongshu for people seeking AI agent development."""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import browser_cookie3 as bc
from xhs import SearchSortType, XhsClient

OUT = Path(__file__).resolve().parents[1] / "data" / "xhs_agent_leads.json"

KEYWORDS = [
    "找人做智能体",
    "有偿 智能体",
    "找人做Coze",
    "找人做Dify",
    "找人做AI客服",
    "求推荐 智能体开发",
    "有偿 AI Agent",
    "找人做知识库",
]

DEMAND_RE = re.compile(
    r"(找人|有偿|求推荐|求做|帮忙做|外包|预算|急招|代做|谁会|有没有人|接吗|多少钱|求大佬)"
)
SUPPLY_RE = re.compile(r"(接单中|可接单|教程|0基础|副业|培训|课程|模板售卖|教你|接单啦)")


def load_cookie_str() -> str:
    jars = []
    for loader, name in [(bc.edge, "edge"), (bc.chrome, "chrome")]:
        try:
            jar = loader(domain_name="xiaohongshu.com")
            cookies = list(jar)
            print(f"{name}: {len(cookies)} cookies")
            jars.append((name, cookies))
        except Exception as e:
            print(f"{name} fail: {type(e).__name__}: {e}")
    if not jars:
        raise SystemExit("未从 Edge/Chrome 读到小红书 cookie，请确认已在浏览器登录")

    def score(cookies):
        names = {c.name for c in cookies}
        return sum(1 for n in ("web_session", "a1", "webId", "customer-sso-sid") if n in names)

    best_name, best = max(jars, key=lambda x: score(x[1]))
    cookie_str = "; ".join(
        f"{c.name}={c.value}" for c in best if "xiaohongshu.com" in (c.domain or "")
    )
    print(f"using {best_name} score={score(best)} cookie_len={len(cookie_str)}")
    if score(best) < 1:
        raise SystemExit("cookie 似乎没有登录态（缺 web_session/a1）")
    return cookie_str


def extract_item(it: dict, kw: str) -> dict:
    nc = it.get("note_card") or it
    title = (nc.get("display_title") or nc.get("title") or "").strip()
    desc = (nc.get("desc") or "").strip()
    user = ((nc.get("user") or {}).get("nickname") or "").strip()
    note_id = nc.get("note_id") or it.get("id") or ""
    interact = nc.get("interact_info") or {}
    text = f"{title}\n{desc}"
    is_demand = bool(DEMAND_RE.search(text)) and not bool(SUPPLY_RE.search(text[:100]))
    return {
        "kw": kw,
        "title": title,
        "desc": desc[:220],
        "user": user,
        "note_id": note_id,
        "liked": interact.get("liked_count"),
        "comments": interact.get("comment_count"),
        "is_demand": is_demand,
        "url": f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
    }


def search(client: XhsClient, kw: str) -> list:
    for sort in (SearchSortType.TIME_DESCENDING, SearchSortType.GENERAL):
        try:
            data = client.get_note_by_keyword(
                kw, page=1, page_size=20, sort=sort
            )
            items = (data or {}).get("items") or []
            print(f"KW {kw} sort={sort.name} items={len(items)}")
            return [extract_item(it, kw) for it in items]
        except Exception as e:
            print(f"SEARCH_FAIL {kw} {sort.name}: {type(e).__name__}: {str(e)[:200]}")
    return []


def main() -> None:
    cookie_str = load_cookie_str()
    client = XhsClient(cookie=cookie_str)

    results: list[dict] = []
    for kw in KEYWORDS:
        results.extend(search(client, kw))
        time.sleep(0.8)

    seen = set()
    uniq = []
    for r in results:
        nid = r.get("note_id") or ""
        if not nid or nid in seen:
            continue
        seen.add(nid)
        uniq.append(r)

    demand = [r for r in uniq if r["is_demand"]]
    other = [r for r in uniq if not r["is_demand"]]
    out = {
        "demand_count": len(demand),
        "other_count": len(other),
        "demand": demand[:40],
        "other_sample": other[:20],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {OUT}")
    print(f"DEMAND {len(demand)} OTHER {len(other)}")
    for r in demand[:25]:
        print("---")
        print(f"{r['user']} | {r['title']}")
        print(r["desc"])
        print(r["url"])


if __name__ == "__main__":
    main()
