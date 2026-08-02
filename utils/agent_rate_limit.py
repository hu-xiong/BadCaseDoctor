# -*- coding: utf-8 -*-
"""Agent 入口限流：按用户 RPM + 可选并发上限。"""

from __future__ import annotations

import os
import threading
import time
from typing import Optional, Tuple

_lock = threading.Lock()
_buckets: dict[str, dict] = {}
_inflight: dict[str, int] = {}


def _to_int(v: str, default: int) -> int:
    try:
        return int(v)
    except Exception:
        return default


def agent_rate_limit_enabled() -> bool:
    raw = (os.getenv("AGENT_RATE_LIMIT") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def check_agent_rate_limit(user_id: int | str, *, action: str = "react") -> Tuple[bool, Optional[str]]:
    """
    返回 (ok, error_code)。
    error_code: rate_limited | concurrency_limited
    环境变量：
      AGENT_RATE_RPM 默认 30
      AGENT_RATE_BURST 默认 10
      AGENT_MAX_CONCURRENT 默认 2（0=不限制并发）
    """
    if not agent_rate_limit_enabled():
        return True, None

    uid = str(user_id or "anon").strip() or "anon"
    rpm = _to_int(os.getenv("AGENT_RATE_RPM", "30"), 30)
    burst = _to_int(os.getenv("AGENT_RATE_BURST", "10"), 10)
    max_conc = _to_int(os.getenv("AGENT_MAX_CONCURRENT", "2"), 2)

    if rpm <= 0 and max_conc <= 0:
        return True, None

    now = time.time()
    key = f"{uid}:{action}"

    with _lock:
        if max_conc > 0:
            cur = int(_inflight.get(uid, 0))
            if cur >= max_conc:
                return False, "concurrency_limited"

        if rpm > 0:
            refill = rpm / 60.0
            st = _buckets.get(key)
            if not st:
                st = {"tokens": float(burst), "ts": now}
                _buckets[key] = st
            dt = max(0.0, now - float(st.get("ts") or now))
            st["tokens"] = min(float(burst), float(st.get("tokens") or 0.0) + dt * refill)
            st["ts"] = now
            if st["tokens"] < 1.0:
                return False, "rate_limited"
            st["tokens"] -= 1.0

        if max_conc > 0:
            _inflight[uid] = int(_inflight.get(uid, 0)) + 1

    return True, None


def release_agent_slot(user_id: int | str) -> None:
    """流式请求结束时释放并发槽。"""
    if not agent_rate_limit_enabled():
        return
    max_conc = _to_int(os.getenv("AGENT_MAX_CONCURRENT", "2"), 2)
    if max_conc <= 0:
        return
    uid = str(user_id or "anon").strip() or "anon"
    with _lock:
        cur = int(_inflight.get(uid, 0)) - 1
        if cur <= 0:
            _inflight.pop(uid, None)
        else:
            _inflight[uid] = cur
