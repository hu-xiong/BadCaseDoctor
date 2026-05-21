# -*- coding: utf-8 -*-
"""
统一模型路由：Auto / 显式 id、成本、升档、降档、vision 描述模型。
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import FrozenSet, Literal, Optional

from config import Config

from .failure_attribution import (
    EscalationState,
    FailureAttribution,
    get_downgrade_sticky,
    get_escalation_state,
    should_escalate,
)
from .model_registry import get_model, is_supported_model, supports_vision
from . import model_scheduler
from .task_complexity import TaskComplexity, infer_task_complexity

logger = logging.getLogger(__name__)

LOGICAL_ALIASES = frozenset(
    {
        "vision-best",
        "vision-cheapest",
        "cheapest",
        "fastest",
        "balanced",
    }
)

Channel = Literal["react", "chat", "summary", "vision_describe"]


@dataclass
class RouteContext:
    raw_model: Optional[str] = None
    has_images: bool = False
    channel: Channel = "react"
    image_intent: Optional[str] = None
    prefer_low_latency: bool = False
    project_id: Optional[int] = None
    session_id: Optional[str] = None
    user_input: str = ""
    has_pending_diff: bool = False
    user_id: Optional[str] = None


@dataclass
class RouteResult:
    business_model_id: str
    vision_model_id: Optional[str] = None
    route_reason: str = ""
    used_auto: bool = False
    escalated_from: Optional[str] = None
    task_complexity: Optional[str] = None
    route_resolve_ms: float = 0.0


def _env_bool(key: str, default: bool = False) -> bool:
    v = (os.getenv(key) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _normalize_raw_model(raw: Optional[str]) -> tuple[str, bool]:
    s = (raw or "").strip()
    if not s or s.lower() == "auto":
        return "auto", False
    if s.lower() in LOGICAL_ALIASES:
        return "auto", True
    return s, False


def _infer_prefer_low_latency(ctx: RouteContext, complexity: TaskComplexity) -> bool:
    if ctx.prefer_low_latency:
        return True
    if _env_bool("ROUTE_PREFER_LOW_LATENCY", False):
        return True
    ch = (ctx.channel or "").lower()
    if ch == "summary":
        return True
    if complexity == "simple":
        return True
    if (ctx.image_intent or "").lower() == "ocr":
        return True
    return False


def _map_cost_policy(
    ctx: RouteContext,
    complexity: TaskComplexity,
    prefer_low_latency: bool,
) -> str:
    ch = (ctx.channel or "react").lower()
    intent = (ctx.image_intent or "").lower()
    if complexity == "complex":
        return "quality_first"
    if complexity == "simple" or prefer_low_latency:
        return "cost_first"
    if ch == "summary":
        return "cost_first"
    if intent == "ocr" and prefer_low_latency:
        return "cost_first"
    if intent in ("react", "prototype") and ctx.has_images:
        return "quality_first"
    return "balanced"


def _vision_for_business(
    business_id: str,
    ctx: RouteContext,
    *,
    cost_policy: str,
    exclude: FrozenSet[str],
) -> Optional[str]:
    if supports_vision(business_id) and ctx.has_images:
        return None
    if not ctx.has_images:
        return None
    if cost_policy == "cost_first" and (ctx.image_intent or "").lower() == "ocr":
        return model_scheduler.pick_cheapest_vision(exclude_model_ids=exclude) or model_scheduler.pick_best_vision(
            exclude_model_ids=exclude
        )
    return model_scheduler.pick_best_vision(exclude_model_ids=exclude)


def _apply_escalation(
    ctx: RouteContext,
    state: EscalationState,
) -> RouteResult:
    failed = state.failed_model_id
    ex: FrozenSet[str] = frozenset({failed})
    if state.failed_vision_model_id:
        ex = frozenset({failed, state.failed_vision_model_id})

    if state.escalation_step >= _max_esc_steps():
        bid = model_scheduler.pick_best_vision(exclude_model_ids=ex) or model_scheduler.pick_balanced_enabled(
            exclude_model_ids=ex
        )
        reason = "escalation_cap_reached"
    else:
        vision_only = state.attribution == FailureAttribution.VISION_FAILURE.value and not ctx.has_images
        if ctx.has_images and state.attribution != FailureAttribution.VISION_FAILURE.value:
            bid = model_scheduler.pick_next_higher_priority(
                failed, vision_only=False, exclude_model_ids=ex
            )
        elif state.attribution == FailureAttribution.VISION_FAILURE.value:
            bid = model_scheduler.pick_next_higher_priority(
                state.failed_vision_model_id or failed,
                vision_only=True,
                exclude_model_ids=ex,
            )
        else:
            bid = model_scheduler.pick_next_higher_priority(failed, exclude_model_ids=ex)
        reason = "auto_escalate_after_inference_failure"

    if not bid:
        bid = model_scheduler.pick_balanced_enabled(exclude_model_ids=ex) or Config.DASHSCOPE_MODEL

    vid = _vision_for_business(bid, ctx, cost_policy="quality_first", exclude=ex)
    return RouteResult(
        business_model_id=bid,
        vision_model_id=vid,
        route_reason=reason,
        used_auto=True,
        escalated_from=failed,
        task_complexity="standard",
    )


def _max_esc_steps() -> int:
    try:
        return max(1, int(os.getenv("AUTO_ESCALATION_MAX_STEPS", "2")))
    except ValueError:
        return 2


def _apply_downgrade(ctx: RouteContext, complexity: TaskComplexity) -> RouteResult:
    forced = (os.getenv("SIMPLE_DOWNGRADE_MODEL") or "").strip()
    if forced and is_supported_model(forced):
        bid = forced
    else:
        bid = model_scheduler.pick_fastest_enabled() or model_scheduler.pick_cheapest_enabled()
    if not bid:
        bid = Config.DASHSCOPE_MODEL
    vid = _vision_for_business(bid, ctx, cost_policy="cost_first", exclude=frozenset())
    return RouteResult(
        business_model_id=bid,
        vision_model_id=vid,
        route_reason="auto_downgrade_simple_task",
        used_auto=True,
        task_complexity=complexity,
    )


def _resolve_auto(ctx: RouteContext, *, rejected_alias: bool) -> RouteResult:
    complexity = infer_task_complexity(
        channel=ctx.channel or "react",
        user_input=ctx.user_input,
        has_images=ctx.has_images,
        image_intent=ctx.image_intent,
        has_pending_diff=ctx.has_pending_diff,
    )
    prefer_ll = _infer_prefer_low_latency(ctx, complexity)

    uid = str(ctx.user_id or "")
    sid = (ctx.session_id or "").strip()
    if uid and sid:
        esc = get_escalation_state(uid, ctx.project_id, sid)
        if esc and should_escalate(FailureAttribution(esc.attribution)):
            return _apply_escalation(ctx, esc)

    sticky = None
    if uid and sid and _env_bool("AUTO_DOWNGRADE_SIMPLE_ENABLED", True):
        sticky = get_downgrade_sticky(uid, ctx.project_id, sid)

    if (
        _env_bool("AUTO_DOWNGRADE_SIMPLE_ENABLED", True)
        and complexity == "simple"
        and not (uid and sid and get_escalation_state(uid, ctx.project_id, sid))
    ):
        return _apply_downgrade(ctx, complexity)

    if sticky and complexity in ("simple", "standard") and len((ctx.user_input or "")) <= int(
        os.getenv("SIMPLE_TASK_MAX_CHARS", "400") or 400
    ):
        bid = sticky.model_id
        if is_supported_model(bid):
            vid = _vision_for_business(bid, ctx, cost_policy="cost_first", exclude=frozenset())
            return RouteResult(
                business_model_id=bid,
                vision_model_id=vid,
                route_reason="auto_downgrade_sticky",
                used_auto=True,
                task_complexity=complexity,
            )

    cost_policy = _map_cost_policy(ctx, complexity, prefer_ll)
    require_vision = None
    if ctx.channel == "vision_describe":
        vid = model_scheduler.pick_best_vision()
        return RouteResult(
            business_model_id=Config.DASHSCOPE_MODEL,
            vision_model_id=vid,
            route_reason="vision_describe_only",
            used_auto=True,
            task_complexity=complexity,
        )

    if ctx.has_images and (ctx.image_intent or "").lower() in ("react", "prototype"):
        require_vision = True

    bid = model_scheduler.choose_auto_model(
        has_images=ctx.has_images,
        channel=ctx.channel or "react",
        image_intent=ctx.image_intent,
        prefer_low_latency=prefer_ll,
        cost_policy=cost_policy,
        require_vision=require_vision,
    )
    if not bid:
        bid = Config.DASHSCOPE_MODEL

    reason = f"auto_{ctx.channel}_{cost_policy}"
    if rejected_alias:
        reason = "reject_logical_alias_" + reason

    vid = _vision_for_business(bid, ctx, cost_policy=cost_policy, exclude=frozenset())
    return RouteResult(
        business_model_id=bid,
        vision_model_id=vid,
        route_reason=reason,
        used_auto=True,
        task_complexity=complexity,
    )


def resolve_request_model(ctx: RouteContext) -> RouteResult:
    t0 = time.perf_counter()
    raw, rejected_alias = _normalize_raw_model(ctx.raw_model)

    if raw != "auto" and is_supported_model(raw):
        bid = raw
        ex = frozenset()
        vid = _vision_for_business(bid, ctx, cost_policy="quality_first", exclude=ex)
        ms = (time.perf_counter() - t0) * 1000.0
        _log_slow(ms, ctx)
        return RouteResult(
            business_model_id=bid,
            vision_model_id=vid,
            route_reason="user_explicit",
            used_auto=False,
            route_resolve_ms=ms,
        )

    result = _resolve_auto(ctx, rejected_alias=rejected_alias)
    ms = (time.perf_counter() - t0) * 1000.0
    result.route_resolve_ms = ms
    _log_slow(ms, ctx)
    return result


def _log_slow(ms: float, ctx: RouteContext) -> None:
    try:
        warn_ms = float(os.getenv("ROUTE_SCHEDULER_WARN_MS", "5"))
    except ValueError:
        warn_ms = 5.0
    if ms > warn_ms:
        logger.warning(
            "[MODEL_ROUTE] slow resolve ms=%.2f channel=%s session=%s",
            ms,
            ctx.channel,
            ctx.session_id,
        )


def resolve_model_name(
    raw_model: Optional[str],
    *,
    has_images: bool = False,
    channel: Channel = "react",
    image_intent: Optional[str] = None,
    project_id: Optional[int] = None,
    session_id: Optional[str] = None,
    user_input: str = "",
    has_pending_diff: bool = False,
    user_id: Optional[str] = None,
    pending_diff_context: Optional[list] = None,
) -> str:
    """供 agent/chat 使用的薄封装，返回 business model id。"""
    ctx = RouteContext(
        raw_model=raw_model,
        has_images=has_images,
        channel=channel,
        image_intent=image_intent,
        project_id=project_id,
        session_id=session_id,
        user_input=user_input,
        has_pending_diff=has_pending_diff or bool(pending_diff_context),
        user_id=user_id,
    )
    return resolve_request_model(ctx).business_model_id


def resolve_route(
    raw_model: Optional[str],
    *,
    has_images: bool = False,
    channel: Channel = "react",
    image_intent: Optional[str] = None,
    project_id: Optional[int] = None,
    session_id: Optional[str] = None,
    user_input: str = "",
    has_pending_diff: bool = False,
    user_id: Optional[str] = None,
) -> RouteResult:
    """完整路由结果（含 vision_model_id）。"""
    ctx = RouteContext(
        raw_model=raw_model,
        has_images=has_images,
        channel=channel,
        image_intent=image_intent,
        project_id=project_id,
        session_id=session_id,
        user_input=user_input,
        has_pending_diff=has_pending_diff,
        user_id=user_id,
    )
    return resolve_request_model(ctx)
