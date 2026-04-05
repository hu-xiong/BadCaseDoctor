# -*- coding: utf-8 -*-
import json

from agents.react_function_call import FcStreamAccumulator, decision_from_assistant_message


class _Delta:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Fn:
    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class _Tc:
    def __init__(self, index=0, id=None, function=None):
        self.index = index
        self.id = id
        self.function = function


def test_accumulator_content_only():
    acc = FcStreamAccumulator()
    assert acc.feed(type("C", (), {"choices": [type("Ch", (), {"delta": _Delta(content="hi")})]})()) == "hi"
    m = acc.build_assistant_message()
    assert m["content"] == "hi"
    assert decision_from_assistant_message(m) is None


def test_accumulator_tool_calls_chunks():
    acc = FcStreamAccumulator()
    ch = type(
        "C",
        (),
        {
            "choices": [
                type(
                    "Ch",
                    (),
                    {
                        "delta": _Delta(
                            tool_calls=[
                                _Tc(0, "c1", _Fn("grep", '{"keywords":')),
                            ]
                        )
                    },
                )
            ]
        },
    )()
    assert acc.feed(ch) == ""
    ch2 = type(
        "C",
        (),
        {
            "choices": [
                type(
                    "Ch",
                    (),
                    {
                        "delta": _Delta(
                            tool_calls=[
                                _Tc(0, None, _Fn(None, '"x"}')),
                            ]
                        )
                    },
                )
            ]
        },
    )()
    acc.feed(ch2)
    m = acc.build_assistant_message()
    d = decision_from_assistant_message(m)
    assert d is not None
    assert d["tool"] == "grep"
    assert d["params"]["keywords"] == "x"


def test_accumulator_dict_chunk():
    acc = FcStreamAccumulator()
    acc.feed(
        {
            "choices": [
                {
                    "delta": {
                        "content": "说明",
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "z",
                                "function": {"name": "modify", "arguments": json.dumps({"confirm": False})},
                            }
                        ],
                    }
                }
            ]
        }
    )
    m = acc.build_assistant_message()
    d = decision_from_assistant_message(m)
    assert d["tool"] == "modify"
