# -*- coding: utf-8 -*-
"""Midscene bridge 映射与配置探测。"""
from agents.cdp.midscene_bridge import (
    default_smoke_goal,
    map_midscene_result_to_explore_observation,
)


def test_map_midscene_success_report():
    raw = {
        "success": True,
        "engine": "midscene",
        "url": "http://localhost:5173/#/project-detail/3",
        "page_title": "Vite + Vue",
        "summary": "主路径可用",
        "tested_flows": ["打开迭代", "新建卡片"],
        "passed": ["侧栏可点", "新建入口可见"],
        "failed": [],
        "has_blocking_bug": False,
        "report_file": "D:/tmp/report.html",
    }
    out = map_midscene_result_to_explore_observation(raw, url=raw["url"])
    assert out["engine"] == "midscene"
    assert out["success"] is True
    assert out["tested_flows"] == ["打开迭代", "新建卡片"]
    assert out["midscene_report_file"].endswith("report.html")
    assert "主路径可用" in out["summary"]
    assert out.get("cdp_test_evidence") is None


def test_map_midscene_failed_builds_evidence():
    raw = {
        "success": False,
        "has_blocking_bug": True,
        "failed": [{"step": "保存卡片", "reason": "按钮无响应"}],
        "passed": [],
        "tested_flows": ["新建卡片"],
        "summary": "保存失败",
        "url": "http://x",
    }
    out = map_midscene_result_to_explore_observation(raw)
    assert out["success"] is False
    assert out["has_obvious_issues"] is True
    assert out["issues_found"] == 1
    assert out["exploration_issues"][0]["type"] == "midscene_failed"
    ev = out["cdp_test_evidence"]
    assert ev["test_failed"] is True
    assert "保存卡片" in ev["suggested_create_fields"]["title"]


def test_map_fallback_legacy_flag():
    out = map_midscene_result_to_explore_observation(
        {"success": False, "fallback_legacy": True, "error": "no api key"}
    )
    assert out["fallback_legacy"] is True
    assert "no api key" in out["error"]


def test_default_smoke_goal_includes_user_query():
    g = default_smoke_goal("测试下这个网站 http://localhost:5173")
    assert "正常人" in g or "界面" in g
    assert "localhost:5173" in g
