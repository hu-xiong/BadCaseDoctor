# -*- coding: utf-8 -*-
"""
ReAct SSE 协议 v1：引擎事件 → 对外 JSON。

两层命名（勿混）：
- **引擎 event**：``step_data["event"]``，种类多（plan_init、executing、reasoning…），仅 Python 侧使用。
- **对外 type**：浏览器 JSON 顶层 ``type``，与文档 §6.1.9 对齐的少数几种（见 ``ClientWireType``）。

**谁负责转换**：``SimplifiedReActEngine.run_stream`` 在出口调用 ``engine_dict_to_wire_packets``；Agent 只透传，不在循环里再做映射。
实现方式：**枚举定「对外 kind」+ 字典把引擎 event 指到打包函数**；未登记的 event → ``stream`` + ``lane=engine`` 原样 ``data`` 兜底。

┌─────────────────┬──────────────────────┬────────────────────────────┐
│ 引擎 event      │ 对外 type            │ 说明                       │
├─────────────────┼──────────────────────┼────────────────────────────┤
│ plan            │ plan                 │ steps / overview_only 等   │
│ plan_init       │ plan                 │ + mode                     │
│ plan_update     │ plan                 │ + reason                   │
│ executing       │ tool                 │ payload.op = start         │
│ observation     │ tool                 │ op=end；body.success=false → op=error │
│ step_status     │ step                 │ s: 0–3                     │
│ finished        │ tail                 │                            │
│ done            │ bye                  │                            │
│ error           │ err                  │                            │
│ reasoning       │ stream               │ lane=think, delta=content │
│ todos_stream    │ stream               │ lane=plan, delta=正文片段 │
│ summary_stream  │ stream               │ lane=summary, delta       │
│ summary_stream_reset │ stream            │ lane=summary, reset=true  │
│ running_summary_stream │ stream         │ lane=running_summary, delta, version?, step_index? │
│ running_summary_stream_reset │ stream    │ lane=running_summary, reset=true │
│ running_summary_done │ stream            │ lane=running_summary, done=true, full_text │
│ tool_task_*     │ tool_task            │ lifecycle=created|running|done|failed；task_id 等 │
│ （其余）        │ stream               │ lane=engine, data=整包    │
│ （出口注入）   │ phase                │ ``run_stream`` 在 ``react_phase`` 变化时插入 │
└─────────────────┴──────────────────────┴────────────────────────────┘
"""
from __future__ import annotations

import os
from enum import Enum
from typing import Any, Callable, Dict, List

from .evidence_extractor import _json_safe_tool_params, deep_sse_json_safe
from .tool_wire_envelope import (
    augment_tool_body_wire_shape,
    ensure_tool_wire_envelope,
    observation_body_is_tool_failure,
)


class ClientWireType(str, Enum):
    """对前端 SSE 顶层 ``type``（文档 §6.1.9 极简协议）。"""

    STREAM = "stream"
    PLAN = "plan"
    STEP = "step"
    TOOL = "tool"
    TOOL_TASK = "tool_task"
    PHASE = "phase"
    TAIL = "tail"
    BYE = "bye"
    ERR = "err"


class ToolPayloadOp(str, Enum):
    """同一 type=tool 下的三态（非三种顶层 kind）。"""

    START = "start"
    END = "end"
    ERROR = "error"


_STEP_STATUS_TO_S: Dict[str, int] = {
    "pending": 0,
    "running": 1,
    "done": 2,
    "skipped": 3,
}

# ReAct 三阶段（与前端约定）：think | act | observe_decide
REACT_PHASE_THINK = "think"
REACT_PHASE_ACT = "act"
REACT_PHASE_OBSERVE_DECIDE = "observe_decide"

_REACT_PHASE_TO_N = {"think": 1, "act": 2, "observe_decide": 3}


