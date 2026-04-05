# -*- coding: utf-8 -*-
"""
回放基线：引擎事件 → v1 包 type 序列（无网络、无 run_stream phase 边沿）。
用于后续「同 fixtures JSON 回放」扩展。
"""
import json
import os
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

from agents.sse_react_v1 import engine_dict_to_wire_packets


def test_golden_wire_types_main_chain():
    events = [
        {"event": "reasoning", "content": "a"},
        {
            "event": "plan_init",
            "mode": "normal",
            "steps": [
                {
                    "id": 1,
                    "name": "t",
                    "tool": None,
                    "params": {},
                    "status": "pending",
                    "result": None,
                }
            ],
        },
        {"event": "executing", "tool": "grep", "index": 0, "step_id": 1, "message": "m"},
        {"event": "observation", "tool": "grep", "index": 0, "data": {"success": True, "results": []}},
        {"event": "step_status", "index": 0, "step_id": 1, "status": "done"},
        {
            "event": "finished",
            "finished": True,
            "steps_count": 1,
            "duration": 1.0,
            "thinking_time": 0.5,
        },
        {
            "event": "done",
            "findings": [],
            "steps_count": 1,
            "duration": 1.0,
            "thinking_time": 0.5,
            "summary": "s",
        },
    ]
    types = []
    for ev in events:
        for pkt in engine_dict_to_wire_packets(ev):
            types.append(pkt.get("type"))
    assert types == ["stream", "plan", "tool", "tool", "step", "tail", "bye"]


def test_replay_fixture_json_roundtrip():
    events = [{"event": "error", "message": "e"}]
    back = json.loads(json.dumps(events, ensure_ascii=False))
    types = []
    for ev in back:
        for pkt in engine_dict_to_wire_packets(ev):
            types.append(pkt.get("type"))
    assert types == ["err"]


if __name__ == "__main__":
    test_golden_wire_types_main_chain()
    test_replay_fixture_json_roundtrip()
    print("ok")
