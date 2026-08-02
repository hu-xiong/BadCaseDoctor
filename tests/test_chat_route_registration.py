# -*- coding: utf-8 -*-
"""不启动完整 app：断言 /api/chat 走真实流式蓝图，而非 mock JSON。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_chat_blueprint_owns_api_chat_route():
    text = (ROOT / "routers" / "chat.py").read_text(encoding="utf-8")
    assert "@chat_bp.route('/api/chat'" in text
    assert "@login_required" in text
    assert "check_agent_rate_limit" in text
    assert "text/event-stream" in text
    assert "模拟回复" not in text


def test_app_py_has_no_api_chat_mock():
    text = (ROOT / "app.py").read_text(encoding="utf-8")
    # 旧 mock 已移除；允许注释说明
    assert "@app.route('/api/chat'" not in text
    assert "模拟回复" not in text


def test_pages_py_has_no_api_chat_mock():
    text = (ROOT / "routers" / "pages.py").read_text(encoding="utf-8")
    assert "@pages_bp.route('/api/chat'" not in text
