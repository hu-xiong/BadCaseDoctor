"""resolve_modify_target_and_id 单元测试（撞号语义由上层传入的 context 表达）。"""

import pytest

from agents.intent.resolution import (
    ModifyResolutionContext,
    ModifyResolutionError,
    resolve_modify_target_and_id,
)


def test_status_forces_source_bug():
    ctx = ModifyResolutionContext(
        last_grep_target="card",
        card_id=99,
        target_id=14,
        has_raw_bug_list=True,
    )
    t, pk, cid = resolve_modify_target_and_id({"status": "open"}, "改状态", ctx)
    assert t == "bug"
    assert pk == 14


def test_mixed_source_and_card_fields_prefers_source():
    ctx = ModifyResolutionContext(target_id=5, card_id=5, has_raw_bug_list=True)
    t, pk, cid = resolve_modify_target_and_id(
        {"status": "open", "plan_id": 1},
        "",
        ctx,
    )
    assert t == "bug"
    assert pk == 5


def test_card_only_plan_id():
    ctx = ModifyResolutionContext(card_id=7, target_id=None)
    t, pk, cid = resolve_modify_target_and_id({"plan_id": 3}, "", ctx)
    assert t == "card"
    assert pk is None
    assert cid == 7


def test_title_ambiguous_last_grep_card():
    ctx = ModifyResolutionContext(
        last_grep_target="card",
        card_id=3,
        target_id=14,
        has_raw_bug_list=True,
        card_rows=[{"id": 3, "source_type": "bug", "source_id": 14}],
    )
    t, pk, cid = resolve_modify_target_and_id({"title": "X"}, "随便改标题", ctx)
    assert t == "card"
    assert cid == 3


def test_title_modify_card_nl_separated_name_not_bug_when_both_ids():
    """「修改卡片…的标题」中间为计划名等，无连续「卡片标题」；且 card_id/target_id 同时存在时仍走卡片层。"""
    ctx = ModifyResolutionContext(
        last_grep_target="all",
        card_id=11,
        target_id=11,
        has_raw_bug_list=True,
        card_rows=[{"id": 11, "source_type": "bug", "source_id": 11}],
    )
    t, pk, cid = resolve_modify_target_and_id(
        {"title": "5月迭代计划第一个"},
        "修改卡片5月迭代计划的标题为5月迭代计划第一个",
        ctx,
    )
    assert t == "card"
    assert pk is None
    assert cid == 11


def test_title_explicit_bug_heading():
    ctx = ModifyResolutionContext(
        last_grep_target="card",
        card_id=3,
        target_id=14,
        has_raw_bug_list=True,
    )
    t, pk, cid = resolve_modify_target_and_id({"title": "X"}, "改Bug标题为 X", ctx)
    assert t == "bug"
    assert pk == 14


def test_editing_surface_bug_title():
    ctx = ModifyResolutionContext(
        last_grep_target="card",
        card_id=3,
        target_id=20,
        editing_surface="bug_title",
    )
    t, pk, cid = resolve_modify_target_and_id({"title": "A"}, "", ctx)
    assert t == "bug"
    assert pk == 20


def test_card_requires_selection():
    ctx = ModifyResolutionContext(card_id=None, target_id=None, last_grep_target="card")
    with pytest.raises(ModifyResolutionError, match="请先选中卡片"):
        resolve_modify_target_and_id({"card_title": "x"}, "看板标题", ctx)


def test_testcase_field_infer():
    ctx = ModifyResolutionContext(target_id=9, has_raw_testcase_list=True)
    t, pk, _ = resolve_modify_target_and_id({"preconditions": "p"}, "", ctx)
    assert t == "testcase"
    assert pk == 9


def test_badcase_field_infer():
    ctx = ModifyResolutionContext(target_id=2, has_raw_badcase_list=True)
    t, pk, _ = resolve_modify_target_and_id({"answer": "a"}, "", ctx)
    assert t == "badcase"
    assert pk == 2


def test_ambiguous_llm_override_when_enabled(monkeypatch):
    monkeypatch.setenv("MODIFY_INTENT_LLM", "1")

    def _fake_llm(user_input, *, keys, **kwargs):
        assert "title" in keys
        return "bug"

    monkeypatch.setattr(
        "agents.intent.modify_intent_llm.llm_classify_modify_ambiguous_target",
        _fake_llm,
    )
    # last_grep=all 且 id 双存在时启发式为 SOURCE，才会进入 LLM 分支（last_grep=card 时启发式已判 card，不再调 LLM）
    ctx = ModifyResolutionContext(
        last_grep_target="all",
        card_id=3,
        target_id=14,
        has_raw_bug_list=True,
        card_rows=[{"id": 3, "source_type": "bug", "source_id": 14}],
    )
    t, pk, cid = resolve_modify_target_and_id({"title": "X"}, "随便改标题", ctx)
    assert t == "bug"
    assert pk == 14


def test_editing_surface_bug_title_skips_llm(monkeypatch):
    monkeypatch.setenv("MODIFY_INTENT_LLM", "1")
    monkeypatch.setattr(
        "agents.intent.modify_intent_llm.llm_classify_modify_ambiguous_target",
        lambda *a, **k: "card",
    )
    ctx = ModifyResolutionContext(
        last_grep_target="card",
        card_id=3,
        target_id=20,
        editing_surface="bug_title",
    )
    t, pk, cid = resolve_modify_target_and_id({"title": "A"}, "", ctx)
    assert t == "bug"
    assert pk == 20
