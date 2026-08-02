# -*- coding: utf-8 -*-
from agents.cdp.step_driver import parse_nl_step, find_ref_by_name


def test_parse_navigate():
    p = parse_nl_step("打开 https://example.com/login")
    assert p["kind"] == "navigate"
    assert "example.com" in p["url"]


def test_parse_click():
    p = parse_nl_step("点击登录按钮")
    assert p["kind"] == "click"
    assert "登录" in p["target"]


def test_parse_fill():
    p = parse_nl_step("在用户名框输入 admin")
    assert p["kind"] == "fill"
    assert p["value"] == "admin"


def test_parse_assert_from_expected():
    p = parse_nl_step("验证进入首页", "欢迎")
    assert p["kind"] == "assert"
    assert p.get("text_contains") or p.get("expected")


def test_find_ref_by_name():
    nodes = [
        {"ref": "@e1", "role": "button", "name": "登录"},
        {"ref": "@e2", "role": "textbox", "name": "用户名"},
    ]
    assert find_ref_by_name(nodes, "登录") == "@e1"
    assert find_ref_by_name(nodes, "用户名", prefer_roles=["textbox"]) == "@e2"
