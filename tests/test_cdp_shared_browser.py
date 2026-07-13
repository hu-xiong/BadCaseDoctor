# -*- coding: utf-8 -*-
"""CDP 共享 Chromium 复用（按用户隔离）。"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.cdp.owner import resolve_cdp_owner_key


@pytest.fixture
def fresh_manager():
    from agents.cdp.session_manager import CdpSessionManager

    CdpSessionManager._instance = None
    mgr = CdpSessionManager.get()
    yield mgr
    CdpSessionManager._instance = None


def test_resolve_cdp_owner_key_prefers_user():
    assert resolve_cdp_owner_key(user_id=42, project_id=1) == "user:42"
    assert resolve_cdp_owner_key(userId="7", project_id=1) == "user:7"
    assert resolve_cdp_owner_key(userId="system_agent", project_id=3) == "project:3"
    assert resolve_cdp_owner_key(project_id=9) == "project:9"
    assert resolve_cdp_owner_key() == "anonymous"


def test_shared_browser_launched_once_per_owner(fresh_manager):
    mgr = fresh_manager
    launch_count = 0

    async def _run():
        nonlocal launch_count
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "about:blank"
        mock_page.title = AsyncMock(return_value="")
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.new_page = AsyncMock(return_value=mock_page)

        mock_pw = MagicMock()

        async def _launch(**kwargs):
            nonlocal launch_count
            launch_count += 1
            return mock_browser

        mock_pw.chromium.launch = _launch

        with patch.object(mgr, "_ensure_pw", AsyncMock(return_value=mock_pw)):
            r1 = await mgr.create(owner_key="user:1")
            r2 = await mgr.create(owner_key="user:1")
            r3 = await mgr.create(owner_key="user:2")
        assert r1["success"] and r2["success"] and r3["success"]
        assert launch_count == 2
        assert mock_browser.new_context.await_count == 3
        await mgr.close(r1["session_id"])
        await mgr.close(r2["session_id"])
        await mgr.close(r3["session_id"])
        mock_browser.close.assert_not_called()

    asyncio.run(_run())


def test_session_close_does_not_close_shared_browser(fresh_manager):
    mgr = fresh_manager

    async def _run():
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_browser.new_context = AsyncMock(return_value=mock_context)
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_pw = MagicMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch.object(mgr, "_ensure_pw", AsyncMock(return_value=mock_pw)):
            created = await mgr.create(owner_key="user:9")
        sid = created["session_id"]
        session = mgr.get_session(sid, owner_key="user:9")
        assert session is not None
        assert session.owns_browser is False
        assert session.owner_key == "user:9"
        await mgr.close(sid, owner_key="user:9")
        mock_context.close.assert_awaited()
        mock_browser.close.assert_not_called()

    asyncio.run(_run())


def test_new_context_retries_after_stale_browser(fresh_manager):
    mgr = fresh_manager

    async def _run():
        mock_browser = MagicMock()
        mock_browser.is_connected.return_value = True
        mock_context = AsyncMock()
        mock_page = AsyncMock()
        mock_page.url = "about:blank"
        mock_page.title = AsyncMock(return_value="")
        calls = {"n": 0}

        async def _new_context(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError(
                    "Browser.new_context: 'NoneType' object has no attribute 'send'"
                )
            return mock_context

        mock_browser.new_context = _new_context
        mock_context.new_page = AsyncMock(return_value=mock_page)
        mock_pw = MagicMock()
        mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

        with patch.object(mgr, "_ensure_pw", AsyncMock(return_value=mock_pw)):
            created = await mgr.create(owner_key="user:retry")
        assert created["success"], created
        assert calls["n"] == 2
        await mgr.close(created["session_id"])

    asyncio.run(_run())
