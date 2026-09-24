# -*- coding: utf-8 -*-
"""CDP LLM 报文采集：解析与落盘自测（不依赖浏览器）。

运行：python tests/test_llm_capture.py
"""
import asyncio
import json
import os
import tempfile
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

_TMP = tempfile.mkdtemp(prefix="llm_capture_test_")
os.environ["BADCASE_LLM_EXCHANGE_DIR"] = _TMP

from agents.cdp import llm_capture as lc  # noqa: E402


def _sse(*chunks):
    lines = []
    for c in chunks:
        lines.append("data: " + (c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)))
        lines.append("")
    lines.append("data: [DONE]")
    return "\n".join(lines)


class _FakeReq:
    method = "POST"
    post_data = None
    timing = {"startTime": 100.0, "requestStart": 110.0, "responseStart": 250.0, "responseEnd": 900.0}


class _FakeResp:
    status = 200
    url = "https://api.example.com/v1/chat/completions"
    headers = {"content-type": "application/json"}
    request = _FakeReq()


def test_parse_sse_openai():
    raw = _sse(
        {"model": "gpt-4o-mini", "choices": [{"delta": {"role": "assistant", "content": "你好"}}]},
        {"model": "gpt-4o-mini", "choices": [{"delta": {"content": "，世界"}}]},
        {
            "model": "gpt-4o-mini",
            "choices": [{"delta": {}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )
    out = lc._parse_llm_sse(raw)
    assert out["text"] == "你好，世界", out
    assert out["model"] == "gpt-4o-mini", out
    assert out["finish_reason"] == "stop", out
    assert out["usage"]["total_tokens"] == 15, out


def test_parse_sse_tool_calls_accumulate():
    raw = _sse(
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"name": "get_weather", "arguments": '{"city":'}}]}}]},
        {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"北京"}'}}]}}]},
    )
    out = lc._parse_llm_sse(raw)
    assert len(out["tool_calls"]) == 1, out
    assert out["tool_calls"][0]["name"] == "get_weather", out
    assert "北京" in out["tool_calls"][0]["arguments"], out


def test_parse_sse_anthropic():
    raw = _sse(
        {"type": "message_start", "message": {"model": "claude-3-5-sonnet"}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hi"}},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}},
    )
    out = lc._parse_llm_sse(raw)
    assert out["text"] == "Hi", out
    assert out["model"] == "claude-3-5-sonnet", out
    assert out["finish_reason"] == "end_turn", out


def test_parse_sse_ignores_non_text_meta():
    raw = _sse(
        {"type": "ping"},
        {"model": "gpt-4o", "choices": [{"delta": {"content": "ok"}}]},
    )
    out = lc._parse_llm_sse(raw)
    assert out["text"] == "ok", out


def test_parse_json_response():
    obj = {
        "model": "qwen-max",
        "choices": [{"message": {"role": "assistant", "content": "答案"}, "finish_reason": "length"}],
        "usage": {"total_tokens": 99},
    }
    out = lc._parse_llm_json(obj)
    assert out["text"] == "答案", out
    assert out["model"] == "qwen-max", out
    assert out["finish_reason"] == "length", out


def test_parse_json_dashscope_style():
    obj = {"output": {"text": "通义答案"}, "usage": {"total_tokens": 7}}
    out = lc._parse_llm_json(obj)
    assert out["text"] == "通义答案", out
    assert out["usage"]["total_tokens"] == 7, out


def test_extract_request_fields():
    body = json.dumps(
        {
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 2048,
            "stream": True,
            "messages": [
                {"role": "system", "content": "你是测试助手"},
                {"role": "user", "content": "你好"},
                {"role": "user", "content": "第二问"},
            ],
            "tools": [
                {"type": "function", "function": {"name": "search"}},
                {"type": "function", "function": {"name": "calc"}},
            ],
        },
        ensure_ascii=False,
    )
    out = lc._extract_request(body)
    assert out["model"] == "gpt-4o", out
    assert out["params"]["temperature"] == 0.7, out
    assert out["params"]["max_tokens"] == 2048, out
    assert out["params"]["stream"] is True, out
    assert out["system_prompt"] == "你是测试助手", out
    assert out["messages_total"] == 3, out
    assert len(out["messages"]) == 2, out
    assert out["tools"] == ["search", "calc"], out


def test_extract_request_content_parts():
    body = json.dumps(
        {
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": "S1"}, {"type": "text", "text": "S2"}]},
                {"role": "user", "content": [{"type": "text", "text": "问题"}]},
            ]
        },
        ensure_ascii=False,
    )
    out = lc._extract_request(body)
    assert out["system_prompt"] == "S1\nS2", out
    assert out["messages"][0]["content"] == "问题", out


