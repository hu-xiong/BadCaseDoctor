"""
同一次 ReAct 对话内工具共享的运行时存储（主要为 grep recent_created 等 meta）。

主线程/async：挂在 result_context["_tool_run_store"]（ToolRunStore 实例）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

STORE_KEY = "_tool_run_store"
SNAPSHOT_VERSION = 1


def row_cache_key(target: str, target_id: int, project_id: int) -> str:
    t = (str(target or "")).strip().lower()
    try:
        tid = int(target_id)
        pid = int(project_id)
    except (TypeError, ValueError):
        return f"{t}:0:0"
    return f"{t}:{pid}:{tid}"


def parse_row_cache_key(key: str) -> Optional[Tuple[str, int, int]]:
    parts = str(key or "").split(":")
    if len(parts) != 3:
        return None
    try:
        return parts[0], int(parts[2]), int(parts[1])
    except (TypeError, ValueError):
        return None


class ToolRunStore:
    """单轮 ReAct 对话内 grep/modify 等工具共享的可序列化存储。"""

    def __init__(self) -> None:
        self.rows: Dict[str, Dict[str, Any]] = {}
        self.cards: Dict[str, Dict[str, Any]] = {}
        self.meta: Dict[str, Any] = {}

    def get_row(
        self, target: str, target_id: int, project_id: int
    ) -> Optional[Dict[str, Any]]:
        row = self.rows.get(row_cache_key(target, target_id, project_id))
        return dict(row) if isinstance(row, dict) else None

    def put_row(
        self,
        target: str,
        target_id: int,
        project_id: int,
        row: Dict[str, Any],
    ) -> None:
        if not row or not isinstance(row, dict):
            return
        self.rows[row_cache_key(target, target_id, project_id)] = dict(row)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "v": SNAPSHOT_VERSION,
            "rows": dict(self.rows),
            "cards": dict(self.cards),
            "meta": dict(self.meta),
        }

    @classmethod
    def from_snapshot(cls, data: Optional[Dict[str, Any]]) -> "ToolRunStore":
        st = cls()
        if not isinstance(data, dict):
            return st
        rows = data.get("rows")
        if isinstance(rows, dict):
            for k, v in rows.items():
                if isinstance(v, dict):
                    st.rows[str(k)] = dict(v)
        cards = data.get("cards")
        if isinstance(cards, dict):
            for k, v in cards.items():
                if isinstance(v, dict):
                    st.cards[str(k)] = dict(v)
        meta = data.get("meta")
        if isinstance(meta, dict):
            st.meta.update(meta)
        return st

    def merge_patch(self, patch: Optional[Dict[str, Any]]) -> None:
        if not isinstance(patch, dict):
            return
        rows = patch.get("rows")
        if isinstance(rows, dict):
            for k, v in rows.items():
                if isinstance(v, dict):
                    self.rows[str(k)] = dict(v)
        cards = patch.get("cards")
        if isinstance(cards, dict):
            for k, v in cards.items():
                if isinstance(v, dict):
                    self.cards[str(k)] = dict(v)
        meta = patch.get("meta")
        if isinstance(meta, dict):
            try:
                from agents.tools.grep_recent_fallback import merge_recent_created_meta

                merge_recent_created_meta(self.meta, meta)
            except Exception:
                pass
            cleaned = {k: v for k, v in meta.items() if k != "recent_created_append"}
            self.meta.update(cleaned)


def get_tool_run_store(result_context: Optional[Dict[str, Any]]) -> ToolRunStore:
    rc = result_context if isinstance(result_context, dict) else {}
    raw = rc.get(STORE_KEY)
    if isinstance(raw, ToolRunStore):
        return raw
    if isinstance(raw, dict):
        st = ToolRunStore.from_snapshot(raw)
    else:
        st = ToolRunStore()
    rc[STORE_KEY] = st
    return st


def attach_tool_run_ctx_to_params(
    params: Dict[str, Any], result_context: Optional[Dict[str, Any]]
) -> None:
    """在线程池执行前：把主上下文快照放进 params。"""
    if not isinstance(params, dict):
        return
    st = get_tool_run_store(result_context)
    params["tool_run_ctx"] = st.snapshot()


def merge_tool_run_patch_from_observation(
    result_context: Optional[Dict[str, Any]],
    observation: Optional[Dict[str, Any]],
) -> None:
    """工具返回后：把 worker 写回的 patch 合并进主上下文。"""
    if not isinstance(observation, dict):
        return
    patch = observation.get("tool_run_ctx_patch")
    if not isinstance(patch, dict):
        return
    get_tool_run_store(result_context).merge_patch(patch)


