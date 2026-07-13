from agents.react_simplified import SimplifiedReActEngine


def test_expected_result_modify_drops_locator_text_fields():
    user_input = "登录bug，密码没有加密模式 的期望结果修改 成登录结果应该是有加密模式1"
    mods = {
        "expected_result": "登录结果应该是有加密模式1",
        "steps_to_reproduce": "登录界面密码没有加密模式",
        "actual_result": "没有加密模式",
    }

    normalized = SimplifiedReActEngine._normalize_modifications_for_bug_expected_result(
        None,
        mods,
        user_input,
    )

    assert normalized == {"expected_result": "登录结果应该是有加密模式1"}


def test_expected_result_modify_keeps_explicit_multi_field_request():
    user_input = "把登录bug的期望结果改成能登录，实际结果改成不能登录"
    mods = {
        "expected_result": "能登录",
        "actual_result": "不能登录",
    }

    normalized = SimplifiedReActEngine._normalize_modifications_for_bug_expected_result(
        None,
        mods,
        user_input,
    )

    assert normalized == mods


def test_todo_with_record_id_and_grep_text_extracts_modify():
    class DummyEngine:
        async def _extract_modifications_with_llm(self, todo, user_input, exploration=None):
            return {"expected_result": "登录结果应该是有加密模式12"}

    todo = (
        "本轮应使用正确的record_id(714020812427890688)重新grep该Bug，"
        "获取其完整信息和ID，以便后续执行修改操作。"
    )

    result = SimplifiedReActEngine._extract_todo_params(
        DummyEngine(),
        todo,
        "登录bug，密码没有加密模式的期望结果修改成登录结果应该是有加密模式12",
    )

    import asyncio

    result = asyncio.run(result)
    assert result["tool"] == "modify"
    assert result["params"]["target"] == "bug"
    assert result["params"]["target_id"] == 714020812427890688
    assert result["params"]["modifications"] == {
        "expected_result": "登录结果应该是有加密模式12"
    }
