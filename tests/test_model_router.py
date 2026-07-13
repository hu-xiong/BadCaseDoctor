# -*- coding: utf-8 -*-
"""模型统一路由单测。"""
from __future__ import annotations

import os

import pytest

from llm.failure_attribution import (
    EscalationState,
    clear_escalation,
    record_escalation,
)
from llm.model_registry import ModelPricing, ModelSpec
from llm.model_router import RouteContext, resolve_request_model, LOGICAL_ALIASES
from llm import model_registry, model_scheduler


def _fake_models():
    return [
        ModelSpec(
            id="qwen3.6-plus",
            label="Plus",
            provider="qwen",
            enabled=True,
            vision=True,
            priority=62,
            pricing=ModelPricing(1, 2),
        ),
        ModelSpec(
            id="qwen3.5-plus",
            label="Plus35",
            provider="qwen",
            enabled=True,
            vision=True,
            priority=55,
            pricing=ModelPricing(2, 4),
        ),
        ModelSpec(
            id="deepseek-v4-flash",
            label="DS Flash",
            provider="deepseek",
            enabled=True,
            vision=False,
            priority=58,
            pricing=ModelPricing(0.5, 0.5),
        ),
        ModelSpec(
            id="deepseek-v4-pro",
            label="DS",
            provider="deepseek",
            enabled=True,
            vision=False,
            priority=68,
            pricing=ModelPricing(3, 6),
        ),
    ]


@pytest.fixture(autouse=True)
def _patch_registry(monkeypatch):
    models = _fake_models()
    monkeypatch.setattr(model_registry, "_REGISTRY", models)
    monkeypatch.setattr(model_registry, "_BY_ID", {m.id: m for m in models})
    monkeypatch.setattr(
        model_registry,
        "list_models",
        lambda include_disabled=False: list(models) if include_disabled else [m for m in models if m.enabled],
    )
    model_scheduler.refresh_scheduler_cache()
    monkeypatch.setenv("VISION_MODEL", "qwen3.6-plus")
    monkeypatch.setenv("AUTO_DOWNGRADE_SIMPLE_ENABLED", "1")
    monkeypatch.setenv("AUTO_ESCALATION_ENABLED", "1")
    yield


def test_reject_logical_alias():
    ctx = RouteContext(raw_model="vision-best", channel="react")
    r = resolve_request_model(ctx)
    assert r.used_auto
    assert r.business_model_id != "vision-best"


def test_auto_downgrade_simple_chat():
    ctx = RouteContext(
        raw_model="auto",
        channel="chat",
        user_input="什么是 BadCase？",
        has_images=False,
    )
    r = resolve_request_model(ctx)
    assert r.business_model_id == "deepseek-v4-flash"
    assert "downgrade" in r.route_reason


def test_auto_escalate_after_failure():
    clear_escalation("u1", 1, "s1")
    record_escalation(
        "u1",
        1,
        "s1",
        attribution=__import__("llm.failure_attribution", fromlist=["FailureAttribution"]).FailureAttribution.INFERENCE_FAILURE,
        failed_model_id="deepseek-v4-flash",
    )
    ctx = RouteContext(
        raw_model="auto",
        channel="react",
        session_id="s1",
        user_id="u1",
        project_id=1,
        user_input="帮我看看",
    )
    r = resolve_request_model(ctx)
    assert r.business_model_id == "qwen3.6-plus"
    assert r.escalated_from == "deepseek-v4-flash"
    assert "escalate" in r.route_reason
    clear_escalation("u1", 1, "s1")


def test_pick_cheapest_not_deepseek():
    bid = model_scheduler.pick_cheapest_enabled()
    assert bid == "deepseek-v4-flash"


def test_pick_next_higher_priority_min_tier():
    nxt = model_scheduler.pick_next_higher_priority("deepseek-v4-flash")
    assert nxt == "qwen3.6-plus"


def test_complex_task_no_downgrade():
    ctx = RouteContext(
        raw_model="auto",
        channel="react",
        user_input="根据这张图创建 bug",
        has_images=True,
        image_intent="react",
    )
    r = resolve_request_model(ctx)
    assert r.business_model_id in ("qwen3.6-plus", "qwen3.5-plus")
    assert "downgrade_simple" not in r.route_reason


def test_non_vision_business_gets_vision_model_id():
    ctx = RouteContext(
        raw_model="deepseek-v4-pro",
        channel="react",
        has_images=True,
        user_input="看图",
    )
    r = resolve_request_model(ctx)
    assert r.business_model_id == "deepseek-v4-pro"
    assert r.vision_model_id == "qwen3.6-plus"
    assert r.route_reason == "user_explicit"


def test_route_resolve_fast():
    import time

    t0 = time.perf_counter()
    for _ in range(500):
        resolve_request_model(RouteContext(raw_model="auto", channel="chat", user_input="hi"))
    ms = (time.perf_counter() - t0) / 500 * 1000
    assert ms < 5.0
