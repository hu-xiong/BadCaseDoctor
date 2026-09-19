# -*- coding: utf-8 -*-
"""弹窗 / 模态层：探测后继续在 overlay 内测试并关闭；隐私政策类弹窗点「同意」。"""

from __future__ import annotations

import asyncio
from typing import Any, List, Optional

# 隐私政策 / 用户协议 / Cookie 类弹窗的「同意」按钮文案（只点同意，不点「暂不使用」）
_CONSENT_BUTTON_TEXTS = (
    "同意并继续",
    "同意并接受",
    "我同意",
    "同意",
    "接受并继续",
    "接受全部",
    "全部接受",
    "允许全部",
    "接受",
    "Agree",
    "Accept All",
    "Accept",
    "I Agree",
)

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


async def dismiss_consent_dialogs(page: Any, *, rounds: int = 2, wait_between_ms: int = 600) -> List[str]:
    """检测并点击「隐私政策/协议/Cookie」类弹窗的同意按钮（如淘股吧「同意」）。

    - 每轮最多点掉一个弹窗，支持层叠弹窗；
    - 只匹配精确文案，避免误点页面上的普通按钮；
    - 点击后按钮仍未消失（点击未生效）时不再重复点击同一按钮；
    - 返回点击过的按钮文案（供日志与报告说明），任何异常均吞掉。
    """
    dismissed: List[str] = []
    ineffective: set = set()
    for rnd in range(max(1, rounds)):
        clicked = False
        for text in _CONSENT_BUTTON_TEXTS:
            for role in ("button", "link"):
                try:
                    loc = page.get_by_role(role, name=text, exact=True)
                    count = await loc.count()
                except Exception:
                    continue
                for i in range(min(count, 2)):
                    if (role, text, i) in ineffective:
                        continue
                    btn = loc.nth(i)
                    try:
                        if not await btn.is_visible(timeout=300):
                            continue
                        await btn.click(timeout=2000)
                        await asyncio.sleep(0.35)
                        dismissed.append(text)
                        clicked = True
                        try:
                            await btn.wait_for(state="hidden", timeout=1500)
                        except Exception:
                            # 点击后按钮仍可见：视为无效点击，避免下一轮重复点
                            ineffective.add((role, text, i))
                        break
                    except Exception:
                        continue
                if clicked:
                    break
            if clicked:
                break
        if not clicked and rnd + 1 < rounds:
            await asyncio.sleep(wait_between_ms / 1000)
    return dismissed


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
