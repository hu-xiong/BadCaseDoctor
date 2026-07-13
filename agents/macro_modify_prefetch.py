# -*- coding: utf-8 -*-
"""grep→modify 宏步骤：macro_step_params_llm 与 ORM 读行预取并行。"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Callable, Coroutine, Dict, Optional, Tuple

from agents.tool_run_context import get_tool_run_store
from utils.entity_id import coerce_plausible_entity_pk

_GREP_LIST_KEYS = {
    "bug": "bug_list",
    "badcase": "badcase_list",
    "testcase": "testcase_list",
}


def _first_plausible_id_from_grep_list(target: str, grep_result: Dict[str, Any]) -> Optional[int]:
    """first_*_id 不可信时，从 grep 列表首条可取主键回退。"""
    lk = _GREP_LIST_KEYS.get((target or "").strip().lower())
    if not lk:
        return None
    for it in grep_result.get(lk) or []:
        if not isinstance(it, dict):
            continue
        rid = coerce_plausible_entity_pk(it.get("id"))
        if rid is not None:
            return rid
    return None


def use_react_macro_modify_prefetch() -> bool:
    """REACT_MACRO_MODIFY_PREFETCH=1（默认）：modify 抽参与读行预取并行。"""
    return (os.getenv("REACT_MACRO_MODIFY_PREFETCH", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def resolve_prefetch_modify_target(
    *,
    result_ctx: Dict[str, Any],
    grep_tool_params: Dict[str, Any],
    frozen_macro: Dict[str, Any],
    ui_context: Optional[Dict[str, Any]],
    user_input: str,
) -> Tuple[str, Optional[int]]:
    """不依赖 LLM modifications，仅用 grep/UI/话术解析 target_id。"""
    gr = result_ctx.get("grep_result") if isinstance(result_ctx.get("grep_result"), dict) else {}
    ui = ui_context if isinstance(ui_context, dict) else {}
    target = (
        str(
            grep_tool_params.get("target")
            or frozen_macro.get("target_hint")
            or ui.get("target")
            or "badcase"
        )
        .strip()
        .lower()
    )
    if target not in ("bug", "badcase", "testcase", "plan", "card"):
        target = "badcase"
    from agents.modify_target_resolve import resolve_modify_target_id

    tid = resolve_modify_target_id(
        target,
        grep_result=gr,
        result_context=result_ctx,
        ui_context=ui,
        user_input=user_input or "",
    )
    if tid is None:
        tid = _first_plausible_id_from_grep_list(target, gr)
    if tid is None:
        return target, None
    try:
        return target, int(tid)
    except (TypeError, ValueError):
        return target, None


def _sync_prefetch_row_into_store(
    store: Any,
    *,
    target: str,
    target_id: int,
    project_id: int,
) -> bool:
    from app import db
    from agents.tools.modify_tool import ModifyTool

    tool = ModifyTool(db)
    with tool._get_app_context():
        rows = tool._fetch_original_rows_batch_orm(target, [int(target_id)], int(project_id))
        row = rows.get(int(target_id))
        if not isinstance(row, dict) or not row:
            return False
        store.put_row(target, int(target_id), int(project_id), row)
        return True


async def parallel_macro_modify_params_llm(
    llm_resolve: Callable[[], Coroutine[Any, Any, Optional[Dict[str, Any]]]],
    *,
    result_ctx: Dict[str, Any],
    grep_tool_params: Dict[str, Any],
    frozen_macro: Dict[str, Any],
    ui_context: Optional[Dict[str, Any]],
    user_input: str,
    project_id: Optional[int],
) -> Optional[Dict[str, Any]]:
    """
    与 resolve_macro_step_params_llm 并行：预解析 target_id 并 ORM 读行写入 ToolRunStore。
    LLM 返回后 modify 命中 tool_run_ctx 行缓存可跳过读库。
    """
    if not use_react_macro_modify_prefetch():
        return await llm_resolve()

    target, target_id = resolve_prefetch_modify_target(
        result_ctx=result_ctx,
        grep_tool_params=grep_tool_params,
        frozen_macro=frozen_macro,
        ui_context=ui_context,
        user_input=user_input,
    )
    store = get_tool_run_store(result_ctx)

    async def _prefetch() -> bool:
        if target_id is None or project_id is None:
            return False
        if target in ("plan", "card"):
            return False
        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        try:
            ok = await loop.run_in_executor(
                None,
                lambda: _sync_prefetch_row_into_store(
                    store,
                    target=target,
                    target_id=target_id,
                    project_id=int(project_id),
                ),
            )
        except Exception as ex:
            if os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
                print(f"[REACT-MACRO] modify_prefetch failed: {ex}", flush=True)
            return False
        wall_ms = (time.perf_counter() - t0) * 1000
        if os.getenv("PERF_LOG", "1") == "1":
            print(
                f"[PERF][react] macro_modify_prefetch_ms={wall_ms:.1f} "
                f"ok={int(ok)} target={target!r} target_id={target_id}",
                flush=True,
            )
        if ok and os.getenv("REACT_MAIN_LOOP_LOG", "1") != "0":
            print(
                f"[REACT-MACRO] modify_row_prefetch ok target={target!r} "
                f"target_id={target_id} project_id={project_id}",
                flush=True,
            )
        return ok

    t_gather = time.perf_counter()
    params, _pref_ok = await asyncio.gather(llm_resolve(), _prefetch())
    if os.getenv("PERF_LOG", "1") == "1":
        print(
            f"[PERF][react] macro_modify_params_parallel_wall_ms="
            f"{(time.perf_counter() - t_gather) * 1000:.1f}",
            flush=True,
        )
    return params
