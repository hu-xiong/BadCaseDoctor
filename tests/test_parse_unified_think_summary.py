# -*- coding: utf-8 -*-
from agents.prompts import parse_unified_response


def test_parse_unified_response_extracts_think_summary_at_end():
    text = (
        "<observation></observation>"
        "<thinking>详细正文<think_summary>准备 cdp 登录</think_summary></thinking>"
        "<decision><execute>true</execute><tool>cdp</tool><params>{}</params>"
        "<reason>打开页面</reason></decision>"
    )
    parsed = parse_unified_response(text)
    assert parsed.get("think_summary") == "准备 cdp 登录"
    assert "准备 cdp 登录" not in parsed.get("thinking", "")
    assert "详细正文" in parsed.get("thinking", "")
