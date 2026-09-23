# -*- coding: utf-8 -*-
"""CDP LLM 报文采集：解析与落盘自测（不依赖浏览器）。

运行：python tests/test_llm_capture.py
"""
import json
import os
import tempfile

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
