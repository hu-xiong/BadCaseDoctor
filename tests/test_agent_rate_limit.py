# -*- coding: utf-8 -*-
import os

from utils.agent_rate_limit import check_agent_rate_limit, release_agent_slot


def test_rate_limit_and_release(monkeypatch):
    monkeypatch.setenv("AGENT_RATE_LIMIT", "1")
    monkeypatch.setenv("AGENT_RATE_RPM", "60")
    monkeypatch.setenv("AGENT_RATE_BURST", "2")
    monkeypatch.setenv("AGENT_MAX_CONCURRENT", "1")

    uid = "test-user-rl-1"
    # 清干净该用户槽位
    for _ in range(3):
        release_agent_slot(uid)

    ok1, err1 = check_agent_rate_limit(uid)
    assert ok1 and err1 is None
    ok2, err2 = check_agent_rate_limit(uid)
    assert not ok2 and err2 == "concurrency_limited"
    release_agent_slot(uid)
    ok3, err3 = check_agent_rate_limit(uid)
    assert ok3 and err3 is None
    release_agent_slot(uid)


def test_rate_limit_can_disable(monkeypatch):
    monkeypatch.setenv("AGENT_RATE_LIMIT", "0")
    ok, err = check_agent_rate_limit("anyone")
    assert ok and err is None
