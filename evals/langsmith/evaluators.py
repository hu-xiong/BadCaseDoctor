# -*- coding: utf-8 -*-
"""金路径规则评分（不依赖 LLM-as-judge，适合后台定时跑）。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def _tools(outputs: Dict[str, Any]) -> List[str]:
    seq = outputs.get("tool_sequence") or outputs.get("tools") or []
    if not isinstance(seq, list):
        return []
    return [str(x).strip().lower() for x in seq if str(x).strip()]


def _ref(example: Any) -> Dict[str, Any]:
    if example is None:
        return {}
    if isinstance(example, dict):
        return example.get("outputs") or example.get("reference") or example
    outs = getattr(example, "outputs", None)
    if isinstance(outs, dict):
        return outs
    return {}


def score_tool_sequence(run: Any = None, example: Any = None, **kwargs) -> Dict[str, Any]:
    """期望工具序列（有序包含或完全匹配）。"""
    outputs = kwargs.get("outputs") or (getattr(run, "outputs", None) if run is not None else None) or {}
    if not isinstance(outputs, dict):
        outputs = {}
    ref = _ref(example)
    tools = _tools(outputs)
    expected: Sequence[str] = ref.get("expected_tools") or []
    prefix: Sequence[str] = ref.get("expected_tools_prefix") or []
    ok = True
    comment = ""
    if expected:
        ok = tools == [str(x).lower() for x in expected]
        comment = f"tools={tools} expected={list(expected)}"
    elif prefix:
        pref = [str(x).lower() for x in prefix]
        ok = tools[: len(pref)] == pref
        comment = f"tools={tools} prefix={pref}"
    else:
        comment = f"tools={tools} (no sequence expectation)"
    return {"key": "tool_sequence", "score": 1.0 if ok else 0.0, "comment": comment}


def score_preview_stop(run: Any = None, example: Any = None, **kwargs) -> Dict[str, Any]:
    outputs = kwargs.get("outputs") or (getattr(run, "outputs", None) if run is not None else None) or {}
    if not isinstance(outputs, dict):
        outputs = {}
    ref = _ref(example)
    if not ref.get("require_preview_stop"):
        return {"key": "preview_stop", "score": 1.0, "comment": "n/a"}
    stopped = bool(outputs.get("preview_await_confirm") or outputs.get("stopped_for_preview"))
    return {
        "key": "preview_stop",
        "score": 1.0 if stopped else 0.0,
        "comment": f"preview_await_confirm={stopped}",
    }


def score_forbid_confirm(run: Any = None, example: Any = None, **kwargs) -> Dict[str, Any]:
    outputs = kwargs.get("outputs") or (getattr(run, "outputs", None) if run is not None else None) or {}
    if not isinstance(outputs, dict):
        outputs = {}
    ref = _ref(example)
    if not ref.get("forbid_confirm_true"):
        return {"key": "forbid_confirm", "score": 1.0, "comment": "n/a"}
    bad = bool(outputs.get("saw_confirm_true"))
    return {
        "key": "forbid_confirm",
        "score": 0.0 if bad else 1.0,
        "comment": f"saw_confirm_true={bad}",
    }


def score_empty_grep_stop(run: Any = None, example: Any = None, **kwargs) -> Dict[str, Any]:
    outputs = kwargs.get("outputs") or (getattr(run, "outputs", None) if run is not None else None) or {}
    if not isinstance(outputs, dict):
        outputs = {}
    ref = _ref(example)
    if not ref.get("require_empty_grep_stop"):
        return {"key": "empty_grep_stop", "score": 1.0, "comment": "n/a"}
    stopped = bool(outputs.get("empty_grep_stop"))
    grep_n = int(outputs.get("grep_calls") or 0)
    max_g = int(ref.get("max_grep_calls") or 1)
    ok = stopped and grep_n <= max_g
    return {
        "key": "empty_grep_stop",
        "score": 1.0 if ok else 0.0,
        "comment": f"empty_stop={stopped} grep_calls={grep_n} max={max_g}",
    }


def all_evaluators() -> List[Any]:
    return [
        score_tool_sequence,
        score_preview_stop,
        score_forbid_confirm,
        score_empty_grep_stop,
    ]


def local_score(outputs: Dict[str, Any], reference: Dict[str, Any]) -> Dict[str, Any]:
    """不连 LangSmith 时本地打分。"""
    scores = {}
    for fn in all_evaluators():
        r = fn(outputs=outputs, example={"outputs": reference})
        scores[r["key"]] = {"score": r["score"], "comment": r.get("comment")}
    vals = [v["score"] for v in scores.values()]
    scores["_mean"] = sum(vals) / len(vals) if vals else 0.0
    return scores
