# -*- coding: utf-8 -*-
"""
LangGraph checkpointer 工厂。

环境变量：
- LANGGRAPH_CHECKPOINTER=memory|sqlite|off（默认 memory；sqlite 需 AsyncSqliteSaver，失败回退 memory）
- LANGGRAPH_CHECKPOINT_SQLITE=路径（默认 data/langgraph_checkpoints.sqlite）

注意：同步 SqliteSaver 不能用于 graph.astream（会报 does not support async methods）。

与自研 langgraph_resume 并存：checkpointer 管图状态；resume 快照仍写 ReactAgentRun 供前端横幅。
"""
from __future__ import annotations

import os
import threading
import uuid
from typing import Any, Optional


_lock = threading.Lock()
_cached: Any = None
_cached_kind: str = ""
_sqlite_conn: Any = None


def checkpointer_backend() -> str:
    # 默认 memory：同步 SqliteSaver 无法用于 graph.astream（会报 does not support async methods）
    raw = (os.getenv("LANGGRAPH_CHECKPOINTER") or "memory").strip().lower()
    if raw in ("0", "false", "no", "off", "none", "disable", "disabled"):
        return "off"
    if raw in ("memory", "mem", "ram"):
        return "memory"
    if raw in ("sqlite", "sqlite3", "file", "1", "true", "on", "yes"):
        return "sqlite"
    return raw or "memory"


def checkpoint_sqlite_path() -> str:
    return (
        os.getenv("LANGGRAPH_CHECKPOINT_SQLITE")
        or os.getenv("LANGGRAPH_CHECKPOINTS_DB")
        or "data/langgraph_checkpoints.sqlite"
    ).strip()


def make_thread_id(
    *,
    chat_session_id: Any = None,
    agent_session_id: Optional[str] = None,
    resume_thread_id: Optional[str] = None,
) -> str:
    """续跑优先复用 resume 里的 thread_id。"""
    prev = (resume_thread_id or "").strip()
    if prev:
        return prev[:240]
    try:
        sid = int(chat_session_id) if chat_session_id is not None else 0
    except (TypeError, ValueError):
        sid = 0
    rid = (agent_session_id or "").strip() or uuid.uuid4().hex[:16]
    return f"lg:{sid}:{rid}"[:240]


def stream_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": (thread_id or "lg:0:anon")[:240]}}


def _build_sqlite_checkpointer() -> Any:
    """
    引擎走 graph.astream，必须用 AsyncSqliteSaver。
    同步 SqliteSaver 会在 astream 时直接失败，故不再使用。
    """
    global _sqlite_conn
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        import aiosqlite
    except ImportError as e:
        raise ImportError(
            f"async sqlite checkpointer unavailable ({e}); use LANGGRAPH_CHECKPOINTER=memory"
        ) from e

    path = checkpoint_sqlite_path()
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    # 在独立 event loop 里完成 connect/setup，供进程内长期持有
    import asyncio

    async def _open():
        conn = await aiosqlite.connect(path)
        # 多线程 Waitress 下跨 loop 访问需允许
        try:
            await conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        cp = AsyncSqliteSaver(conn)
        if hasattr(cp, "setup"):
            await cp.setup()
        return cp, conn

    try:
        try:
            asyncio.get_running_loop()
            # 已在异步上下文：不能 asyncio.run；回退 memory 由调用方处理
            raise RuntimeError("cannot open AsyncSqliteSaver inside running event loop")
        except RuntimeError as e:
            if "running event loop" in str(e):
                raise
        cp, conn = asyncio.run(_open())
    except RuntimeError:
        # 有 running loop 时退回新建 loop 线程不安全；改抛出让上层回退 memory
        raise

    _sqlite_conn = conn
    return cp


def _build_memory_checkpointer() -> Any:
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


def get_checkpointer(*, force_reload: bool = False) -> Any:
    """
    进程内单例。返回 checkpointer 或 None（off）。
    sqlite（同步）不兼容 astream 时自动回退 memory。
    """
    global _cached, _cached_kind
    with _lock:
        kind = checkpointer_backend()
        if not force_reload and _cached is not None:
            # 命中同后端；或 sqlite 已回退 memory 时保持单例（勿每次 new MemorySaver）
            if _cached_kind == kind:
                return _cached
            if kind == "off" and _cached_kind == "off":
                return None
            if kind == "sqlite" and _cached_kind == "memory":
                return _cached

        _cached = None
        _cached_kind = kind
        if kind == "off":
            print("[LANGGRAPH] checkpointer=off", flush=True)
            return None

        if kind == "memory":
            _cached = _build_memory_checkpointer()
            print("[LANGGRAPH] checkpointer=memory", flush=True)
            return _cached

        # sqlite：仅 AsyncSqliteSaver；失败则 memory（避免 astream 直接炸成空 Thought）
        try:
            _cached = _build_sqlite_checkpointer()
            _cached_kind = "sqlite"
            print(
                f"[LANGGRAPH] checkpointer=async-sqlite path={checkpoint_sqlite_path()}",
                flush=True,
            )
            return _cached
        except Exception as e:
            _cached = _build_memory_checkpointer()
            _cached_kind = "memory"
            print(
                f"[LANGGRAPH] checkpointer sqlite→memory ({e})",
                flush=True,
            )
            return _cached


def reset_checkpointer_for_tests() -> None:
    """单测用：释放单例。"""
    global _cached, _cached_kind, _sqlite_conn
    with _lock:
        try:
            if _sqlite_conn is not None:
                _sqlite_conn.close()
        except Exception:
            pass
        _sqlite_conn = None
        _cached = None
        _cached_kind = ""


def graph_has_checkpoint(graph: Any, thread_id: str) -> bool:
    """是否已有可续跑的 checkpoint。"""
    if graph is None or not thread_id:
        return False
    try:
        st = graph.get_state(stream_config(thread_id))
        vals = getattr(st, "values", None) or {}
        return bool(vals.get("messages"))
    except Exception:
        return False
