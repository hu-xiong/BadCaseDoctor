"""agent_tasks 表 + DAG 分层与失败传播（不跑真实 LLM/工具）。"""
import asyncio

import pytest

from agents.agent_task_dag import (
    topological_batches,
    create_task_row,
    propagate_failed_dependencies,
    mark_failed,
)


def test_topological_batches_parallel_and_chain():
    # A, B 无依赖并行；C 依赖 A、B
    ids = ["a", "b", "c"]
    deps = {"a": [], "b": [], "c": ["a", "b"]}
    batches = topological_batches(ids, deps)
    assert len(batches) == 2
    assert set(batches[0]) == {"a", "b"}
    assert batches[1] == ["c"]


def test_topological_batches_cycle_raises():
    ids = ["a", "b"]
    deps = {"a": ["b"], "b": ["a"]}
    with pytest.raises(ValueError):
        topological_batches(ids, deps)


def test_dependency_fail_propagation():
    """策略 A：依赖 failed → 下游 pending 变 failed。"""
    from app import app, db, sync_database_schema, AgentTask

    with app.app_context():
        sync_database_schema()
        t1 = create_task_row(name="t1", params={}, dependencies=[], session_id="s-test")
        t2 = create_task_row(name="t2", params={}, dependencies=[t1], session_id="s-test")
        mark_failed(t1, "boom")
        propagate_failed_dependencies([t1, t2])
        db.session.expire_all()
        r2 = AgentTask.query.get(t2)
        assert r2 is not None
        assert r2.status == "failed"
        assert "依赖" in (r2.error or "")


def test_tool_execution_max_attempts_default_and_cap(monkeypatch):
    from agents import agent_task_dag as m

    monkeypatch.delenv("AGENT_TOOL_MAX_ATTEMPTS", raising=False)
    assert m.tool_execution_max_attempts() == 2
    monkeypatch.setenv("AGENT_TOOL_MAX_ATTEMPTS", "99")
    assert m.tool_execution_max_attempts() == 5
    monkeypatch.setenv("AGENT_TOOL_MAX_ATTEMPTS", "1")
    assert m.tool_execution_max_attempts() == 1


def test_execute_tool_implementation_with_retry_second_ok(monkeypatch):
    from agents.agent_task_dag import execute_tool_implementation_with_retry

    monkeypatch.setenv("AGENT_TOOL_MAX_ATTEMPTS", "2")

    class _Eng:
        def __init__(self):
            self.calls = 0

        async def _execute_tool_implementation(self, decision):
            self.calls += 1
            if self.calls < 2:
                return {"success": False, "error": "transient"}
            return {"success": True, "data": 1}

    eng = _Eng()
    out = asyncio.run(
        execute_tool_implementation_with_retry(eng, {"tool": "x", "params": {}})
    )
    assert out.get("success") is not False
    assert out.get("data") == 1
    assert eng.calls == 2


def test_execute_tool_implementation_with_retry_all_fail(monkeypatch):
    from agents.agent_task_dag import execute_tool_implementation_with_retry

    monkeypatch.setenv("AGENT_TOOL_MAX_ATTEMPTS", "2")

    class _Eng:
        def __init__(self):
            self.calls = 0

        async def _execute_tool_implementation(self, decision):
            self.calls += 1
            return {"success": False, "error": "always"}

    eng = _Eng()
    out = asyncio.run(
        execute_tool_implementation_with_retry(eng, {"tool": "x", "params": {}})
    )
    assert out.get("success") is False
    assert eng.calls == 2
