# -*- coding: utf-8 -*-
import asyncio
from unittest.mock import patch

from agents.macro_modify_prefetch import (
    parallel_macro_modify_params_llm,
    resolve_prefetch_modify_target,
    use_react_macro_modify_prefetch,
)
from agents.tool_run_context import get_tool_run_store


def test_use_react_macro_modify_prefetch_default_on(monkeypatch):
    monkeypatch.delenv("REACT_MACRO_MODIFY_PREFETCH", raising=False)
    assert use_react_macro_modify_prefetch() is True
    monkeypatch.setenv("REACT_MACRO_MODIFY_PREFETCH", "0")
    assert use_react_macro_modify_prefetch() is False


def test_first_plausible_id_from_list_when_first_id_invalid():
    from agents.macro_modify_prefetch import _first_plausible_id_from_grep_list

    gr = {
        "first_badcase_id": 9,
        "badcase_list": [{"id": 715068135836749824, "title": "登录"}],
    }
    assert _first_plausible_id_from_grep_list("badcase", gr) == 715068135836749824


def test_resolve_prefetch_ui_detail_over_grep_first():
    ctx = {
        "grep_result": {
            "first_badcase_id": 710034601191411712,
            "badcase_list": [{"id": 710034601191411712, "title": "进京证"}],
        }
    }
    ui = {
        "target": "badcase",
        "record_id": "715068135836749824",
        "view": "detail",
        "title": "问登录问题答的不好",
    }
    target, tid = resolve_prefetch_modify_target(
        result_ctx=ctx,
        grep_tool_params={"target": "badcase"},
        frozen_macro={"target_hint": "badcase"},
        ui_context=ui,
        user_input="问登录问题答的不好 答案修改为 新内容",
    )
    assert target == "badcase"
    assert tid == 715068135836749824


def test_parallel_macro_modify_params_llm_puts_row(monkeypatch):
    monkeypatch.setenv("REACT_MACRO_MODIFY_PREFETCH", "1")
    _bid = 715068135836749824
    result_ctx = {
        "grep_result": {
            "first_badcase_id": _bid,
            "badcase_list": [{"id": _bid, "title": "t"}],
        }
    }
    row = {"id": _bid, "title": "t", "answer": "old"}

    async def _llm():
        await asyncio.sleep(0.02)
        return {
            "target": "badcase",
            "target_id": _bid,
            "modifications": {"answer": "new"},
            "confirm": False,
        }

    def _fake_sync(store, *, target, target_id, project_id):
        store.put_row(target, target_id, project_id, row)
        return True

    with patch(
        "agents.macro_modify_prefetch._sync_prefetch_row_into_store",
        side_effect=_fake_sync,
    ):
        params = asyncio.run(
            parallel_macro_modify_params_llm(
                _llm,
                result_ctx=result_ctx,
                grep_tool_params={"target": "badcase"},
                frozen_macro={"target_hint": "badcase"},
                ui_context={
                    "target": "badcase",
                    "record_id": str(_bid),
                },
                user_input="改答案",
                project_id=1,
            )
        )

    assert params and params["modifications"]["answer"] == "new"
    st = get_tool_run_store(result_ctx)
    assert st.get_row("badcase", _bid, 1) == row


def test_parallel_skipped_when_prefetch_off(monkeypatch):
    monkeypatch.setenv("REACT_MACRO_MODIFY_PREFETCH", "0")
    called = []

    async def _llm():
        called.append("llm")
        return {"target": "badcase", "target_id": 1, "modifications": {}, "confirm": False}

    with patch("agents.macro_modify_prefetch._sync_prefetch_row_into_store") as m:
        asyncio.run(
            parallel_macro_modify_params_llm(
                _llm,
                result_ctx={},
                grep_tool_params={},
                frozen_macro={},
                ui_context=None,
                user_input="x",
                project_id=1,
            )
        )
        m.assert_not_called()
    assert called == ["llm"]