def test_extract_request_garbage():
    assert lc._extract_request(None)["model"] is None
    assert lc._extract_request("not-json")["messages_total"] == 0


def test_finalize_mismatch_truncation_and_persist():
    cap = lc.LlmCapture("sess_test1", project_id=7, declared={"model": "gpt-4o"})
    rec = cap._blank_record(_FakeResp())
    assert rec["ttfb_ms"] == 250, rec
    assert rec["duration_ms"] == 790, rec
    rec["response"] = {
        "model": "gpt-4o-mini",
        "text": "hi",
        "tool_calls": [],
        "finish_reason": "length",
        "usage": None,
    }
    cap._finalize(rec)
    assert rec["turn"] == 1, rec
    assert rec["model_mismatch"] is True, rec
    assert rec["truncated_by_max_tokens"] is True, rec

    items = lc.read_session_exchanges("sess_test1")
    assert len(items) == 1, items
    assert items[0]["session_id"] == "sess_test1", items
    assert items[0]["project_id"] == 7, items
    assert items[0]["declared"]["model"] == "gpt-4o", items

    s = lc.summarize_exchanges(items)
    assert s["exchanges"] == 1, s
    assert s["models"] == ["gpt-4o-mini"], s
    assert s["truncated"] == 1, s
    assert s["model_mismatch"] == 1, s


def test_finalize_no_mismatch_when_declared_absent():
    cap = lc.LlmCapture("sess_test2", project_id=None, declared={})
    rec = cap._blank_record(_FakeResp())
    rec["response"] = {"model": "gpt-4o", "text": "ok", "tool_calls": [], "finish_reason": "stop", "usage": None}
    cap._finalize(rec)
    assert rec["model_mismatch"] is False, rec
    assert rec["turn"] == 1, rec


def test_model_matches_normalization():
    assert lc._model_matches("gpt-4o", "gpt-4o-2024-08-06") is True
    assert lc._model_matches("GPT-4o", "gpt-4o") is True
    assert lc._model_matches("gpt-4o", "gpt-4o-mini") is False
    assert lc._model_matches("claude-3-5-sonnet", "claude-3-5-sonnet-20241022") is True
    assert lc._model_matches("qwen-max", "qwen-max-latest") is True
    assert lc._model_matches("openai/gpt-4o", "gpt-4o") is True
    assert lc._model_matches("", "gpt-4o") is True
    assert lc._model_matches("gpt-4o", None) is True


def test_candidate_filter():
    cap = lc.LlmCapture("sess_test3")

    class R:
        def __init__(self, url, ct, method="POST"):
            self.url = url
            self.headers = {"content-type": ct}
            self.request = type("Q", (), {"method": method})()

    assert cap._candidate(R("https://x/api/chat", "application/json")) is True
    assert cap._candidate(R("https://x/sse", "text/event-stream")) is True
    assert cap._candidate(R("https://x/app.js", "application/javascript", "GET")) is False
    assert cap._candidate(R("https://x/logo.png", "image/png", "GET")) is False
    assert cap._candidate(R("https://x/page", "text/html", "GET")) is False


class _FakePage:
    url = "about:blank"

    def __init__(self):
        self.listeners = {}

    def on(self, event, callback):
        self.listeners.setdefault(event, []).append(callback)

    def remove_listener(self, event, callback):
        self.listeners[event].remove(callback)

    def emit(self, event, value):
        for callback in list(self.listeners.get(event, [])):
            callback(value)

    async def title(self):
        return "test page"


