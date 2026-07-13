# -*- coding: utf-8 -*-
"""验证码登录闭环：识别、提取、跨轮 pending、自动续登判定。"""
import os
import tempfile

from agents.cdp.login_flow import (
    analyze_login_page,
    extract_verification_code_from_text,
    inject_cdp_login_resume_params,
    should_auto_resume_credentials_login,
    should_auto_resume_cdp_login,
    should_auto_resume_verification_login,
    update_login_pending_context,
)
from agents.cdp.credentials import extract_credentials_from_text
from agents.cdp.login_pending_store import (
    clear_login_pending,
    load_login_pending,
    save_login_pending,
)


def test_analyze_verification_login_page():
    nodes = [
        {"ref": "@e1", "role": "textbox", "name": "手机号"},
        {"ref": "@e2", "role": "textbox", "name": "验证码"},
        {"ref": "@e3", "role": "button", "name": "发送验证码"},
        {"ref": "@e4", "role": "button", "name": "登录"},
    ]
    a = analyze_login_page(nodes, "http://localhost:5173/#/login")
    assert a.is_login_page
    assert a.code_ref == "@e2"
    assert a.send_code_ref == "@e3"
    assert a.login_type in ("verification_code", "mixed")


def test_extract_verification_code():
    assert extract_verification_code_from_text("123456") == "123456"
    assert extract_verification_code_from_text("验证码：888888") == "888888"
    assert extract_verification_code_from_text("code: 654321") == "654321"
    assert extract_verification_code_from_text("你好") is None


def test_pending_store_roundtrip():
    clear_login_pending(chat_session_id=99, project_id=1)
    save_login_pending(
        chat_session_id=99,
        project_id=1,
        pending={"session_id": "sess_abc", "snapshot_id": "snap_x", "login_type": "verification_code"},
    )
    loaded = load_login_pending(chat_session_id=99, project_id=1)
    assert loaded["session_id"] == "sess_abc"
    assert loaded["login_type"] == "verification_code"
    clear_login_pending(chat_session_id=99, project_id=1)
    assert load_login_pending(chat_session_id=99, project_id=1) is None


def test_inject_resume_params_from_pending():
    ctx = {
        "cdp_login_pending": {"session_id": "sess_1", "snapshot_id": "snap_1"},
    }
    params: dict = {}
    inject_cdp_login_resume_params(
        params,
        result_context=ctx,
        user_input="123456",
        chat_session_id=1,
        project_id=1,
    )
    assert params["action"] == "login"
    assert params["session_id"] == "sess_1"
    assert params["verification_code"] == "123456"


def test_should_auto_resume():
    ctx = {"cdp_login_pending": {"session_id": "sess_1"}}
    assert should_auto_resume_verification_login(
        "123456",
        result_context=ctx,
        chat_session_id=1,
        project_id=1,
    )
    assert not should_auto_resume_verification_login(
        "继续测试页面",
        result_context=ctx,
        chat_session_id=1,
        project_id=1,
    )


def test_update_pending_context_clears_on_success():
    ctx: dict = {}
    update_login_pending_context(
        ctx,
        {"await_verification_code": True, "session_id": "s1", "snapshot_id": "snap1"},
        chat_session_id=7,
        project_id=2,
    )
    assert ctx["cdp_login_pending"]["session_id"] == "s1"
    assert load_login_pending(chat_session_id=7, project_id=2)["session_id"] == "s1"
    update_login_pending_context(
        ctx,
        {"login_success": True, "session_id": "s1"},
        chat_session_id=7,
        project_id=2,
    )
    assert "cdp_login_pending" not in ctx
    assert load_login_pending(chat_session_id=7, project_id=2) is None


def test_config_matches_url_localhost():
    from agents.cdp.credentials import config_matches_url, pick_login_config_for_url

    cfg = {
        "url": "http://localhost:5173/#/login",
        "username": "h2629258027@163.com",
        "password": "secret",
    }
    assert config_matches_url(cfg, "http://localhost:5173/#/login")
    assert config_matches_url(cfg, "http://localhost:5173/#/home")
    picked = pick_login_config_for_url([cfg], "http://localhost:5173/#/login")
    assert picked["username"] == "h2629258027@163.com"


def test_build_project_login_prompt_hint_offline():
    from agents.cdp.credentials import build_project_login_prompt_hint

    hint = build_project_login_prompt_hint(
        None,
        user_input="测 http://localhost:5173 登录",
    )
    assert hint is None
    c = extract_credentials_from_text("用户名 admin@test.com 密码 secret123")
    assert c["username"] == "admin@test.com"
    assert c["password"] == "secret123"
    c2 = extract_credentials_from_text("密码 onlypass")
    assert c2["password"] == "onlypass"
    assert extract_credentials_from_text("继续测试")["username"] is None


def test_should_auto_resume_credentials():
    ctx = {"cdp_login_pending": {"session_id": "sess_1", "await_type": "credentials"}}
    assert should_auto_resume_credentials_login(
        "用户名 u@x.com 密码 p123",
        result_context=ctx,
        chat_session_id=1,
        project_id=1,
    )
    assert should_auto_resume_cdp_login(
        "123456",
        result_context={"cdp_login_pending": {"session_id": "sess_1", "await_type": "verification_code"}},
        chat_session_id=1,
        project_id=1,
    )


def test_update_pending_credentials_context():
    ctx: dict = {}
    update_login_pending_context(
        ctx,
        {
            "await_user_credentials": True,
            "session_id": "s2",
            "snapshot_id": "snap2",
            "login_type": "password",
            "url": "http://localhost/#/login",
        },
        chat_session_id=8,
        project_id=3,
    )
    assert ctx["cdp_login_pending"]["await_type"] == "credentials"
    loaded = load_login_pending(chat_session_id=8, project_id=3)
    assert loaded["session_id"] == "s2"
    clear_login_pending(chat_session_id=8, project_id=3)
