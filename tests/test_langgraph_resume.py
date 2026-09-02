# -*- coding: utf-8 -*-
"""LangGraph 断点快照与恢复单测。"""
from __future__ import annotations

from agents.langgraph_resume import (
    apply_langgraph_resume,
    build_langgraph_resume_snapshot,
    compact_result_context,
    format_long_memory_block,
    format_project_hint_block,
    user_input_already_has_terminal_block,
)


def test_terminal_block_detect():
    assert user_input_already_has_terminal_block("【本机终端执行结果】\nok")
    assert user_input_already_has_terminal_block("[Client terminal]\nok")
    assert not user_input_already_has_terminal_block("改一下登录 bug")


def test_build_and_apply_resume():
    msgs = [
        {"role": "system", "content": "old sys"},
        {"role": "user", "content": "改登录失败"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "grep", "arguments": '{"keywords":"登录"}'},
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "name": "grep",
            "content": '{"success":true,"first_bug_id":1}',
        },
    ]
    snap = build_langgraph_resume_snapshot(
        messages=msgs,
        result_context={"first_bug_id": 1, "grep_result": {"first_bug_id": 1}, "noise": "x"},
        grep_tool_calls=1,
        failure_retries=1,
        reason="awaiting_human",
    )
    assert snap["schema_version"] == 1
    assert snap["grep_tool_calls"] == 1
    assert "noise" not in snap["result_context"]
    assert snap["result_context"]["first_bug_id"] == 1

    restored = apply_langgraph_resume(
        system_prompt="new sys",
        resume_state=snap,
        new_user_content="继续，改成已解决",
    )
    assert restored["messages"][0]["content"] == "new sys"
    assert restored["messages"][-1]["content"] == "继续，改成已解决"
    assert restored["grep_tool_calls"] == 1
    assert restored["failure_retries"] == 1
    assert restored["result_context"]["first_bug_id"] == 1
    assert restored["done"] is False


def test_compact_result_context_lists():
    rc = compact_result_context({"bug_list": list(range(50)), "first_bug_id": 9})
    assert len(rc["bug_list"]) == 30
    assert rc["first_bug_id"] == 9


def test_compact_keeps_login_pending():
    pending = {"session_id": "s1", "await_type": "verification_code"}
    rc = compact_result_context(
        {"cdp_login_pending": pending, "pending_modify_preview": {"target_id": 3}, "noise": 1}
    )
    assert rc["cdp_login_pending"] == pending
    assert rc["pending_modify_preview"]["target_id"] == 3
    assert "noise" not in rc


def test_hint_and_memory_blocks():
    assert "项目" in format_project_hint_block(
        hint_project_name="Demo", hint_plan_name="迭代1", locale="zh"
    )
    assert "Long-term" in format_long_memory_block(
        {"long_memory_text": "prefer grep first"}, locale="en"
    )
    assert format_long_memory_block(None) == ""
