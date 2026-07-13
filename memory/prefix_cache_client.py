# -*- coding: utf-8
"""推理侧 Automatic Prefix Caching 统计（DeepSeek/OpenAI 兼容 usage 字段）。"""
from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = [
    "parse_engine_prefix_cache",
    "record_engine_prefix_cache",
    "merge_engine_stats_into",
]


def parse_engine_prefix_cache(usage: Any) -> Optional[Dict[str, Any]]:
    if usage is None:
        return None
    hit = getattr(usage, "prompt_cache_hit_tokens", None)
    miss = getattr(usage, "prompt_cache_miss_tokens", None)
    pt = getattr(usage, "prompt_tokens", None)
    ct = getattr(usage, "completion_tokens", None)
    tt = getattr(usage, "total_tokens", None)
    if isinstance(usage, dict):
        hit = usage.get("prompt_cache_hit_tokens", hit)
        miss = usage.get("prompt_cache_miss_tokens", miss)
        pt = usage.get("prompt_tokens", pt)
        ct = usage.get("completion_tokens", ct)
        tt = usage.get("total_tokens", tt)
    if hit is None and miss is None:
        return None
    try:
        hi = int(hit or 0)
        mi = int(miss or 0)
    except Exception:
        return None
    denom = hi + mi
    hit_rate = (float(hi) / float(denom)) if denom > 0 else None
    return {
        "engine_prefix_cache_hit_tokens": hi,
        "engine_prefix_cache_miss_tokens": mi,
        "engine_prefix_cache_hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        "engine_prompt_tokens": int(pt) if pt is not None else denom,
        "engine_completion_tokens": int(ct) if ct is not None else None,
        "engine_total_tokens": int(tt) if tt is not None else None,
    }


def merge_engine_stats_into(stats: Dict[str, Any], engine: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(stats)
    out.update(engine)
    app_ratio = out.get("prefix_cache_hit_ratio") or out.get("cache_hit_ratio")
    eng_ratio = engine.get("engine_prefix_cache_hit_rate")
    if app_ratio is not None and eng_ratio is not None:
        out["cache_hit_delta"] = round(float(app_ratio) - float(eng_ratio), 4)
    return out


def record_engine_prefix_cache(
    session_id: str,
    usage: Any,
    *,
    request_id: str = "",
    tag: str = "",
    round_idx: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    fields = parse_engine_prefix_cache(usage)
    if not fields:
        return None
    if tag:
        fields["engine_tag"] = tag
    try:
        from memory.prompt_page_pipeline import get_session_state, use_prompt_page_table
        from utils.observability import append_agent_trace

        if not use_prompt_page_table():
            return fields
        st = get_session_state(session_id)
        st.last_stats = merge_engine_stats_into(st.last_stats, fields)
        append_agent_trace(
            "kv.engine_prefix_cache",
            fields,
            react_request_id=request_id or session_id,
            round_idx=round_idx,
        )
    except Exception:
        pass
    return fields
