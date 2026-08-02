# -*- coding: utf-8 -*-
from utils.cors_config import (
    cors_origin_allowed,
    cors_origins_list,
    session_cookie_samesite,
)


def test_default_origins_include_vite(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOW_NULL_ORIGIN", raising=False)
    origins = cors_origins_list()
    assert "http://localhost:5173" in origins
    assert "null" not in origins


def test_null_origin_when_enabled(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.setenv("CORS_ALLOW_NULL_ORIGIN", "1")
    origins = cors_origins_list()
    assert "null" in origins
    assert cors_origin_allowed("null", origins)


def test_custom_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com, https://admin.example.com")
    monkeypatch.delenv("CORS_ALLOW_NULL_ORIGIN", raising=False)
    origins = cors_origins_list()
    assert origins == ["https://app.example.com", "https://admin.example.com"]
    assert cors_origin_allowed("https://app.example.com", origins)
    assert not cors_origin_allowed("http://evil.example", origins)


def test_session_samesite_none(monkeypatch):
    monkeypatch.setenv("SESSION_COOKIE_SAMESITE", "none")
    assert session_cookie_samesite() == "None"
    monkeypatch.setenv("SESSION_COOKIE_SAMESITE", "Strict")
    assert session_cookie_samesite() == "Strict"


def test_production_requires_cors_config(monkeypatch):
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOW_NULL_ORIGIN", raising=False)
    try:
        cors_origins_list()
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "CORS_ORIGINS" in str(e)
    monkeypatch.setenv("CORS_ALLOW_NULL_ORIGIN", "1")
    origins = cors_origins_list()
    assert "null" in origins
