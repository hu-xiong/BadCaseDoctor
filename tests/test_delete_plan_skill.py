"""delete_plan 技能匹配与 macro target_hint 推断。"""
from agents.intent_guards import user_text_implies_plan_entity_type
from agents.react_macro import _infer_macro_target_hint
from agents.skill_loader import SkillLoader


def test_delete_plan_skill_beats_delete_badcase():
    loader = SkillLoader()
    loader.load_all()
    text = "帮忙删除这个迭代计划2"
    assert user_text_implies_plan_entity_type(text)
    skill, score = loader.match_skill(text, {})
    assert skill is not None
    assert skill.name == "delete_plan"
    assert score >= 0.3


def test_delete_badcase_downranked_when_plan_explicit():
    loader = SkillLoader()
    loader.load_all()
    text = "帮忙删除这个迭代计划2"
    scores = {}
    user_input_lower = text.lower()
    intents = loader._extract_intents(user_input_lower)
    entities = loader._extract_entities(user_input_lower)
    for skill in loader.skills.values():
        s = skill.trigger.match(user_input_lower, intents, entities)
        if s > 0:
            scores[skill.name] = s
    assert scores.get("delete_plan", 0) > scores.get("delete_badcase", 0)


def test_macro_target_hint_infers_plan():
    hint = _infer_macro_target_hint("帮忙删除这个迭代计划2", {})
    assert hint == "plan"


def test_delete_plan_may_skip_grep():
    from agents.intent_guards import react_delete_plan_may_skip_grep

    assert react_delete_plan_may_skip_grep(
        {"target": "plan", "plan_id": 721227006875799552},
        sidebar_plan_id=721227006875799552,
    )
    assert not react_delete_plan_may_skip_grep({"target": "plan"})
    assert not react_delete_plan_may_skip_grep({"target": "badcase", "target_id": 1})
