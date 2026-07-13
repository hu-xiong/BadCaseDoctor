"""沙箱预览：登录 bug 将 status 改为 closed，验证 diff 与 modifications。"""
from contextlib import contextmanager

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from agents.tools.modify_tool import ModifyTool

BUG_ID = 714020812427890688
USER_PHRASE = "登录bug，密码没有加密模式"


def _original_bug_row():
    return {
        "id": BUG_ID,
        "title": "登录bug, 密码没有加密模式",
        "status": "new",
        "priority": "medium",
        "severity": "major",
        "steps_to_reproduce": "<p>登录界面密码没有加密模式</p>",
        "expected_result": "",
        "actual_result": "",
        "project_id": 1,
        "plan_id": None,
        "card_id": None,
        "assignee_id": None,
    }


@contextmanager
def _fake_app_context():
    yield MagicMock()


def test_authoritative_status_snap_prefers_sql_over_stale_orm():
    tool = ModifyTool(MagicMock())
    flask_db = MagicMock()
    orm_enum = MagicMock()
    orm_enum.value = "reopened"
    with patch.object(tool, "_badcase_status_sql_fallback", return_value="closed"):
        snap = tool._authoritative_status_snap(flask_db, "badcase", 1, 2, orm_enum)
    assert snap == "closed"


def test_sandbox_preview_status_closed_for_login_bug():
    asyncio.run(_run_sandbox_preview_status_closed())


async def _run_sandbox_preview_status_closed():
    tool = ModifyTool(MagicMock())
    original = _original_bug_row()

    with (
        patch.object(tool, "_get_app_context", _fake_app_context),
        patch.object(
            tool,
            "_get_original_data",
            new_callable=AsyncMock,
            return_value=original,
        ),
        patch.object(tool, "_ensure_text2sql_if_needed_for_preview"),
        patch.object(
            tool,
            "_preview_in_sandbox",
            new_callable=AsyncMock,
            return_value={"sandbox_skipped": True},
        ),
        patch.object(tool, "_light_prep_skip_full_reconcile", return_value=True),
        patch.object(tool, "_modify_source_row_exists_cached", return_value=True),
    ):
        result = await tool.execute(
            target="bug",
            target_id=BUG_ID,
            project_id=1,
            confirm=False,
            natural_query=f"{USER_PHRASE} 状态改为已关闭",
            modifications={"status": "closed"},
            ui_locale="zh-CN",
        )

    assert result.get("success") is True
    assert result.get("confirmation_required") is True
    assert result.get("after", {}).get("status") == "closed"
    assert result.get("before", {}).get("status") == "new"
    diff = result.get("diff") or []
    status_rows = [d for d in diff if isinstance(d, dict) and d.get("field") == "status"]
    assert status_rows, f"diff 应含 status 行: {diff!r}"
    lines = status_rows[0].get("lines") or []
    line_text = {ln.get("type"): ln.get("content") for ln in lines if isinstance(ln, dict)}
    assert line_text.get("delete") == "new"
    assert line_text.get("add") == "closed"
    assert result.get("modifications", {}).get("status") == "closed"


if __name__ == "__main__":
    _run = asyncio.run(_run_sandbox_preview_status_closed())
    print("sandbox preview ok:", _run.get("summary"))
