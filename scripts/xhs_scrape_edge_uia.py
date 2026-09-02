# -*- coding: utf-8 -*-
"""Scrape Xiaohongshu search results from already-open Edge window via UIA."""
from __future__ import annotations

import json
import re
from pathlib import Path

from pywinauto import Desktop

OUT = Path(__file__).resolve().parents[1] / "data" / "xhs_agent_leads_uia.json"

DEMAND_RE = re.compile(
    r"(找人|有偿|求推荐|求做|帮忙做|外包|预算|急招|代做|谁会|有没有人|求大佬|求问)"
)
SUPPLY_RE = re.compile(r"(接单中|可接单|教程|0基础|副业|培训|课程|教你|接单啦)")


def _safe(s: str) -> str:
    return (s or "").replace("\u200b", "").encode("utf-8", "ignore").decode("utf-8")


def main() -> None:
    desk = Desktop(backend="uia")
    wins = [
        w
        for w in desk.windows()
        if "小红书" in (w.window_text() or "")
        or "找人做智能体" in (w.window_text() or "")
    ]
    print(f"wins={len(wins)}")
    all_texts: list[str] = []
    for w in wins:
        title = _safe(w.window_text())
        print(f"TITLE: {title}")
        try:
            children = w.descendants()
        except Exception as e:
            print(f"descendants_fail: {type(e).__name__}: {e}")
            continue
        for c in children:
            try:
                t = _safe(c.window_text() or "").strip()
            except Exception:
                continue
            if len(t) >= 4:
                all_texts.append(t)

    seen = set()
    uniq = []
    for t in all_texts:
        if t in seen:
            continue
        seen.add(t)
        uniq.append(t)

    candidates = []
    for t in uniq:
        if DEMAND_RE.search(t) or ("智能体" in t) or ("Coze" in t) or ("Dify" in t) or ("扣子" in t):
            kind = "demand" if DEMAND_RE.search(t) and not SUPPLY_RE.search(t[:80]) else "other"
            candidates.append({"text": t[:300], "kind": kind})

    out = {
        "window_count": len(wins),
        "text_count": len(uniq),
        "candidates": candidates[:80],
        "all_sample": uniq[:120],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"WROTE {OUT}")
    print(f"candidates={len(candidates)}")
    for c in candidates[:40]:
        print(f"[{c['kind']}] {c['text']}")


if __name__ == "__main__":
    main()
