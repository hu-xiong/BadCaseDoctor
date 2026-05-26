"""
ReAct SSE 断线续流：按 react_request_id 缓冲已下发的 wire 包（含 seq），供刷新后 GET /api/agent/react/buffer 拉取。

与 ChatSession.id 无关；session_id 在 agent_tasks 里指 react_request_id。
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from typing import Any, Dict, List, Optional

_MAX_EVENTS = max(100, int(os.getenv("REACT_SSE_BUFFER_MAX", "3000")))
_TTL_SEC = max(60, int(os.getenv("REACT_SSE_BUFFER_TTL", "7200")))

_lock = threading.Lock()
# request_id -> {"status": "running"|"completed"|"failed", "events": [(seq, dict)], "thread": Thread|None}
_memory: Dict[str, Dict[str, Any]] = {}

_append_q: "queue.Queue[Any]" = queue.Queue(maxsize=20000)
_append_worker_lock = threading.Lock()
_append_worker_started = False


def _append_async_enabled() -> bool:
    return (os.getenv("REACT_SSE_BUFFER_ASYNC", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _ensure_append_worker() -> None:
    global _append_worker_started
    with _append_worker_lock:
        if _append_worker_started:
            return

        def _worker() -> None:
            while True:
                item = _append_q.get()
                if item is None:
                    break
                rid, ev = item
                try:
                    _append_event_sync(rid, ev)
                except Exception:
                    pass

        t = threading.Thread(target=_worker, name="react-sse-buffer-append", daemon=True)
        t.start()
        _append_worker_started = True


def _use_redis() -> bool:
    return (os.getenv("REACT_SSE_BUFFER_REDIS", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _redis():
    try:
        from app import get_redis_client

        return get_redis_client()
    except Exception:
        return None


def _list_key(rid: str) -> str:
    return f"react:sse:buf:{rid[:64]}"


def _meta_key(rid: str) -> str:
    return f"react:sse:run:{rid[:64]}"


def register_run_thread(request_id: str, thread: threading.Thread) -> None:
    rid = (request_id or "").strip()
    if not rid:
        return
    with _lock:
        slot = _memory.setdefault(rid, {"status": "running", "events": [], "thread": None})
        slot["thread"] = thread
        slot["status"] = "running"


def mark_run_started(request_id: str) -> None:
    rid = (request_id or "").strip()
    if not rid:
        return
    try:
        from agents.react_run_store import supersede_interrupted_by_react_request

        supersede_interrupted_by_react_request(rid)
    except Exception:
        pass
    r = _redis()
    if r and _use_redis():
        try:
            r.set(_meta_key(rid), "running", ex=_TTL_SEC)
            r.delete(_list_key(rid))
        except Exception:
            pass
    with _lock:
        _memory.setdefault(rid, {"status": "running", "events": [], "thread": None})
        _memory[rid]["status"] = "running"
        _memory[rid]["events"] = []


def mark_run_finished(request_id: str, status: str = "completed") -> None:
    rid = (request_id or "").strip()
    if not rid:
        return
    st = status if status in ("completed", "failed", "cancelled") else "completed"
    r = _redis()
    if r and _use_redis():
        try:
            r.set(_meta_key(rid), st, ex=_TTL_SEC)
        except Exception:
            pass
    with _lock:
        slot = _memory.get(rid)
        if slot:
            slot["status"] = st
            slot["thread"] = None


def _append_event_sync(request_id: str, event: Dict[str, Any]) -> None:
    """同步写入续流缓冲（仅供后台 worker 或 REACT_SSE_BUFFER_ASYNC=0）。"""
    rid = (request_id or "").strip()
    if not rid or not isinstance(event, dict):
        return
    seq = event.get("seq")
    if seq is None:
        return
    line = json.dumps(event, ensure_ascii=False, default=str)
    r = _redis()
    if r and _use_redis():
        try:
            lk = _list_key(rid)
            pipe = r.pipeline()
            pipe.rpush(lk, line)
            pipe.ltrim(lk, -_MAX_EVENTS, -1)
            pipe.expire(lk, _TTL_SEC)
            pipe.execute()
        except Exception:
            pass
    with _lock:
        slot = _memory.setdefault(rid, {"status": "running", "events": [], "thread": None})
        evs: List = slot["events"]
        evs.append((int(seq), event))
        if len(evs) > _MAX_EVENTS:
            del evs[: len(evs) - _MAX_EVENTS]


def append_event(request_id: str, event: Dict[str, Any]) -> None:
    """
    缓冲单条已带 seq 的 SSE JSON 对象；跳过 heartbeat 以控体积。
    默认异步落库：不阻塞 SSE 热路径；断线续传仍从 buffer 拉 since_seq。
    """
    rid = (request_id or "").strip()
    if not rid or not isinstance(event, dict):
        return
    if event.get("type") == "heartbeat":
        return
    if event.get("seq") is None:
        return
    if _append_async_enabled():
        _ensure_append_worker()
        try:
            _append_q.put_nowait((rid, event))
        except queue.Full:
            _append_event_sync(rid, event)
        return
    _append_event_sync(rid, event)


def get_run_status(request_id: str) -> Dict[str, Any]:
    rid = (request_id or "").strip()
    if not rid:
        return {"status": "unknown", "running": False}
    status = "unknown"
    r = _redis()
    if r and _use_redis():
        try:
            raw = r.get(_meta_key(rid))
            if raw:
                status = str(raw)
        except Exception:
            pass
    thread_alive = False
    with _lock:
        slot = _memory.get(rid)
        if slot:
            if status == "unknown":
                status = slot.get("status") or "unknown"
            th = slot.get("thread")
            if th is not None and getattr(th, "is_alive", lambda: False)():
                thread_alive = True
    running = status == "running" or thread_alive
    return {
        "status": status,
        "running": running,
        "request_id": rid,
    }


def get_events_since(request_id: str, since_seq: int = 0) -> List[Dict[str, Any]]:
    rid = (request_id or "").strip()
    if not rid:
        return []
    try:
        since = int(since_seq)
    except (TypeError, ValueError):
        since = 0
    out: List[Dict[str, Any]] = []
    r = _redis()
    if r and _use_redis():
        try:
            lines = r.lrange(_list_key(rid), 0, -1) or []
            for line in lines:
                try:
                    ev = json.loads(line)
                    if isinstance(ev, dict) and int(ev.get("seq") or 0) > since:
                        out.append(ev)
                except Exception:
                    continue
            if out:
                return sorted(out, key=lambda x: int(x.get("seq") or 0))
        except Exception:
            pass
    with _lock:
        slot = _memory.get(rid)
        if slot:
            for seq, ev in slot.get("events") or []:
                if int(seq) > since:
                    out.append(ev)
    return sorted(out, key=lambda x: int(x.get("seq") or 0))
