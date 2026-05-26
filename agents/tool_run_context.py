"""
同一次 ReAct 对话内工具共享的运行时存储。

主线程/async：挂在 result_context["_tool_run_store"]（ToolRunStore 实例）。
线程池工具（modify）：经 params["tool_run_ctx"] 传入 snapshot，返回 tool_run_ctx_patch 回写。

ContextVar 仅适合单线程内微缓存（如 modify 单次 execute 内复用），不能替代本模块做跨线程共享。
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


def _row_id_from_grep_item(item: Dict[str, Any], target: str) -> Optional[int]:
    if not isinstance(item, dict):
        return None
    keys = ("id", f"{target}_id", "source_id", "pk")
    for k in keys:
        v = item.get(k)
        if v is None or v == "":
            continue
        try:
            i = int(v)
            if i > 0:
                return i
        except (TypeError, ValueError):
            continue
    return None


def seed_tool_run_store_from_grep_context(
    result_context: Dict[str, Any],
    *,
    project_id: Optional[int] = None,
) -> None:
    """
    grep 合并进 result_context 后，把导航列表里的行快照写入 ToolRunStore，
    供后续 modify 经 tool_run_ctx 带入线程池，减少重复 ORM。
    """
    if not isinstance(result_context, dict):
        return
    pid = project_id
    if pid is None:
        try:
            pid = int(result_context.get("project_id") or 0) or None
        except (TypeError, ValueError):
            pid = None
    if not pid:
        return
    st = get_tool_run_store(result_context)
    pairs: List[Tuple[str, str]] = [
        ("bug", "bug_list"),
        ("badcase", "badcase_list"),
        ("testcase", "testcase_list"),
    ]
    for target, list_key in pairs:
        for item in result_context.get(list_key) or []:
            if not isinstance(item, dict):
                continue
            rid = _row_id_from_grep_item(item, target)
            if rid:
                st.put_row(target, rid, int(pid), item)
    for item in result_context.get("card_list") or []:
        if not isinstance(item, dict):
            continue
        cid = item.get("id") or item.get("card_id")
        try:
            cid_i = int(cid) if cid is not None else 0
        except (TypeError, ValueError):
            cid_i = 0
        if cid_i > 0:
            st.cards[str(cid_i)] = dict(item)
