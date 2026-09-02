# -*- coding: utf-8 -*-
"""服务端内部选模：成本、priority、flash 档；禁止 I/O。"""
from __future__ import annotations

import os
from typing import Callable, FrozenSet, List, Optional, Sequence, Tuple

from .model_registry import ModelSpec, get_model, list_models

# 启动/ reload 时刷新
_CACHED_ENABLED: Tuple[ModelSpec, ...] = ()
_CACHED_VISION_ENABLED: Tuple[ModelSpec, ...] = ()


def refresh_scheduler_cache() -> None:
    global _CACHED_ENABLED, _CACHED_VISION_ENABLED
    enabled = tuple(list_models(include_disabled=False))
    _CACHED_ENABLED = enabled
    _CACHED_VISION_ENABLED = tuple(m for m in enabled if m.vision)


refresh_scheduler_cache()


def cost_total(m: ModelSpec) -> float:
    p = m.pricing
    if p.input_per_million is None or p.output_per_million is None:
        return float("inf")
    try:
        return float(p.input_per_million) + float(p.output_per_million)
    except (TypeError, ValueError):
        return float("inf")


def _is_flash(m: ModelSpec) -> bool:
    mid = (m.id or "").lower()
    return "flash" in mid or "-flash" in mid


def _is_thinking(m: ModelSpec) -> bool:
    mid = (m.id or "").lower()
    return "thinking" in mid or m.id == "deepseek-r1"


def provider_credentials_ok(provider: str) -> bool:
    """选模时跳过未配置密钥的 provider，避免 Auto 选到 deepseek 却调不通。"""
    try:
        from config import Config
    except Exception:
        return True
    p = (provider or "").strip().lower()
    if p == "deepseek":
        return bool((getattr(Config, "DEEPSEEK_API_KEY", None) or "").strip())
    if p == "doubao":
        if not (getattr(Config, "DOUBAO_API_KEY", None) or "").strip():
            return False
        # 方舟常用接入点 ep-xxx；命名模型常 404，除非显式放行
        mid = (getattr(Config, "DOUBAO_MODEL", None) or "").strip()
        if mid.startswith("ep-"):
            return True
        allow = (os.getenv("DOUBAO_ALLOW_NAMED_MODEL") or "").strip().lower()
        return allow in ("1", "true", "yes", "on")
    if p == "zhipu":
        return bool((getattr(Config, "ZHIPU_API_KEY", None) or "").strip())
    if p in ("qwen", "dashscope"):
        return bool(
            (getattr(Config, "DASHSCOPE_API_KEY", None) or os.getenv("DASHSCOPE_API_KEY") or "").strip()
            or (getattr(Config, "QWEN_API_KEY", None) or os.getenv("QWEN_API_KEY") or "").strip()
        )
    if p == "qianfan":
        return bool(
            (getattr(Config, "QIANFAN_API_KEY", None) or "").strip()
            or (os.getenv("QIANFAN_ACCESS_KEY") or "").strip()
        )
    return True


def _filter_candidates(
    candidates: Sequence[ModelSpec],
    *,
    exclude_model_ids: Optional[FrozenSet[str]] = None,
    require_vision: Optional[bool] = None,
    max_cost: Optional[float] = None,
    flash_only: bool = False,
    skip_thinking: bool = False,
) -> List[ModelSpec]:
    ex = exclude_model_ids or frozenset()
    out: List[ModelSpec] = []
    for m in candidates:
        if m.id in ex:
            continue
        if not provider_credentials_ok(m.provider):
            continue
        if require_vision is True and not m.vision:
            continue
        if require_vision is False and m.vision:
            continue
        if flash_only and not _is_flash(m):
            continue
        if skip_thinking and _is_thinking(m):
            continue
        if max_cost is not None and cost_total(m) > max_cost:
            continue
        out.append(m)
    return out


def _sort_key_cost_first(m: ModelSpec) -> Tuple[float, int, str]:
    return (cost_total(m), -int(m.priority or 0), m.id)


def _sort_key_quality_first(m: ModelSpec) -> Tuple[int, float, str]:
    return (-int(m.priority or 0), cost_total(m), m.id)


def _sort_key_balanced(m: ModelSpec, cost_weight: float) -> Tuple[float, str]:
    score = int(m.priority or 0) - cost_weight * cost_total(m)
    return (-score, m.id)


def _sort_key_next_tier(m: ModelSpec) -> Tuple[int, float, str]:
    """升档：取 priority 高于失败档的最小 priority（下一档，非全局最强）。"""
    return (int(m.priority or 0), cost_total(m), m.id)


def _pick_first(
    candidates: Sequence[ModelSpec],
    key_fn: Callable[[ModelSpec], Tuple],
) -> Optional[str]:
    if not candidates:
        return None
    return min(candidates, key=key_fn).id


def pick_best_vision(*, exclude_model_ids: Optional[FrozenSet[str]] = None) -> Optional[str]:
    forced = (os.getenv("VISION_MODEL") or "").strip()
    if forced and get_model(forced) and get_model(forced).enabled:
        return forced
    cands = _filter_candidates(
        _CACHED_VISION_ENABLED or tuple(m for m in list_models() if m.vision),
        exclude_model_ids=exclude_model_ids,
    )
    return _pick_first(cands, _sort_key_quality_first)


