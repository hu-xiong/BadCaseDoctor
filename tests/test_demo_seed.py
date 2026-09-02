# -*- coding: utf-8 -*-
from app_services.demo_seed import seed_demo_enabled


def test_seed_demo_enabled(monkeypatch):
    monkeypatch.delenv("SEED_DEMO_USERS", raising=False)
    assert seed_demo_enabled() is False
    monkeypatch.setenv("SEED_DEMO_USERS", "1")
    assert seed_demo_enabled() is True
    monkeypatch.setenv("SEED_DEMO_USERS", "yes")
    assert seed_demo_enabled() is True
