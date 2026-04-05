# -*- coding: utf-8 -*-
from agents.intent_guards import (
    resolve_need_todo_list_effective,
    react_need_todo_list_heuristic_fallback,
    try_parse_completed_think_embedded_gate,
)


def test_gate_need_todo_list_parsed():
    s = '[GATE]{"need_tools": true, "need_todo_list": false}[/GATE]x'
    got = try_parse_completed_think_embedded_gate(s)
    assert got is not None
    intent, rest = got
    assert intent["need_tools"] is True
    assert intent["need_todo_list"] is False
    assert rest == "x"


def test_resolve_model_wins():
    assert resolve_need_todo_list_effective({"need_todo_list": True}, "hello") is True
    assert resolve_need_todo_list_effective({"need_todo_list": False}, "先 grep 再 modify 再总结") is False


def test_resolve_fallback_multi_tool():
    assert resolve_need_todo_list_effective(None, "先 grep 再 modify") is True
    assert resolve_need_todo_list_effective({}, "把负责人改成张三") is False


def test_heuristic_off_env(monkeypatch):
    monkeypatch.setenv("REACT_NEED_TODO_LIST_HEURISTIC", "0")
    try:
        assert react_need_todo_list_heuristic_fallback("短句") is True
    finally:
        monkeypatch.delenv("REACT_NEED_TODO_LIST_HEURISTIC", raising=False)
