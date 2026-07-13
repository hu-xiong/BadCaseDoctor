# -*- coding: utf-8 -*-
"""CDP ElementActor 点击/填写策略（role 优先、JS click 兜底）。"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from agents.cdp.element_actor import ElementActor, _click_name_variants
from agents.cdp.errors import CdpError
from agents.cdp.snapshot import SnapshotNode


def _make_actor():
    session = MagicMock()
    session.page = AsyncMock()
    session.session_id = "s1"
    session.last_snapshot = None
    session.touch = AsyncMock()
    session.page_info = AsyncMock(return_value={"url": "http://x", "title": "T"})
    session.cdp_session = AsyncMock()
    return ElementActor(session)


def test_click_name_variants_new_plan():
    variants = _click_name_variants("新建迭代")
    assert "新建迭代" in variants
    assert "新增迭代" in variants


def test_click_prefers_role_when_button_has_name():
    actor = _make_actor()
    node = SnapshotNode(
        ref="@e1",
        role="button",
        name="新建迭代",
        backend_node_id=99,
    )
    actor.resolve_ref = AsyncMock(return_value=node)
    actor._try_click_by_role_name = AsyncMock(return_value=True)
    actor._try_click_backend_node = AsyncMock(return_value=True)

    res = asyncio.run(actor.click(ref="@e1"))

    assert res["success"] is True
    actor._try_click_by_role_name.assert_awaited_once()
    actor._try_click_backend_node.assert_not_awaited()


def test_click_backend_js_when_box_model_fails():
    actor = _make_actor()
    node = SnapshotNode(
        ref="@e2",
        role="treeitem",
        name="",
        backend_node_id=100,
    )
    steps = []

    actor._try_click_backend_node = AsyncMock(return_value=False)
    actor._try_click_backend_js = AsyncMock(return_value=True)
    actor._try_click_by_role_name = AsyncMock(return_value=False)
    actor._try_click_css_heuristics = AsyncMock(return_value=False)

    asyncio.run(actor._perform_click(node, steps, 3000))

    actor._try_click_backend_js.assert_awaited_once()


def test_click_role_uses_nth_index():
    actor = _make_actor()
    page = actor.session.page
    loc = AsyncMock()
    loc.count = AsyncMock(return_value=3)
    loc.nth = MagicMock(return_value=loc)
    loc.click = AsyncMock()
    page.get_by_role = MagicMock(return_value=loc)

    node = SnapshotNode(ref="@e3", role="button", name="保存", role_name_index=2)
    steps = []
    ok = asyncio.run(actor._try_click_by_role_name(node, steps, 3000))

    assert ok is True
    loc.nth.assert_called_with(2)
    loc.click.assert_awaited_once()


def test_unnamed_button_tries_heuristics_before_fail():
    actor = _make_actor()
    node = SnapshotNode(ref="@e4", role="button", name="", backend_node_id=None)
    actor._try_click_by_role_name = AsyncMock(return_value=False)
    actor._try_click_css_heuristics = AsyncMock(return_value=False)

    steps = []
    with __import__("pytest").raises(CdpError):
        asyncio.run(actor._perform_click(node, steps, 3000))

    actor._try_click_css_heuristics.assert_awaited_once()
