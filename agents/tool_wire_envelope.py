# -*- coding: utf-8 -*-
"""
工具结果在 SSE「tool end」上的过渡契约（对照需求 §6.2）。

目标：在**不改变**现有扁平字段（results、batch_results、preview…）的前提下，
补齐 ``success`` / ``message``，便于前端与日志一致；后续可再迁到严格 ``{ success, data, navigation }``。
"""
from __future__ import annotations

from typing import Any, Dict


def _meaningful_error(err: Any) -> bool:
    if err is None or err == "":
        return False
    if isinstance(err, (list, dict, tuple, set)) and len(err) == 0:
        return False
    return True


_WIRE_DATA_EXCLUDE = frozenset({"success", "message", "error", "code", "data", "navigation"})


def augment_tool_body_wire_shape(body: Any) -> Any:
    """
    在兼容原有扁平字段的前提下，为 §6.2 目标态补上 ``data``（非元信息字段的聚合）。
    已有非空 ``data`` 对象时不修改。
    """
    b = ensure_tool_wire_envelope(body)
    if not isinstance(b, dict):
        return b
    existing = b.get("data")
    if isinstance(existing, dict) and len(existing) > 0:
        return b
    data = {k: v for k, v in b.items() if k not in _WIRE_DATA_EXCLUDE}
    out = dict(b)
    out["data"] = data
    return out


def ensure_tool_wire_envelope(body: Any) -> Any:
    """若为 dict，浅拷贝并补全 ``success``、``message``；其它类型原样返回。"""
    if body is None:
        return {"success": False, "message": "无返回数据"}
    if not isinstance(body, dict):
        return body
    out: Dict[str, Any] = dict(body)
    if "success" not in out:
        out["success"] = not _meaningful_error(out.get("error"))
    if out.get("message") in (None, "") and out.get("error") not in (None, ""):
        e = out["error"]
        out["message"] = e if isinstance(e, str) else str(e)
    elif out.get("message") in (None, "") and isinstance(out.get("summary"), str) and str(out["summary"]).strip():
        out["message"] = str(out["summary"]).strip()
    return out


def observation_body_is_tool_failure(body: Any) -> bool:
    """是否应按工具失败走 ``tool`` + ``op=error``（含仅有 ``error`` 而无 ``success`` 的旧包）。"""
    if not isinstance(body, dict):
        return False
    if body.get("success") is False:
        return True
    return _meaningful_error(body.get("error"))
