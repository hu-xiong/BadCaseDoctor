"""agent_tasks 依赖图的拓扑分层。"""
import pytest

from agents.agent_task_dag import topological_batches


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
