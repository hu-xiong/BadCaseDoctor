# -*- coding: utf-8 -*-
"""协议 P1 契约：stream 车道形状（§6.1.9）。运行：项目根下 ``python tests/test_sse_react_v1_lanes.py`` 或 ``pytest``。"""
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

from agents.sse_react_v1 import (
    ClientWireType,
    engine_dict_to_wire_packets,
    map_engine_step_to_client_packets,
    react_phase_wire_payload,
)
from agents.tool_wire_envelope import (
    augment_tool_body_wire_shape,
    ensure_tool_wire_envelope,
    observation_body_is_tool_failure,
)


def test_reasoning_maps_to_stream_think():
    pkts = engine_dict_to_wire_packets({"event": "reasoning", "content": "hi"})
    assert len(pkts) == 1
    assert pkts[0]["type"] == "stream"
    pl = pkts[0]["payload"]
    assert pl["lane"] == "think"
    assert pl["delta"] == "hi"
    assert pl.get("stream_channel") == "reasoning"


def test_todos_stream_maps_to_stream_plan():
    pkts = engine_dict_to_wire_packets({"event": "todos_stream", "delta": "<t>"})
    assert pkts[0]["payload"]["lane"] == "plan"
    assert pkts[0]["payload"]["delta"] == "<t>"


def test_summary_stream_and_reset():
    p1 = engine_dict_to_wire_packets({"event": "summary_stream", "delta": "S"})
    assert p1[0]["payload"]["lane"] == "summary"
    assert p1[0]["payload"]["delta"] == "S"
    p2 = engine_dict_to_wire_packets({"event": "summary_stream_reset"})
    assert p2[0]["payload"]["lane"] == "summary"
    assert p2[0]["payload"].get("reset") is True


def test_tool_task_lifecycle_maps_to_tool_task_type():
    pkts = engine_dict_to_wire_packets(
        {
            "event": "tool_task_done",
            "task_id": "tid-1",
            "name": "grep",
            "session_id": "sess",
            "result_preview": {"success": True, "summary": "ok"},
        }
    )
    assert len(pkts) == 1
    assert pkts[0]["type"] == ClientWireType.TOOL_TASK.value
    pl = pkts[0]["payload"]
    assert pl["lifecycle"] == "done"
    assert pl["task_id"] == "tid-1"
    assert pl["name"] == "grep"
    assert pl.get("react_phase") == "act"


def test_running_summary_stream_lane():
    p1 = engine_dict_to_wire_packets(
        {"event": "running_summary_stream", "delta": "x", "version": 2, "index": 1}
    )
    pl = p1[0]["payload"]
    assert pl["lane"] == "running_summary"
    assert pl["delta"] == "x"
    assert pl["version"] == 2
    assert pl["step_index"] == 1
    pr = engine_dict_to_wire_packets({"event": "running_summary_stream_reset", "version": 3})
    assert pr[0]["payload"]["lane"] == "running_summary"
    assert pr[0]["payload"].get("reset") is True
    assert pr[0]["payload"]["version"] == 3
    pd = engine_dict_to_wire_packets(
        {
            "event": "running_summary_done",
            "full_text": "## A\n- b",
            "version": 3,
            "index": 0,
        }
    )
    assert pd[0]["payload"]["lane"] == "running_summary"
    assert pd[0]["payload"].get("done") is True
    assert pd[0]["payload"]["full_text"] == "## A\n- b"


def test_unknown_event_stays_engine_lane():
    pkts = map_engine_step_to_client_packets(
        {"event": "phase_wait", "kind": "x", "active": True, "message": "m", "react_phase": "think"}
    )
    assert pkts[0]["type"] == "stream"
    assert pkts[0]["payload"]["lane"] == "engine"


def test_observation_failure_maps_to_tool_error():
    pkts = map_engine_step_to_client_packets(
        {
            "event": "observation",
            "tool": "grep",
            "index": 0,
            "data": {"success": False, "error": "not found"},
        }
    )
    assert len(pkts) == 1
    assert pkts[0]["type"] == "tool"
    pl = pkts[0]["payload"]
    assert pl["op"] == "error"
    assert pl["name"] == "grep"
    assert pl["message"] == "not found"
    assert pl["details"]["success"] is False


