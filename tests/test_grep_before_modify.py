"""modify/delete 前须先 grep 的门控。"""
from agents.intent_guards import (
    react_context_has_grep_for_mutate,
    react_grep_before_modify_coerce,
    react_require_grep_before_modify,
)
from agents.prompts import unified_round_grep_first_prompt_block


def test_require_grep_default_on():
    assert react_require_grep_before_modify() is True
    assert react_grep_before_modify_coerce() is True


def test_round0_prompt_forbids_first_modify():
    blk = unified_round_grep_first_prompt_block(round_idx=0, prev_observation=None)
    assert "grep" in blk
    assert "modify" in blk
    assert "禁止" in blk or "Forbidden" in blk


def test_no_grep_context_blocks_mutate():
    assert (
        react_context_has_grep_for_mutate(None, None, grep_tool_calls=0) is False
    )
    seeded = {
        "_grep_seeded_from_ui_context": True,
        "grep_result": {"first_bug_id": 1234567890123456789},
    }
    assert (
        react_context_has_grep_for_mutate(seeded, None, grep_tool_calls=0) is False
    )


def test_after_grep_allows_mutate():
    ctx = {"grep_result": {"bug_list": [{"id": 1}], "first_bug_id": 1}}
    assert (
        react_context_has_grep_for_mutate(ctx, None, grep_tool_calls=1) is True
    )
    assert (
        react_context_has_grep_for_mutate(
            None, {"tool": "grep", "params": {}}, grep_tool_calls=0
        )
        is True
    )
