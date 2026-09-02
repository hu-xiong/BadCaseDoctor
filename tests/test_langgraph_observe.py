# -*- coding: utf-8 -*-
"""LangGraph observe 与 task_plan 断点字段单测。"""
from __future__ import annotations

from agents.langgraph_observe import build_observe_note, observe_message
from agents.langgraph_resume import apply_langgraph_resume, build_langgraph_resume_snapshot


def test_observe_grep_success():
    note = build_observe_note(
        tool_name="grep",
        observation={"success": True},
        failure_action="continue",
        result_context={"first_bug_id": 99},
        locale="en",
    )
    assert "grep succeeded" in note.lower() or "Located" in note
    assert "99" in note


def test_observe_preview():
    note = build_observe_note(
        tool_name="modify",
        observation={"success": True, "preview_only": True, "target_id": 1},
        failure_action="continue",
        locale="en",
    )
    assert "preview" in note.lower()
    assert "confirm" in note.lower()


def test_observe_retry():
    note = build_observe_note(
        tool_name="modify",
        observation={"success": False, "error": "missing id"},
        failure_action="retry",
        failure_kind="missing_id",
        locale="en",
    )
    assert "RETRY" in note


def test_observe_message_prefix():
    m = observe_message("grep ok", locale="en")
    assert m["role"] == "user"
    assert m["content"].startswith("[Observe]")


def test_resume_keeps_task_plan():
    snap = build_langgraph_resume_snapshot(
        messages=[{"role": "user", "content": "x"}],
        result_context={"first_bug_id": 1},
        task_plan_steps=[
            {"id": 1, "name": "Search", "status": "done"},
            {"id": 2, "name": "Modify", "status": "in_progress"},
        ],
    )
    assert snap.get("task_plan_steps")
    restored = apply_langgraph_resume(
        system_prompt="sys",
        resume_state=snap,
        new_user_content="continue",
    )
    assert restored.get("task_plan_emitted") is True
    assert len(restored.get("task_plan_steps") or []) == 2