class _StreamResp(_FakeResp):
    headers = {"content-type": "text/event-stream", "set-cookie": "secret"}

    def __init__(self, model="gpt-4o", blocked=False):
        self.request = _FakeReq()
        self.request.post_data = json.dumps({"model": model, "cookie": "secret"})
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        if not blocked:
            self.release.set()
        self.model = model

    async def body(self):
        self.started.set()
        await self.release.wait()
        return _sse({"model": self.model, "choices": [{"delta": {"content": "ok"}}]}).encode()


def _sid():
    return "sess_" + uuid.uuid4().hex


def test_ensure_capture_updates_project_without_rewriting_history():
    page, sid = _FakePage(), _sid()
    declared = {"model": "gpt-4o", "params": {"temperature": 0.2}}
    cap = lc.ensure_capture(page, sid, project_id=1, cdp_run_id="run-a", declared=declared)
    try:
        rec = cap._blank_record(_FakeResp())
        cap._finalize(rec)
        assert lc.ensure_capture(page, sid, project_id=2, cdp_run_id="run-b") is cap
        assert (cap.project_id, cap.cdp_run_id, cap.declared) == (2, "run-b", {})
        assert (rec["project_id"], rec["cdp_run_id"], rec["declared"]) == (1, "run-a", declared)
        assert all(len(callbacks) == 1 for callbacks in page.listeners.values())
        assert uuid.UUID(rec["exchange_id"]).version == 4
        assert cap._blank_record(_FakeResp())["exchange_id"] != rec["exchange_id"]
        lc.ensure_capture(page, sid, project_id=2)
        assert cap.cdp_run_id is None
        lc.ensure_capture(page, sid)
        assert cap.project_id is None
    finally:
        lc.drop_capture(sid)


def test_request_start_freezes_project_run_and_declared_before_response():
    async def run():
        page = _FakePage()
        cap = lc.LlmCapture(_sid(), project_id=1, cdp_run_id="run-a", declared={
            "model": "gpt-4o", "params": {"temperature": 0.2},
        })
        cap.attach(page)
        resp = _StreamResp()
        page.emit("request", resp.request)
        cap.declared["params"]["temperature"] = 0.9
        cap.set_context(project_id=2, cdp_run_id="run-b", declared={"model": "gpt-4o-mini"})
        page.emit("response", resp)
        # Even a switch before the capture coroutine is scheduled cannot rebind it.
        cap.set_context(project_id=3, cdp_run_id="run-c")
        await cap.drain()
        rec = cap.exchanges()[0]
        assert (rec["project_id"], rec["cdp_run_id"]) == (1, "run-a")
        assert rec["declared"] == {"model": "gpt-4o", "params": {"temperature": 0.2}}
        assert rec["model_mismatch"] is False
        assert "headers" not in rec and "cookies" not in rec
        assert "secret" not in json.dumps(rec)
        cap.detach()

    asyncio.run(run())


def test_run_switch_while_stream_body_pending_keeps_declared_mismatch():
    async def run():
        page = _FakePage()
        cap = lc.LlmCapture(_sid(), project_id=7, cdp_run_id="run-a", declared={"model": "gpt-4o"})
        cap.attach(page)
        resp = _StreamResp(model="gpt-4o-mini", blocked=True)
        page.emit("request", resp.request)
        page.emit("response", resp)
        await asyncio.wait_for(resp.started.wait(), timeout=2)
        cap.set_context(project_id=7, cdp_run_id="run-b", declared={"model": "gpt-4o-mini"})
        resp.release.set()
        await cap.drain()
        rec = cap.exchanges()[0]
        assert rec["cdp_run_id"] == "run-a"
        assert rec["declared"] == {"model": "gpt-4o"}
        assert rec["model_mismatch"] is True
        next_resp = _StreamResp(model="gpt-4o-mini")
        page.emit("request", next_resp.request)
        page.emit("response", next_resp)
        await cap.drain()
        assert cap.exchanges()[1]["cdp_run_id"] == "run-b"
        assert cap.exchanges()[1]["model_mismatch"] is False
        cap.detach()

    asyncio.run(run())


