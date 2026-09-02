# -*- coding: utf-8 -*-
"""OpenClaw 风格 cdp 动作迁移冒烟（不启动真实浏览器）。"""
from __future__ import annotations

import asyncio
from agents.tools.cdp_tool import CdpTool
from agents.cdp.element_actor import ElementActor


async def _main():
    tool = CdpTool()
    # 缺 session 时应有清晰错误
    for act in (
        "hover",
        "press",
        "type",
        "scroll",
        "drag",
        "select",
        "click_coords",
        "screenshot",
        "pdf",
        "evaluate",
        "extract",
        "resize",
        "console",
        "tabs",
        "batch",
    ):
        out = await tool.execute(action=act)
        assert isinstance(out, dict), act
        assert out.get("success") is False, (act, out)
        assert "error" in out or out.get("message"), (act, out)
        print("ok_dispatch", act, out.get("error") or out.get("message"))

    # ElementActor 新方法存在
    for name in (
        "hover",
        "scroll_into_view",
        "press",
        "type_text",
        "select_option",
        "drag",
        "click_coords",
        "evaluate_js",
        "resize_viewport",
    ):
        assert hasattr(ElementActor, name), name
    print("SMOKE_OK openclaw-aligned cdp actions")


if __name__ == "__main__":
    asyncio.run(_main())
