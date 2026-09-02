# -*- coding: utf-8 -*-
"""LangGraph 桥接与引擎配置单测（不连真实 LLM/DB）。"""
from __future__ import annotations

from agents.agent_engine_config import agent_engine_backend, langgraph_max_rounds, langgraph_tool_allowlist
from agents.langgraph_bridge import prepare_mutate_or_coerce_grep


def test_agent_engine_default_langgraph(monkeypatch):
    monkeypatch.delenv("AGENT_ENGINE", raising=False)
    monkeypatch.delenv("REACT_ENGINE", raising=False)
    assert agent_engine_backend() == "langgraph"


def test_agent_engine_react_override(monkeypatch):
    monkeypatch.setenv("AGENT_ENGINE", "react")
    assert agent_engine_backend() == "react"


def test_langgraph_max_rounds_clamped(monkeypatch):
    monkeypatch.setenv("AGENT_LANGGRAPH_MAX_ROUNDS", "99")
    assert langgraph_max_rounds() == 40
    monkeypatch.setenv("AGENT_LANGGRAPH_MAX_ROUNDS", "3")
    assert langgraph_max_rounds() == 3


def test_langgraph_tool_allowlist_star(monkeypatch):
    monkeypatch.setenv("AGENT_LANGGRAPH_TOOLS", "*")
    assert langgraph_tool_allowlist() is None
    monkeypatch.setenv("AGENT_LANGGRAPH_TOOLS", "grep,modify")
    assert langgraph_tool_allowlist() == frozenset({"grep", "modify"})


def test_prepare_mutate_coerce_grep_without_context():
    from agents.langgraph_bridge import _lazy_helpers
    from agents.tool_registry import ToolRegistry

    helpers = _lazy_helpers(llm=None, tool_registry=ToolRegistry())
    name, params, block = prepare_mutate_or_coerce_grep(
        helpers=helpers,
        tool_name="modify",
        tool_params={"target": "bug", "modifications": {"status": "resolved"}},
        user_input="把登录失败的 bug 改成已解决",
        result_context={},
        grep_tool_calls=0,
        project_id=1,
        plan_id=None,
        ui_context=None,
        locale="zh",
    )
    assert block is None
    assert name == "grep"
    assert isinstance(params, dict)


def test_langgraph_import_and_graph_compile():
    from agents.langgraph_engine import LangGraphReactEngine, _LANGGRAPH_OK
    from agents.tool_registry import ToolRegistry

    assert _LANGGRAPH_OK is True

    class _Fake:
        def chat_completion_with_tools(self, messages, tools, **kwargs):
            class M:
                content = "hi"
                tool_calls = []

            class C:
                message = M()

            class R:
                choices = [C()]

            return R()

    eng = LangGraphReactEngine(_Fake(), ToolRegistry())
    assert eng._ensure_graph() is not None
