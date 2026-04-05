# -*- coding: utf-8 -*-
from agents.intent_guards import (
    strip_leading_think_embedded_gate,
    try_parse_completed_think_embedded_gate,
)


def test_embedded_gate_incomplete():
    assert try_parse_completed_think_embedded_gate("[GATE]{") is None
    assert try_parse_completed_think_embedded_gate("[GATE]{\"need_tools\":false") is None


def test_embedded_gate_chat():
    s = '[GATE]{"need_tools": false, "message": "你好，请问需要什么帮助"}[/GATE]'
    got = try_parse_completed_think_embedded_gate(s)
    assert got is not None
    intent, rest = got
    assert intent["need_tools"] is False
    assert "帮助" in intent["message"]
    assert rest == ""


def test_embedded_gate_tools_suffix():
    s = '[GATE]{"need_tools": true, "need_plan_ui": false}[/GATE]说明\n<todo_list><item>grep</item></todo_list>'
    got = try_parse_completed_think_embedded_gate(s)
    assert got is not None
    intent, rest = got
    assert intent["need_tools"] is True
    assert "todo_list" in rest


def test_strip_leading():
    intent, body = strip_leading_think_embedded_gate(
        '[GATE]{"need_tools":true}[/GATE]  \n<todo_list></todo_list>'
    )
    assert intent is not None
    assert intent["need_tools"] is True
    assert "<todo_list>" in body


def test_strip_no_close():
    intent, body = strip_leading_think_embedded_gate('[GATE]{"need_tools":true}')
    assert intent is None
    assert "[GATE]" in body
