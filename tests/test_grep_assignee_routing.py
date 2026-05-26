from agents.intent_guards import user_text_implies_bug_entity_type
from agents.react_simplified import SimplifiedReActEngine


def test_hx_bug_phrase_implies_bug_entity():
    assert user_text_implies_bug_entity_type("将负责人 hx的bug都检索出来")


def test_bug_target_not_widened_to_all():
    engine = SimplifiedReActEngine(llm=None, tool_registry={})
    params = {"target": "bug", "keywords": "负责人:hx"}
    user_input = "将负责人 hx的bug都检索出来"

    engine._coerce_grep_target_for_user_intent(
        {"execute": True, "tool": "grep", "params": params},
        user_input,
        "",
    )
    engine._widen_grep_target_to_include_cards_unless_explicit(params, user_input, "")

    assert params["target"] == "bug"


def test_enrich_assignee_from_user_text():
    engine = SimplifiedReActEngine(llm=None, tool_registry={})
    params = {"target": "bug", "keywords": "负责人:hx", "assignee": None}
    user_input = "将负责人 hx的bug都检索出来"

    engine._enrich_grep_params_from_user_text(params, user_input, "")

    assert params.get("assignee") == "hx"
    assert params.get("keywords") is None
