# -*- coding: utf-8 -*-
"""CDP 探测性测试：元素筛选与证据构造。"""
from agents.cdp.explore import (
    build_element_inventory,
    filter_explorable_nodes,
    filter_fillable_nodes,
    severe_explore_issues,
    _attach_explore_evidence,
)
from agents.cdp.evidence import CdpStepRecord


def test_filter_explorable_skips_disabled_and_destructive():
    nodes = [
        {"ref": "@e1", "role": "button", "name": "提交", "disabled": False},
        {"ref": "@e2", "role": "button", "name": "删除项目", "disabled": False},
        {"ref": "@e3", "role": "button", "name": "保存", "disabled": True},
        {"ref": "@e4", "role": "StaticText", "name": "标题", "disabled": False},
        {"ref": "@e5", "role": "link", "name": "详情", "disabled": False},
    ]
    out = filter_explorable_nodes(nodes)
    refs = [n["ref"] for n in out]
    assert "@e1" in refs
    assert "@e5" in refs
    assert "@e2" not in refs
    assert "@e3" not in refs
    assert "@e4" not in refs


def test_build_element_inventory():
    nodes = [
        {"ref": "@e1", "role": "tab", "name": "概览", "disabled": False},
        {"ref": "@e2", "role": "button", "name": "注销", "disabled": False},
    ]
    inv = build_element_inventory(nodes)
    assert len(inv) == 1
    assert inv[0]["ref"] == "@e1"
    assert inv[0]["role"] == "tab"


def test_filter_fillable_nodes():
    nodes = [
        {"ref": "@e1", "role": "textbox", "name": "标题", "disabled": False},
        {"ref": "@e2", "role": "button", "name": "保存", "disabled": False},
        {"ref": "@e3", "role": "searchbox", "name": "搜索", "disabled": True},
    ]
    out = filter_fillable_nodes(nodes)
    assert len(out) == 1
    assert out[0]["ref"] == "@e1"


def test_attach_explore_evidence_click_failed_only_logs_no_bug():
    records = [
        CdpStepRecord(1, "snapshot", True, "页面快照", url="http://x", title="T"),
        CdpStepRecord(
            2,
            "click",
            False,
            "点击 @e1 (option/全部类型) [Could not compute box model]",
            url="http://x",
            title="T",
            ref="@e1",
        ),
    ]
    obs = {
        "success": True,
        "session_id": "s1",
        "exploration_clicks": 8,
        "issues_found": 1,
    }
    issues = [{
        "type": "click_failed",
        "message": "点击 @e1 (option/全部类型) 失败：Could not compute box model",
        "url_before": "http://x",
        "ref": "@e1",
        "role": "option",
        "name": "全部类型",
        "severity": "low",
    }]
    out = _attach_explore_evidence(obs, records=records, issues=issues, user_query="探测首页")
    assert out.get("exploration_issues") == issues
    assert out.get("cdp_test_evidence") is None
    assert out.get("has_obvious_issues") is not True
    assert "交互问题" in out.get("summary", "")
    assert "exploration_issues_summary" in out


def test_attach_explore_evidence_severe_page_issue_triggers_bug():
    records = [CdpStepRecord(1, "snapshot", True, "页面快照", url="http://x", title="T")]
    obs = {"success": False, "session_id": "s1", "exploration_clicks": 3, "issues_found": 1}
    issues = [{
        "type": "error_text",
        "message": "页面含明显错误文案：500",
        "url_before": "http://x",
        "severity": "medium",
    }]
    out = _attach_explore_evidence(obs, records=records, issues=issues, user_query="探测首页")
    assert out.get("has_obvious_issues") is True
    assert out.get("cdp_test_evidence", {}).get("test_failed") is True
    assert "steps_to_reproduce" in out["cdp_test_evidence"]["suggested_create_fields"]


def test_severe_explore_issues():
    issues = [
        {"type": "click_failed", "severity": "low"},
        {"type": "error_text", "severity": "medium"},
    ]
    assert len(severe_explore_issues(issues)) == 1
    assert severe_explore_issues(issues)[0]["type"] == "error_text"


def test_issue_from_click_failure_includes_role_name():
    from agents.cdp.explore import _issue_from_click_failure

    issue = _issue_from_click_failure(
        ref="@e27",
        node={"role": "button", "name": "编辑"},
        click_res={"message": "Could not compute box model"},
        before_url="http://localhost/#/project-detail/2",
        before_title="迭代 1",
    )
    assert issue["role"] == "button"
    assert issue["name"] == "编辑"
    assert issue["severity"] == "low"
    assert "@e27 (button/编辑)" in issue["message"]
    assert "Could not compute box model" in issue["message"]
