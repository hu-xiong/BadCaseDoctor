# -*- coding: utf-8 -*-
from agents.locale_prompts import (
    format_diagnostic_evidence_for_prompt,
    format_ui_context_for_prompt,
)


def test_diagnostic_only_without_record_id():
    text = format_ui_context_for_prompt(
        {
            "diagnostic_evidence": {
                "testcase_id": 42,
                "title": "登录失败",
                "execution_result": "FAIL",
                "steps": [
                    {"step": "打开登录页", "expected": "显示表单"},
                    {"step": "输入错误密码", "expected": "提示错误"},
                ],
            }
        }
    )
    assert "[诊断证据]" in text
    assert "testcase_id=42" in text
    assert "登录失败" in text
    assert "FAIL" in text
    assert "打开登录页" in text
    assert "[界面上下文]" not in text


def test_record_id_and_diagnostic_merged():
    text = format_ui_context_for_prompt(
        {
            "target": "bug",
            "record_id": "1234567890123456789",
            "title": "支付超时",
            "diagnostic_evidence": {"title": "用例A", "execution_result": "FAIL"},
        }
    )
    assert "[诊断证据]" in text
    assert "[界面上下文]" in text
    assert "1234567890123456789" in text
    assert "用例A" in text


def test_empty_ui_context():
    assert format_ui_context_for_prompt(None) == ""
    assert format_ui_context_for_prompt({}) == ""
    assert format_diagnostic_evidence_for_prompt(None) == ""


def test_diagnostic_english():
    text = format_diagnostic_evidence_for_prompt(
        {"title": "login fail", "execution_result": "FAIL"},
        locale="en",
    )
    assert "[Diagnostic evidence]" in text
    assert "login fail" in text
