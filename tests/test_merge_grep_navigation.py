"""_merge_grep_observation_into_context：批量 modify 仅以 grep navigation 中的 ID 为候选。"""
from unittest.mock import MagicMock

from agents.react_simplified import SimplifiedReActEngine


def test_merge_grep_restricts_bug_list_to_navigation_ids():
    eng = SimplifiedReActEngine(MagicMock(), MagicMock())
    observation = {
        "success": True,
        "data": {
            "bug_location": [
                {"id": 10, "title": "1"},
                {"id": 9, "title": "登录相关的bug"},
                {"id": 8, "title": "登录bug"},
            ],
            "badcase_analysis": [],
            "testcase_location": [],
            "navigation": {
                "type": "multiple",
                "items": [
                    {"type": "expand_and_locate", "target": "bug", "record_id": 9},
                    {"type": "expand_and_locate", "target": "bug", "record_id": 8},
                ],
            },
        },
    }
    ctx = {}
    eng._merge_grep_observation_into_context(observation, {"keywords": "登录"}, ctx)
    ids = [b["id"] for b in ctx.get("bug_list", [])]
    assert ids == [9, 8]
    assert 10 not in ids
    nav = (ctx.get("grep_result") or {}).get("navigation_ids") or {}
    assert nav.get("bug") == [9, 8]


def test_merge_grep_with_navigation_but_missing_ids_yields_empty_lists():
    """navigation 存在但解析不到 record_id 时，不得回退到全量 bug_location。"""
    eng = SimplifiedReActEngine(MagicMock(), MagicMock())
    observation = {
        "success": True,
        "data": {
            "bug_location": [{"id": 10, "title": "x"}],
            "badcase_analysis": [],
            "testcase_location": [],
            "navigation": {
                "type": "multiple",
                "items": [{"type": "expand_and_locate", "target": "bug"}],
            },
        },
    }
    ctx = {}
    eng._merge_grep_observation_into_context(observation, {}, ctx)
    assert ctx.get("bug_list") == []
    assert (ctx.get("grep_result") or {}).get("first_bug_id") is None


def test_constrain_modify_batch_intersects_navigation_ids():
    eng = SimplifiedReActEngine(MagicMock(), MagicMock())
    ctx = {
        "grep_result": {
            "navigation_ids": {"bug": [9, 8], "badcase": [], "testcase": []}
        }
    }
    target_list = [{"id": 10, "title": "x"}, {"id": 9}, {"id": 8}]
    out = eng._constrain_modify_target_list_by_grep_navigation(
        target_list, "bug", ctx, trace_phase="test"
    )
    assert [x["id"] for x in out] == [9, 8]
