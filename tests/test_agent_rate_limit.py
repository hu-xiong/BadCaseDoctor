# -*- coding: utf-8 -*-
import os
import time

from utils.agent_rate_limit import (
    check_agent_rate_limit,
    release_agent_slot,
    reset_agent_slots,
)


def test_rate_limit_and_release(monkeypatch):
    monkeypatch.setenv("AGENT_RATE_LIMIT", "1")
    monkeypatch.setenv("AGENT_RATE_RPM", "60")
    monkeypatch.setenv("AGENT_RATE_BURST", "2")
    monkeypatch.setenv("AGENT_MAX_CONCURRENT", "1")

    uid = "test-user-rl-1"
    reset_agent_slots(uid)

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


def test_concurrent_slot_ttl_auto_release(monkeypatch):
    monkeypatch.setenv("AGENT_RATE_LIMIT", "1")
    monkeypatch.setenv("AGENT_RATE_RPM", "0")
    monkeypatch.setenv("AGENT_MAX_CONCURRENT", "1")
    monkeypatch.setenv("AGENT_CONCURRENT_TTL_SEC", "30")

    uid = "test-user-rl-ttl"
    reset_agent_slots(uid)
    ok1, _ = check_agent_rate_limit(uid)
    assert ok1
    ok2, err2 = check_agent_rate_limit(uid)
    assert not ok2 and err2 == "concurrency_limited"

    # 把占用时间戳拨到超时之前
    import utils.agent_rate_limit as m

    with m._lock:
        m._inflight[uid] = [time.time() - 120]
    ok3, err3 = check_agent_rate_limit(uid)
    assert ok3 and err3 is None
    reset_agent_slots(uid)