def test_observation_success_stays_tool_end():
    pkts = map_engine_step_to_client_packets(
        {
            "event": "observation",
            "tool": "grep",
            "index": 0,
            "data": {"success": True, "results": []},
        }
    )
    assert pkts[0]["payload"]["op"] == "end"


def test_observation_error_only_string_maps_to_tool_error():
    pkts = map_engine_step_to_client_packets(
        {
            "event": "observation",
            "tool": "grep",
            "index": 0,
            "data": {"error": "timeout"},
        }
    )
    assert pkts[0]["payload"]["op"] == "error"


def test_ensure_envelope_adds_success_and_message():
    d = ensure_tool_wire_envelope({"results": [], "query": "x"})
    assert d["success"] is True
    d2 = ensure_tool_wire_envelope({"error": "bad"})
    assert d2["success"] is False
    assert "bad" in (d2.get("message") or "")


def test_observation_body_is_tool_failure():
    assert observation_body_is_tool_failure({"success": False}) is True
    assert observation_body_is_tool_failure({"error": "e"}) is True
    assert observation_body_is_tool_failure({"results": []}) is False


def test_tool_end_body_has_data_shape():
    pkts = map_engine_step_to_client_packets(
        {
            "event": "observation",
            "tool": "grep",
            "index": 0,
            "data": {"success": True, "results": [{"id": 1}]},
        }
    )
    body = pkts[0]["payload"]["body"]
    assert isinstance(body.get("data"), dict)
    assert body["data"].get("results") == [{"id": 1}]
    assert body.get("success") is True


def test_augment_tool_body_wire_shape():
    b = augment_tool_body_wire_shape({"success": True, "query": "q", "results": []})
    assert b["data"]["query"] == "q"
    assert b["success"] is True


def _inject_phase_edges(pkts, last_phase):
    """与 ``run_stream`` 出口一致的 phase 边沿插入（单测）。"""
    out = []
    new_last = last_phase
    for pkt in pkts:
        pl = pkt.get("payload")
        if isinstance(pl, dict):
            rp = pl.get("react_phase")
            if isinstance(rp, str) and rp and rp != new_last:
                out.append(
                    {"type": ClientWireType.PHASE.value, "payload": react_phase_wire_payload(rp)}
                )
                new_last = rp
        out.append(pkt)
    return out, new_last


def test_phase_edges_think_then_act():
    acc = []
    last = None
    for raw in (
        {"event": "reasoning", "content": "hi"},
        {"event": "executing", "tool": "grep", "index": 0, "message": "m"},
    ):
        pkts = engine_dict_to_wire_packets(raw)
        batch, last = _inject_phase_edges(pkts, last)
        acc.extend(batch)
    types = [p["type"] for p in acc]
    assert types.count("phase") >= 2
    assert acc[0]["type"] == "phase"
    assert acc[0]["payload"]["name"] == "think"
    assert acc[2]["type"] == "phase"
    assert acc[2]["payload"]["name"] == "act"


def test_plan_init_passes_suppress_plan_ui():
    pkts = engine_dict_to_wire_packets(
        {
            "event": "plan_init",
            "mode": "normal",
            "steps": [{"id": 1, "name": "a"}],
            "suppress_plan_ui": True,
        }
    )
    assert len(pkts) == 1
    assert pkts[0]["type"] == "plan"
    assert pkts[0]["payload"].get("suppress_plan_ui") is True


if __name__ == "__main__":
    test_reasoning_maps_to_stream_think()
    test_todos_stream_maps_to_stream_plan()
    test_summary_stream_and_reset()
    test_running_summary_stream_lane()
    test_unknown_event_stays_engine_lane()
    test_observation_failure_maps_to_tool_error()
    test_observation_success_stays_tool_end()
    test_observation_error_only_string_maps_to_tool_error()
    test_ensure_envelope_adds_success_and_message()
    test_observation_body_is_tool_failure()
    test_tool_end_body_has_data_shape()
    test_augment_tool_body_wire_shape()
    test_phase_edges_think_then_act()
    test_plan_init_passes_suppress_plan_ui()
    print("ok")