def test_requests_before_run_or_listener_are_not_backfilled():
    async def run():
        page = _FakePage()
        cap = lc.LlmCapture(_sid(), project_id=7)
        cap.attach(page)
        started = _StreamResp()
        page.emit("request", started.request)
        cap.set_context(project_id=7, cdp_run_id="new-run", declared={"model": "gpt-4o"})
        page.emit("response", started)
        page.emit("response", _StreamResp())  # No observed request-start event.
        await cap.drain()
        first, unknown = cap.exchanges()
        assert (first["project_id"], first["cdp_run_id"], first["declared"]) == (7, None, {})
        assert (unknown["project_id"], unknown["cdp_run_id"], unknown["declared"]) == (None, None, {})
        assert lc.read_session_exchanges(cap.session_id, project_id=7, cdp_run_id="new-run") == []
        cap.detach()

    asyncio.run(run())


def test_declared_input_and_record_are_independent_snapshots():
    declared = {"model": "gpt-4o", "params": {"temperature": 0.2}}
    cap = lc.LlmCapture(_sid(), project_id=1, declared=declared)
    declared["params"]["temperature"] = 1
    rec = cap._blank_record(_FakeResp())
    cap.set_context(project_id=1, cdp_run_id="next")
    assert cap.declared["params"]["temperature"] == 0.2
    cap.declared["params"]["temperature"] = 0.8
    cap.set_context(project_id=1, declared={})
    rec["response"]["model"] = "gpt-4o-mini"
    cap._finalize(rec)
    assert rec["declared"]["params"]["temperature"] == 0.2
    assert rec["model_mismatch"] is True
    assert cap.declared == {}


def test_drop_capture_detaches_without_cancelling_pending_body():
    async def run():
        page, sid = _FakePage(), _sid()
        cap = lc.ensure_capture(page, sid, project_id=7, cdp_run_id="run-a")
        resp = _StreamResp(blocked=True)
        page.emit("request", resp.request)
        page.emit("response", resp)
        await asyncio.wait_for(resp.started.wait(), timeout=2)
        lc.drop_capture(sid)
        assert lc.get_capture(sid) is None
        assert all(not callbacks for callbacks in page.listeners.values())
        resp.release.set()
        await cap.drain()
        assert len(lc.read_session_exchanges(sid, project_id=7, cdp_run_id="run-a")) == 1

    asyncio.run(run())


def test_request_tracking_cleans_finished_and_failed_requests():
    page = _FakePage()
    cap = lc.LlmCapture(_sid())
    cap.attach(page)
    for event in ("requestfinished", "requestfailed"):
        request = _FakeReq()
        page.emit("request", request)
        assert len(cap._request_contexts) == 1
        page.emit(event, request)
        assert len(cap._request_contexts) == 0
    cap.detach()


def test_read_filters_exact_project_run_session_before_bounded_limit():
    from utils.observability import append_llm_exchange

    sid = _sid()
    rows = [
        {"session_id": sid},  # legacy: no project/run
        {"session_id": sid, "project_id": None, "cdp_run_id": "run-a"},
        {"session_id": sid, "project_id": 7, "cdp_run_id": None},
        {"session_id": sid, "project_id": 7, "cdp_run_id": "run-a", "n": 1},
        {"session_id": sid, "project_id": 7, "cdp_run_id": "run-a", "n": 2},
        {"session_id": sid, "project_id": 7, "cdp_run_id": "run-b"},
        {"session_id": sid, "project_id": 8, "cdp_run_id": "run-a"},
        {"session_id": sid, "project_id": "7", "cdp_run_id": "run-a"},
        {"session_id": sid + "!", "project_id": 7, "cdp_run_id": "run-a"},
    ]
    for row in rows:
        append_llm_exchange(row)
    with patch.object(lc, "deque", wraps=lc.deque) as bounded:
        items = lc.read_session_exchanges(sid, 1, project_id=7, cdp_run_id="run-a")
        bounded.assert_called_once_with(maxlen=1)
    assert [item["n"] for item in items] == [2]
    assert len(lc.read_session_exchanges(sid, project_id=7, cdp_run_id="run-a")) == 2
    assert lc.read_session_exchanges(sid, project_id=9, cdp_run_id="run-a") == []
    assert lc.read_session_exchanges(sid, 2) == rows[6:8]
    assert len(lc.read_session_exchanges(sid)) == 8
    assert len(lc.read_session_exchanges(sid, 0)) == 8
    assert lc.read_session_exchanges(sid, -1, project_id=7, cdp_run_id="run-a") == [rows[4]]


