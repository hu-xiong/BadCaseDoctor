from agents.intent_guards import user_text_implies_bug_entity_type
from agents.react_simplified import SimplifiedReActEngine


def test_bug_title_phrase_implies_bug_entity():
    assert user_text_implies_bug_entity_type(
        "登录忘记密码按钮点击问题，没有调用接口 这个bug标题修改成登录bug忘记密码"
    )


def test_extract_old_bug_title_before_title_change():
    engine = SimplifiedReActEngine(llm=None, tool_registry={})

    kw = engine._extract_title_keywords_for_grep(
        "登录忘记密码按钮点击问题，没有调用接口 这个bug标题修改成登录bug忘记密码",
        "",
    )

    assert kw == "登录忘记密码按钮点击问题，没有调用接口"


def test_card_target_coerces_to_bug_for_bug_title_change():
    engine = SimplifiedReActEngine(llm=None, tool_registry={})
    params = {"target": "card", "keywords": "709944091793690600"}
    user_input = "登录忘记密码按钮点击问题，没有调用接口 这个bug标题修改成登录bug忘记密码"

    engine._coerce_grep_target_for_user_intent(
        {"execute": True, "tool": "grep", "params": params},
        user_input,
        "",
    )

    assert params["target"] == "bug"