def pick_cheapest_vision(*, exclude_model_ids: Optional[FrozenSet[str]] = None) -> Optional[str]:
    cands = _filter_candidates(
        _CACHED_VISION_ENABLED or tuple(m for m in list_models() if m.vision),
        exclude_model_ids=exclude_model_ids,
    )
    return _pick_first(cands, _sort_key_cost_first)


def pick_cheapest_enabled(
    *,
    exclude_model_ids: Optional[FrozenSet[str]] = None,
    require_vision: Optional[bool] = None,
) -> Optional[str]:
    forced = (os.getenv("SCHEDULER_CHEAPEST_MODEL") or "").strip()
    if forced and get_model(forced) and get_model(forced).enabled:
        return forced
    cands = _filter_candidates(
        _CACHED_ENABLED or tuple(list_models()),
        exclude_model_ids=exclude_model_ids,
        require_vision=require_vision,
        skip_thinking=True,
    )
    return _pick_first(cands, _sort_key_cost_first)


def pick_fastest_enabled(*, exclude_model_ids: Optional[FrozenSet[str]] = None) -> Optional[str]:
    cands = _filter_candidates(
        _CACHED_ENABLED or tuple(list_models()),
        exclude_model_ids=exclude_model_ids,
        flash_only=True,
        skip_thinking=True,
    )
    if not cands:
        return pick_cheapest_enabled(exclude_model_ids=exclude_model_ids)
    return _pick_first(cands, _sort_key_quality_first)


def pick_balanced_enabled(
    *,
    exclude_model_ids: Optional[FrozenSet[str]] = None,
    require_vision: Optional[bool] = None,
) -> Optional[str]:
    try:
        w = float(os.getenv("AUTO_COST_WEIGHT", "0.5"))
    except ValueError:
        w = 0.5
    cands = _filter_candidates(
        _CACHED_ENABLED or tuple(list_models()),
        exclude_model_ids=exclude_model_ids,
        require_vision=require_vision,
        skip_thinking=True,
    )
    if not cands:
        return None
    return min(cands, key=lambda m: _sort_key_balanced(m, w)).id


def pick_next_higher_priority(
    failed_id: str,
    *,
    vision_only: bool = False,
    exclude_model_ids: Optional[FrozenSet[str]] = None,
) -> Optional[str]:
    failed = get_model(failed_id)
    if not failed:
        return pick_best_vision(exclude_model_ids=exclude_model_ids) if vision_only else pick_balanced_enabled(
            exclude_model_ids=exclude_model_ids
        )
    fp = int(failed.priority or 0)
    pool = _CACHED_VISION_ENABLED if vision_only else _CACHED_ENABLED
    ex = set(exclude_model_ids or frozenset())
    ex.add(failed_id)
    higher = [m for m in pool if m.id not in ex and int(m.priority or 0) > fp]
    if higher:
        return min(higher, key=_sort_key_next_tier).id
    if vision_only:
        return pick_best_vision(exclude_model_ids=frozenset(ex))
    return pick_balanced_enabled(exclude_model_ids=frozenset(ex)) or pick_best_vision(
        exclude_model_ids=frozenset(ex)
    )


def choose_auto_model(
    *,
    has_images: bool,
    channel: str = "react",
    image_intent: Optional[str] = None,
    prefer_low_latency: bool = False,
    cost_policy: str = "balanced",
    require_vision: Optional[bool] = None,
    exclude_model_ids: Optional[FrozenSet[str]] = None,
) -> Optional[str]:
    """扩展 Auto 选模；供 model_router / 旧代码兼容。"""
    del channel, image_intent  # 矩阵层已处理 intent/channel
    max_cost = None
    raw_max = (os.getenv("AUTO_MAX_COST_PER_MILLION") or "").strip()
    if raw_max:
        try:
            max_cost = float(raw_max)
        except ValueError:
            pass

    if require_vision is None:
        require_vision = True if has_images else None

    ex = exclude_model_ids

    if cost_policy == "cost_first":
        if prefer_low_latency:
            return pick_fastest_enabled(exclude_model_ids=ex) or pick_cheapest_enabled(
                exclude_model_ids=ex, require_vision=require_vision if has_images else None
            )
        return pick_cheapest_enabled(
            exclude_model_ids=ex,
            require_vision=True if require_vision else (True if has_images else None),
        )

    if cost_policy == "quality_first":
        if has_images or require_vision:
            return pick_best_vision(exclude_model_ids=ex)
        return pick_balanced_enabled(exclude_model_ids=ex)

    # balanced
    if has_images:
        return pick_best_vision(exclude_model_ids=ex)
    if prefer_low_latency:
        return pick_fastest_enabled(exclude_model_ids=ex)
    cands = _filter_candidates(
        _CACHED_ENABLED,
        exclude_model_ids=ex,
        max_cost=max_cost,
        skip_thinking=True,
    )
    if not cands:
        return None
    try:
        w = float(os.getenv("AUTO_COST_WEIGHT", "0.5"))
    except ValueError:
        w = 0.5
    return min(cands, key=lambda m: _sort_key_balanced(m, w)).id
