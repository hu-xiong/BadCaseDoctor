# -*- coding: utf-8 -*-
"""
OpenClaw 风格：截图 → 视觉理解 → 文本回传 Agent（工具结果里的 vision_description）。

环境变量：
  CDP_SCREENSHOT_VISION=1   默认开启（screenshot / 操作失败时）
"""

from __future__ import annotations

import asyncio
import base64
import os
from typing import Any, Dict, Optional

_AGENT_VISION_PROMPT = """你是浏览器自动化 Agent 的视觉助手（对齐 OpenClaw screenshot vision）。
请根据截图用中文简要说明（总计不超过 220 字）：
1. 页面类型与关键可见文案/错误提示
2. 是否有弹窗、遮罩、登录页、空状态
3. 建议 Agent 下一步：重新 snapshot 换 ref / 关弹层 / login / navigate / 换控件 / 停止并汇报

上下文：{context}
"""


def cdp_screenshot_vision_enabled() -> bool:
    return (os.getenv("CDP_SCREENSHOT_VISION", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def agent_loop_hint(
    *,
    stale: bool = False,
    has_vision: bool = False,
    kind: str = "failure",
) -> str:
    """
    kind:
      failure — click/fill 失败
      screenshot — 主动截图成功
      stale — ref 失效
    """
    if stale or kind == "stale":
        return (
            "ref 可能已失效：请用 observation 中的 new_snapshot_id / focus_hints 重选 @eN，"
            "先 snapshot 再 click/fill；不要沿用旧 ref。"
            + (" 同时参考 vision_description。" if has_vision else "")
        )
    if kind == "screenshot":
        if has_vision:
            return (
                "已根据截图生成 vision_description：请据此决定下一步 "
                "（snapshot/click/fill/login/关弹层），勿忽略视觉结论。"
            )
        return "截图已保存；请结合 snapshot 树继续操作。"
    if has_vision:
        return (
            "操作未成功：请阅读 vision_description，再决定 "
            "snapshot / screenshot / 关弹层 / login / 换 ref 重试；勿空口结束。"
        )
    return (
        "操作未成功：先 cdp snapshot 或 screenshot（含视觉描述），"
        "再决定下一步；UI 变化后必须重新 snapshot。"
    )


async def describe_png_for_agent(
    png: bytes,
    *,
    context: str = "",
) -> str:
    """同步视觉 API 放线程池，失败返回空串。"""
    if not png or not cdp_screenshot_vision_enabled():
        return ""
    b64 = base64.b64encode(png).decode("ascii")
    prompt = _AGENT_VISION_PROMPT.format(context=(context or "浏览器页面")[:400])
    try:
        from agents.vision_describe import _call_vision_api

        raw = await asyncio.to_thread(_call_vision_api, b64, prompt, "")
        return (raw or "").strip()[:1200]
    except Exception as ex:
        print(f"[CDP] screenshot vision failed: {ex}", flush=True)
        return ""


async def describe_page_for_agent(
    page: Any,
    *,
    context: str = "",
    full_page: bool = False,
) -> Dict[str, Any]:
    """截当前页并描述。返回 png / vision_description（可能为空）。"""
    out: Dict[str, Any] = {"png": b"", "vision_description": ""}
    try:
        png = await page.screenshot(type="png", full_page=bool(full_page))
    except Exception as ex:
        out["error"] = str(ex)
        return out
    out["png"] = png or b""
    if out["png"]:
        out["vision_description"] = await describe_png_for_agent(
            out["png"], context=context
        )
    return out


async def attach_vision_fields(
    observation: Dict[str, Any],
    page: Any,
    *,
    context: str = "",
    stale: bool = False,
    upload: bool = True,
    session_id: str = "",
    tag: str = "vision",
) -> Dict[str, Any]:
    """
    给工具 observation 挂 screenshot_url / vision_description / agent_hint。
    不抛异常。
    """
    if not isinstance(observation, dict):
        return observation
    try:
        described = await describe_page_for_agent(page, context=context, full_page=False)
        png = described.get("png") or b""
        desc = str(described.get("vision_description") or "").strip()
        if upload and png:
            try:
                from .screenshot import upload_png_bytes
                import time

                sid = (session_id or "sess")[:16]
                url = upload_png_bytes(
                    png,
                    folder="cdp",
                    filename=f"cdp_{sid}_{tag}_{int(time.time())}.png",
                )
                if url and not observation.get("screenshot_url"):
                    observation["screenshot_url"] = url
            except Exception:
                pass
        if desc:
            observation["vision_description"] = desc
        observation["agent_hint"] = agent_loop_hint(
            stale=stale, has_vision=bool(desc)
        )
        observation["screenshot_vision"] = bool(desc)
    except Exception as ex:
        print(f"[CDP] attach_vision_fields skipped: {ex}", flush=True)
        if "agent_hint" not in observation:
            observation["agent_hint"] = agent_loop_hint(stale=stale, has_vision=False)
    return observation
