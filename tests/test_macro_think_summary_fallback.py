# -*- coding: utf-8 -*-
from agents.react_simplified import _unified_think_summary_fallback


def test_think_summary_fallback_skips_internal_macro_reason():
    out = _unified_think_summary_fallback(
        {"decision": {"reason": "frozen_macro_step_1", "tool": "modify"}}
    )
    assert out == "执行 modify"


def test_think_summary_fallback_keeps_human_reason():
    out = _unified_think_summary_fallback(
        {"decision": {"reason": "对 badcase 执行 modify 改状态", "tool": "modify"}}
    )
    assert "modify" in out
