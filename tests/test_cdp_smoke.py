# -*- coding: utf-8 -*-
"""CDP 冒烟：需 playwright + chromium。"""
import asyncio
import os
import tempfile


async def _run():
    os.environ["CDP_ENABLED"] = "1"
    html = """<!DOCTYPE html><html><body>
    <input id="u" aria-label="用户名" />
    <input id="p" type="password" aria-label="密码" />
    <button id="btn">登录</button>
    </body></html>"""
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        path = f.name
    url = "file:///" + path.replace("\\", "/")

    from agents.cdp.session_manager import CdpSessionManager

    mgr = CdpSessionManager.get()
    created = await mgr.create(url=url, headless=True)
    assert created["success"], created
    sid = created["session_id"]
    snap = await mgr.snapshot(sid)
    assert snap["success"], snap
    assert len(snap.get("nodes") or []) >= 1
    ref = snap["nodes"][0]["ref"]
    r = await mgr.actor(sid).fill(text="hello", ref=ref, snapshot_id=snap["snapshot_id"])
    assert r.get("success"), r
    await mgr.close(sid)
    os.unlink(path)
    print("cdp_smoke_ok")


if __name__ == "__main__":
    asyncio.run(_run())
