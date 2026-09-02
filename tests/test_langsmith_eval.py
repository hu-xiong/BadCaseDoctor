# -*- coding: utf-8 -*-
from __future__ import annotations

import os

os.environ.setdefault("LANGGRAPH_CHECKPOINTER", "memory")
os.environ.setdefault("LANGGRAPH_OBSERVE", "0")


def test_langsmith_tracing_noop_without_key(monkeypatch):
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    from agents import langsmith_tracing as lt

    lt._setup_done = False
    assert lt.setup_langsmith_tracing(force=True) is False


def test_langsmith_tracing_env(monkeypatch):
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_test_key")
    monkeypatch.setenv("LANGSMITH_TRACING", "1")
    monkeypatch.setenv("LANGSMITH_PROJECT", "unit-test-proj")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    from agents import langsmith_tracing as lt

    lt._setup_done = False
    assert lt.setup_langsmith_tracing(force=True) is True
    assert os.environ.get("LANGCHAIN_TRACING_V2") == "true"
    assert lt.langsmith_project() == "unit-test-proj"
    # 避免后续用例继承 tracing on
    lt._setup_done = False
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "false")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)


def test_evaluators_local_preview():
    from evals.langsmith.evaluators import local_score

    scores = local_score(
        {
            "tool_sequence": ["grep", "modify"],
            "preview_await_confirm": True,
            "saw_confirm_true": False,
            "empty_grep_stop": False,
            "grep_calls": 1,
        },
        {
            "expected_tools": ["grep", "modify"],
            "require_preview_stop": True,
            "forbid_confirm_true": True,
        },
    )
    assert scores["_mean"] == 1.0


def test_golden_dry_run_pass():
    from evals.langsmith.run_eval import run_dry

    report = run_dry()
    assert report["n"] >= 3
    assert float(report["overall_mean"]) >= 0.99, report
