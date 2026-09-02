# -*- coding: utf-8 -*-
from agents.cdp.vision_recover import _parse_verdict


def test_parse_verdict_json():
    out = _parse_verdict('{"verdict":"false_positive","reason":"控件已禁用","retry_hint":"none"}')
    assert out["verdict"] == "false_positive"
    assert "禁用" in out["reason"]


def test_parse_verdict_retry():
    out = _parse_verdict('{"verdict":"retry","reason":"遮挡导致点偏","retry_hint":"js_click"}')
    assert out["verdict"] == "retry"
    assert out["retry_hint"] == "js_click"


def test_parse_verdict_markdown_wrapped():
    out = _parse_verdict('```json\n{"verdict":"close_overlay","reason":"弹层挡着","retry_hint":"none"}\n```')
    assert out["verdict"] == "close_overlay"


def test_parse_verdict_fallback_cn():
    out = _parse_verdict("这不是缺陷，属于误报")
    assert out["verdict"] == "false_positive"
