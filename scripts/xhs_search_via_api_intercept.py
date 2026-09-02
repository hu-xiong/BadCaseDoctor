# -*- coding: utf-8 -*-
"""Search XHS leads by intercepting search API via Edge debug profile."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "data" / "xhs_agent_leads.json"
SHOT_DIR = Path(__file__).resolve().parents[1] / "data" / "xhs_shots"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not Path(EDGE).exists():
    EDGE = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

SRC_ROOT = Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Edge" / "User Data"
DST_ROOT = Path(os.environ["TEMP"]) / "xhs-edge-debug-profile"
PORT = 9333

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

DEMAND_RE = re.compile(r"(找人|有偿|求推荐|求做|帮忙做|外包|预算|急招|代做|谁会|有没有人|求大佬)")
SUPPLY_RE = re.compile(r"(接单中|可接单|教程|0基础|副业|培训|课程|教你|接单啦)")


def ensure_profile() -> None:
    DST_ROOT.mkdir(parents=True, exist_ok=True)
    for name in ("Local State",):
        src = SRC_ROOT / name
        if src.exists():
            shutil.copy2(src, DST_ROOT / name)
    default_src = SRC_ROOT / "Default"
    default_dst = DST_ROOT / "Default"
    default_dst.mkdir(parents=True, exist_ok=True)
    for f in ("Preferences", "Secure Preferences", "Login Data", "Web Data"):
        s = default_src / f
        if s.exists():
            try:
                shutil.copy2(s, default_dst / f)
            except Exception as e:
                print("skip", f, e)
    for d in ("Local Storage", "Session Storage", "IndexedDB"):
        s = default_src / d
        if s.exists():
            try:
                shutil.copytree(s, default_dst / d, dirs_exist_ok=True)
            except Exception as e:
                print("skip dir", d, e)
    # Try unlock copy cookies via powershell Copy-Item
    net_dst = default_dst / "Network"
    net_dst.mkdir(exist_ok=True)
    for nf in ("Cookies", "Cookies-journal"):
        src = default_src / "Network" / nf
        dst = net_dst / nf
        if not src.exists():
            continue
        try:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Copy-Item -LiteralPath '{src}' -Destination '{dst}' -Force",
                ],
                check=False,
                capture_output=True,
            )
            print("cookie copy", nf, "ok" if dst.exists() else "missing")
        except Exception as e:
            print("cookie copy fail", nf, e)


def launch_edge() -> subprocess.Popen:
    # kill previous debug edge on port if any
    return subprocess.Popen(
        [
            EDGE,
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={DST_ROOT}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-popup-blocking",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def parse_items(payload: dict, kw: str) -> list[dict]:
    rows = []
    for it in (payload or {}).get("data", {}).get("items") or (payload or {}).get("items") or []:
        nc = it.get("note_card") or it
        title = (nc.get("display_title") or nc.get("title") or "").strip()
        desc = (nc.get("desc") or "").strip()
        user = ((nc.get("user") or {}).get("nickname") or "").strip()
        note_id = nc.get("note_id") or it.get("id") or ""
        interact = nc.get("interact_info") or {}
        text = f"{title}\n{desc}"
        is_demand = bool(DEMAND_RE.search(text)) and not bool(SUPPLY_RE.search(text[:100]))
        rows.append(
            {
                "kw": kw,
                "title": title,
                "desc": desc[:240],
                "user": user,
                "note_id": note_id,
                "liked": interact.get("liked_count"),
                "comments": interact.get("comment_count"),
                "is_demand": is_demand,
                "url": f"https://www.xiaohongshu.com/explore/{note_id}" if note_id else "",
            }
        )
    return rows


def main() -> None:
    ensure_profile()
    proc = launch_edge()
    time.sleep(3)
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()

            captured: list[tuple[str, dict]] = []

            def on_response(resp):
                try:
                    u = resp.url
                    if "search/notes" not in u and "search/notes" not in u:
                        if "/search/" not in u and "search/notes" not in u:
                            return
                    if "search" not in u:
                        return
                    if resp.status != 200:
                        return
                    ct = (resp.headers or {}).get("content-type", "")
                    if "json" not in ct and "javascript" not in ct and "text" not in ct:
                        # still try
                        pass
                    data = resp.json()
                    captured.append((u, data))
                except Exception:
                    return

            page.on("response", on_response)

            for i, kw in enumerate(KEYWORDS):
                captured.clear()
                url = (
                    "https://www.xiaohongshu.com/search_result?keyword="
                    + quote(kw)
                    + "&source=web_search_result_notes"
                )
                print("goto", kw)
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(6000)
                try:
                    page.get_by_text("最新", exact=True).first.click(timeout=2500)
                    page.wait_for_timeout(3500)
                except Exception:
                    pass
                # scroll to trigger more
                for _ in range(3):
                    page.mouse.wheel(0, 2400)
                    page.wait_for_timeout(1200)

                shot = SHOT_DIR / f"{i}_{kw.replace(' ', '_')}.png"
                try:
                    page.screenshot(path=str(shot), full_page=False)
                    print("shot", shot.name)
                except Exception as e:
                    print("shot fail", e)

                print("captured_resps", len(captured))
                for u, data in captured:
                    if isinstance(data, dict):
                        rows = parse_items(data, kw)
                        if rows:
                            print("  api rows", len(rows), "from", u[:80])
                            all_rows.extend(rows)
                if not any(True for _ in captured):
                    # debug title/body snippet
                    title = page.title()
                    body = page.inner_text("body")[:500].replace("\n", " ")
                    print("  title=", title)
                    print("  body=", body[:300])

            cookies = context.cookies("https://www.xiaohongshu.com")
            names = {c["name"] for c in cookies}
            print("cookies", len(cookies), "web_session" in names, "a1" in names)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    seen = set()
    uniq = []
    for r in all_rows:
        k = r.get("note_id") or r.get("title")
        if not k or k in seen:
            continue
        seen.add(k)
        uniq.append(r)
    demand = [r for r in uniq if r["is_demand"]]
    other = [r for r in uniq if not r["is_demand"]]
    out = {
        "demand_count": len(demand),
        "other_count": len(other),
        "demand": demand[:50],
        "other_sample": other[:30],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT)
    print("DEMAND", len(demand), "OTHER", len(other))
    for r in demand[:30]:
        print("---")
        print(r.get("user"), "|", r.get("title"))
        print(r.get("desc"))
        print(r.get("url"))


if __name__ == "__main__":
    main()
