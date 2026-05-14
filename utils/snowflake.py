# -*- coding: utf-8 -*-
"""
Bug / Card / BadCase / TestCase / Plan 共用的 64 位雪花 id（同一进程内全局递增、跨表不撞号）。

环境变量（可选）：
- SNOWFLAKE_WORKER_ID：0–31，默认 1
- SNOWFLAKE_DATACENTER_ID：0–31，默认 0

MySQL 须将对应列改为 BIGINT 并去掉自增后，再写入雪花值；启动迁移见 app.sync_database_schema 中
SNOWFLAKE_ENTITY_PK_MIGRATE=1。
"""
from __future__ import annotations

import os
import threading
import time
from typing import Optional

# 与常见实现一致：41 位时间戳 + 5 位机房 + 5 位机器 + 12 位序列
_TWEPOCH_MS = 1609459200000  # 2021-01-01 UTC


class SnowflakeGenerator:
    __slots__ = ("_lock", "_last_ts", "_seq", "worker_id", "datacenter_id")

    def __init__(self, worker_id: int = 1, datacenter_id: int = 0) -> None:
        if not (0 <= worker_id <= 31):
            raise ValueError("worker_id must be 0..31")
        if not (0 <= datacenter_id <= 31):
            raise ValueError("datacenter_id must be 0..31")
        self.worker_id = worker_id
        self.datacenter_id = datacenter_id
        self._lock = threading.Lock()
        self._last_ts = -1
        self._seq = 0

    def next_id(self) -> int:
        with self._lock:
            ts = int(time.time() * 1000)
            if ts < self._last_ts:
                raise RuntimeError("snowflake: system clock moved backwards")
            if ts == self._last_ts:
                self._seq = (self._seq + 1) & 0xFFF
                if self._seq == 0:
                    while (ts := int(time.time() * 1000)) <= self._last_ts:
                        time.sleep(0.001)
            else:
                self._seq = 0
            self._last_ts = ts
            return (
                ((ts - _TWEPOCH_MS) & ((1 << 41) - 1)) << 22
                | (self.datacenter_id & 0x1F) << 17
                | (self.worker_id & 0x1F) << 12
                | self._seq
            )


_entity_gen: Optional[SnowflakeGenerator] = None
_entity_gen_lock = threading.Lock()


def get_entity_snowflake_generator() -> SnowflakeGenerator:
    global _entity_gen
    with _entity_gen_lock:
        if _entity_gen is None:
            try:
                wid = int((os.getenv("SNOWFLAKE_WORKER_ID") or "1").strip())
            except ValueError:
                wid = 1
            try:
                did = int((os.getenv("SNOWFLAKE_DATACENTER_ID") or "0").strip())
            except ValueError:
                did = 0
            wid = max(0, min(31, wid))
            did = max(0, min(31, did))
            _entity_gen = SnowflakeGenerator(worker_id=wid, datacenter_id=did)
        return _entity_gen


def next_entity_snowflake_id() -> int:
    """Bug / BadCase / TestCase / Card 新建行主键用（四表同一序列空间）。"""
    return get_entity_snowflake_generator().next_id()
