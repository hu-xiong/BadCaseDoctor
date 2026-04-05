# -*- coding: utf-8 -*-
import json

from agents.react_function_call import (
    THINK_FC_TOOL,
    OBSERVE_FC_TOOL,
    build_react_decision_tools_from_registry,
    build_react_think_fc_tools,
    build_react_observe_fc_tools,
    decision_from_assistant_message,
    observe_fc_result_from_assistant_message,
    think_fc_result_from_assistant_message,
    use_react_decide_function_call,
)


class _FakeTool:
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description


class _FakeRegistry:
    def __init__(self, tools):
        self.tools = tools


def test_build_tools_from_registry():
    reg = _FakeRegistry({"grep": _FakeTool("grep", "搜索")})
    tools = build_react_decision_tools_from_registry(reg)
    assert len(tools) == 1
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "grep"
    assert tools[0]["function"]["parameters"]["type"] == "object"


def test_build_tools_excludes_get_tool_description_by_default(monkeypatch):
    reg = _FakeRegistry(
        {
            "grep": _FakeTool("grep", "搜"),
            "get_tool_description": _FakeTool("get_tool_description", "元"),
        }
    )
    tools = build_react_decision_tools_from_registry(reg)
    names = {t["function"]["name"] for t in tools}
    assert "grep" in names
    assert "get_tool_description" not in names


def test_decision_from_assistant_message_normalizes_tool_case():
    msg = {
        "tool_calls": [
            {
                "function": {
                    "name": "Grep",
                    "arguments": json.dumps({"keywords": "x"}, ensure_ascii=False),
                }
            }
        ]
    }
    d = decision_from_assistant_message(msg)
    assert d["tool"] == "grep"


def test_decision_from_assistant_message_dict():
    msg = {
        "content": "",
        "tool_calls": [
            {
                "id": "1",
                "type": "function",
                "function": {
                    "name": "grep",
                    "arguments": json.dumps({"keywords": "foo"}, ensure_ascii=False),
                },
            }
        ],
    }
    d = decision_from_assistant_message(msg)
    assert d is not None
    assert d["execute"] is True
    assert d["tool"] == "grep"
    assert d["params"]["keywords"] == "foo"


def test_decision_none_without_tool_calls():
    assert decision_from_assistant_message({"content": "<decision/>"}) is None


def test_use_react_decide_function_call_env(monkeypatch):
    monkeypatch.delenv("REACT_DECIDE_FUNCTION_CALL", raising=False)
    assert use_react_decide_function_call() is False
    monkeypatch.setenv("REACT_DECIDE_FUNCTION_CALL", "1")
    assert use_react_decide_function_call() is True


def test_build_react_think_fc_tools():
    tools = build_react_think_fc_tools()
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == THINK_FC_TOOL


def test_build_react_observe_fc_tools():
    tools = build_react_observe_fc_tools()
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == OBSERVE_FC_TOOL


def test_think_fc_tool_name_case_insensitive():
    msg = {
        "tool_calls": [
            {
                "function": {
                    "name": "Submit_React_Think",
                    "arguments": json.dumps(
                        {"need_tools": True, "need_todo_list": False, "todo_items": []},
                        ensure_ascii=False,
                    ),
                }
            }
        ],
    }
    tr = think_fc_result_from_assistant_message(msg)
    assert tr is not None
    assert tr["need_tools"] is True
    assert tr["need_todo_list"] is False


def test_think_fc_fallback_parse_json_in_content():
    msg = {
        "content": '前置说明\n```json\n{"need_tools": true, "need_todo_list": false, "todo_items": []}\n```\n',
        "tool_calls": None,
    }
    tr = think_fc_result_from_assistant_message(msg)
    assert tr is not None
    assert tr["need_todo_list"] is False


def test_think_fc_result_from_assistant_message():
    msg = {
        "content": "说明",
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {
                    "name": THINK_FC_TOOL,
                    "arguments": json.dumps(
                        {
                            "need_tools": True,
                            "need_todo_list": True,
                            "todo_items": ["grep foo"],
                        },
                        ensure_ascii=False,
                    ),
                },
            }
        ],
    }
    tr = think_fc_result_from_assistant_message(msg)
    assert tr is not None
    assert tr["need_tools"] is True
    assert tr["need_todo_list"] is True
    assert tr["todo_items"] == ["grep foo"]


def test_observe_fc_result_from_assistant_message():
    msg = {
        "content": "",
        "tool_calls": [
            {
                "id": "c2",
                "type": "function",
                "function": {
                    "name": OBSERVE_FC_TOOL,
                    "arguments": json.dumps(
                        {
                            "findings": ["ok"],
                            "context_update": {"bug_list": [1]},
                            "next_step": "modify",
                        },
                        ensure_ascii=False,
                    ),
                },
            }
        ],
    }
    ob = observe_fc_result_from_assistant_message(msg)
    assert ob is not None
    assert ob["findings"] == ["ok"]
    assert ob["context_update"] == {"bug_list": [1]}
    assert ob["next_step"] == "modify"