def _manager_with_capture(*, owner="user:1"):
    from agents.cdp.session_manager import BrowserSession, CdpSessionManager

    mgr = CdpSessionManager()
    page, sid = _FakePage(), _sid()
    cap = lc.ensure_capture(page, sid, project_id=7, cdp_run_id="old-run")
    mgr._sessions[sid] = BrowserSession(
        session_id=sid, playwright=None, browser=None, context=None, page=page,
        owner_key=owner, llm_capture=cap,
    )
    return mgr, sid, cap


def test_manager_create_attaches_context_before_initial_navigation():
    from agents.cdp.session_manager import CdpSessionManager

    async def run():
        mgr = CdpSessionManager()
        page = _FakePage()
        context = SimpleNamespace(new_page=AsyncMock(return_value=page))
        seen = []

        async def navigate(sid, url, **kwargs):
            cap = lc.get_capture(sid)
            seen.append((cap.project_id, cap.cdp_run_id, bool(page.listeners)))
            return {"success": True}

        with patch.object(mgr, "_start_sweeper"), \
             patch.object(mgr, "_resolve_connection_mode", AsyncMock(return_value="launch")), \
             patch.object(mgr, "_new_browser_context", AsyncMock(return_value=(None, context))), \
             patch.object(mgr, "ensure_console_hook", AsyncMock()), \
             patch.object(mgr, "navigate", side_effect=navigate):
            result = await mgr.create(
                url="https://example.test", owner_key="user:1", project_id=7, cdp_run_id="run-a"
            )
        assert result["success"]
        assert seen == [(7, "run-a", True)]
        lc.drop_capture(result["session_id"])

    asyncio.run(run())


def test_tool_create_uses_trusted_result_context_run():
    from agents.tools.cdp_tool import CdpTool

    async def run():
        tool = CdpTool()
        tool._mgr = SimpleNamespace(create=AsyncMock(return_value={"success": True}))
        await tool.execute(
            "session", project_id=7, user_id=1, cdp_run_id="untrusted",
            result_context={"cdp_test_run_id": "run-a"},
        )
        tool._mgr.create.assert_awaited_once_with(
            url=None, headless=None, storage_state_path=None, owner_key="user:1",
            project_id=7, cdp_run_id="run-a",
        )

    asyncio.run(run())


def test_tool_rebinds_owned_session_before_action_and_clears_stale_run():
    from agents.tools.cdp_tool import CdpTool

    async def run():
        mgr, sid, cap = _manager_with_capture()
        tool = CdpTool()
        tool._mgr = mgr
        seen = []

        async def tabs(**kwargs):
            seen.append((cap.project_id, cap.cdp_run_id, kwargs["session_id"]))
            return {"success": True}

        try:
            with patch.object(tool, "_tabs", side_effect=tabs):
                await tool.execute("tabs", user_id=1, project_id=8,
                                   result_context={"cdp_test_run_id": "new-run"})
                await tool.execute("tabs", session_id=sid, user_id=1, project_id=8,
                                   cdp_run_id="untrusted", result_context={})
            assert seen == [(8, "new-run", sid), (8, None, sid)]
        finally:
            lc.drop_capture(sid)

    asyncio.run(run())


