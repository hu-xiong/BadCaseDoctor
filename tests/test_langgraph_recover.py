# -*- coding: utf-8 -*-
"""LangGraph 结构化纠错与 task_plan 单测。"""
from __future__ import annotations

import asyncio

from agents.langgraph_recover import (
    advance_task_plan,
    heuristic_task_plan_steps,
    needs_structured_recover,
    replan_forbid_repeat_hint,
    try_structured_recover,
)


def test_needs_structured_recover():
    assert needs_structured_recover(
        "modify", {"success": False, "error": "missing target_id"}
    )
    assert needs_structured_recover(
        "modify",
        {"success": False, "blocked": True, "reason": "grep_required_before_modify"},
    )
    assert not needs_structured_recover("modify", {"success": True, "preview_only": True})
    assert not needs_structured_recover("grep", {"success": False, "error": "x"})


def test_heuristic_task_plan_modify():
    steps = heuristic_task_plan_steps("please modify status to resolve login bug", locale="en")
    assert len(steps) >= 2
    assert steps[0]["status"] == "in_progress"
    assert any("Search" in (s.get("name") or "") or "locate" in (s.get("name") or "").lower() for s in steps)


def test_advance_task_plan():
    steps = heuristic_task_plan_steps("search and list bugs", locale="en")
    nxt = advance_task_plan(steps, "grep", success=True)
    assert nxt[0]["status"] == "done"
    assert nxt[0]["tool"] == "grep"
    if len(nxt) > 1:
        assert nxt[1]["status"] == "in_progress"


def test_replan_forbid_repeat():
    h = replan_forbid_repeat_hint(
        tool_name="create",
        tool_params={"target": "bug", "title": "x"},
        base_hint="try another approach",
        locale="en",
    )
    assert "Do NOT repeat" in h and "create" in h


def test_structured_recover_grep_then_modify():
    class _Tools:
        async def execute_grep(self, **kwargs):
            return {
                "success": True,
                "data": {
                    "bug_location": [{"id": 42, "title": "login"}],
                    "navigation": {
                        "type": "expand_and_locate",
                        "target": "bug",
                        "record_id": 42,
                        "bug_id": 42,
                    },
                },
            }

        async def execute_modify(self, **kwargs):
            if kwargs.get("target_id") in (42, "42"):
                return {"success": True, "preview_only": True, "confirmation_required": True}
            return {"success": False, "error": "缺少必要参数 target_id"}

    tools = _Tools()

    class _Eng:
        async def _execute_prepared_tool(self, name, params, progress_q=None):
            if name == "grep":
                return await tools.execute_grep(**params)
            return await tools.execute_modify(**params)

    from agents.langgraph_bridge import _lazy_helpers
    from agents.tool_registry import ToolRegistry

    helpers = _lazy_helpers(llm=None, tool_registry=ToolRegistry())

    async def _run():
        return await try_structured_recover(
            engine=_Eng(),
            helpers=helpers,
            tool_name="modify",
            tool_params={"target": "bug", "modifications": {"status": "resolved"}},
            observation={"success": False, "error": "missing target_id"},
            user_input="modify login fail bug to resolved",
            result_context={},
            grep_tool_calls=0,
            grep_attempts=0,
            last_grep_empty=False,
            project_id=1,
            plan_id=None,
            user_id="1",
            locale="en",
            ui_context=None,
            client_shell=None,
            pending_diff_context=None,
        )

    outcome = asyncio.run(_run())
    assert outcome is not None
    assert outcome.ran_grep is True
    assert outcome.grep_attempts >= 1
