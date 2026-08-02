# -*- coding: utf-8 -*-
"""CDP 测试任务意图识别。"""
from agents.cdp.test_intent import detect_cdp_test_intent, extract_testcase_ids_from_context


def test_manual_test_intent():
    out = detect_cdp_test_intent(
        user_input="先打开登录页，输入账号密码，然后点击登录，验证进入首页",
        tool_action="click",
    )
    assert out["should_open"] is True
    assert out["mode"] == "manual"


def test_testcase_plan_intent():
    out = detect_cdp_test_intent(
        user_input="用当前迭代计划的测试用例跑一遍 UI 测试",
        tool_action="navigate",
        context={"plan_id": 2},
    )
    assert out["should_open"] is True
    assert out["mode"] == "testcase"


def test_explore_intent():
    out = detect_cdp_test_intent(user_input="探测首页", tool_action="explore")
    assert out["should_open"] is True
    assert out["mode"] == "explore"


def test_explicit_off():
    out = detect_cdp_test_intent(
        user_input="测试登录",
        tool_action="click",
        params={"test_task": False},
    )
    assert out["should_open"] is False


def test_advise_only_how_to_test():
    out = detect_cdp_test_intent(
        user_input="这个登录用例怎么测？",
        tool_action="",
    )
    assert out["should_open"] is False
    assert out.get("reason") == "advise_only"


def test_extract_testcase_ids():
    ids = extract_testcase_ids_from_context({
        "first_testcase_id": 101,
        "testcase_ids": [101, 102],
    })
    assert ids == [101, 102]