def test_tool_rejects_foreign_session_before_changing_capture():
    from agents.tools.cdp_tool import CdpTool

    async def run():
        mgr, sid, cap = _manager_with_capture()
        tool = CdpTool()
        tool._mgr = mgr
        try:
            with patch.object(mgr, "ensure_llm_capture", wraps=mgr.ensure_llm_capture) as ensure:
                result = await tool.execute("tabs", session_id=sid, user_id=2, project_id=8,
                                            result_context={"cdp_test_run_id": "foreign"})
                assert result["success"] is False
                ensure.assert_not_called()
            assert (cap.project_id, cap.cdp_run_id) == (7, "old-run")
        finally:
            lc.drop_capture(sid)

    asyncio.run(run())


def test_batch_subaction_cannot_override_trusted_capture_context():
    from agents.tools.cdp_tool import CdpTool

    async def run():
        mgr, sid, cap = _manager_with_capture()
        tool = CdpTool()
        tool._mgr = mgr
        try:
            with patch.object(tool, "_tabs", AsyncMock(return_value={"success": True})):
                result = await tool.execute(
                    "batch", session_id=sid, user_id=1, project_id=7,
                    result_context={"cdp_test_run_id": "run-a"},
                    actions=[{"action": "tabs", "project_id": 99, "user_id": 2,
                              "result_context": {"cdp_test_run_id": "foreign"}}],
                )
            assert result["success"]
            assert (cap.project_id, cap.cdp_run_id) == (7, "run-a")
        finally:
            lc.drop_capture(sid)

    asyncio.run(run())


def test_nested_testcase_actions_keep_result_context():
    from agents.tools.cdp_tool import CdpTool

    async def run():
        tool = CdpTool()
        context = {"cdp_test_run_id": "run-a"}
        for method, target, extra in (
            (tool._run_step, "run_testcase_step", {"step": "click button"}),
            (tool._run_testcase, "run_testcase_steps", {"steps": ["click button"]}),
        ):
            with patch("agents.cdp.step_driver." + target, AsyncMock(return_value={})) as driver:
                await method(session_id="known-session", user_id=1, project_id=7,
                             result_context=context, **extra)
                assert driver.call_args.kwargs["owner_kwargs"]["result_context"] is context

    asyncio.run(run())


def test_postprocess_binds_observation_session_after_run_creation_only():
    from agents.cdp.postprocess import enrich_cdp_observation
    from agents.cdp.session_manager import CdpSessionManager
    from contextlib import ExitStack

    async def run():
        mgr, sid, cap = _manager_with_capture()
        observation = {"success": True, "action": "create", "session_id": sid}
        result_context = {}
        recorder = MagicMock()

        def ensure_run(*args, **kwargs):
            assert cap.cdp_run_id == "old-run"
            kwargs["result_context"]["cdp_test_run_id"] = "new-run"

        async def auto_run(engine, observation, **kwargs):
            assert cap.cdp_run_id == "new-run"
            return observation

        old = cap._blank_record(_FakeResp())
        cap._finalize(old)
        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(CdpSessionManager, "get", return_value=mgr))
                stack.enter_context(patch("agents.cdp.test_task.ensure_cdp_test_task", side_effect=ensure_run))
                stack.enter_context(patch("agents.cdp.test_task.record_cdp_test_task_step"))
                stack.enter_context(patch("agents.cdp.auto_run_testcase.maybe_auto_run_testcases", side_effect=auto_run))
                stack.enter_context(patch("agents.cdp.auto_run_explore.maybe_auto_run_explore", side_effect=auto_run))
                stack.enter_context(patch("agents.cdp.postprocess.get_cdp_evidence_recorder", return_value=recorder))
                await enrich_cdp_observation(
                    SimpleNamespace(user_id=1), observation, action="session",
                    params={"session_id": "not-the-observation-session"}, project_id=7,
                    result_context=result_context,
                )
            assert cap.cdp_run_id == "new-run"
            assert old["cdp_run_id"] == "old-run"
            assert len(lc.read_session_exchanges(sid, project_id=7, cdp_run_id="old-run")) == 1
            assert lc.read_session_exchanges(sid, project_id=7, cdp_run_id="new-run") == []
        finally:
            lc.drop_capture(sid)

    asyncio.run(run())


