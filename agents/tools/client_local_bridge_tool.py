# -*- coding: utf-8 -*-
"""Web 端引导下载本机本地代理可执行文件（Windows exe / Unix 二进制）；对话面板展示多环境命令。"""
from __future__ import annotations

from typing import Any, Dict

from agents.tool_registry import BaseTool

from badcase_client_binaries import local_proxy_artifacts_for_api


class ClientLocalBridgeTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="client_local_bridge",
            description=(
                "**仅**用于：用户需要**首次下载/安装** go-local-proxy 可执行文件（与云端分离的本机进程）时。"
                "**禁止**用本工具执行 pwd、ls、git、构建等任意 Shell 命令——那些必须用 **terminal**。"
                "前端在桌面版或已探测到本机代理在线时**不展示**本工具的下载卡片，仅保留说明。"
                "本工具只下发下载链接与复制用的安装命令，不会自动运行程序。"
                "可选：reason（一句话说明为何需要安装代理）。"
            ),
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        reason = (kwargs.get("reason") or kwargs.get("user_reason") or "").strip()
        body_zh = (
            "此卡片**仅用于安装本地代理程序**。"
            "若你只是要执行本机命令（如查看目录），应使用工具 **terminal**，助手流结束后会通过本机连接自动执行，无需在此复制命令。"
            "下载后请在系统终端中手动运行启动命令。"
        )
        if reason:
            body_zh = f"{reason}\n\n{body_zh}"
        return {
            "success": True,
            "summary": "已展示本地代理多平台下载与运行说明",
            "message": body_zh,
            "client_local_run": {
                "title": "本地代理（可执行文件）",
                "body": body_zh,
                "artifacts": local_proxy_artifacts_for_api(),
            },
        }
