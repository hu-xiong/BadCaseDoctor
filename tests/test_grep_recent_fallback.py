import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.tools.grep_recent_fallback import (
    RECENT_CREATED_META_KEY,
    append_recent_created_entries,
    build_recent_created_patch,
    get_recent_created_entries,
    merge_recent_created_sql_fallback,
)
from agents.tool_run_context import ToolRunStore


def test_append_recent_created_dedup():
    base = append_recent_created_entries(
        None, entity_type="bug", record_id=1, project_id=10
    )
    base = append_recent_created_entries(
        base, entity_type="bug", record_id=1, project_id=10
    )
    assert len(base) == 1
    assert base[0]["record_id"] == 1


def test_tool_run_store_merge_recent_created():
    st = ToolRunStore()
    st.merge_patch(build_recent_created_patch("bug", 42, 7))
    entries = get_recent_created_entries(st.snapshot(), project_id=7, entity_type="bug")
    assert len(entries) == 1
    assert entries[0]["record_id"] == 42
    assert RECENT_CREATED_META_KEY in st.meta


def test_touch_work_items_after_write_patch():
    from unittest.mock import patch

    from agents.tools.grep_recent_fallback import touch_work_items_after_write

    with patch("memory.work_item_indexer.schedule_work_item_index") as sched:
        out = touch_work_items_after_write("bug", [1, 2], 7)
    assert out is not None
    assert len(out["tool_run_ctx_patch"]["meta"]["recent_created_append"]) == 2
    assert sched.call_count == 2


@pytest.mark.asyncio
async def test_sql_fallback_merges_missing_recent_bug():
    grep_tool = MagicMock()
    fake_row = {
        "id": 99,
        "title": "new bug",
        "_search_backend": "sql_fallback",
        "source": "sql_fallback",
    }
    grep_tool._get_bug_list_by_ids = AsyncMock(return_value=[fake_row])

    ctx = {
        "meta": {
            RECENT_CREATED_META_KEY: [
                {
                    "entity_type": "bug",
                    "record_id": 99,
                    "project_id": 1,
                    "ts": time.time(),
                }
            ]
        }
    }
    bugs, bcs, meta = await merge_recent_created_sql_fallback(
        grep_tool,
        project_id="1",
        bug_list=[],
        badcase_list=[],
        hybrid_bug=True,
        hybrid_bc=False,
        raw_target="bug",
        keywords=None,
        assignee="hx",
        status=None,
        plan_id=None,
        tool_run_ctx=ctx,
    )
    assert len(bugs) == 1
    assert bugs[0]["id"] == 99
    assert meta["sql_fallback"]["bug"] == [99]
    grep_tool._get_bug_list_by_ids.assert_awaited_once()
    assert grep_tool._get_bug_list_by_ids.await_args.kwargs.get("skip_keyword_filter") is True
