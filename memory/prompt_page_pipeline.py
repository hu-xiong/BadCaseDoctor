# -*- coding: utf-8
"""页表管线：build → compress → assemble → trace；对接 ReAct / Agent 入口。"""
from __future__ import annotations

import os
import time
import threading
from typing import Any, Dict, List, Optional, Sequence

from memory.prefix_cache_client import merge_engine_stats_into, record_engine_prefix_cache
from memory.prompt_page_table import (
    PromptPageTableBuilder,
    PromptVPN,
    estimate_tokens,
    resolve_kv_observation,
    vpn_trace_payload,
)
from utils.token_meter import TokenMeter

__all__ = [
    "use_prompt_page_table",
    "use_canonical_assemble",
    "prepare_llm_messages",
    "preflight_agent_request",
    "PromptPageSessionState",
    "record_llm_timing",
    "record_engine_prefix_cache",
    "get_session_state",
    "LlmStreamTimer",
    "tools_version_from_names",
    "warm_prompt_page_subsystem",
]

_BUILDER = PromptPageTableBuilder()
_METER = TokenMeter()
_STATE_LOCK = threading.Lock()
_SESSION_STATES: Dict[str, "PromptPageSessionState"] = {}
_WARMED = False


def use_prompt_page_table() -> bool:
    return (os.getenv("PROMPT_PAGE_TABLE_ENABLED", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def use_canonical_assemble() -> bool:
    default = "1"
    try:
        from config import Config

        if hasattr(Config, "PROMPT_PAGE_CANONICAL_ASSEMBLE"):
            return bool(Config.PROMPT_PAGE_CANONICAL_ASSEMBLE)
    except Exception:
        pass
    return (os.getenv("PROMPT_PAGE_CANONICAL_ASSEMBLE", default) or default).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def tools_version_from_names(tool_names: Sequence[str]) -> str:
    from memory.canonical_messages import content_hash_text

    names = sorted({str(n).strip() for n in tool_names if str(n).strip()})
    return content_hash_text("|".join(names)) if names else "default"


class PromptPageSessionState:
    def __init__(self) -> None:
        self.last_vpn: Optional[PromptVPN] = None
        self.last_stats: Dict[str, Any] = {}
        self.pending_timing: Dict[str, Any] = {}
        self.request_started_at: Optional[float] = None

    def set_vpn(self, vpn: PromptVPN, stats: Dict[str, Any]) -> None:
        self.last_vpn = vpn
        self.last_stats = dict(stats)


def get_session_state(session_id: str) -> PromptPageSessionState:
    key = (session_id or "").strip() or "_anonymous"
    with _STATE_LOCK:
        st = _SESSION_STATES.get(key)
        if st is None:
            st = PromptPageSessionState()
            _SESSION_STATES[key] = st
        return st


def preflight_agent_request(
    *,
    session_id: str = "",
    user_id: str = "",
    estimated_tokens: int = 0,
) -> Dict[str, Any]:
    if not use_prompt_page_table():
        return {"allowed": True, "skipped": True}
    st = get_session_state(session_id)
    st.request_started_at = time.perf_counter()
    stats = _METER.preflight(
        estimate_tokens=max(0, estimated_tokens),
        session_id=session_id,
        user_id=user_id,
    )
    try:
        from utils.observability import append_agent_trace

        append_agent_trace(
            "token.budget",
            stats,
            react_request_id=session_id,
        )
    except Exception:
        pass
    return stats


def warm_prompt_page_subsystem() -> None:
    global _WARMED
    if _WARMED or not use_prompt_page_table():
        return
    try:
        from agents.locale_prompts import warm_static_prompt_prefix_cache

        warm_static_prompt_prefix_cache()
    except Exception as ex:
        if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
            print(f"[PROMPT-PAGES] warm skipped: {ex}", flush=True)
    _WARMED = True


class LlmStreamTimer:
    """FC / 流式调用 TTFT 与 early_execute 计时。"""

    def __init__(
        self,
        session_id: str,
        *,
        request_id: str = "",
        fc_stream: bool = True,
        round_idx: Optional[int] = None,
    ) -> None:
        self.session_id = session_id or ""
        self.request_id = request_id or session_id or ""
        self.fc_stream = fc_stream
        self.round_idx = round_idx
        self.t0 = time.perf_counter()
        self._first_token_recorded = False
        self._early_execute_recorded = False

    def on_fc_chunk(self, chunk: Any) -> None:
        if self._first_token_recorded:
            return
        if not _chunk_has_visible_delta(chunk):
            return
        self._first_token_recorded = True
        record_llm_timing(
            self.session_id,
            request_id=self.request_id,
            ttft_ms=(time.perf_counter() - self.t0) * 1000.0,
            fc_stream=self.fc_stream,
        )

    def on_early_execute(self) -> None:
        if self._early_execute_recorded:
            return
        self._early_execute_recorded = True
        record_llm_timing(
            self.session_id,
            request_id=self.request_id,
            early_execute_ms=(time.perf_counter() - self.t0) * 1000.0,
            fc_stream=self.fc_stream,
        )

    def on_tool_start(self) -> None:
        record_llm_timing(
            self.session_id,
            request_id=self.request_id,
            tool_start_ms=(time.perf_counter() - self.t0) * 1000.0,
            fc_stream=self.fc_stream,
        )

    def on_stream_usage(self, usage: Any, *, tag: str = "") -> None:
        fields = record_engine_prefix_cache(
            self.session_id,
            usage,
            request_id=self.request_id,
            tag=tag,
            round_idx=self.round_idx,
        )
        if fields:
            st = get_session_state(self.session_id)
            st.last_stats = merge_engine_stats_into(st.last_stats, fields)


def _chunk_has_visible_delta(chunk: Any) -> bool:
    if chunk is None:
        return False
    try:
        if isinstance(chunk, dict):
            ch0 = (chunk.get("choices") or [None])[0] or {}
            delta = ch0.get("delta") if isinstance(ch0, dict) else None
        else:
            if not chunk.choices:
                return False
            delta = chunk.choices[0].delta
    except Exception:
        return False
    if delta is None:
        return False
    c = getattr(delta, "content", None)
    if c is None and isinstance(delta, dict):
        c = delta.get("content")
    if isinstance(c, str) and c:
        return True
    tcs = getattr(delta, "tool_calls", None)
    if tcs is None and isinstance(delta, dict):
        tcs = delta.get("tool_calls")
    return bool(tcs)


def record_llm_timing(
    session_id: str,
    *,
    request_id: str = "",
    ttft_ms: Optional[float] = None,
    early_execute_ms: Optional[float] = None,
    tool_start_ms: Optional[float] = None,
    fc_stream: Optional[bool] = None,
    decode_tokens: Optional[int] = None,
) -> None:
    if not use_prompt_page_table():
        return
    st = get_session_state(session_id)
    timing = dict(st.pending_timing)
    if ttft_ms is not None:
        timing["ttft_ms"] = round(ttft_ms, 2)
    if early_execute_ms is not None:
        timing["early_execute_ms"] = round(early_execute_ms, 2)
    if tool_start_ms is not None:
        timing["tool_start_ms"] = round(tool_start_ms, 2)
    if fc_stream is not None:
        timing["fc_stream"] = fc_stream
    if decode_tokens is not None:
        timing["decode_tokens"] = decode_tokens
    st.pending_timing = timing
    if st.last_vpn is None:
        return
    try:
        from utils.observability import append_agent_trace

        payload = vpn_trace_payload(
            st.last_vpn,
            st.last_stats,
            ttft_ms=timing.get("ttft_ms"),
            early_execute_ms=timing.get("early_execute_ms"),
            tool_start_ms=timing.get("tool_start_ms"),
            fc_stream=timing.get("fc_stream"),
        )
        if decode_tokens is not None:
            payload["decode_tokens"] = decode_tokens
        append_agent_trace(
            "prompt.pages.timing",
            payload,
            react_request_id=request_id or session_id,
        )
    except Exception:
        pass


def prepare_llm_messages(
    messages: Sequence[Dict[str, Any]],
    *,
    session_id: str = "",
    request_id: str = "",
    template: str = "full",
    phase: str = "decide",
    round_idx: Optional[int] = None,
    locale: str = "",
    tools_version: str = "",
    project_id: str = "",
    fc_stream: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    msgs = [dict(m) for m in messages]
    if not use_prompt_page_table():
        return msgs

    warm_prompt_page_subsystem()
    st = get_session_state(session_id)
    prev = st.last_vpn
    if prev is not None:
        _BUILDER.release_vpn(prev)

    token_est = sum(estimate_tokens(str(m.get("content") or "")) for m in msgs)
    preflight = _METER.preflight(
        estimate_tokens=token_est,
        session_id=session_id,
    )
    if not preflight.get("allowed", True):
        return msgs

    vpn = _BUILDER.build_vpn(
        msgs,
        session_id=session_id,
        request_id=request_id,
        template=template,
        phase=phase,
        locale=locale,
        tools_version=tools_version or "default",
        project_id=project_id,
    )
    stats = resolve_kv_observation(vpn, prev)
    stats.update(preflight)
    compression_saved = getattr(_BUILDER, "_compression_saved", 0)

    try:
        from utils.observability import append_agent_trace

        payload = vpn_trace_payload(
            vpn,
            stats,
            compression_saved_tokens=compression_saved,
            fc_stream=fc_stream,
        )
        append_agent_trace(
            "prompt.pages",
            payload,
            react_request_id=request_id or session_id,
            round_idx=round_idx,
        )
    except Exception:
        pass

    st.set_vpn(vpn, stats)
    _METER.postflight(session_id=session_id, prefill_tokens=stats.get("prefill_tokens", 0))

    if use_canonical_assemble():
        return _BUILDER.reassemble_messages(vpn)
    return msgs
