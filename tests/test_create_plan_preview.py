"""create(target=plan, confirm=false)：应生成 diff 与必填日期。"""
from contextlib import contextmanager
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import asyncio

from agents.tools.create_tool import CreateTool


@contextmanager
def _fake_app_context():
    yield MagicMock()


def test_validate_plan_fields_fills_default_dates():
    tool = CreateTool(MagicMock())
    out = tool._validate_plan_fields({"name": "迭代 2"}, project_id=1)
    assert out["name"] == "迭代 2"
    assert isinstance(out["start_date"], date)
    assert isinstance(out["end_date"], date)
    assert out["end_date"] >= out["start_date"]


def test_validate_plan_fields_accepts_title_alias():
    tool = CreateTool(MagicMock())
    out = tool._validate_plan_fields({"title": "迭代计划2"}, project_id=1)
    assert out["name"] == "迭代计划2"


def test_create_plan_preview_generates_diff():
    asyncio.run(_run_create_plan_preview())


async def _run_create_plan_preview():
    tool = CreateTool(MagicMock())
    with (
        patch("app.app.app_context", _fake_app_context),
        patch.object(tool, "_check_similar_records", new_callable=AsyncMock, return_value=[]),
    ):
        result = await tool.execute(
            target="plan",
            fields={"name": "测试迭代计划"},
            project_id=1,
            confirm=False,
            ui_locale="zh-CN",
        )

    assert result.get("success") is True
    assert result.get("confirmation_required") is True
    assert result.get("target") == "plan"
    preview = result.get("preview") or {}
    assert preview.get("name") == "测试迭代计划"
    assert preview.get("start_date") is not None
    assert preview.get("end_date") is not None
    diff = result.get("diff") or []
    name_rows = [d for d in diff if isinstance(d, dict) and d.get("field") == "name"]
    assert name_rows, f"diff 应含 name: {diff!r}"
    lines = name_rows[0].get("lines") or []
    assert any(ln.get("type") == "add" and "测试迭代计划" in str(ln.get("content")) for ln in lines)
