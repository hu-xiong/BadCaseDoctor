# -*- coding: utf-8 -*-
import os

from agents.cdp.vision_understand import agent_loop_hint, cdp_screenshot_vision_enabled


def test_screenshot_vision_enabled_default(monkeypatch):
    monkeypatch.delenv("CDP_SCREENSHOT_VISION", raising=False)
    assert cdp_screenshot_vision_enabled() is True
    monkeypatch.setenv("CDP_SCREENSHOT_VISION", "0")
    assert cdp_screenshot_vision_enabled() is False


def test_agent_loop_hint_kinds():
    shot = agent_loop_hint(has_vision=True, kind="screenshot")
    assert "vision_description" in shot
    assert "未成功" not in shot

    fail = agent_loop_hint(has_vision=True, kind="failure")
    assert "未成功" in fail

    stale = agent_loop_hint(stale=True, has_vision=True)
    assert "focus_hints" in stale or "new_snapshot_id" in stale
