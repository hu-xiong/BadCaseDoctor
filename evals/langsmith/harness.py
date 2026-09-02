# -*- coding: utf-8 -*-
"""
金路径评测执行器：假 LLM + 假工具，不打真实模型和库。

产出 outputs 供 LangSmith evaluators / 本地评分使用。
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# 评测默认 memory checkpointer，避免污染本地 sqlite；dry-run 默认不开云端 tracing
os.environ.setdefault("LANGGRAPH_CHECKPOINTER", "memory")
os.environ.setdefault("LANGGRAPH_OBSERVE", "0")
if (os.getenv("LANGSMITH_EVAL_ALLOW_TRACE") or "").strip().lower() not in (
    "1",
    "true",
    "yes",
    "on",
):
    os.environ.setdefault("LANGSMITH_TRACING", "false")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")


def dataset_path() -> Path:
    return Path(__file__).resolve().parent / "golden_path.json"


def load_dataset() -> Dict[str, Any]:
    return json.loads(dataset_path().read_text(encoding="utf-8"))


def _build_engine(*, grep_empty: bool = False, force_first_tool: Optional[str] = None):
    from types import SimpleNamespace

    from agents.langgraph_checkpointer import reset_checkpointer_for_tests
    from agents.langgraph_engine import LangGraphReactEngine
    from agents.tool_registry import BaseTool, ToolRegistry

    reset_checkpointer_for_tests()

    class _GrepTool(BaseTool):
        def __init__(self):
            super().__init__(name="grep", description="eval grep")

        async def execute(self, **kwargs):
            if grep_empty:
                return {
                    "success": False,
                    "message": "无检索结果",
                    "data": {"bug_location": [], "navigation": {}},
                }
            return {
                "success": True,
                "data": {
                    "bug_location": [{"id": 1001, "title": "login fail", "plan_id": 1}],
                    "navigation": {
                        "type": "expand_and_locate",
                        "target": "bug",
                        "record_id": 1001,
                        "bug_id": 1001,
                    },
                },
            }

    class _ModifyTool(BaseTool):
        def __init__(self):
            super().__init__(name="modify", description="eval modify")

        async def execute(self, **kwargs):
            return {
                "success": True,
                "preview_only": True,
                "confirmation_required": True,
                "target": kwargs.get("target") or "bug",
                "target_id": kwargs.get("target_id") or 1001,
                "confirm": kwargs.get("confirm"),
                "modifications": kwargs.get("modifications") or {"priority": "p1"},
            }

    class _FakeLLM:
        def __init__(self):
            self.n = 0
            self.force_first = (force_first_tool or "").strip().lower() or None

        def chat_completion_with_tools(self, messages, tools, **kwargs):
            self.n += 1
            # 已有 tool 结果则结束
            for m in reversed(messages or []):
                if isinstance(m, dict) and m.get("role") == "tool":
                    try:
                        body = json.loads(m.get("content") or "{}")
                    except Exception:
                        body = {}
                    if body.get("preview_only") or body.get("confirmation_required"):
                        return SimpleNamespace(
                            choices=[
                                SimpleNamespace(
                                    message=SimpleNamespace(content="预览已就绪", tool_calls=None)
                                )
                            ]
                        )
                    if body.get("stop_retry") or body.get("success") is False:
                        return SimpleNamespace(
                            choices=[
                                SimpleNamespace(
                                    message=SimpleNamespace(
                                        content="未找到目标记录", tool_calls=None
                                    )
                                )
                            ]
                        )
                    # grep 成功后下一轮 modify
                    if m.get("name") == "grep" and body.get("success"):
                        args = json.dumps(
                            {
                                "target": "bug",
                                "target_id": 1001,
                                "modifications": {"priority": "p1"},
                            },
                            ensure_ascii=False,
                        )
                        return SimpleNamespace(
                            choices=[
                                SimpleNamespace(
                                    message=SimpleNamespace(
                                        content="",
                                        tool_calls=[
                                            SimpleNamespace(
                                                id="call_mod",
                                                type="function",
                                                function=SimpleNamespace(
                                                    name="modify", arguments=args
                                                ),
                                            )
                                        ],
                                    )
                                )
                            ]
                        )

            tool_name = self.force_first if self.n == 1 and self.force_first else "grep"
            if tool_name == "modify":
                args = json.dumps(
                    {"target": "bug", "modifications": {"status": "closed"}},
                    ensure_ascii=False,
                )
            else:
                args = json.dumps({"keywords": "登录", "target": "bug"}, ensure_ascii=False)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content="",
                            tool_calls=[
                                SimpleNamespace(
                                    id=f"call_{self.n}",
                                    type="function",
                                    function=SimpleNamespace(name=tool_name, arguments=args),
                                )
                            ],
                        )
                    )
                ]
            )

    reg = ToolRegistry()
    reg.register(_GrepTool(), quiet=True)
    reg.register(_ModifyTool(), quiet=True)
    eng = LangGraphReactEngine(_FakeLLM(), reg)
    eng.user_id = "eval_user"
    eng._user_id = "eval_user"
    return eng


async def _run_one_async(inputs: Dict[str, Any]) -> Dict[str, Any]:
    user_input = str((inputs or {}).get("user_input") or "").strip() or "测试"
    grep_empty = bool((inputs or {}).get("grep_empty"))
    force_first = (inputs or {}).get("force_first_tool")
    eng = _build_engine(grep_empty=grep_empty, force_first_tool=force_first)

    tool_sequence: List[str] = []
    preview_await = False
    empty_grep_stop = False
    saw_confirm_true = False
    grep_calls = 0
    failure_kinds: List[str] = []

    async for pkt in eng.run_stream(
        user_input,
        project_id=1,
        plan_id=1,
        locale="zh",
        agent_session_id=f"eval-{abs(hash(user_input)) % 10_000_000}",
    ):
        if not isinstance(pkt, dict):
            continue
        ptype = str(pkt.get("type") or "")
        pl = pkt.get("payload") if isinstance(pkt.get("payload"), dict) else {}

        # tool start/end（SSE v1）
        if ptype == "tool":
            op = str(pl.get("op") or "").lower()
            t = str(pl.get("name") or "").lower()
            if op == "start":
                if t:
                    tool_sequence.append(t)
                    if t == "grep":
                        grep_calls += 1
                params = pl.get("params") if isinstance(pl.get("params"), dict) else {}
                if params.get("confirm") is True:
                    saw_confirm_true = True
            body = pl.get("body") if isinstance(pl.get("body"), dict) else {}
            if body.get("confirm") is True:
                saw_confirm_true = True
            continue

        # engine lane：interrupt / resume / failure_edge
        if ptype == "stream" and pl.get("lane") == "engine":
            data = pl.get("data") if isinstance(pl.get("data"), dict) else {}
            ev_name = str(data.get("event") or "")
            if ev_name == "interrupt":
                reason = str(data.get("reason") or "")
                failure_kinds.append(reason)
                if reason == "preview_await_confirm":
                    preview_await = True
                if "empty" in reason:
                    empty_grep_stop = True
            elif ev_name == "failure_edge":
                failure_kinds.append(str(data.get("kind") or ""))
            elif ev_name == "langgraph_resume":
                st = data.get("state") if isinstance(data.get("state"), dict) else {}
                fk = str(st.get("failure_kind") or data.get("reason") or "")
                failure_kinds.append(fk)
                if fk == "preview_await_confirm":
                    preview_await = True
                if fk == "empty_grep":
                    empty_grep_stop = True
            continue

        # finished / bye / tail
        if ptype in ("bye", "tail", "done"):
            summary = str(pl.get("summary") or pkt.get("summary") or "")
            if "未找到" in summary or "无检索" in summary or "empty" in summary.lower():
                empty_grep_stop = True
            continue
        if ptype == "stream":
            summary = str(pl.get("delta") or pl.get("summary") or "")
            if any(
                k in summary
                for k in ("未找到", "无检索", "未命中", "没有找到", "empty grep", "no match")
            ):
                empty_grep_stop = True
            continue

    # 门控 coerce：agent 先报 modify，tools 再 executing grep → 归一为 grep…
    compact: List[str] = []
    for t in tool_sequence:
        if compact and compact[-1] == "modify" and t == "grep":
            compact[-1] = "grep"
            continue
        if not compact or compact[-1] != t:
            compact.append(t)

    # 空检索熔断与预览停图互斥：空检索优先
    if empty_grep_stop:
        preview_await = False
    if not empty_grep_stop and grep_empty and grep_calls >= 1 and "modify" not in compact:
        # finished 文案未解析到时，用输入意图兜底
        empty_grep_stop = True

    return {
        "tool_sequence": compact,
        "preview_await_confirm": preview_await,
        "stopped_for_preview": preview_await,
        "empty_grep_stop": empty_grep_stop,
        "saw_confirm_true": saw_confirm_true,
        "grep_calls": grep_calls,
        "failure_kinds": failure_kinds,
        "success": True,
    }


def run_example(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """LangSmith target：同步入口。"""
    return asyncio.run(_run_one_async(inputs if isinstance(inputs, dict) else {}))
