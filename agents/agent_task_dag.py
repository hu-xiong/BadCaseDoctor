"""
Agent 任务依赖的拓扑分层（读侧工具）。

`agents.react_run_store.snapshot_agent_task_dag` 用它把 agent_tasks 依赖切成可并行层。
写入 agent_tasks 的编排路径（REACT_AGENT_TASK_DAG / run_dag_async）已随自研 ReAct 引擎删除。
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, List, Sequence


def topological_batches(
    task_ids: Sequence[str],
    id_to_deps: Dict[str, List[str]],
) -> List[List[str]]:
    ids = list(task_ids)
    pending = set(ids)
    rev: Dict[str, List[str]] = defaultdict(list)
    indeg: Dict[str, int] = {i: 0 for i in ids}
    for tid in ids:
        for d in id_to_deps.get(tid) or []:
            if d in pending:
                rev[d].append(tid)
                indeg[tid] = indeg.get(tid, 0) + 1
    batches: List[List[str]] = []
    q = deque([i for i in ids if indeg[i] == 0])
    while q:
        layer = list(q)
        q.clear()
        batches.append(layer)
        for u in layer:
            for v in rev.get(u, []):
                indeg[v] -= 1
                if indeg[v] == 0:
                    q.append(v)
    if sum(len(b) for b in batches) != len(ids):
        raise ValueError("agent_task_dag: cycle or invalid dependency in task graph")
    return batches
