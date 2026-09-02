# -*- coding: utf-8 -*-
"""在用户本机执行 Shell：由前端通过 go-local-proxy（Web）或 Electron IPC 实际跑命令，服务端仅下发参数。"""
from __future__ import annotations

from typing import Any, Dict

from agents.tool_registry import BaseTool


class TerminalTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="terminal",
            description=(
                "在用户本机执行一条 Shell 命令并返回 stdout/stderr/退出码。"
                "整行仅为 cd（无 &&|;）时由前端/本机代理只更新会话工作目录，不启子进程。"
                "适用于需要本地构建、git、文件系统操作等 Flask 服务器无法完成的步骤。"
                "参数：command（必填）、cwd（可选工作目录）、timeout（可选秒数，默认 60）、"
                "stop_on_error（可选布尔，默认 false；为 true 时若本消息内后续还有终端队列项，前序失败则跳过后续）。"
                "Web 端需用户已启动本地代理；桌面端走 Electron。"
            ),
        )

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        command = str(kwargs.get("command") or "").strip()
        if not command:
            return {
                "success": False,
                "error": "缺少 command",
                "message": "缺少 command",
            }
        cwd = str(kwargs.get("cwd") or "").strip()
        if not cwd:
            cs = kwargs.get("client_shell")
            if isinstance(cs, dict):
                cwd = str(cs.get("cwd") or cs.get("workingDirectory") or "").strip()
        try:
            timeout = int(kwargs.get("timeout") or 60)
        except (TypeError, ValueError):
            timeout = 60
        if timeout < 1:
            timeout = 1
        if timeout > 86400:
            timeout = 86400
        stop_on_error = kwargs.get("stop_on_error")
        if stop_on_error is None:
            stop_on_error = kwargs.get("stopOnError")
        stop_on_error_b = bool(stop_on_error) if stop_on_error is not None else False
        summ = f"本机执行：{command[:200]}"
        out: Dict[str, Any] = {
            "success": True,
            "terminal_pause_for_client": True,
            "summary": summ,
            "message": summ,
            "command": command,
            "cwd": cwd,
            "timeout": timeout,
        }
        if stop_on_error_b:
            out["stop_on_error"] = True
        return out
