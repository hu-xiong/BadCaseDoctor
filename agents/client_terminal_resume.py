# -*- coding: utf-8 -*-
"""
终端子 Agent 续跑：结构化结果 → 主 Agent 提示词。

架构：主图 terminal_pause → 前端子 Agent 执行 → 带 client_terminal_results 再 POST /react。
不在服务端阻塞等待 PTY；用结构化载荷替代纯自然语言拼接。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def normalize_terminal_results(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cmd = str(item.get("command") or "").strip()
        if not cmd:
            continue
        try:
            exit_code = int(item.get("exit_code", item.get("exitCode", -1)))
        except (TypeError, ValueError):
            exit_code = -1
        out.append(
            {
                "command": cmd[:4000],
                "cwd": str(item.get("cwd") or "")[:2000],
                "exit_code": exit_code,
                "ok": bool(item.get("ok", exit_code == 0)),
                "cancelled": bool(item.get("cancelled")),
                "proxy_down": bool(item.get("proxy_down") or item.get("proxyDown")),
                "stdout": str(item.get("stdout") or "")[:12000],
                "stderr": str(item.get("stderr") or "")[:8000],
                "error": str(item.get("error") or "")[:2000],
            }
        )
    return out


def format_terminal_results_prompt(
    results: List[Dict[str, Any]],
    *,
    locale: Optional[str] = None,
) -> str:
    """把子 Agent 执行结果格式化为续跑 user 段。"""
    rows = normalize_terminal_results(results)
    if not rows:
        return ""
    en = (locale or "").lower().startswith("en")
    header = (
        "[Client terminal sub-agent results — continue the task; do not re-run succeeded commands]"
        if en
        else "【本机终端子 Agent 执行结果】请基于下列结果继续任务；已成功的命令勿重复执行。"
    )
    blocks = [header, ""]
    for i, r in enumerate(rows, 1):
        blocks.append(f"--- #{i} ---")
        blocks.append(f"command: {r['command']}")
        if r.get("cwd"):
            blocks.append(f"cwd: {r['cwd']}")
        if r.get("proxy_down"):
            blocks.append("status: proxy_down")
        elif r.get("cancelled"):
            blocks.append("status: cancelled")
        elif r.get("error"):
            blocks.append(f"status: error — {r['error']}")
        else:
            blocks.append(f"exit_code: {r['exit_code']} ok={r['ok']}")
        if r.get("stdout"):
            blocks.append("--- stdout ---")
            blocks.append(r["stdout"])
        if r.get("stderr"):
            blocks.append("--- stderr ---")
            blocks.append(r["stderr"])
        blocks.append("")
    return "\n".join(blocks).strip()


def merge_client_shell_cwd(params: Dict[str, Any], client_shell: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """terminal 工具未带 cwd 时，用前端 client_shell.cwd 补全。"""
    out = dict(params or {})
    if str(out.get("cwd") or "").strip():
        return out
    if not isinstance(client_shell, dict):
        return out
    cwd = str(client_shell.get("cwd") or client_shell.get("workingDirectory") or "").strip()
    if cwd:
        out["cwd"] = cwd
    return out
