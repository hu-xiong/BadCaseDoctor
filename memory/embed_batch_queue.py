from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class _PendingEmbed:
    doc_id: str
    search_text: str
    doc_body: Dict[str, Any]
    content_hash: str


class EmbedBatchQueue:
    """
    攒批 Embedding + ES bulk 写入。

    flush 触发条件（满足任一）：
    1. pending 数量 >= batch_size
    2. 本批首条入队后经过 flush_ms（默认 300ms）
    """

    def __init__(
        self,
        *,
        batch_size: int = 16,
        flush_ms: int = 300,
        embed_fn: Callable[[List[str]], List[List[float]]],
        upsert_fn: Callable[[List[Dict[str, Any]], int], int],
    ):
        self.batch_size = max(1, int(batch_size))
        self.flush_ms = max(50, int(flush_ms))
        self._embed_fn = embed_fn
        self._upsert_fn = upsert_fn
        self._lock = threading.Lock()
        self._pending: List[_PendingEmbed] = []
        self._batch_started_at: Optional[float] = None
        self._last_flush = time.time()
        self._flush_timer: Optional[threading.Timer] = None
        self._dims: Optional[int] = None

    def _cancel_flush_timer_unlocked(self) -> None:
        if self._flush_timer is not None:
            self._flush_timer.cancel()
            self._flush_timer = None

    def _arm_flush_timer_unlocked(self) -> None:
        if self._flush_timer is not None or not self._pending:
            return
        delay_s = self.flush_ms / 1000.0
        timer = threading.Timer(delay_s, self._on_flush_timer)
        timer.daemon = True
        self._flush_timer = timer
        timer.start()

    def _on_flush_timer(self) -> None:
        with self._lock:
            if not self._pending:
                self._flush_timer = None
                return
            started = self._batch_started_at
            if started is not None and (time.time() - started) * 1000.0 < self.flush_ms:
                # 定时器竞态：重新 arm
                self._flush_timer = None
                self._arm_flush_timer_unlocked()
                return
            self._flush_timer = None
        self.flush()

    def enqueue(self, item: _PendingEmbed) -> None:
        should_flush = False
        with self._lock:
            if not self._pending:
                self._batch_started_at = time.time()
            self._pending.append(item)
            if len(self._pending) >= self.batch_size:
                self._cancel_flush_timer_unlocked()
                should_flush = True
            elif len(self._pending) == 1:
                self._arm_flush_timer_unlocked()
        if should_flush:
            self.flush()

    def flush(self) -> int:
        with self._lock:
            if not self._pending:
                return 0
            self._cancel_flush_timer_unlocked()
            batch = self._pending[:]
            self._pending = []
            self._batch_started_at = None
            self._last_flush = time.time()
        texts = [b.search_text for b in batch]
        try:
            vectors = self._embed_fn(texts)
        except Exception as e:
            print(f"[GREP-INDEX] embed batch 失败: {e}", flush=True)
            return 0
        if not vectors:
            return 0
        if self._dims is None:
            self._dims = len(vectors[0])
        docs: List[Dict[str, Any]] = []
        for item, vec in zip(batch, vectors):
            if not vec:
                continue
            body = dict(item.doc_body)
            body["embedding"] = vec
            body["content_hash"] = item.content_hash
            body["_id"] = item.doc_id
            docs.append(body)
        try:
            return self._upsert_fn(docs, int(self._dims))
        except Exception as e:
            print(f"[GREP-INDEX] bulk upsert 失败: {e}", flush=True)
            return 0

    def maybe_flush_idle(self) -> int:
        """兼容旧调用：本批等待时间已达 flush_ms 则 flush。"""
        with self._lock:
            if not self._pending:
                return 0
            started = self._batch_started_at if self._batch_started_at is not None else self._last_flush
            if (time.time() - started) * 1000.0 < self.flush_ms:
                return 0
        return self.flush()
