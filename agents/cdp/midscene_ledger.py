# -*- coding: utf-8 -*-
"""Midscene 探测的 run_ledger 接入助手。

把工具 kwargs 里的台账参数（user/project/session 隔离 + entries/resume 续跑）
解析成 run_midscene_smoke 可接收的 keyword 参数；任何一步失败都静默降级为
「不开账」（普通一次性 smoke），绝不影响主流程。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def ledger_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        v = int(value)
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def ledger_kwargs_from_tool(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """从 cdp 工具 kwargs 提取台账参数（未配置返回空 dict）。"""
    if not isinstance(kwargs, dict):
        return {}
    uid = ledger_int(kwargs.get("user_id") or kwargs.get("userId"))
    if uid is None:
        return {}
    out: Dict[str, Any] = {
        "user_id": uid,
        "project_id": ledger_int(kwargs.get("project_id")),
        "chat_session_id": ledger_int(kwargs.get("chat_session_id")),
    }
    entries = kwargs.get("entries")
    if isinstance(entries, list) and entries:
        out["entries"] = entries
    entry = kwargs.get("entry")
    if isinstance(entry, str) and entry.strip():
        out["entry"] = entry.strip()
    prev = kwargs.get("prev_run_id")
    if isinstance(prev, str) and prev.strip():
        out["prev_run_id"] = prev.strip()

    resume = kwargs.get("resume_run_id") or kwargs.get("resume")
    resume_id = resolve_resume_run_id(
        resume,
        user_id=uid,
        project_id=out["project_id"],
        chat_session_id=out["chat_session_id"],
    )
    if resume_id:
        out["resume_run_id"] = resume_id
    return out


def resolve_resume_run_id(
    resume: Any,
    *,
    user_id: int,
    project_id: Optional[int] = None,
    chat_session_id: Optional[int] = None,
) -> Optional[str]:
    """resume 支持两种形态：具体 run_id 字符串，或 true→自动找本会话最近中断的任务。"""
    if isinstance(resume, str):
        s = resume.strip()
        if not s:
            return None
        if s.lower() in ("true", "1", "yes", "latest"):
            return _latest_interrupted_run_id(
                user_id, project_id=project_id, chat_session_id=chat_session_id
            )
        return s
    if resume in (True, 1):
        return _latest_interrupted_run_id(
            user_id, project_id=project_id, chat_session_id=chat_session_id
        )
    return None


def _latest_interrupted_run_id(
    user_id: int,
    *,
    project_id: Optional[int] = None,
    chat_session_id: Optional[int] = None,
) -> Optional[str]:
    try:
        from app_services import run_ledger

        info = run_ledger.latest_interrupted(
            user_id=user_id,
            project_id=project_id,
            chat_session_id=chat_session_id,
            tool_kind="midscene_explore",
        )
        if info and info.get("run_id"):
            return str(info["run_id"])
    except Exception as e:
        try:
            print(f"[midscene_ledger] latest_interrupted 查询失败: {e}", flush=True)
        except Exception:
            pass
    return None