def test_postprocess_does_not_bind_foreign_missing_or_guessed_session():
    from agents.cdp.postprocess import enrich_cdp_observation
    from agents.cdp.session_manager import CdpSessionManager
    from contextlib import ExitStack

    async def run():
        mgr, sid, cap = _manager_with_capture()

        async def passthrough(engine, observation, **kwargs):
            return observation

        try:
            with ExitStack() as stack:
                stack.enter_context(patch.object(CdpSessionManager, "get", return_value=mgr))
                stack.enter_context(patch("agents.cdp.test_task.ensure_cdp_test_task"))
                stack.enter_context(patch("agents.cdp.test_task.record_cdp_test_task_step"))
                stack.enter_context(patch("agents.cdp.auto_run_testcase.maybe_auto_run_testcases", side_effect=passthrough))
                stack.enter_context(patch("agents.cdp.auto_run_explore.maybe_auto_run_explore", side_effect=passthrough))
                stack.enter_context(patch("agents.cdp.postprocess.get_cdp_evidence_recorder", return_value=MagicMock()))
                ensure = stack.enter_context(patch.object(mgr, "ensure_llm_capture", wraps=mgr.ensure_llm_capture))
                for user_id, observation in (
                    (2, {"session_id": sid}),
                    (1, {"session_id": "closed-session"}),
                    (1, {}),
                ):
                    await enrich_cdp_observation(
                        SimpleNamespace(user_id=user_id), observation, action="session",
                        params={"session_id": sid}, project_id=8,
                        result_context={"cdp_test_run_id": "new-run"},
                    )
                    assert (cap.project_id, cap.cdp_run_id) == (7, "old-run")
                ensure.assert_not_called()
                # A known, owned session with no current run clears the previous run.
                await enrich_cdp_observation(
                    SimpleNamespace(user_id=1), {"session_id": sid}, action="session",
                    project_id=7, result_context={},
                )
                assert cap.cdp_run_id is None
        finally:
            lc.drop_capture(sid)

    asyncio.run(run())


def test_recovery_reattaches_and_close_keeps_persisted_records():
    async def run():
        mgr, sid, cap = _manager_with_capture()
        old = cap._blank_record(_FakeResp())
        cap._finalize(old)
        session = mgr.get_session(sid)
        session.local_mode = True
        page = _FakePage()
        context = SimpleNamespace()
        slot = SimpleNamespace(browser=SimpleNamespace(contexts=[context]))
        with patch.object(mgr, "_ensure_local_browser", AsyncMock(return_value=slot)), \
             patch.object(mgr, "_choose_local_page", AsyncMock(return_value=(page, False))):
            await mgr._recover_local_session(session)
        assert session.llm_capture is cap
        assert len(page.listeners["request"]) == 1
        resp = _StreamResp()
        page.emit("request", resp.request)
        page.emit("response", resp)
        await cap.drain()
        result = await mgr.close(sid, owner_key="user:1")
        assert result["success"] and lc.get_capture(sid) is None
        assert all(not callbacks for callbacks in page.listeners.values())
        records = lc.read_session_exchanges(sid, project_id=7, cdp_run_id="old-run")
        assert len(records) == 2
        assert records[0]["exchange_id"] == old["exchange_id"]

    asyncio.run(run())


if __name__ == "__main__":
    import sys
    import traceback

    names = [n for n in list(globals()) if n.startswith("test_") and callable(globals()[n])]
    fails = 0
    for name in sorted(names):
        try:
            globals()[name]()
            print(f"[PASS] {name}")
        except Exception:
            fails += 1
            print(f"[FAIL] {name}")
            traceback.print_exc()
    print(f"\n{len(names) - fails}/{len(names)} passed")
    sys.exit(1 if fails else 0)
