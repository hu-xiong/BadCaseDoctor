"""实体评论 Redis 队列：API 入队后立即返回，后台 worker 落库。"""
from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any, Callable, Optional

COMMENT_QUEUE_KEY = "bcd:comment:queue"
COMMENT_RESULT_PREFIX = "bcd:comment:result:"
RESULT_TTL_SEC = 86400


def new_client_temp_id() -> str:
    return f"pending-{uuid.uuid4().hex}"


def enqueue(redis_client, job: dict) -> bool:
    if redis_client is None:
        return False
    try:
        redis_client.lpush(COMMENT_QUEUE_KEY, json.dumps(job, ensure_ascii=False))
        return True
    except Exception as ex:
        print(f"[comment-queue] 入队失败: {ex}", flush=True)
        return False


def store_result(redis_client, client_temp_id: str, comment_dict: dict) -> None:
    if not redis_client or not client_temp_id:
        return
    try:
        key = f"{COMMENT_RESULT_PREFIX}{client_temp_id}"
        redis_client.setex(key, RESULT_TTL_SEC, json.dumps(comment_dict, ensure_ascii=False))
    except Exception as ex:
        print(f"[comment-queue] 写入结果缓存失败: {ex}", flush=True)


def fetch_result(redis_client, client_temp_id: str) -> Optional[dict]:
    if not redis_client or not client_temp_id:
        return None
    try:
        raw = redis_client.get(f"{COMMENT_RESULT_PREFIX}{client_temp_id}")
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception:
        return None


def start_worker(
    app,
    redis_client,
    persist_fn: Callable[[dict], dict],
    *,
    thread_name: str = "comment-queue",
) -> None:
    """启动后台 daemon，BRPOP 消费评论队列并落库。"""

    def _loop() -> None:
        while True:
            try:
                if redis_client is None:
                    time.sleep(5)
                    continue
                popped = redis_client.brpop(COMMENT_QUEUE_KEY, timeout=2)
                if not popped:
                    continue
                _, raw = popped
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                job = json.loads(raw)
                with app.app_context():
                    comment = persist_fn(job)
                    temp_id = job.get("client_temp_id")
                    if temp_id and comment:
                        store_result(redis_client, temp_id, comment)
            except Exception as ex:
                print(f"[comment-queue] worker 处理失败: {ex}", flush=True)

    threading.Thread(target=_loop, name=thread_name, daemon=True).start()
