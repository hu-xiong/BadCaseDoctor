"""
项目级 diff_review 变更推送：upsert/resolve 后广播，供 GET /diff-reviews/stream (SSE) 下发。

单进程内用内存 Queue；多 worker 时可经 Redis pub/sub 转发（与 REACT_SSE_BUFFER 类似）。
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from typing import Any, Dict, List, Optional

_lock = threading.Lock()
# project_id -> list[Queue]
_local_subs: Dict[int, List["queue.Queue[Any]"]] = {}

_REDIS_CHANNEL_PREFIX = "bcd:diff_review:"


def _use_redis() -> bool:
    return (os.getenv("DIFF_REVIEW_PUSH_REDIS", "1") or "1").strip().lower() in (
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


def _channel(project_id: int) -> str:
    return f"{_REDIS_CHANNEL_PREFIX}{int(project_id)}"


def subscribe(project_id: int, maxsize: int = 128) -> "queue.Queue[Any]":
    q: queue.Queue[Any] = queue.Queue(maxsize=maxsize)
    with _lock:
        _local_subs.setdefault(int(project_id), []).append(q)
    return q


def unsubscribe(project_id: int, q: "queue.Queue[Any]") -> None:
    with _lock:
        lst = _local_subs.get(int(project_id), [])
        if q in lst:
            lst.remove(q)


def _fanout_local(project_id: int, msg: Dict[str, Any]) -> None:
    with _lock:
        targets = list(_local_subs.get(int(project_id), []))
    dead: List["queue.Queue[Any]"] = []
    for q in targets:
        try:
            q.put_nowait(msg)
        except queue.Full:
            dead.append(q)
    if dead:
        with _lock:
            lst = _local_subs.get(int(project_id), [])
            for q in dead:
                if q in lst:
                    lst.remove(q)


def publish(project_id: int, event_type: str, payload: Any) -> None:
    """event_type: upsert | resolve | snapshot（snapshot 仅 SSE 连接时由 app 发送）"""
    msg = {
        "type": str(event_type or "").strip().lower(),
        "payload": payload,
        "ts": time.time(),
    }
    _fanout_local(project_id, msg)
    if not _use_redis():
        return
    r = _redis()
    if r is None:
        return
    try:
        r.publish(_channel(project_id), json.dumps(msg, ensure_ascii=False))
    except Exception:
        pass


def iter_redis_messages(project_id: int, stop_event: threading.Event):
    """阻塞迭代 Redis 消息；供 SSE 线程消费。"""
    r = _redis()
    if r is None:
        return
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    try:
        pubsub.subscribe(_channel(project_id))
        while not stop_event.is_set():
            raw = pubsub.get_message(timeout=1.0)
            if not raw or raw.get("type") != "message":
                continue
            data = raw.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            if isinstance(data, str):
                try:
                    yield json.loads(data)
                except Exception:
                    continue
    finally:
        try:
            pubsub.unsubscribe()
            pubsub.close()
        except Exception:
            pass
