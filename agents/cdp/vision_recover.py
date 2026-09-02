# -*- coding: utf-8 -*-
"""
探测失败时：截图 → 视觉模型判断 → 纠错动作（对齐 OpenClaw「看图再决策」兜底，非主路径）。

环境变量：
  CDP_VISION_RECOVER=1     默认开启
  CDP_VISION_RECOVER_MAX=3 单次 explore 最多调用视觉纠错次数
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
from typing import Any, Dict, Optional


def cdp_vision_recover_enabled() -> bool:
    return (os.getenv("CDP_VISION_RECOVER", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def cdp_vision_recover_max() -> int:
    try:
        return max(0, min(int(os.getenv("CDP_VISION_RECOVER_MAX", "3")), 8))
    except (TypeError, ValueError):
        return 3


_PROMPT = """你是浏览器自动化纠错助手。刚才对页面控件操作失败，请根据截图判断下一步。

失败操作：{action}
控件：role={role} name={name}
错误：{error}
当前 URL：{url}

只输出一行 JSON（不要 markdown）：
{{"verdict":"false_positive|real_bug|retry|close_overlay|go_back|skip","reason":"一句话中文原因","retry_hint":"role_click|js_click|none"}}

含义：
- false_positive：不是产品缺陷（控件本来就不能这样点/填，或已不可见）
- real_bug：像真缺陷（按钮点了没反应且界面异常、报错文案等）
- retry：值得换策略再试一次
- close_overlay：先关掉弹层/遮罩再继续
- go_back：应返回上一页
- skip：跳过该控件继续探测
"""


def _parse_verdict(raw: str) -> Dict[str, str]:
    text = (raw or "").strip()
    if not text:
        return {"verdict": "skip", "reason": "视觉无返回", "retry_hint": "none"}
    m = re.search(r"\{[^{}]+\}", text, re.S)
    blob = m.group(0) if m else text
    try:
        data = json.loads(blob)
        if isinstance(data, dict):
            v = str(data.get("verdict") or "skip").strip().lower()
            if v not in (
                "false_positive",
                "real_bug",
                "retry",
                "close_overlay",
                "go_back",
                "skip",
            ):
                v = "skip"
            return {
                "verdict": v,
                "reason": str(data.get("reason") or "")[:200],
                "retry_hint": str(data.get("retry_hint") or "none")[:40],
            }
    except Exception:
        pass
    low = text.lower()
    if "false" in low or "误报" in text or "不是缺陷" in text:
        return {"verdict": "false_positive", "reason": text[:160], "retry_hint": "none"}
    if "overlay" in low or "弹" in text or "遮罩" in text:
        return {"verdict": "close_overlay", "reason": text[:160], "retry_hint": "none"}
    if "retry" in low or "重试" in text:
        return {"verdict": "retry", "reason": text[:160], "retry_hint": "js_click"}
    return {"verdict": "skip", "reason": text[:160], "retry_hint": "none"}


async def vision_recover_from_page(
    page: Any,
    *,
    action: str,
    role: str = "",
    name: str = "",
    error: str = "",
    url: str = "",
) -> Dict[str, Any]:
    """
    截当前页 → 视觉模型 → 返回 verdict 结构。
    失败时返回 skip，不抛异常。
    """
    if not cdp_vision_recover_enabled():
        return {"verdict": "skip", "reason": "vision recover disabled", "retry_hint": "none"}
    try:
        png = await page.screenshot(type="png", full_page=False)
    except Exception as ex:
        return {"verdict": "skip", "reason": f"screenshot failed: {ex}", "retry_hint": "none"}
    if not png:
        return {"verdict": "skip", "reason": "empty screenshot", "retry_hint": "none"}

    b64 = base64.b64encode(png).decode("ascii")
    prompt = _PROMPT.format(
        action=action or "unknown",
        role=role or "",
        name=name or "",
        error=(error or "")[:300],
        url=(url or "")[:300],
    )
    try:
        from agents.vision_describe import _call_vision_api

        raw = await asyncio.to_thread(_call_vision_api, b64, prompt, "")
    except Exception as ex:
        print(f"[CDP] vision recover call failed: {ex}", flush=True)
        return {"verdict": "skip", "reason": f"vision error: {ex}", "retry_hint": "none"}

    out = _parse_verdict(raw)
    out["raw"] = (raw or "")[:400]
    print(
        f"[CDP] vision recover action={action} verdict={out.get('verdict')} reason={out.get('reason')}",
        flush=True,
    )
    return out


async def apply_vision_recover_action(
    *,
    page: Any,
    mgr: Any,
    session_id: str,
    owner_key: Optional[str],
    actor: Any,
    node: Dict[str, Any],
    snap_id: Optional[str],
    decision: Dict[str, Any],
) -> Dict[str, Any]:
    """
    根据视觉判决执行纠错。返回：
      handled: bool 是否已处理（不再记原缺陷或已改写）
      issue: optional 仍要记录的问题
      recovered: bool
    """
    from .overlay import close_overlay, overlay_is_visible

    verdict = str((decision or {}).get("verdict") or "skip")
    reason = str((decision or {}).get("reason") or "")
    hint = str((decision or {}).get("retry_hint") or "none")

    if verdict == "false_positive":
        return {
            "handled": True,
            "recovered": True,
            "issue": None,
            "note": f"视觉判定误报：{reason}",
        }
    if verdict == "skip":
        return {"handled": True, "recovered": False, "issue": None, "note": reason or "skip"}
    if verdict == "close_overlay":
        try:
            if await overlay_is_visible(page):
                await close_overlay(page)
            return {
                "handled": True,
                "recovered": True,
                "issue": None,
                "note": f"已关弹层：{reason}",
            }
        except Exception as ex:
            return {"handled": False, "recovered": False, "issue": None, "note": str(ex)}
    if verdict == "go_back":
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=8000)
            return {
                "handled": True,
                "recovered": True,
                "issue": None,
                "note": f"已返回：{reason}",
            }
        except Exception as ex:
            return {"handled": False, "recovered": False, "issue": None, "note": str(ex)}
    if verdict == "retry":
        ref = str(node.get("ref") or "")
        try:
            # 先刷新 snapshot 再点
            snap = await mgr.snapshot(session_id, scope="interactive", owner_key=owner_key)
            sid = snap.get("snapshot_id") if isinstance(snap, dict) else snap_id
            click2 = await actor.click(ref=ref, snapshot_id=sid)
            if click2.get("success"):
                return {
                    "handled": True,
                    "recovered": True,
                    "issue": None,
                    "note": f"视觉纠错重试成功（{hint}）：{reason}",
                    "click_res": click2,
                }
        except Exception as ex:
            reason = f"{reason}; retry failed: {ex}"
        return {"handled": False, "recovered": False, "issue": None, "note": reason}
    if verdict == "real_bug":
        return {
            "handled": False,
            "recovered": False,
            "issue": {
                "type": "vision_confirmed_bug",
                "ref": node.get("ref"),
                "role": node.get("role"),
                "name": node.get("name"),
                "message": reason or "视觉确认存在交互问题",
                "severity": "high",
            },
            "note": reason,
        }
    return {"handled": True, "recovered": False, "issue": None, "note": reason}
