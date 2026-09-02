# -*- coding: utf-8 -*-
"""LangGraph 融合冒烟：门控 coerce + ID 补全 + 工具执行。"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

# CI/本地冒烟默认 memory，避免写盘；生产用 sqlite
os.environ.setdefault("LANGGRAPH_CHECKPOINTER", "memory")

from agents.langgraph_bridge import enrich_tool_params_for_execute, prepare_mutate_or_coerce_grep
from agents.langgraph_checkpointer import reset_checkpointer_for_tests
from agents.langgraph_engine import LangGraphReactEngine, _LANGGRAPH_OK
from agents.tool_registry import BaseTool, ToolRegistry

reset_checkpointer_for_tests()


class _GrepTool(BaseTool):
    def __init__(self):
        super().__init__(name="grep", description="grep smoke")

    async def execute(self, **kwargs):
        return {
            "success": True,
            "data": {
                "bug_location": [{"id": 1000000000001, "title": "login fail", "plan_id": 1}],
                "navigation": {
                    "type": "expand_and_locate",
                    "target": "bug",
                    "record_id": 1000000000001,
                    "bug_id": 1000000000001,
                },
            },
        }


class _ModifyTool(BaseTool):
    def __init__(self):
        super().__init__(name="modify", description="modify smoke")

    async def execute(self, **kwargs):
        return {
            "success": True,
            "preview_only": True,
            "confirmation_required": True,
            "target": kwargs.get("target"),
            "target_id": kwargs.get("target_id"),
            "confirm": kwargs.get("confirm"),
            "modifications": kwargs.get("modifications"),
            "sandbox_preview": {"ok": True},
        }


class _SkillTool(BaseTool):
    def __init__(self):
        super().__init__(name="skill_executor", description="skill smoke")

    async def execute(self, params=None, **kwargs):
        p = params if isinstance(params, dict) else kwargs
        return {"success": True, "skill_name": "smoke", "params_keys": sorted(p.keys())}


class _FakeLLM:
    """第1轮假装直接 modify；门控应 coerce 成 grep；第2轮再 modify；第3轮结束。"""

    def __init__(self):
        self.n = 0

    def chat_completion_with_tools(self, messages, tools, **kwargs):
        self.n += 1
        names = []
        for t in tools or []:
            fn = (t.get("function") or {}) if isinstance(t, dict) else {}
            if fn.get("name"):
                names.append(fn["name"])
        assert "grep" in names and "modify" in names and "skill_executor" in names

        if self.n == 1:
            fn = SimpleNamespace(
                name="modify",
                arguments='{"target":"bug","modifications":{"status":"resolved"}}',
            )
            tc = SimpleNamespace(id="c1", function=fn)
            msg = SimpleNamespace(content="will modify", tool_calls=[tc])
        elif self.n == 2:
            fn = SimpleNamespace(
                name="modify",
                arguments='{"target":"bug","modifications":{"status":"resolved"}}',
            )
            tc = SimpleNamespace(id="c2", function=fn)
            msg = SimpleNamespace(content="modify after grep", tool_calls=[tc])
        else:
            msg = SimpleNamespace(content="preview ready", tool_calls=[])
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


async def _main():
    assert _LANGGRAPH_OK
    reg = ToolRegistry()
    reg.register(_GrepTool(), quiet=True)
    reg.register(_ModifyTool(), quiet=True)
    reg.register(_SkillTool(), quiet=True)
    eng = LangGraphReactEngine(_FakeLLM(), reg)

    # 单元：门控 coerce
    name, params, block = prepare_mutate_or_coerce_grep(
        helpers=eng.helpers,
        tool_name="modify",
        tool_params={"target": "bug", "modifications": {"status": "x"}},
        user_input="把登录失败的 bug 改成已解决",
        result_context={},
        grep_tool_calls=0,
        project_id=1,
        plan_id=None,
        ui_context=None,
        locale="zh",
    )
    assert name == "grep" and block is None, (name, block)

    pkts = []
    async for p in eng.run_stream("把登录失败的 bug 改成已解决", project_id=1, locale="zh"):
        pkts.append(p)
    types = [p.get("type") for p in pkts if isinstance(p, dict)]
    print("packet_types sample", types[:24], "total", len(pkts))
    assert "tool" in types and "bye" in types
    assert "plan" in types, "heuristic task_plan should emit plan_init"
    engine_ev = []
    for p in pkts:
        pl = (p.get("payload") or {}) if isinstance(p, dict) else {}
        data = pl.get("data") if pl.get("lane") == "engine" else None
        if isinstance(data, dict) and data.get("event"):
            engine_ev.append(data.get("event"))
    assert "observe" in engine_ev, engine_ev
    print("observe_ok", [e for e in engine_ev if e in ("observe", "failure_edge", "plan_init")])

    # 确认 enrich 默认 confirm=False
    p2 = enrich_tool_params_for_execute(
        helpers=eng.helpers,
        tool_name="modify",
        tool_params={"target": "bug", "modifications": {"status": "resolved"}},
        user_input="x",
        result_context={
            "grep_result": {"first_bug_id": 1000000000001},
            "first_bug_id": 1000000000001,
        },
        project_id=1,
        plan_id=None,
        user_id="u1",
        locale="zh",
        ui_context=None,
        client_shell=None,
        pending_diff_context=None,
    )
    assert p2.get("confirm") is False
    assert p2.get("target_id") in (1000000000001, "1000000000001") or p2.get("target_id") == 1000000000001
    print("enrich_ok", {k: p2.get(k) for k in ("confirm", "target", "target_id")})

    # 失败边：工具失败 → replan → 回 agent 再收尾
    import os

    from agents.langgraph_failure import FailureAction, classify_tool_failure
    from agents.langgraph_resume import apply_langgraph_resume, build_langgraph_resume_snapshot

    d = classify_tool_failure(
        tool_name="create",
        observation={"success": False, "error": "permission denied"},
        failure_retries=0,
    )
    assert d.action == FailureAction.REPLAN, d

    class _FailCreate(BaseTool):
        def __init__(self):
            super().__init__(name="create", description="fail create")

        async def execute(self, **kwargs):
            return {"success": False, "error": "permission denied"}

    class _FailThenStopLLM:
        def __init__(self):
            self.n = 0

        def chat_completion_with_tools(self, messages, tools, **kwargs):
            self.n += 1
            if self.n == 1:
                fn = SimpleNamespace(name="create", arguments='{"target":"bug","title":"x"}')
                tc = SimpleNamespace(id="f1", function=fn)
                msg = SimpleNamespace(content="try create", tool_calls=[tc])
            else:
                # 收到 replan hint 后停止
                msg = SimpleNamespace(content="need user help after replan", tool_calls=[])
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    reg2 = ToolRegistry()
    reg2.register(_FailCreate(), quiet=True)
    eng2 = LangGraphReactEngine(_FailThenStopLLM(), reg2)
    fail_pkts = []
    async for p in eng2.run_stream("新建一条 bug", project_id=1, locale="zh"):
        fail_pkts.append(p)
    engine_events = []
    for p in fail_pkts:
        if not isinstance(p, dict):
            continue
        pl = p.get("payload") or {}
        if p.get("type") == "stream" and pl.get("lane") == "engine" and isinstance(pl.get("data"), dict):
            engine_events.append(pl["data"].get("event"))
    assert "failure_edge" in engine_events, engine_events
    print("failure_edge_ok", [e for e in engine_events if e])

    # interrupt + langgraph_resume 快照（max_retries=0 → 首次失败即 interrupt）
    os.environ["LANGGRAPH_FAILURE_MAX_RETRIES"] = "0"

    class _OnceFailLLM:
        def chat_completion_with_tools(self, messages, tools, **kwargs):
            fn = SimpleNamespace(name="create", arguments='{"target":"bug","title":"x"}')
            tc = SimpleNamespace(id="i1", function=fn)
            msg = SimpleNamespace(content="try", tool_calls=[tc])
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    class _ResumeLLM:
        def __init__(self):
            self.seen_ids = False

        def chat_completion_with_tools(self, messages, tools, **kwargs):
            # 恢复后应看到此前 tool 消息
            for m in messages or []:
                if isinstance(m, dict) and m.get("role") == "tool":
                    self.seen_ids = True
            msg = SimpleNamespace(content="resumed ok", tool_calls=[])
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

    reg3 = ToolRegistry()
    reg3.register(_FailCreate(), quiet=True)
    eng3 = LangGraphReactEngine(_OnceFailLLM(), reg3)
    int_pkts = []
    async for p in eng3.run_stream("新建失败测 interrupt", project_id=1, locale="zh"):
        int_pkts.append(p)
    resume_states = []
    for p in int_pkts:
        pl = (p.get("payload") or {}) if isinstance(p, dict) else {}
        data = pl.get("data") if pl.get("lane") == "engine" else None
        if isinstance(data, dict) and data.get("event") == "langgraph_resume":
            resume_states.append(data.get("state"))
    assert resume_states and resume_states[0].get("messages"), resume_states
    assert resume_states[0].get("thread_id"), resume_states[0]
    print(
        "langgraph_resume_ok msgs",
        len(resume_states[0]["messages"]),
        "thread",
        resume_states[0].get("thread_id"),
    )

    rllm = _ResumeLLM()
    eng4 = LangGraphReactEngine(rllm, reg3)
    async for _ in eng4.run_stream(
        "请继续",
        project_id=1,
        locale="zh",
        langgraph_resume=resume_states[0],
        agent_session_id="smoke-resume",
    ):
        pass
    assert rllm.seen_ids, "resume should restore tool messages"
    print("langgraph_resume_restore_ok")

    # 纯单元：apply 保留 first_bug_id
    snap = build_langgraph_resume_snapshot(
        messages=[{"role": "user", "content": "x"}],
        result_context={"first_bug_id": 42},
        grep_tool_calls=1,
    )
    ap = apply_langgraph_resume(system_prompt="s", resume_state=snap, new_user_content="go")
    assert ap["result_context"]["first_bug_id"] == 42

    print("SMOKE_OK")


if __name__ == "__main__":
    asyncio.run(_main())
