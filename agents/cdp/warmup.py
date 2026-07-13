# -*- coding: utf-8 -*-
"""CDP Chromium 后台预热，避免首条 session create 冷启动。"""
from __future__ import annotations

import asyncio
import time


async def warmup_cdp_browser() -> None:
    from .settings import cdp_browser_warmup_enabled, cdp_enabled

    if not cdp_enabled() or not cdp_browser_warmup_enabled():
        return
    from .session_manager import CdpSessionManager

    mgr = CdpSessionManager.get()
    t0 = time.perf_counter()
    await mgr.ensure_browser_warm()
    print(
        f"[CDP-WARMUP] Chromium 预热完成 {(time.perf_counter() - t0) * 1000:.0f}ms",
        flush=True,
    )


def warmup_cdp_browser_sync() -> None:
    try:
        asyncio.run(warmup_cdp_browser())
    except Exception as ex:
        print(f"[CDP-WARMUP] 预热失败(忽略): {ex}", flush=True)
