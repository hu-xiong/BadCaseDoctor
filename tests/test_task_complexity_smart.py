# -*- coding: utf-8 -*-
from llm.task_complexity import assess_task_complexity, infer_task_complexity


def test_faq_is_simple():
    a = assess_task_complexity(channel="chat", user_input="What is BadCase?")
    assert a.complexity == "simple"
    assert a.prefer_cheap


def test_mutate_blocks_downgrade():
    a = assess_task_complexity(
        channel="react",
        user_input="modify the login bug status to resolved",
    )
    assert a.complexity in ("standard", "complex")
    assert a.block_downgrade
    assert a.score >= 50


def test_terminal_followup_raises():
    a = assess_task_complexity(
        channel="react",
        user_input="[Client terminal sub-agent results]\ncommand: ls\nexit_code: 0",
        has_client_terminal_results=True,
    )
    assert a.block_downgrade
    assert a.score > 40


def test_pending_diff_complex():
    a = assess_task_complexity(
        channel="react",
        user_input="confirm",
        has_pending_diff=True,
    )
    assert a.complexity == "complex"
    assert a.prefer_quality


def test_toolchain_keyword():
    a = assess_task_complexity(
        channel="react",
        user_input="run npm test in the terminal shell",
    )
    assert "toolchain" in ",".join(a.signals)
    assert a.block_downgrade


def test_cn_mutate_keyword():
    a = assess_task_complexity(
        channel="react",
        user_input="\u628a\u767b\u5f55\u5931\u8d25\u7684 bug \u6539\u6210\u5df2\u89e3\u51b3",
    )
    assert a.block_downgrade
    assert a.score >= 50


def test_legacy_toggle(monkeypatch):
    monkeypatch.setenv("AUTO_SMART", "0")
    c = infer_task_complexity(channel="chat", user_input="What is BadCase?")
    assert c == "simple"
