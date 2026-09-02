# -*- coding: utf-8 -*-
"""LangGraph 失败边分类与路由单测。"""
from __future__ import annotations

from agents.langgraph_failure import (
    FailureAction,
    classify_tool_failure,
    failure_edge_sse,
    failure_max_retries,
)


def test_failure_max_retries_clamped(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_FAILURE_MAX_RETRIES", "99")
    assert failure_max_retries() == 6
    monkeypatch.setenv("LANGGRAPH_FAILURE_MAX_RETRIES", "1")
    assert failure_max_retries() == 1


def test_preview_stops_for_confirm():
    d = classify_tool_failure(
        tool_name="modify",
        observation={"success": True, "preview_only": True, "confirmation_required": True},
        failure_retries=0,
    )
    assert d.action == FailureAction.STOP
    assert d.kind == "preview_await_confirm"


def test_await_login_stops():
    d = classify_tool_failure(
        tool_name="cdp",
        observation={"success": True, "await_verification_code": True},
        failure_retries=0,
    )
    assert d.action == FailureAction.STOP
    assert d.kind == "await_login"


def test_success_continues():
    d = classify_tool_failure(
        tool_name="modify",
        observation={"success": True, "modifications": {"priority": "p1"}},
        failure_retries=0,
    )
    assert d.action == FailureAction.CONTINUE
    assert d.kind == "ok"


def test_policy_block_retry_then_interrupt(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_FAILURE_MAX_RETRIES", "2")
    obs = {
        "success": False,
        "blocked": True,
        "reason": "grep_required_before_modify",
        "message": "须先 grep",
    }
    d0 = classify_tool_failure(tool_name="modify", observation=obs, failure_retries=0)
    assert d0.action == FailureAction.RETRY
    assert "grep" in (d0.hint or "").lower() or "检索" in (d0.hint or "")

    d_ex = classify_tool_failure(tool_name="modify", observation=obs, failure_retries=2)
    assert d_ex.action == FailureAction.INTERRUPT
    assert d_ex.kind == "policy_block_exhausted"


def test_tool_error_replan_then_interrupt(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_FAILURE_MAX_RETRIES", "1")
    obs = {"success": False, "error": "db timeout"}
    d0 = classify_tool_failure(tool_name="create", observation=obs, failure_retries=0)
    assert d0.action == FailureAction.REPLAN
    assert d0.kind == "tool_error"

    d1 = classify_tool_failure(tool_name="create", observation=obs, failure_retries=1)
    assert d1.action == FailureAction.INTERRUPT
    assert d1.kind == "tool_error_exhausted"


def test_missing_id_retry():
    obs = {"success": False, "error": "缺少必要参数 target_id"}
    d = classify_tool_failure(tool_name="modify", observation=obs, failure_retries=0)
    assert d.action == FailureAction.RETRY
    assert d.kind == "missing_id"


def test_failure_edge_sse_shape():
    d = classify_tool_failure(
        tool_name="modify",
        observation={"success": False, "error": "boom"},
        failure_retries=0,
    )
    pkt = failure_edge_sse(d)
    assert pkt["event"] == "failure_edge"
    assert pkt["action"] in ("retry", "replan", "interrupt", "continue", "stop")
    assert "kind" in pkt


def test_route_after_tools_logic():
    """与 langgraph_engine._route_after_tools 对齐的纯函数语义。"""
    from agents.langgraph_failure import FailureAction as FA

    def route(state):
        if state.get("done"):
            return "end"
        fa = str(state.get("failure_action") or FA.CONTINUE.value).lower()
        if fa in (FA.RETRY.value, FA.REPLAN.value, FA.CONTINUE.value):
            return "agent"
        if fa in (FA.INTERRUPT.value, FA.STOP.value):
            return "end"
        return "agent"

    assert route({"done": False, "failure_action": "retry"}) == "agent"
    assert route({"done": False, "failure_action": "replan"}) == "agent"
    assert route({"done": True, "failure_action": "retry"}) == "end"
    assert route({"done": False, "failure_action": "interrupt"}) == "end"
    assert route({"done": False, "failure_action": "stop"}) == "end"
