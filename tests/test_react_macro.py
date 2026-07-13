# -*- coding: utf-8 -*-
from agents.react_macro import (
    build_macro_modify_decision,
    infer_tool_from_plan_line,
    macro_execution_separation_enabled,
    macro_grep_has_actionable_hit,
    parse_macro_modify_params_json,
    plan_steps_imply_grep_then_modify,
    plan_steps_to_macro_steps,
    try_freeze_macro_from_plan,
    try_freeze_macro_grep_modify,
)


def test_plan_steps_imply_grep_modify():
    assert plan_steps_imply_grep_then_modify(
        ["grep 定位", "modify 改状态"]
    )
    assert not plan_steps_imply_grep_then_modify(["仅 grep"])


def test_infer_tool_and_macro_steps():
    assert infer_tool_from_plan_line("grep 定位 badcase") == "grep"
    assert infer_tool_from_plan_line("modify 状态") == "modify"
    assert (
        infer_tool_from_plan_line('根据 grep 结果，调用 modify 修改状态为"已关闭"')
        == "modify"
    )
    steps = plan_steps_to_macro_steps(
        [
            "grep 定位 BadCase 记录",
            '根据 grep 结果，调用 modify 修改状态为"已关闭"',
        ],
        user_input="状态修改为已关闭",
    )
    assert [s["tool"] for s in steps] == ["grep", "modify"]
    steps = plan_steps_to_macro_steps(["grep 定位", "modify 改状态", "terminal 验证"])
    assert [s["tool"] for s in steps] == ["grep", "modify", "terminal"]
    assert steps[0]["needs_param_llm"] is False
    assert steps[1]["needs_param_llm"] is True
    assert steps[2]["needs_param_llm"] is True


def test_freeze_macro_modify_always_needs_param_llm(monkeypatch):
    monkeypatch.setenv("REACT_MACRO_GREP_MODIFY", "1")
    fm = try_freeze_macro_grep_modify(
        user_input="问登录问题答的不好 答案修改为 提问登录问题即可456789101",
        ui_context={"target": "badcase", "record_id": "715068135836749824", "view": "detail"},
        plan_steps=[],
        round_id="r-answer",
    )
    assert fm is not None
    modify_step = next(s for s in fm["steps"] if s["tool"] == "modify")
    assert modify_step.get("needs_param_llm") is True
    assert not (fm.get("intent_hints") or {}).get("modifications")


def test_freeze_macro_with_ui_and_modify_intent(monkeypatch):
    monkeypatch.setenv("REACT_MACRO_GREP_MODIFY", "1")
    fm = try_freeze_macro_grep_modify(
        user_input="问登录问题答的不好 状态修改为已关闭",
        ui_context={"target": "badcase", "record_id": "715068135836749824"},
        plan_steps=["grep 定位", "modify 改状态"],
        round_id="req-1",
    )
    assert fm is not None
    assert fm.get("macro_version") == 2
    modify_step = next(s for s in fm["steps"] if s["tool"] == "modify")
    assert modify_step.get("needs_param_llm") is True


def test_macro_auto_enabled_with_two_step_plan(monkeypatch):
    monkeypatch.delenv("REACT_MACRO_GREP_MODIFY", raising=False)
    monkeypatch.setenv("REACT_MACRO_AUTO", "1")
    assert macro_execution_separation_enabled(["grep 定位", "modify 改状态"])
    fm = try_freeze_macro_from_plan(
        user_input="状态改为 hold",
        ui_context={"record_id": "1"},
        plan_steps=["grep", "modify"],
        round_id="auto",
        first_tool="grep",
    )
    assert fm is not None


def test_macro_auto_disabled_when_explicit_off(monkeypatch):
    monkeypatch.setenv("REACT_MACRO_GREP_MODIFY", "0")
    assert not macro_execution_separation_enabled(["grep", "modify"])
    assert try_freeze_macro_from_plan(
        user_input="x",
        ui_context={"record_id": "1"},
        plan_steps=["grep", "modify"],
        round_id="x",
        first_tool="grep",
    ) is None


def test_freeze_macro_from_plan_first_tool_params(monkeypatch):
    monkeypatch.setenv("REACT_MACRO_GREP_MODIFY", "1")
    fm = try_freeze_macro_from_plan(
        user_input="改负责人",
        ui_context={"record_id": "1"},
        plan_steps=["grep", "modify"],
        round_id="r2",
        first_tool="grep",
        first_tool_params={"target": "badcase", "keywords": "登录"},
    )
    assert fm is not None
    assert fm["steps"][0].get("params_seed") == {
        "target": "badcase",
        "keywords": "登录",
    }


def test_build_macro_modify_from_grep_snapshot(monkeypatch):
    monkeypatch.setenv("REACT_MACRO_GREP_MODIFY", "1")
    fm = try_freeze_macro_grep_modify(
        user_input="状态改为 hold",
        ui_context={"record_id": "9"},
        plan_steps=["grep", "modify"],
        round_id="r",
        modifications={"status": "hold"},
    )
    ctx = {
        "grep_result": {
            "first_badcase_id": 715068135836749824,
            "badcase_list": [{"id": 715068135836749824, "title": "t"}],
        }
    }
    d = build_macro_modify_decision(
        user_input="状态改为 hold",
        result_ctx=ctx,
        grep_tool_params={"target": "badcase"},
        frozen_macro=fm,
        project_id=1,
        plan_id=1,
        ui_context=None,
    )
    assert d is not None
    assert d["tool"] == "modify"
    assert d["params"]["target_id"] == 715068135836749824
    assert d["params"]["modifications"]["status"] == "hold"


def test_grep_hit_detection():
    assert macro_grep_has_actionable_hit({"grep_result": {"first_badcase_id": 1}})
    assert not macro_grep_has_actionable_hit({"grep_result": {}})


def test_parse_macro_params_json():
    p = parse_macro_modify_params_json(
        '{"target":"badcase","target_id":9,"modifications":{"status":"closed"},"confirm":false}'
    )
    assert p is not None
    assert p["target"] == "badcase"
    assert p["target_id"] == 9
    assert p["modifications"]["status"] == "closed"
