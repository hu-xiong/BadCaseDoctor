# -*- coding: utf-8 -*-
"""LangGraph checkpointer 工厂与 thread_id 单测。"""
import operator
import os
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.langgraph_checkpointer import (
    checkpointer_backend,
    get_checkpointer,
    graph_has_checkpoint,
    make_thread_id,
    reset_checkpointer_for_tests,
    stream_config,
)


class _CpState(TypedDict):
    messages: Annotated[list, operator.add]


def setup_function():
    reset_checkpointer_for_tests()
    os.environ["LANGGRAPH_CHECKPOINTER"] = "memory"


def teardown_function():
    reset_checkpointer_for_tests()


def test_backend_off(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER", "off")
    assert checkpointer_backend() == "off"
    reset_checkpointer_for_tests()
    assert get_checkpointer() is None


def test_memory_checkpointer(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER", "memory")
    reset_checkpointer_for_tests()
    cp = get_checkpointer()
    assert cp is not None
    assert get_checkpointer() is cp  # singleton


def test_make_thread_id_resume_preferred():
    tid = make_thread_id(
        chat_session_id=1,
        agent_session_id="abc",
        resume_thread_id="lg:9:prev",
    )
    assert tid == "lg:9:prev"
    tid2 = make_thread_id(chat_session_id=3, agent_session_id="rid1")
    assert tid2.startswith("lg:3:")


def test_graph_checkpoint_roundtrip(monkeypatch):
    monkeypatch.setenv("LANGGRAPH_CHECKPOINTER", "memory")
    reset_checkpointer_for_tests()

    def node(s):
        return {"messages": [{"role": "assistant", "content": "hi"}]}

    g = StateGraph(_CpState)
    g.add_node("n", node)
    g.add_edge(START, "n")
    g.add_edge("n", END)
    app = g.compile(checkpointer=get_checkpointer())
    tid = "lg:test:cp1"
    cfg = stream_config(tid)
    assert not graph_has_checkpoint(app, tid)
    app.invoke({"messages": [{"role": "user", "content": "x"}]}, cfg)
    assert graph_has_checkpoint(app, tid)
