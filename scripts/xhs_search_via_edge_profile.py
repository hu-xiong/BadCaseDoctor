# -*- coding: utf-8 -*-
"""Copy Edge profile cookies into a debug profile, search XHS agent leads."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "data" / "xhs_agent_leads.json"
EDGE = os.environ.get(
    "EDGE_PATH",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)
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


def copy_profile() -> None:
    if DST_ROOT.exists():
        shutil.rmtree(DST_ROOT, ignore_errors=True)
    DST_ROOT.mkdir(parents=True, exist_ok=True)
    # Local State holds OSCrypt key
    for name in ("Local State",):
        src = SRC_ROOT / name
        if src.exists():
            shutil.copy2(src, DST_ROOT / name)
    default_src = SRC_ROOT / "Default"
    default_dst = DST_ROOT / "Default"
    default_dst.mkdir(parents=True, exist_ok=True)
    # Essential login-related files
    files = [
        "Preferences",
        "Secure Preferences",
        "Cookies",
        "Network Cookies",
        "Login Data",
        "Web Data",
    ]
    dirs = [
        "Network",
        "Local Storage",
        "Session Storage",
        "Sessions",
        "IndexedDB",
    ]
    for f in files:
        s = default_src / f
        if s.exists():
            try:
                shutil.copy2(s, default_dst / f)
                print(f"copied file {f}")
            except Exception as e:
                print(f"skip file {f}: {e}")
    for d in dirs:
        s = default_src / d
        if not s.exists():
            continue
        try:
            shutil.copytree(s, default_dst / d, dirs_exist_ok=True)
            print(f"copied dir {d}")
        except Exception as e:
            print(f"skip dir {d}: {e}")
            # Network/Cookies often locked; try file-level
            if d == "Network":
                (default_dst / "Network").mkdir(exist_ok=True)
                for nf in ("Cookies", "Cookies-journal", "Network Persistent State"):
                    ns = s / nf
                    if ns.exists():
                        try:
                            shutil.copy2(ns, default_dst / "Network" / nf)
                            print(f"copied Network/{nf}")
                        except Exception as e2:
                            print(f"lock Network/{nf}: {e2}")


def launch_edge() -> subprocess.Popen:
    cmd = [
        EDGE,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={DST_ROOT}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]
    print("launching", cmd[0])
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def extract_notes(page) -> list[dict]:
    return page.evaluate(
        """() => {
      const cards = [];
      const anchors = Array.from(document.querySelectorAll('a[href*="/search_result/"] a, a[href*="/explore/"], a[href*="/search_result/"]'));
      // Prefer note section items
      const nodes = Array.from(document.querySelectorAll('section.note-item, div.note-item, a.cover, [data-note-id], .feeds-container a, #search-result a'));
      const pool = nodes.length ? nodes : Array.from(document.querySelectorAll('a'));
      const seen = new Set();
      for (const el of pool) {
        const a = el.closest('a') || (el.tagName === 'A' ? el : null);
        if (!a) continue;
        const href = a.href || '';
        if (!href.includes('/explore/') && !href.includes('/search_result/')) continue;
        const m = href.match(/\\/explore\\/([a-zA-Z0-9]+)/);
        const noteId = m ? m[1] : '';
        const title = (a.getAttribute('title') || a.innerText || '').trim().replace(/\\s+/g,' ').slice(0,180);
        if (!title || title.length < 4) continue;
        const key = noteId || title;
        if (seen.has(key)) continue;
        seen.add(key);
        cards.push({note_id: noteId, title, url: noteId ? `https://www.xiaohongshu.com/explore/${noteId}` : href});
      }
      // fallback: any visible text blocks with demand keywords
      if (cards.length < 5) {
        const texts = Array.from(document.querySelectorAll('span, a, div, p'))
          .map(e => (e.innerText||'').trim().replace(/\\s+/g,' '))
          .filter(t => t.length >= 8 && t.length <= 120);
        const uniq = [];
        const s2 = new Set();
        for (const t of texts) {
          if (s2.has(t)) continue;
          s2.add(t);
          if (/找人|有偿|求推荐|智能体|Coze|Dify|扣子|AI客服|知识库|外包/.test(t)) {
            uniq.push({note_id:'', title:t, url: location.href});
          }
        }
        return [...cards, ...uniq.slice(0,40)];
      }
      return cards;
    }"""
    )


def main() -> None:
    print("copying edge profile essentials...")
    copy_profile()
    proc = launch_edge()
    time.sleep(3)
    all_rows: list[dict] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
            for kw in KEYWORDS:
                url = f"https://www.xiaohongshu.com/search_result?keyword={kw}&source=web_search_result_notes"
                print(f"goto {kw}")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(4500)
                    # try newest sort if button exists
                    try:
                        page.get_by_text("最新", exact=True).first.click(timeout=2000)
                        page.wait_for_timeout(2500)
                    except Exception:
                        pass
                    rows = extract_notes(page)
                    print(f"  got {len(rows)}")
                    for r in rows:
                        r["kw"] = kw
                        all_rows.append(r)
                except Exception as e:
                    print(f"  fail {type(e).__name__}: {e}")
                time.sleep(1.0)

            # login check
            cookies = context.cookies("https://www.xiaohongshu.com")
            names = {c["name"] for c in cookies}
            print("cookie_names_has_web_session", "web_session" in names, "a1" in names, "count", len(cookies))
    finally:
        try:
            proc.terminate()
        except Exception:
            pass

    # classify
    demand, other = [], []
    seen = set()
    for r in all_rows:
        key = r.get("note_id") or r.get("title")
        if key in seen:
            continue
        seen.add(key)
        title = r.get("title") or ""
        is_demand = bool(
            __import__("re").search(r"找人|有偿|求推荐|求做|帮忙做|外包|预算|急招|代做|谁会|有没有人|求大佬", title)
        ) and not bool(__import__("re").search(r"接单中|可接单|教程|0基础|副业|培训|课程|教你", title[:80]))
        r["is_demand"] = is_demand
        (demand if is_demand else other).append(r)

    out = {"demand_count": len(demand), "other_count": len(other), "demand": demand[:40], "other_sample": other[:25]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {OUT}")
    print(f"DEMAND {len(demand)} OTHER {len(other)}")
    for r in demand[:25]:
        print("---")
        print(r.get("title"))
        print(r.get("url"))


if __name__ == "__main__":
    main()