def sse_v1_emit_phase_packets_enabled() -> bool:
    """是否在下发其它 v1 包前插入 ``type=phase`` 边沿（关：``SSE_V1_EMIT_PHASE=0``）。"""
    return os.getenv("SSE_V1_EMIT_PHASE", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def react_phase_wire_payload(phase_name: str) -> Dict[str, Any]:
    """§6.1.9 可选 ``phase`` 事件 payload：字符串名 + 整数阶段（与文档 Phase 1–3 对齐）。"""
    return {
        "name": phase_name,
        "n": int(_REACT_PHASE_TO_N.get(phase_name, 0)),
    }


def react_sse_meta(step_data: Dict[str, Any]) -> Dict[str, Any]:
    """由引擎 ``event`` 推断 ``react_phase`` / ``stream_channel``，合并进 step 后再打包。"""
    ev = step_data.get("event")
    if isinstance(ev, str) and ev.startswith("tool_task_"):
        return {"react_phase": REACT_PHASE_ACT}
    if not ev:
        return {}
    if ev == "reasoning_timing":
        seg = (step_data.get("segment") or "").lower()
        if seg == "think":
            return {"react_phase": REACT_PHASE_THINK}
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev == "reasoning":
        return {"react_phase": REACT_PHASE_THINK, "stream_channel": "reasoning"}
    if ev == "todos_stream":
        return {"react_phase": REACT_PHASE_THINK, "stream_channel": "content"}
    if ev in ("todos_partial", "todos"):
        return {"react_phase": REACT_PHASE_THINK}
    if ev in ("plan", "plan_update", "plan_init"):
        return {"react_phase": REACT_PHASE_THINK}
    if ev == "skill_matched":
        return {"react_phase": REACT_PHASE_THINK}
    if ev in ("immutable_field_rejection", "intent_clarification"):
        return {"react_phase": REACT_PHASE_THINK}
    if ev == "agent_thought":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE, "stream_channel": "content"}
    if ev == "agent_thought_done":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev == "reasoning_step":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE, "stream_channel": "reasoning"}
    if ev == "thought_content_step":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE, "stream_channel": "content"}
    if ev == "react_ui_stream":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE, "stream_channel": "content"}
    if ev == "llm_text_stream":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE, "stream_channel": "content"}
    if ev == "executing":
        return {"react_phase": REACT_PHASE_ACT}
    if ev == "batch_preview_row":
        return {"react_phase": REACT_PHASE_ACT}
    if ev == "observation":
        return {"react_phase": REACT_PHASE_ACT}
    if ev in ("exploring", "retry"):
        return {"react_phase": REACT_PHASE_ACT}
    if ev in ("todo_start", "todo_end"):
        return {"react_phase": REACT_PHASE_ACT}
    if ev == "step_status":
        return {"react_phase": REACT_PHASE_ACT}
    if ev == "skip":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev in ("finding", "evidence"):
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev == "summary_stream":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE, "stream_channel": "content"}
    if ev == "summary_stream_reset":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev in ("running_summary_stream", "running_summary_stream_reset", "running_summary_done"):
        return {
            "react_phase": REACT_PHASE_OBSERVE_DECIDE,
            "stream_channel": "running_summary",
        }
    if ev in ("done", "finished"):
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev == "phase_wait":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    if ev == "unified_summary_loading":
        return {"react_phase": REACT_PHASE_OBSERVE_DECIDE}
    return {}


def _with_react_phase(step_data: Dict[str, Any], pl: Dict[str, Any]) -> None:
    if step_data.get("react_phase") is not None:
        pl["react_phase"] = step_data["react_phase"]


