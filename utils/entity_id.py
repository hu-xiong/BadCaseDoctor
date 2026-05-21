# -*- coding: utf-8 -*-
"""实体主键（雪花 ID）校验：拒绝截图/模型幻觉的小整数 id。"""
from __future__ import annotations

import os
from typing import Any, Optional


def _min_entity_pk() -> int:
    try:
        return int((os.getenv("SNOWFLAKE_MIN_ENTITY_ID") or "1000000000000").strip())
    except ValueError:
        return 1_000_000_000_000


def is_plausible_entity_pk(value: Any) -> bool:
    """True 表示像雪花主键（默认 ≥1e12），排除 9、11 等历史/幻觉小整数。"""
    if value is None or value == "":
        return False
    if isinstance(value, bool):
        return False
    try:
        n = int(value)
    except (TypeError, ValueError):
        s = str(value).strip()
        if not s.isdigit():
            return False
        n = int(s, 10)
    return n >= _min_entity_pk()


def coerce_plausible_entity_pk(value: Any) -> Optional[int]:
    if not is_plausible_entity_pk(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(str(value).strip(), 10)


def strip_invalid_entity_pk_fields(
    fields: dict,
    keys: tuple[str, ...],
) -> list[str]:
    """从 dict 中删除不可信的主键字段，返回被删除的键名列表。"""
    removed: list[str] = []
    if not isinstance(fields, dict):
        return removed
    for k in keys:
        if k not in fields:
            continue
        v = fields.get(k)
        if v in (None, "", 0, "0"):
            continue
        if not is_plausible_entity_pk(v):
            fields.pop(k, None)
            removed.append(k)
    return removed


_COPY_BUG_KEYS = ("copy_from_bug_id", "source_bug_id", "bug_id")
_COPY_BC_KEYS = ("copy_from_badcase_id", "source_badcase_id", "badcase_id")
_COPY_TC_KEYS = ("copy_from_testcase_id", "source_testcase_id", "testcase_id")
_COPY_CARD_KEYS = ("copy_from_card_id", "source_card_id", "card_id")


def _ui_record_for_target(ui_context: Optional[dict], target: str) -> Optional[int]:
    if not isinstance(ui_context, dict):
        return None
    ut = str(ui_context.get("target") or "").strip().lower()
    tt = (target or "").strip().lower()
    if ut != tt:
        return None
    return coerce_plausible_entity_pk(
        ui_context.get("record_id") or ui_context.get("recordId")
    )


def _first_id_from_grep(target: str, grep_result: dict, result_context: dict) -> Optional[int]:
    gr = grep_result if isinstance(grep_result, dict) else {}
    rc = result_context if isinstance(result_context, dict) else {}
    key_map = {
        "bug": "first_bug_id",
        "badcase": "first_badcase_id",
        "testcase": "first_testcase_id",
        "card": "first_card_id",
    }
    k = key_map.get((target or "").strip().lower())
    if not k:
        return None
    raw = gr.get(k) or rc.get(k)
    return coerce_plausible_entity_pk(raw)


def sanitize_tool_entity_ids(
    tool_name: str,
    tool_params: dict,
    *,
    grep_result: Optional[dict] = None,
    result_context: Optional[dict] = None,
    ui_context: Optional[dict] = None,
) -> None:
    """
    就地修正 copy/create/modify/delete 中的实体主键：
    剔除不可信小整数；copy/create 优先 ui_context，其次 grep first_*_id。
    """
    if not isinstance(tool_params, dict):
        return
    tn = (tool_name or "").strip().lower()
    gr = grep_result or {}
    rc = result_context or {}

    if tn == "copy":
        tt = str(tool_params.get("target") or "bug").strip().lower()
        keys = (
            _COPY_BUG_KEYS
            if tt == "bug"
            else _COPY_BC_KEYS
            if tt == "badcase"
            else _COPY_TC_KEYS
            if tt == "testcase"
            else _COPY_CARD_KEYS
            if tt == "card"
            else ("source_id",)
        )
        strip_invalid_entity_pk_fields(tool_params, ("source_id",) + keys)
        sid = coerce_plausible_entity_pk(tool_params.get("source_id"))
        if sid is None:
            sid = _ui_record_for_target(ui_context, tt)
        if sid is None:
            sid = _first_id_from_grep(tt, gr, rc)
        if sid is not None:
            tool_params["source_id"] = sid
        return

    if tn == "create":
        fields = tool_params.get("fields")
        if not isinstance(fields, dict):
            fields = {}
            tool_params["fields"] = fields
        strip_invalid_entity_pk_fields(
            fields,
            _COPY_BUG_KEYS + _COPY_BC_KEYS + _COPY_TC_KEYS + _COPY_CARD_KEYS,
        )
        tgt = str(tool_params.get("target") or "bug").strip().lower()
        if tgt == "bug":
            if not coerce_plausible_entity_pk(
                fields.get("copy_from_bug_id") or fields.get("source_bug_id")
            ):
                sid = _ui_record_for_target(ui_context, "bug") or _first_id_from_grep("bug", gr, rc)
                if sid is not None:
                    fields["copy_from_bug_id"] = sid
        elif tgt == "badcase":
            if not coerce_plausible_entity_pk(
                fields.get("copy_from_badcase_id") or fields.get("source_badcase_id")
            ):
                sid = _ui_record_for_target(ui_context, "badcase") or _first_id_from_grep(
                    "badcase", gr, rc
                )
                if sid is not None:
                    fields["copy_from_badcase_id"] = sid
        elif tgt == "testcase":
            if not coerce_plausible_entity_pk(
                fields.get("copy_from_testcase_id") or fields.get("source_testcase_id")
            ):
                sid = _ui_record_for_target(ui_context, "testcase") or _first_id_from_grep(
                    "testcase", gr, rc
                )
                if sid is not None:
                    fields["copy_from_testcase_id"] = sid
        elif tgt == "card":
            if not coerce_plausible_entity_pk(
                fields.get("copy_from_card_id") or fields.get("source_card_id")
            ):
                sid = _ui_record_for_target(ui_context, "card") or _first_id_from_grep("card", gr, rc)
                if sid is not None:
                    fields["copy_from_card_id"] = sid
        return

    if tn in ("modify", "delete"):
        tt = str(tool_params.get("target") or "bug").strip().lower()
        if tool_params.get("target_id") is not None:
            tid = coerce_plausible_entity_pk(tool_params.get("target_id"))
            if tid is None:
                tool_params.pop("target_id", None)
            else:
                tool_params["target_id"] = tid
        if not tool_params.get("target_id"):
            sid = _ui_record_for_target(ui_context, tt) or _first_id_from_grep(tt, gr, rc)
            if sid is not None:
                tool_params["target_id"] = sid
