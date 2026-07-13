# -*- coding: utf-8 -*-
"""D4：CDP 断言失败自动 create 预览决策。"""
import os

from agents.cdp.auto_create import (
    build_create_decision_from_cdp_failure,
    cdp_auto_create_enabled,
)


def _fail_obs():
    return {
        "success": False,
        "assertion_failed": True,
        "session_id": "s1",
        "cdp_test_evidence": {
            "test_failed": True,
            "suggested_create_target": "bug",
            "suggested_create_fields": {
                "title": "UI测试失败：登录页",
                "steps_to_reproduce": "1. [✓] 打开登录页",
                "actual_result": "断言失败",
                "expected_result": "URL 匹配 /dashboard",
            },
        },
    }


def test_build_create_decision():
    dec = build_create_decision_from_cdp_failure(
        _fail_obs(),
        project_id=1,
        plan_id=2,
    )
    assert dec is not None
    assert dec["tool"] == "create"
    params = dec["params"]
    assert params["target"] == "bug"
    assert params["confirm"] is False
    assert params["project_id"] == 1
    assert params["fields"]["plan_id"] == 2
    assert "steps_to_reproduce" in params["fields"]


def test_build_create_decision_for_explore_issues():
    obs = {
        "success": False,
        "has_obvious_issues": True,
        "session_id": "s1",
        "cdp_test_evidence": {
            "test_failed": True,
            "suggested_create_target": "bug",
            "suggested_create_fields": {
                "title": "UI测试失败：首页",
                "steps_to_reproduce": "1. [✗] 点击 @e1",
                "actual_result": "点击失败",
                "expected_result": "交互正常",
            },
        },
    }
    dec = build_create_decision_from_cdp_failure(obs, project_id=1, plan_id=3)
    assert dec is not None
    assert dec["params"]["fields"]["plan_id"] == 3


def test_skip_when_already_emitted():
    ctx = {"cdp_create_preview_emitted": True}
    assert build_create_decision_from_cdp_failure(_fail_obs(), project_id=1, result_context=ctx) is None


def test_build_interaction_issue_create_decision():
    from agents.cdp.auto_create import (
        build_interaction_issue_create_decision,
        interaction_explore_issues,
    )

    issues = [
        {"type": "click_failed", "ref": "@e1", "role": "button", "name": "编辑", "message": "点击失败"},
        {"type": "error_text", "message": "500"},
    ]
    assert len(interaction_explore_issues(issues)) == 1
    dec = build_interaction_issue_create_decision(
        issues[0],
        project_id=2,
        plan_id=5,
        index=0,
    )
    assert dec["params"]["target"] == "bug"
    assert dec["params"]["fields"]["plan_id"] == 5
    assert "编辑" in dec["params"]["fields"]["title"]


def test_interaction_issue_fields_with_screenshot_in_steps():
    from agents.cdp.auto_create import build_interaction_issue_create_fields

    fields = build_interaction_issue_create_fields(
        {
            "message": "点击失败",
            "screenshot_url": "/api/uploads/image/x.png",
            "name": "编辑",
            "role": "button",
        },
        index=1,
    )
    assert "/api/uploads/image/x.png" in fields["steps_to_reproduce"]


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("CDP_AUTO_CREATE_ON_FAIL", "0")
    assert cdp_auto_create_enabled() is False
    assert build_create_decision_from_cdp_failure(_fail_obs(), project_id=1) is None
