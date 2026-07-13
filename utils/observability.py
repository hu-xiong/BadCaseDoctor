# utils/observability.py
"""
Agent + Prometheus 本地观测：指标落盘 + 结构化 trace（JSONL）。

用法（项目根目录）：
  python scripts/dump_observability.py
  # 或设环境变量后跑 Agent，自动写入 observability/

环境变量：
- BADCASE_SDK_ENABLED：是否记录 Prometheus 指标（默认 true）
- BADCASE_SDK_APP / BADCASE_SDK_ENV
- BADCASE_METRICS_TEXT_DIR / BADCASE_METRICS_TEXT_INTERVAL
- BADCASE_AGENT_TRACE_DIR：JSONL 目录，默认 observability/agent_trace
- BADCASE_AGENT_TRACE_ENABLED：默认 1
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_trace_lock = threading.Lock()
_setup_done = False


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_sdk_path() -> None:
    sdk_dir = _repo_root() / "sdk"
    if sdk_dir.is_dir():
        p = str(sdk_dir)
        if p not in sys.path:
            sys.path.insert(0, p)


def setup_observability() -> None:
    """应用启动时调用一次：init SDK + 周期落盘。"""
    global _setup_done
    if _setup_done:
        return
    _setup_done = True
    _ensure_sdk_path()
    enabled = (os.getenv("BADCASE_SDK_ENABLED", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not enabled:
        return
    try:
        from badcase_sdk import init
        from badcase_sdk.text_export import start_periodic_export, write_snapshot

        init(
            app=os.getenv("BADCASE_SDK_APP", "badcase_doctor"),
            env=os.getenv("BADCASE_SDK_ENV", os.getenv("FLASK_ENV", "dev")),
            enabled=True,
        )
        write_snapshot()
        start_periodic_export()
    except Exception as ex:
        print(f"[observability] SDK init skipped: {ex}", flush=True)


def trace_dir() -> Path:
    env = (os.getenv("BADCASE_AGENT_TRACE_DIR") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return _repo_root() / "observability" / "agent_trace"


def trace_enabled() -> bool:
    return (os.getenv("BADCASE_AGENT_TRACE_ENABLED", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def truncate_modifications_for_trace(mods: Any, max_val_len: int = 200) -> Any:
    if not isinstance(mods, dict):
        return mods
    out: Dict[str, Any] = {}
    for k, v in mods.items():
        if str(k).startswith("_"):
            continue
        if isinstance(v, dict):
            entry = {}
            for sk in ("old", "new"):
                if sk in v:
                    sv = v[sk]
                    s = "" if sv is None else str(sv)
                    entry[sk] = s if len(s) <= max_val_len else s[:max_val_len] + "…"
            out[str(k)] = entry
        else:
            s = "" if v is None else str(v)
            out[str(k)] = s if len(s) <= max_val_len else s[:max_val_len] + "…"
    return out


def summarize_modify_observation(obs: Any) -> Dict[str, Any]:
    if not isinstance(obs, dict):
        return {}
    diff = obs.get("diff") or []
    fields: List[str] = []
    effective: List[str] = []
    if isinstance(diff, list):
        for fd in diff:
            if not isinstance(fd, dict):
                continue
            fk = fd.get("field") or fd.get("field_label")
            if fk:
                fields.append(str(fk))
            lines = fd.get("lines") or []
            old_c = new_c = ""
            for ln in lines:
                if not isinstance(ln, dict):
                    continue
                if ln.get("type") == "delete":
                    old_c = str(ln.get("content") or "")
                elif ln.get("type") == "add":
                    new_c = str(ln.get("content") or "")
            if old_c != new_c:
                effective.append(str(fk or "?"))
    mods = obs.get("modifications")
    mod_keys: List[str] = []
    if isinstance(mods, dict):
        mod_keys = [str(k) for k in mods.keys() if not str(k).startswith("_")]
    verdict = "ok"
    if not obs.get("success"):
        verdict = "fail"
    elif mod_keys and not effective:
        verdict = "noop_or_same_value"
    elif len(fields) > len(effective) and effective:
        verdict = "partial_diff"
    return {
        "success": obs.get("success"),
        "target": obs.get("target"),
        "target_id": obs.get("target_id"),
        "diff_fields": fields,
        "effective_change_fields": effective,
        "modification_keys": mod_keys,
        "diff_count": len(fields),
        "verdict": verdict,
    }


def append_agent_trace(
    span: str,
    data: Optional[Dict[str, Any]] = None,
    *,
    react_request_id: Optional[str] = None,
    round_idx: Optional[int] = None,
    tool: Optional[str] = None,
) -> None:
    if not trace_enabled():
        return
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "span": span,
        "react_request_id": react_request_id,
        "round": round_idx,
        "tool": tool,
        "data": data or {},
    }
    base = trace_dir()
    base.mkdir(parents=True, exist_ok=True)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = base / f"agent_trace_{day}.jsonl"
    line = json.dumps(event, ensure_ascii=False, default=str)
    with _trace_lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    if react_request_id:
        run_path = base / f"run_{react_request_id}.jsonl"
        with _trace_lock:
            with run_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


def record_react_tool_metrics(
    tool_name: str,
    *,
    result: str,
    duration_sec: float,
    provider: str = "react",
    model: str = "agent",
) -> None:
    if not (os.getenv("BADCASE_SDK_ENABLED", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    _ensure_sdk_path()
    try:
        from badcase_sdk import BadCaseCollector

        c = BadCaseCollector()
        c.record_tool_call(
            provider=provider,
            endpoint="tool",
            model=model,
            tool_name=tool_name,
            result=result,
            duration_sec=duration_sec,
        )
        c.record_workflow_step(
            workflow_id="react",
            workflow_step=tool_name[:32],
            step_type="tool",
            result=result,
            seconds=duration_sec,
        )
    except Exception:
        pass


def flush_observability(prefix: str = "metrics") -> Dict[str, str]:
    """一次运行结束或手动脚本：落盘 Prometheus + 返回路径说明。"""
    out: Dict[str, str] = {}
    _ensure_sdk_path()
    try:
        from badcase_sdk.text_export import write_snapshot

        prom, summary = write_snapshot(prefix=prefix)
        out["prom"] = str(prom)
        out["summary"] = str(summary)
    except Exception as ex:
        out["error"] = str(ex)
    out["trace_dir"] = str(trace_dir())
    return out
