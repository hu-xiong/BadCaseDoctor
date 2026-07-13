# -*- coding: utf-8 -*-
"""D3：CDP 步骤累积与失败证据结构化。"""
from agents.cdp.evidence import (
    CdpEvidenceRecorder,
    build_actual_result,
    build_create_fields_from_failure,
    build_steps_to_reproduce,
    build_test_evidence_bundle,
    format_ref_label,
    summarize_step,
)
from agents.evidence_extractor import EvidenceExtractor


def _fail_assert_obs():
    return {
        "success": False,
        "assertion_failed": True,
        "tool": "cdp_assert",
        "session_id": "sess_x",
        "message": "断言超时未满足条件：url~/dashboard",
        "page": {"url": "http://localhost:5173/#/login", "title": "登录"},
    }


def test_summarize_and_accumulate_steps():
    rec = CdpEvidenceRecorder()
    rec.reset("s1")
    rec.record(
        "s1",
        "create",
        {"url": "http://localhost:5173/#/login"},
        {
            "success": True,
            "session_id": "s1",
            "action": "create",
            "page": {"url": "http://localhost:5173/#/login", "title": "登录"},
        },
    )
    rec.record(
        "s1",
        "login",
        {},
        {
            "success": True,
            "session_id": "s1",
            "login_success": True,
            "message": "登录完成",
            "page": {"url": "http://localhost:5173/#/project_detail/1", "title": "项目"},
        },
    )
    records = rec.get_records("s1")
    assert len(records) == 2
    text = build_steps_to_reproduce(records)
    assert "1." in text and "2." in text
    assert "登录" in text or "会话" in text


def test_assert_failure_bundle():
    rec = CdpEvidenceRecorder()
    rec.reset("s1")
    rec.record("s1", "create", {"url": "http://x/login"}, {"success": True, "session_id": "s1", "page": {"url": "http://x/login", "title": "登录"}})
    rec.record("s1", "navigate", {"url": "http://x/dash"}, {"success": True, "session_id": "s1", "page": {"url": "http://x/login", "title": "登录"}})
    fail = _fail_assert_obs()
    fail["session_id"] = "s1"
    bundle = build_test_evidence_bundle(
        "s1",
        rec.get_records("s1"),
        fail,
        assert_params={"url_matches": "/dashboard"},
        user_query="测登录后进项目详情",
    )
    assert bundle["test_failed"] is True
    assert bundle["steps_to_reproduce"]
    assert "dashboard" in bundle["actual_result"] or "断言" in bundle["actual_result"]
    fields = bundle["suggested_create_fields"]
    assert fields["title"].startswith("UI测试失败")
    assert fields["steps_to_reproduce"]
    assert fields["actual_result"]


def test_recorder_attach_on_assert_fail():
    rec = CdpEvidenceRecorder()
    rec.reset("s2")
    obs = _fail_assert_obs()
    obs["session_id"] = "s2"
    out = rec.attach_to_observation(obs, action="assert", params={"url_matches": "/dashboard"}, user_query="测首页")
    assert out.get("cdp_test_evidence")
    assert out["cdp_test_evidence"]["suggested_create_fields"]["expected_result"]


def test_evidence_extractor_cdp():
    obs = _fail_assert_obs()
    obs["cdp_test_evidence"] = build_test_evidence_bundle(
        "sess_x",
        [],
        obs,
        assert_params={"url_matches": "/dashboard"},
    )
    ev = EvidenceExtractor.extract_from_observation("cdp", {"action": "assert"}, obs)
    assert ev["status"] == "failure"
    assert any("复现步骤" in r or "实际结果" in r for r in ev["results"])


def test_mask_password_in_summary():
    s = summarize_step(
        "fill",
        {"ref": "@e2", "text": "secret123"},
        {"success": True, "ref": "@e2", "text_preview": "***"},
    )
    assert "secret123" not in s
    assert "***" in s or "@e2" in s


def test_format_ref_label_and_click_summary():
    assert format_ref_label("@e27", role="button", name="编辑") == "@e27 (button/编辑)"
    assert format_ref_label("@e3", role="tab") == "@e3 (tab)"
    s = summarize_step(
        "click",
        {"ref": "@e27", "role": "button", "name": "编辑"},
        {
            "success": False,
            "ref": "@e27",
            "role": "button",
            "name": "编辑",
            "message": "Could not compute box model",
        },
    )
    assert "@e27 (button/编辑)" in s
    assert "Could not compute box model" in s
