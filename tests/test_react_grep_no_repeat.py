"""grep 无命中 / 已有命中后不再重复检索。"""
from agents.react_simplified import (
    _grep_observation_empty_lists,
    _react_should_block_repeat_grep,
)


def test_block_repeat_grep_after_empty():
    obs = {
        "success": True,
        "data": {
            "bug_location": [],
            "badcase_analysis": [],
            "grep_search_meta": {"low_relevance_empty": True},
        },
    }
    block, reason = _react_should_block_repeat_grep(
        prev_observation=obs,
        prev_action={"tool": "grep", "params": {}},
        grep_call_count=1,
    )
    assert block is True
    assert reason == "empty"


def test_block_repeat_grep_after_hits():
    obs = {
        "success": True,
        "data": {"bug_location": [{"id": 1, "title": "x"}]},
    }
    block, reason = _react_should_block_repeat_grep(
        prev_observation=obs,
        prev_action={"tool": "grep", "params": {}},
        grep_call_count=1,
    )
    assert block is True
    assert reason == "has_hits"


def test_allow_first_grep():
    block, reason = _react_should_block_repeat_grep(
        prev_observation=None,
        prev_action=None,
        grep_call_count=0,
    )
    assert block is False
    assert reason == ""


def test_grep_observation_empty_lists():
    assert _grep_observation_empty_lists({"data": {"bug_location": []}}) is True
    assert _grep_observation_empty_lists(
        {"data": {"bug_location": [{"id": 1}]}}
    ) is False
