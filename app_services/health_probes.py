# -*- coding: utf-8 -*-
"""轻量健康探针载荷（无 Flask/DB 依赖，便于单测）。"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def liveness_payload() -> Dict[str, Any]:
    return {"status": "ok", "service": "badcase-doctor"}


def readiness_payload(
    db_ok: bool, redis_ok: Optional[bool]
) -> Tuple[Dict[str, Any], int]:
    payload = {
        "status": "ok" if db_ok else "unavailable",
        "db_ok": bool(db_ok),
        "redis_ok": redis_ok,
    }
    return payload, (200 if db_ok else 503)
