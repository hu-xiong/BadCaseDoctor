# -*- coding: utf-8 -*-
"""
经客户本机 go-local-proxy 启动 Chrome（不在云端起浏览器）。
前端收到 client_action kind=browser_local 后调用本机代理 /browser/start|stop|status。
"""
from __future__ import annotations

from typing import Any, Dict

from agents.tool_registry import BaseTool


class ClientBrowserTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="client_browser",
            description=(
                "在用户本机通过 go-local-proxy 启动/停止 Chrome（有头 + CDP），用于操作内网页面。"
                "云端不直接开浏览器；需用户已安装并运行本地代理。"
                "action=start|stop|status；start 可选 url、headless（默认 false 有头）。"
                "启动后本机 CDP：go-local-proxy 返回的 cdp_http，或 http://127.0.0.1:8794/browser/cdp 。"
            ),
        )

    async def execute(self, action: str = "start", **kwargs: Any) -> Dict[str, Any]:
        act = (action or kwargs.get("sub_action") or "start").strip().lower()
        if act in ("start", "open", "launch"):
            url = str(kwargs.get("url") or "").strip()
            headless = bool(kwargs.get("headless"))
            summ = "请在本机经 go-local-proxy 启动 Chrome（有头调试）"
            return {
                "success": True,
                "browser_pause_for_client": True,
                "summary": summ,
                "message": summ,
                "client_browser": {
                    "action": "start",
                    "url": url,
                    "headless": headless,
                },
            }
        if act in ("stop", "close"):
            return {
                "success": True,
                "browser_pause_for_client": True,
                "summary": "请停止本机 Chrome",
                "message": "请停止本机 Chrome",
                "client_browser": {"action": "stop"},
            }
        if act in ("status",):
            return {
                "success": True,
                "browser_pause_for_client": True,
                "summary": "查询本机 Chrome/CDP 状态",
                "message": "查询本机 Chrome/CDP 状态",
                "client_browser": {"action": "status"},
            }
        return {"success": False, "error": f"未知 action: {act}"}
