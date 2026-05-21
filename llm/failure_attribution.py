# -*- coding: utf-8 -*-
"""失败归因与 Auto 升档状态（内存 + 可选 Redis）。"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Dict, Optional


class FailureAttribution(str, Enum):
    INFERENCE_FAILURE = "inference_failure"
    VISION_FAILURE = "vision_failure"
    NETWORK_AUTH = "network_auth"
    TOOL_OR_LOGIC = "tool_or_logic"
    USER_INPUT = "user_input"
    UNKNOWN = "unknown"


@dataclass
class EscalationState:
    attribution: str
    failed_model_id: str
    failed_vision_model_id: Optional[str] = None
    escalation_step: int = 1
    ts: float = 0.0


@dataclass
class DowngradeStickyState:
    model_id: str
    success_count: int = 1
    ts: float = 0.0


_MEMORY_ESC: Dict[str, EscalationState] = {}
_MEMORY_STICKY: Dict[str, DowngradeStickyState] = {}


def _env_bool(key: str, default: bool) -> bool:
    v = (os.getenv(key) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _ttl_sec() -> int:
    try:
        return int(os.getenv("AUTO_ESCALATION_TTL_SEC", "1800"))
    except ValueError:
        return 1800


def _session_key(user_id: str, project_id: Optional[int], session_id: str) -> str:
    return f"{user_id}:{project_id or 0}:{session_id}"


def _redis_key_escalation(user_id: str, project_id: Optional[int], session_id: str) -> str:
    return f"auto_escalation:{user_id}:{project_id or 0}:{session_id}"


def _redis_key_sticky(user_id: str, project_id: Optional[int], session_id: str) -> str:
    return f"auto_downgrade_sticky:{user_id}:{project_id or 0}:{session_id}"


def _redis_get(key: str) -> Optional[str]:
    try:
        from app import get_redis_client

        rc = get_redis_client()
        if rc is None:
            return None
        raw = rc.get(key)
        if raw is None:
            return None
        if isinstance(raw, bytes):
            return raw.decode("utf-8", errors="replace")
        return str(raw)
    except Exception:
        return None


def _redis_set(key: str, value: str, ttl: int) -> None:
    try:
        from app import get_redis_client

        rc = get_redis_client()
        if rc is None:
            return
        rc.setex(key, ttl, value)
    except Exception:
        pass


def _redis_delete(key: str) -> None:
    try:
        from app import get_redis_client

        rc = get_redis_client()
        if rc is not None:
            rc.delete(key)
    except Exception:
        pass


def classify_failure(
    exc: Optional[BaseException] = None,
    *,
    message: str = "",
    http_status: Optional[int] = None,
    error_code: str = "",
    empty_output: bool = False,
    context_length_exceeded: bool = False,
) -> FailureAttribution:
    msg = (message or "").strip()
    if exc and not msg:
        msg = str(exc)
    low = msg.lower()
    code = (error_code or "").lower()

    if context_length_exceeded or "context length" in low or "maximum context" in low:
        return FailureAttribution.INFERENCE_FAILURE
    if empty_output:
        return FailureAttribution.INFERENCE_FAILURE
    if "invalid_model" in low or "model not found" in low or "model_not_found" in code:
        return FailureAttribution.INFERENCE_FAILURE
    if http_status and http_status >= 500:
        return FailureAttribution.INFERENCE_FAILURE
    if any(x in low for x in ("timeout", "timed out", "connection reset", "upstream")):
        return FailureAttribution.INFERENCE_FAILURE
    if "unauthorized" in low or "insufficient_quota" in low or http_status in (401, 403, 402):
        return FailureAttribution.NETWORK_AUTH
    if "vision" in low and ("describe" in low or "image" in low or "ocr" in low):
        return FailureAttribution.VISION_FAILURE

    return FailureAttribution.UNKNOWN


def should_escalate(attribution: FailureAttribution) -> bool:
    if not _env_bool("AUTO_ESCALATION_ENABLED", True):
        return False
    if attribution in (FailureAttribution.INFERENCE_FAILURE, FailureAttribution.VISION_FAILURE):
        return True
    if attribution == FailureAttribution.UNKNOWN:
        return _env_bool("AUTO_ESCALATE_ON_UNKNOWN", False)
    return False


def get_escalation_state(
    user_id: str,
    project_id: Optional[int],
    session_id: str,
) -> Optional[EscalationState]:
    if not session_id:
        return None
    rk = _redis_key_escalation(user_id, project_id, session_id)
    raw = _redis_get(rk)
    if raw:
        try:
            d = json.loads(raw)
            return EscalationState(**d)
        except Exception:
            pass
    sk = _session_key(user_id, project_id, session_id)
    st = _MEMORY_ESC.get(sk)
    if st and time.time() - st.ts > _ttl_sec():
        _MEMORY_ESC.pop(sk, None)
        return None
    return st


def record_escalation(
    user_id: str,
    project_id: Optional[int],
    session_id: str,
    *,
    attribution: FailureAttribution,
    failed_model_id: str,
    failed_vision_model_id: Optional[str] = None,
) -> None:
    if not session_id or not failed_model_id:
        return
    prev = get_escalation_state(user_id, project_id, session_id)
    step = 1
    if prev and prev.failed_model_id == failed_model_id:
        step = min(prev.escalation_step + 1, _max_escalation_steps())
    st = EscalationState(
        attribution=attribution.value,
        failed_model_id=failed_model_id,
        failed_vision_model_id=failed_vision_model_id,
        escalation_step=step,
        ts=time.time(),
    )
    sk = _session_key(user_id, project_id, session_id)
    _MEMORY_ESC[sk] = st
    rk = _redis_key_escalation(user_id, project_id, session_id)
    _redis_set(rk, json.dumps(asdict(st)), _ttl_sec())
    clear_downgrade_sticky(user_id, project_id, session_id)


def clear_escalation(user_id: str, project_id: Optional[int], session_id: str) -> None:
    if not session_id:
        return
    sk = _session_key(user_id, project_id, session_id)
    _MEMORY_ESC.pop(sk, None)
    _redis_delete(_redis_key_escalation(user_id, project_id, session_id))


def _max_escalation_steps() -> int:
    try:
        return max(1, int(os.getenv("AUTO_ESCALATION_MAX_STEPS", "2")))
    except ValueError:
        return 2


def get_downgrade_sticky(
    user_id: str,
    project_id: Optional[int],
    session_id: str,
) -> Optional[DowngradeStickyState]:
    if not session_id:
        return None
    rk = _redis_key_sticky(user_id, project_id, session_id)
    raw = _redis_get(rk)
    if raw:
        try:
            d = json.loads(raw)
            return DowngradeStickyState(**d)
        except Exception:
            pass
    sk = _session_key(user_id, project_id, session_id) + ":sticky"
    st = _MEMORY_STICKY.get(sk)
    if st and time.time() - st.ts > _ttl_sec():
        _MEMORY_STICKY.pop(sk, None)
        return None
    return st


def record_downgrade_success(
    user_id: str,
    project_id: Optional[int],
    session_id: str,
    model_id: str,
) -> None:
    if not _env_bool("AUTO_DOWNGRADE_SIMPLE_ENABLED", True) or not session_id:
        return
    need = 2
    try:
        need = int(os.getenv("AUTO_DOWNGRADE_STICKY_SUCCESS", "2"))
    except ValueError:
        pass
    sk = _session_key(user_id, project_id, session_id) + ":sticky"
    prev = _MEMORY_STICKY.get(sk)
    cnt = 1
    if prev and prev.model_id == model_id:
        cnt = prev.success_count + 1
    st = DowngradeStickyState(model_id=model_id, success_count=cnt, ts=time.time())
    _MEMORY_STICKY[sk] = st
    if cnt >= need:
        rk = _redis_key_sticky(user_id, project_id, session_id)
        _redis_set(rk, json.dumps(asdict(st)), _ttl_sec())


def clear_downgrade_sticky(user_id: str, project_id: Optional[int], session_id: str) -> None:
    if not session_id:
        return
    sk = _session_key(user_id, project_id, session_id) + ":sticky"
    _MEMORY_STICKY.pop(sk, None)
    _redis_delete(_redis_key_sticky(user_id, project_id, session_id))


def record_auto_route_outcome(
    *,
    user_id: str,
    project_id: Optional[int],
    session_id: str,
    used_auto: bool,
    business_model_id: str,
    vision_model_id: Optional[str],
    success: bool,
    exc: Optional[BaseException] = None,
    error_message: str = "",
    task_was_simple: bool = False,
) -> None:
    """请求结束时调用（不阻塞路由热路径）。"""
    if not used_auto or not session_id:
        return
    if success:
        clear_escalation(user_id, project_id, session_id)
        if task_was_simple and business_model_id:
            record_downgrade_success(user_id, project_id, session_id, business_model_id)
        return

    attr = classify_failure(exc, message=error_message)
    if not should_escalate(attr):
        return
    failed_v = vision_model_id if attr == FailureAttribution.VISION_FAILURE else None
    record_escalation(
        user_id,
        project_id,
        session_id,
        attribution=attr,
        failed_model_id=business_model_id,
        failed_vision_model_id=failed_v,
    )