def _pack_plan(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    pl: Dict[str, Any] = {"steps": step_data.get("steps") or []}
    if step_data.get("overview_only") is not None:
        pl["overview_only"] = bool(step_data.get("overview_only"))
    if step_data.get("suppress_plan_ui") is not None:
        pl["suppress_plan_ui"] = bool(step_data.get("suppress_plan_ui"))
    _with_react_phase(step_data, pl)
    return [{"type": ClientWireType.PLAN.value, "payload": pl}]


def _pack_plan_init(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    pl: Dict[str, Any] = {"steps": step_data.get("steps") or [], "mode": step_data.get("mode")}
    if step_data.get("suppress_plan_ui") is not None:
        pl["suppress_plan_ui"] = bool(step_data.get("suppress_plan_ui"))
    _with_react_phase(step_data, pl)
    return [{"type": ClientWireType.PLAN.value, "payload": pl}]


def _pack_plan_update(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    pl: Dict[str, Any] = {
        "steps": step_data.get("steps") or [],
        "reason": step_data.get("reason") or "",
    }
    if step_data.get("suppress_plan_ui") is not None:
        pl["suppress_plan_ui"] = bool(step_data.get("suppress_plan_ui"))
    _with_react_phase(step_data, pl)
    return [{"type": ClientWireType.PLAN.value, "payload": pl}]


def _pack_tool_start(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    idx = step_data.get("index")
    _raw_p = step_data.get("params")
    _params = _json_safe_tool_params(_raw_p) if isinstance(_raw_p, dict) else _raw_p
    return [
        {
            "type": ClientWireType.TOOL.value,
            "payload": {
                "op": ToolPayloadOp.START.value,
                "name": step_data.get("tool") or step_data.get("action"),
                "index": idx,
                "step_id": step_data.get("step_id"),
                "message": step_data.get("message"),
                "params": _params,
                "reason": step_data.get("reason"),
                "react_phase": step_data.get("react_phase"),
            },
        }
    ]


def _compute_step_id_for_tool(step_data: Dict[str, Any]) -> Any:
    idx = step_data.get("index")
    _sid = step_data.get("step_id")
    if _sid is not None:
        return _sid
    if idx is not None:
        try:
            return int(idx) + 1
        except (TypeError, ValueError):
            return None
    return None


def _pack_tool_error(step_data: Dict[str, Any], body: Dict[str, Any]) -> List[Dict[str, Any]]:
    if isinstance(body, dict):
        body = augment_tool_body_wire_shape(body)
        body = deep_sse_json_safe(body)
    else:
        body = ensure_tool_wire_envelope(body)
    idx = step_data.get("index")
    msg = body.get("error") or body.get("message") if isinstance(body, dict) else None
    if not isinstance(msg, str) or not str(msg).strip():
        msg = "工具执行失败"
    code = body.get("code")
    if code is not None and not isinstance(code, (str, int)):
        code = str(code)
    return [
        {
            "type": ClientWireType.TOOL.value,
            "payload": {
                "op": ToolPayloadOp.ERROR.value,
                "name": step_data.get("tool"),
                "index": idx,
                "step_id": _compute_step_id_for_tool(step_data),
                "message": str(msg).strip(),
                "code": code,
                "details": body,
                "summary_nl": step_data.get("summary_nl"),
                "react_phase": step_data.get("react_phase"),
            },
        }
    ]


def _pack_tool_end(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = step_data.get("data")
    if observation_body_is_tool_failure(raw):
        return _pack_tool_error(step_data, raw if isinstance(raw, dict) else {"error": str(raw)})
    if isinstance(raw, dict) or raw is None:
        body = augment_tool_body_wire_shape(raw)
        if isinstance(body, dict):
            body = deep_sse_json_safe(body)
    else:
        body = raw
    idx = step_data.get("index")
    _computed_sid = _compute_step_id_for_tool(step_data)
    return [
        {
            "type": ClientWireType.TOOL.value,
            "payload": {
                "op": ToolPayloadOp.END.value,
                "name": step_data.get("tool"),
                "index": idx,
                "step_id": _computed_sid,
                "body": body,
                "summary_nl": step_data.get("summary_nl"),
                "react_phase": step_data.get("react_phase"),
            },
        }
    ]


def _pack_step_status(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    st = step_data.get("status")
    s = _STEP_STATUS_TO_S.get(st, 1)
    pl: Dict[str, Any] = {
        "index": step_data.get("index"),
        "step_id": step_data.get("step_id"),
        "s": s,
    }
    _with_react_phase(step_data, pl)
    return [{"type": ClientWireType.STEP.value, "payload": pl}]


def _pack_finished(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "type": ClientWireType.TAIL.value,
            "payload": {
                "mode": step_data.get("mode"),
                "finished": step_data.get("finished"),
                "steps_count": step_data.get("steps_count"),
                "duration": step_data.get("duration"),
                "thinking_time": step_data.get("thinking_time"),
                "observations": step_data.get("observations"),
                "plan_snapshot": step_data.get("plan_snapshot"),
                "react_phase": step_data.get("react_phase"),
            },
        }
    ]


def _pack_done(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    pl: Dict[str, Any] = {
        "findings": step_data.get("findings"),
        "steps_count": step_data.get("steps_count"),
        "duration": step_data.get("duration"),
        "thinking_time": step_data.get("thinking_time"),
        "summary": step_data.get("summary"),
        "react_phase": step_data.get("react_phase"),
    }
    if step_data.get("direct_reply") is True:
        pl["direct_reply"] = True
    return [{"type": ClientWireType.BYE.value, "payload": pl}]


def _pack_error(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "type": ClientWireType.ERR.value,
            "payload": {
                "message": str(step_data.get("message", "") or ""),
                "react_phase": step_data.get("react_phase"),
            },
        }
    ]


def _pack_stream_engine_raw(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """未在映射表中的引擎事件：顶层仍为 stream，内层整包给前端解析 event / delta。"""
    safe = deep_sse_json_safe(step_data) if isinstance(step_data, dict) else step_data
    return [
        {
            "type": ClientWireType.STREAM.value,
            "payload": {"lane": "engine", "data": safe},
        }
    ]


def _pack_stream_think(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """§6.1.9：思考类增量 → ``stream`` + ``lane=think``（对应原 ``reasoning``）。"""
    delta = step_data.get("content")
    if delta is None:
        delta = step_data.get("data")
    if not isinstance(delta, str):
        delta = str(delta) if delta is not None else ""
    pl: Dict[str, Any] = {
        "lane": "think",
        "delta": delta,
        "react_phase": step_data.get("react_phase"),
        "stream_channel": step_data.get("stream_channel") or "reasoning",
    }
    if step_data.get("index") is not None:
        pl["index"] = step_data.get("index")
    _as = step_data.get("as")
    if isinstance(_as, str) and _as.strip():
        pl["as"] = _as.strip()
    return [{"type": ClientWireType.STREAM.value, "payload": pl}]


def _pack_stream_agent_thought(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    引擎 event=agent_thought：对外仍走 lane=think，但 payload.as=agent_thought，
    以便前端复用既有 think lane reducer（reactSseV1ChunkToLegacyStepEvent）。
    """
    # react_simplified.py 使用 {"event":"agent_thought","delta":...}
    d = step_data.get("delta")
    if d is None:
        d = step_data.get("content")
    if not isinstance(d, str):
        d = str(d) if d is not None else ""
    merged = {**step_data, "content": d, "as": "agent_thought"}
    return _pack_stream_think(merged)


def _pack_stream_plan_raw(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Todo/XML 等计划原文流 → ``lane=plan``（对应 ``todos_stream``）。"""
    d = step_data.get("delta")
    if not isinstance(d, str):
        d = str(d) if d is not None else ""
    pl: Dict[str, Any] = {"lane": "plan", "delta": d, "react_phase": step_data.get("react_phase")}
    if step_data.get("index") is not None:
        pl["index"] = step_data.get("index")
    return [{"type": ClientWireType.STREAM.value, "payload": pl}]


def _pack_stream_summary(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    d = step_data.get("delta")
    if not isinstance(d, str):
        d = str(d) if d is not None else ""
    return [
        {
            "type": ClientWireType.STREAM.value,
            "payload": {
                "lane": "summary",
                "delta": d,
                "react_phase": step_data.get("react_phase"),
            },
        }
    ]


def _pack_stream_summary_reset(_step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"type": ClientWireType.STREAM.value, "payload": {"lane": "summary", "reset": True}}]


def _pack_stream_running_summary(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    d = step_data.get("delta")
    if not isinstance(d, str):
        d = str(d) if d is not None else ""
    pl: Dict[str, Any] = {
        "lane": "running_summary",
        "delta": d,
        "react_phase": step_data.get("react_phase"),
    }
    if step_data.get("version") is not None:
        pl["version"] = step_data.get("version")
    if step_data.get("index") is not None:
        pl["step_index"] = step_data.get("index")
    return [{"type": ClientWireType.STREAM.value, "payload": pl}]


def _pack_stream_running_summary_reset(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    pl: Dict[str, Any] = {"lane": "running_summary", "reset": True}
    if step_data.get("version") is not None:
        pl["version"] = step_data.get("version")
    return [{"type": ClientWireType.STREAM.value, "payload": pl}]


def _pack_stream_running_summary_done(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    ft = step_data.get("full_text")
    if not isinstance(ft, str):
        ft = str(ft) if ft is not None else ""
    pl: Dict[str, Any] = {
        "lane": "running_summary",
        "done": True,
        "full_text": ft,
        "react_phase": step_data.get("react_phase"),
    }
    if step_data.get("version") is not None:
        pl["version"] = step_data.get("version")
    if step_data.get("index") is not None:
        pl["step_index"] = step_data.get("index")
    return [{"type": ClientWireType.STREAM.value, "payload": pl}]


def _pack_tool_task_lifecycle(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """持久化工具任务 DAG：created / running / done / failed。"""
    ev = step_data.get("event") or ""
    lifecycle = ev.replace("tool_task_", "") if ev.startswith("tool_task_") else str(ev)
    pl: Dict[str, Any] = {
        "lifecycle": lifecycle,
        "task_id": step_data.get("task_id"),
        "name": step_data.get("name"),
        "session_id": step_data.get("session_id"),
        "dependencies": step_data.get("dependencies"),
        "started_at": step_data.get("started_at"),
        "finished_at": step_data.get("finished_at"),
        "error": step_data.get("error"),
        "result_preview": step_data.get("result_preview"),
        "react_phase": step_data.get("react_phase") or REACT_PHASE_ACT,
    }
    pl = {k: v for k, v in pl.items() if v is not None}
    return [{"type": ClientWireType.TOOL_TASK.value, "payload": deep_sse_json_safe(pl)}]


# 引擎 event 字符串 → 打包函数（新增映射时只改这一处表即可）
_ENGINE_EVENT_TO_PACKETS: Dict[str, Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = {
    "plan": _pack_plan,
    "plan_init": _pack_plan_init,
    "plan_update": _pack_plan_update,
    "executing": _pack_tool_start,
    "observation": _pack_tool_end,
    "step_status": _pack_step_status,
    "finished": _pack_finished,
    "done": _pack_done,
    "error": _pack_error,
    "reasoning": _pack_stream_think,
    "agent_thought": _pack_stream_agent_thought,
    "todos_stream": _pack_stream_plan_raw,
    "summary_stream": _pack_stream_summary,
    "summary_stream_reset": _pack_stream_summary_reset,
    "running_summary_stream": _pack_stream_running_summary,
    "running_summary_stream_reset": _pack_stream_running_summary_reset,
    "running_summary_done": _pack_stream_running_summary_done,
    "tool_task_created": _pack_tool_task_lifecycle,
    "tool_task_running": _pack_tool_task_lifecycle,
    "tool_task_done": _pack_tool_task_lifecycle,
    "tool_task_failed": _pack_tool_task_lifecycle,
}


def map_engine_step_to_client_packets(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """仅做 ``event`` → v1 包；不含 meta。对外入口请用 ``engine_dict_to_wire_packets``。"""
    if not isinstance(step_data, dict):
        return []
    engine_event = step_data.get("event")
    if not isinstance(engine_event, str):
        return _pack_stream_engine_raw(step_data)
    builder = _ENGINE_EVENT_TO_PACKETS.get(engine_event)
    if builder is None:
        return _pack_stream_engine_raw(step_data)
    return builder(step_data)


def engine_dict_to_wire_packets(step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """引擎 yield 的 ``{event: ...}``：先合并 ``react_sse_meta``，再转为 v1 ``{type, payload}`` 列表。"""
    if not isinstance(step_data, dict):
        return []
    merged = {**step_data, **react_sse_meta(step_data)}
    return map_engine_step_to_client_packets(merged)


def is_wire_v1_packet(d: Dict[str, Any]) -> bool:
    """已为 SSE v1 形态（含 ``payload`` 对象），出口可原样下发。"""
    return isinstance(d, dict) and bool(d.get("type")) and isinstance(d.get("payload"), dict)
