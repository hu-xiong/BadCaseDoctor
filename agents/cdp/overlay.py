# -*- coding: utf-8 -*-
"""弹窗 / 模态层：探测后继续在 overlay 内测试并关闭。"""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional

_OVERLAY_SELECTORS = (
    ".modal-overlay:visible",
    '[role="dialog"]:visible',
    '[aria-modal="true"]:visible',
    ".plan-modal-content:visible",
)

_CLOSE_SELECTORS = (
    ".plan-modal-close:visible",
    ".close-btn:visible",
    ".modal-header .close-btn:visible",
    'button:has-text("取消"):visible',
    'button:has-text("Cancel"):visible',
    '[aria-label="Close"]:visible',
    '[aria-label="关闭"]:visible',
)


async def overlay_is_visible(page: Any) -> bool:
    try:
        for sel in _OVERLAY_SELECTORS:
            if await page.locator(sel).count() > 0:
                return True
    except Exception:
        pass
    return False


async def close_overlay(page: Any, *, timeout_ms: int = 2500) -> bool:
    """关闭当前弹窗：关闭按钮 → 取消 → Esc。"""
    for sel in _CLOSE_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=400):
                await loc.click(timeout=timeout_ms)
                await asyncio.sleep(0.25)
                if not await overlay_is_visible(page):
                    return True
        except Exception:
            continue
    try:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.25)
        return not await overlay_is_visible(page)
    except Exception:
        return False


def overlay_close_button_nodes(nodes: List[dict]) -> List[dict]:
    """优先在弹窗内点击「取消/关闭」类按钮，避免误提交。"""
    keywords = ("取消", "关闭", "cancel", "close", "✕", "×")
    out: List[dict] = []
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        name = str(n.get("name") or "").strip().lower()
        role = str(n.get("role") or "").lower()
        if role not in ("button", "link"):
            continue
        if any(k in name for k in keywords):
            out.append(n)
    return out
