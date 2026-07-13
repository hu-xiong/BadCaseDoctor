# -*- coding: utf-8 -*-
from agents.modify_field_schema import (
    allowed_fields_for_target,
    coerce_badcase_modifications_from_user_intent,
    modify_field_semantics_for_llm,
    normalize_field_key_for_target,
    remap_entity_modification_keys,
)
from agents.react_macro import build_macro_step_params_prompt


def test_badcase_full_cross_entity_remap():
    mods = remap_entity_modification_keys(
        "badcase",
        {
            "expected_result": "ans",
            "actual_result": "ca",
            "steps_to_reproduce": "repro",
            "severity": "p1",
            "similar_questions": "bp",
            "classification": "cat",
            "preconditions": "should_drop",
            "related_defects": "should_drop",
        },
    )
    assert mods == {
        "answer": "ans",
        "correct_answer": "ca",
        "reproduction_steps": "repro",
        "priority": "p1",
        "base_problem": "bp",
        "case_category": "cat",
    }


def test_bug_badcase_keys_remap_or_strip():
    mods = remap_entity_modification_keys(
        "bug",
        {
            "answer": "e",
            "correct_answer": "a",
            "reproduction_steps": "s",
            "base_problem": "drop",
            "badcase_result": "drop",
        },
    )
    assert mods == {
        "expected_result": "e",
        "actual_result": "a",
        "steps_to_reproduce": "s",
    }


def test_testcase_repro_to_steps():
    mods = remap_entity_modification_keys(
        "testcase",
        {
            "reproduction_steps": "step1",
            "expected_result": "drop",
            "answer": "drop",
        },
    )
    assert mods == {"steps": "step1"}


def test_normalize_field_key_badcase_zh():
    assert normalize_field_key_for_target("预期结果", "badcase") == "answer"
    assert normalize_field_key_for_target("复现步骤", "badcase") == "reproduction_steps"
    assert normalize_field_key_for_target("复现步骤", "bug") == "steps_to_reproduce"
    assert normalize_field_key_for_target("测试步骤", "testcase") == "steps"


def test_allowed_fields_badcase_has_no_expected():
    assert "expected_result" not in allowed_fields_for_target("badcase")
    assert "answer" in allowed_fields_for_target("badcase")


def test_coerce_priority_from_badcase_result_when_user_says_priority():
    user = "对话有问题，问进京证不能很好答完整 优先级改为紧急"
    mods = coerce_badcase_modifications_from_user_intent(
        user, {"badcase_result": "紧急"}
    )
    assert mods == {"priority": "紧急"}


def test_coerce_priority_from_status_mislabel():
    user = "把优先级改成 P1"
    mods = coerce_badcase_modifications_from_user_intent(user, {"status": "p1"})
    assert mods == {"priority": "p1"}


def test_coerce_keeps_badcase_result_when_user_asks_result():
    user = "BadCase结果改为已解决"
    mods = coerce_badcase_modifications_from_user_intent(
        user, {"badcase_result": "已解决"}
    )
    assert mods == {"badcase_result": "已解决"}


def test_modify_field_semantics_distinguishes_status_from_badcase_result():
    text = modify_field_semantics_for_llm("badcase")
    assert "status" in text
    assert "badcase_result" in text
    assert "禁止" in text and "badcase_result" in text


def test_modify_field_semantics_mentions_base_problem_not_title():
    text = modify_field_semantics_for_llm("badcase")
    assert "base_problem" in text
    assert "相似问题" in text
    assert "不是 title" in text or "**不是** title" in text


def test_macro_modify_prompt_includes_field_semantics():
    prompt = build_macro_step_params_prompt(
        tool="modify",
        step_spec={"plan_line": "modify badcase"},
        user_input="相似问题改为进京证5环6环区别",
        ui_context={"target": "badcase", "record_id": "1"},
        execution_context={"last_params": {"target": "badcase"}},
        frozen_macro={"target_hint": "badcase", "intent_hints": {}},
    )
    assert "base_problem" in prompt
    assert "问登录问题答的不好" not in prompt
