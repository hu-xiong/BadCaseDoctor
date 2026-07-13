# -*- coding: utf-8 -*-
from agents.cdp.params import inject_cdp_tool_params, resolve_cdp_target_url


def test_resolve_cdp_target_url_from_user_message():
    url = resolve_cdp_target_url(
        params={},
        user_input="请测试 http://localhost:5173/#/project-detail/3 这个页面",
    )
    assert url == "http://localhost:5173/#/project-detail/3"


def test_inject_cdp_tool_params_session_create():
    ctx = {}
    params = {"action": "session", "sub_action": "create"}
    inject_cdp_tool_params(
        params,
        user_input="打开 http://localhost:5173/#/project-detail/3 做探测",
        result_context=ctx,
    )
    assert params["url"] == "http://localhost:5173/#/project-detail/3"
    assert ctx["cdp_target_url"] == "http://localhost:5173/#/project-detail/3"


def test_resolve_cdp_target_url_from_context():
    url = resolve_cdp_target_url(
        params={},
        user_input="继续探测",
        result_context={"cdp_target_url": "http://localhost:5173/#/project-detail/3"},
    )
    assert url == "http://localhost:5173/#/project-detail/3"
