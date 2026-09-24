# -*- coding: utf-8 -*-
"""CDP 层 LLM 报文采集：把被测系统的「对话原始报文」变成可判定的资产。

挂在 Playwright Page 上监听响应 → 过滤 LLM 接口 → 解析模型/参数/输出/工具调用/时延
→ 内存缓冲（供 Agent 即时读取）+ 落盘 observability/llm_exchange/（供判定与证据回溯）。

设计取舍：
- 黑盒零接入：只依赖浏览器能看到的报文，不要求被测方装 SDK
- 原文优先：报文是没被前端粉饰的证据（前端渲染可能吞错误、截断文本）
- 申报 vs 实际：项目里填写的模型/参数作为 declared 一起落盘，实际报文里的 model
  与之不一致时标记 model_mismatch（模型降级检测）

环境变量：
- BADCASE_LLM_CAPTURE_ENABLED：默认 1
- BADCASE_LLM_CAPTURE_FULL：默认 0；1=不截断原文
- BADCASE_LLM_CAPTURE_TEXT_KEEP：每段文本保留字符数，默认 4000
- BADCASE_LLM_CAPTURE_MESSAGES_KEEP：请求 messages 保留条数，默认 8
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from weakref import WeakKeyDictionary

# LLM 接口 URL 特征（自研接口 URL 常无这些词，故另有「POST+JSON 候选」兜底）
LLM_URL_HINTS = (
    "chat/completions",
    "/completions",
    "/messages",
    "/generate",
    "/chat",
    "ai/",
    "llm",
    "inference",
    "assistant",
    "stream",
)

_SSE_CT = "text/event-stream"
_JSON_CT_HINTS = ("application/json", "text/json", "application/x-ndjson")

# 响应里出现这些字段才认为是 LLM 报文（用于放行 URL 无特征的 POST 接口）
_LLM_FIELD_HINTS = (
    "choices",
    "usage",
    "finish_reason",
    "tool_calls",
    "completion",
    "output_text",
    "content_block",
    "stop_reason",
)

_STATIC_EXT_RE = re.compile(
    r"\.(js|css|png|jpe?g|gif|svg|webp|woff2?|ttf|ico|map|mp4|webm)(\?|$)", re.I
)

MAX_BODY_CHARS = 2_000_000
BODY_TIMEOUT_SEC = 90.0
MAX_EXCHANGES = 200


def _env_flag(name: str, default: str = "1") -> bool:
    return (os.getenv(name, default) or default).strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _text_keep() -> int:
    try:
        return max(200, int(os.getenv("BADCASE_LLM_CAPTURE_TEXT_KEEP", "4000")))
    except Exception:
        return 4000


def _messages_keep() -> int:
    try:
        return max(0, int(os.getenv("BADCASE_LLM_CAPTURE_MESSAGES_KEEP", "8")))
    except Exception:
        return 8


def _clip(s: Any, limit: Optional[int] = None) -> str:
    if s is None:
        return ""
    if not isinstance(s, str):
        try:
            s = json.dumps(s, ensure_ascii=False)
        except Exception:
            s = str(s)
    if _env_flag("BADCASE_LLM_CAPTURE_FULL", "0"):
        return s
    n = limit or _text_keep()
    return s if len(s) <= n else s[:n] + f"…[截断 {len(s) - n} 字]"


def _as_dict(obj: Any) -> Dict[str, Any]:
    return obj if isinstance(obj, dict) else {}


def _deep_find_str(obj: Any, keys: Set[str], _depth: int = 0) -> str:
    """在嵌套结构里找第一个命中 keys 的字符串值（兜底抽取文本）。"""
    if _depth > 6:
        return ""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in keys and isinstance(v, str) and v.strip():
                return v
        for v in obj.values():
            found = _deep_find_str(v, keys, _depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj[:20]:
            found = _deep_find_str(item, keys, _depth + 1)
            if found:
                return found
    return ""


def _content_to_text(content: Any) -> str:
    """content 可能是 str，也可能是 [{type:'text',text:...}] 之类多段结构。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in ("text", "content", "value"):
                    v = item.get(key)
                    if isinstance(v, str) and v:
                        parts.append(v)
                        break
        return "\n".join(parts)
    if isinstance(content, dict):
        return _deep_find_str(content, {"text", "content", "value"}) or ""
    return ""


def _extract_message_text(msg: Dict[str, Any]) -> str:
    """从一条 message/choice 里取正文（兼容 OpenAI / Anthropic / DashScope）。"""
    if not isinstance(msg, dict):
        return ""
    for key in ("content", "text", "output_text", "reasoning_content"):
        if key in msg:
            t = _content_to_text(msg.get(key))
            if t:
                return t
    inner = msg.get("message")
    if isinstance(inner, dict):
        return _extract_message_text(inner)
    return _deep_find_str(msg, {"content", "text", "output_text"})


def _extract_delta_text(chunk: Dict[str, Any]) -> str:
    """从流式 chunk 里取增量文本。"""
    if not isinstance(chunk, dict):
        return ""
    for key in ("delta", "message", "content_block"):
        inner = chunk.get(key)
        if isinstance(inner, dict):
            t = _extract_message_text(inner)
            if t:
                return t
    # DashScope / 自研：output.text 或 choices[].message.content
    output = chunk.get("output")
    if isinstance(output, dict):
        t = _extract_message_text(output)
        if t:
            return t
    for key in ("choices", "outputs", "content"):
        v = chunk.get(key)
        if isinstance(v, list):
            for item in v:
                t = _extract_message_text(_as_dict(item))
                if t:
                    return t
        elif isinstance(v, str) and v:
            return v
    # 真正的最末：仅当 chunk 自身像「消息体」时才深挖，避免把 usage 之类当正文
    if any(k in chunk for k in ("role", "message", "content", "text")):
        return _extract_message_text(chunk)
    return ""


def _tool_call_containers(obj: Any, _depth: int = 0) -> List[Any]:
    """收集可能装着 tool_calls 的容器（兼容各家不同的包裹层级）。"""
    if not isinstance(obj, dict) or _depth > 6:
        return []
    out: List[Any] = []
    for key in ("tool_calls", "tools_called", "function_call"):
        if key in obj:
            out.append(obj[key])
    for key in ("delta", "message", "output", "data", "choices", "outputs", "content"):
        v = obj.get(key)
        items = v if isinstance(v, list) else [v]
        for item in items[:10]:
            if isinstance(item, dict):
                out.extend(_tool_call_containers(item, _depth + 1))
    return out


def _extract_tool_calls(obj: Dict[str, Any], acc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """累积工具调用（流式会被拆成多个 delta 片段）。"""
    out: Dict[str, Any] = acc if isinstance(acc, dict) else {}
    if not isinstance(obj, dict):
        return out
    for cand in _tool_call_containers(obj):
        items = cand if isinstance(cand, list) else [cand]
        for item in items:
            if not isinstance(item, dict):
                continue
            fn = _as_dict(item.get("function"))
            name = str(item.get("name") or fn.get("name") or "").strip()
            args = fn.get("arguments") or item.get("arguments") or item.get("input") or ""
            if isinstance(args, (dict, list)):
                try:
                    args = json.dumps(args, ensure_ascii=False)
                except Exception:
                    args = str(args)
            idx = str(item.get("index") if item.get("index") is not None else len(out))
            slot = out.setdefault(idx, {"name": "", "arguments": ""})
            if name:
                slot["name"] = name
            if args:
                slot["arguments"] = str(slot.get("arguments") or "") + str(args)
    return out


def _usage(obj: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    u = obj.get("usage")
    if isinstance(u, dict) and u:
        return u
    out = obj.get("output")
    if isinstance(out, dict):
        u = out.get("usage")
        if isinstance(u, dict) and u:
            return u
    return None


def _finish_reason(obj: Any, _depth: int = 0) -> Optional[str]:
    """取结束原因（兼容 choices[].finish_reason / delta.stop_reason 等包裹）。"""
    if not isinstance(obj, dict) or _depth > 6:
        return None
    for key in ("finish_reason", "stop_reason"):
        v = obj.get(key)
        if isinstance(v, str) and v:
            return v
    for key in ("delta", "message", "output", "choices", "outputs"):
        v = obj.get(key)
        items = v if isinstance(v, list) else [v]
        for item in items[:10]:
            fr = _finish_reason(item, _depth + 1)
            if fr:
                return fr
    return None


def _parse_llm_json(obj: Dict[str, Any]) -> Dict[str, Any]:
    """解析非流式 JSON 响应。"""
    text = _extract_message_text(obj)
    tool_calls = _extract_tool_calls(obj)
    fr = _finish_reason(obj)
    return {
        "model": obj.get("model") or None,
        "text": _clip(text),
        "tool_calls": _finalize_tool_calls(tool_calls),
        "finish_reason": fr,
        "usage": _usage(obj),
    }


def _parse_llm_sse(raw: str) -> Dict[str, Any]:
    """解析 SSE 流：逐行取 data:，拼接增量文本。"""
    parts: List[str] = []
    model: Optional[str] = None
    fr: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    tool_acc: Dict[str, Any] = {}
    chunk_count = 0
    for line in raw.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload in ("[DONE]", "[done]"):
            continue
        try:
            chunk = json.loads(payload)
        except Exception:
            continue
        if not isinstance(chunk, dict):
            continue
        chunk_count += 1
        if not model:
            model = chunk.get("model")
            if not model:
                msg = chunk.get("message")
                if isinstance(msg, dict):
                    model = msg.get("model")
        delta = _extract_delta_text(chunk)
        if delta:
            parts.append(delta)
        tool_acc = _extract_tool_calls(chunk, tool_acc)
        fr = _finish_reason(chunk) or fr
        usage = _usage(chunk) or usage
    return {
        "model": model,
        "text": _clip("".join(parts)),
        "tool_calls": _finalize_tool_calls(tool_acc),
        "finish_reason": fr,
        "usage": usage,
        "chunk_count": chunk_count,
    }


def _finalize_tool_calls(acc: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for _idx, slot in sorted((acc or {}).items(), key=lambda kv: str(kv[0])):
        if not isinstance(slot, dict):
            continue
        name = str(slot.get("name") or "").strip()
        if not name:
            continue
        args = slot.get("arguments") or ""
        out.append({"name": name, "arguments": _clip(args, 1000)})
    return out


def _extract_request(post_data: Optional[str]) -> Dict[str, Any]:
    """从请求体抽模型/参数/system prompt/messages 概要。"""
    out: Dict[str, Any] = {
        "model": None,
        "params": {},
        "system_prompt": "",
        "messages": [],
        "messages_total": 0,
        "tools": [],
    }
    if not post_data:
        return out
    try:
        body = json.loads(post_data)
    except Exception:
        return out
    if not isinstance(body, dict):
        return out

    out["model"] = body.get("model") or None
    for key in ("temperature", "top_p", "top_k", "max_tokens", "max_output_tokens", "stream", "seed", "presence_penalty", "frequency_penalty"):
        if key in body:
            out["params"][key] = body[key]

    msgs = body.get("messages") or body.get("input") or []
    if isinstance(msgs, str):
        msgs = [{"role": "user", "content": msgs}]
    if isinstance(msgs, list):
        out["messages_total"] = len(msgs)
        keep = _messages_keep()
        for m in msgs[-keep:] if keep else []:
            if not isinstance(m, dict):
                continue
            role = str(m.get("role") or m.get("type") or "")
            text = _extract_message_text(m)
            if not text:
                continue
            if role == "system" and not out["system_prompt"]:
                out["system_prompt"] = _clip(text)
                continue
            out["messages"].append({"role": role, "content": _clip(text, 2000)})
    if not out["system_prompt"]:
        sp = body.get("system") or body.get("system_prompt")
        if isinstance(sp, str):
            out["system_prompt"] = _clip(sp)
        elif isinstance(sp, list):
            out["system_prompt"] = _clip(_content_to_text(sp))

    tools = body.get("tools") or body.get("functions") or []
    if isinstance(tools, list):
        names: List[str] = []
        for t in tools:
            if not isinstance(t, dict):
                continue
            fn = _as_dict(t.get("function"))
            name = fn.get("name") or t.get("name")
            if name:
                names.append(str(name))
        out["tools"] = names[:30]
    return out


def _looks_like_llm(resp_meta: Dict[str, Any], req_info: Dict[str, Any]) -> bool:
    """判定这条报文是不是 LLM 调用（用于放行无 URL 特征的 POST 接口）。"""
    if resp_meta.get("looking_llm"):
        return True
    if req_info.get("model"):
        return True
    keys = resp_meta.get("_top_keys") or []
    return any(k in keys for k in _LLM_FIELD_HINTS)


def _timing_ms(response: Any) -> Dict[str, Any]:
    """Playwright timing：startTime 是 epoch ms，其余字段已是「相对 startTime 的毫秒偏移」。"""
    try:
        t = response.request.timing or {}
        rs = t.get("responseStart", -1)
        req_start = t.get("requestStart", -1)
        re = t.get("responseEnd", -1)
        ttfb = int(rs) if rs is not None and rs >= 0 else None
        dur = int(re - req_start) if (re >= 0 and req_start >= 0) else None
        return {"ttfb_ms": ttfb, "duration_ms": dur}
    except Exception:
        return {"ttfb_ms": None, "duration_ms": None}


_MODEL_TAIL_RE = re.compile(
    r"[-_@:](20\d{2}[-_]\d{2}[-_]\d{2}|\d{8}|latest|preview|stable|v\d+(?:\.\d+)*)$", re.I
)


def _normalize_model(s: Any) -> str:
    """归一化模型名：小写，去掉日期/快照/版本后缀（gpt-4o-2024-08-06 → gpt-4o）。"""
    v = str(s or "").strip().lower()
    prev = None
    while prev != v:
        prev = v
        v = _MODEL_TAIL_RE.sub("", v).strip()
    return v


def _model_matches(declared: Any, actual: Any) -> bool:
    """申报模型与实际模型是否同一模型（忽略快照日期与供应商前缀）。

    注意不能用子串判断：gpt-4o 是 gpt-4o-mini 的子串，但两者不同模型。
    """
    d = _normalize_model(declared)
    a = _normalize_model(actual)
    if not d or not a:
        return True
    if d == a:
        return True
    return a.endswith("/" + d) or d.endswith("/" + a)


class LlmCapture:
    """单个浏览器会话的 LLM 报文采集器。"""

    def __init__(
        self,
        session_id: str,
        *,
        project_id: Optional[int] = None,
        cdp_run_id: Optional[str] = None,
        declared: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.session_id = session_id
        self.project_id = project_id
        self.cdp_run_id = cdp_run_id
        self.declared: Dict[str, Any] = deepcopy(declared) if declared is not None else {}
        self._pages: Dict[int, Any] = {}
        self._request_contexts: WeakKeyDictionary = WeakKeyDictionary()
        self._items: List[Dict[str, Any]] = []
        self._tasks: Set[asyncio.Task] = set()
        self._lock = asyncio.Lock()
        self._skipped = 0

    def set_context(
        self,
        *,
        project_id: Optional[int] = None,
        cdp_run_id: Optional[str] = None,
        declared: Optional[Dict[str, Any]] = None,
    ) -> None:
        """只更新后续请求的上下文；None 清空归属，不回填历史/在途报文。

        同项目未传 declared 时保留申报值；换项目则清空，显式 {} 也可清空。
        """
        if declared is not None:
            self.declared = deepcopy(declared)
        elif project_id != self.project_id:
            self.declared = {}
        self.project_id = project_id
        self.cdp_run_id = cdp_run_id

    def _context_snapshot(self) -> Dict[str, Any]:
        return {
            "project_id": self.project_id,
            "cdp_run_id": self.cdp_run_id,
            "declared": deepcopy(self.declared),
        }

    # ---------- 挂载 ----------

    def attach(self, page: Any) -> None:
        """请求事件同步冻结归属；响应事件仍按原规则决定是否采集报文。"""
        if page is None or id(page) in self._pages:
            return

        def _on_request(request: Any) -> None:
            self._request_contexts[request] = self._context_snapshot()

        def _on_request_done(request: Any) -> None:
            self._request_contexts.pop(request, None)

        def _on_response(response: Any) -> None:
            try:
                # 未观察到请求开始（例如接入时已在途）时不可猜测/回填归属。
                context = self._request_contexts.pop(response.request, None)
                if context is None:
                    context = {"project_id": None, "cdp_run_id": None, "declared": {}}
                if not self._candidate(response):
                    return
                task = asyncio.ensure_future(self._capture(response, context=context))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
            except Exception:
                pass

        listeners = {
            "request": _on_request,
            "response": _on_response,
            "requestfinished": _on_request_done,
            "requestfailed": _on_request_done,
        }
        try:
            for event, callback in listeners.items():
                page.on(event, callback)
            self._pages[id(page)] = (page, listeners)
        except Exception:
            for event, callback in listeners.items():
                try:
                    page.remove_listener(event, callback)
                except Exception:
                    pass

    def detach(self) -> None:
        """停止新请求采集，不取消已开始的 body 读取或修改已有记录。"""
        for page, listeners in self._pages.values():
            for event, callback in listeners.items():
                try:
                    page.remove_listener(event, callback)
                except Exception:
                    pass
        self._pages.clear()
        self._request_contexts.clear()

    def _candidate(self, response: Any) -> bool:
        if not _env_flag("BADCASE_LLM_CAPTURE_ENABLED", "1"):
            return False
        try:
            url = response.url or ""
            ct = str((response.headers or {}).get("content-type") or "").lower()
            if _STATIC_EXT_RE.search(url):
                return False
            if _SSE_CT in ct:
                return True
            low = url.lower()
            if any(h in low for h in LLM_URL_HINTS):
                return True
            if response.request.method.upper() == "POST" and any(h in ct for h in _JSON_CT_HINTS):
                return True
        except Exception:
            return False
        return False

    async def _capture(
        self, response: Any, *, context: Optional[Dict[str, Any]] = None
    ) -> None:
        t0 = time.perf_counter()
        record = self._blank_record(response, context=context)
        try:
            req_info = _extract_request(getattr(response.request, "post_data", None))
            record["request"] = req_info
        except Exception:
            req_info = record["request"]

        ct = ""
        try:
            ct = str((response.headers or {}).get("content-type") or "").lower()
        except Exception:
            pass
        is_sse = _SSE_CT in ct

        raw = ""
        try:
            body = await asyncio.wait_for(response.body(), timeout=BODY_TIMEOUT_SEC)
            raw = body.decode("utf-8", "replace") if isinstance(body, (bytes, bytearray)) else str(body)
        except asyncio.TimeoutError:
            record["error"] = f"body 超时（>{int(BODY_TIMEOUT_SEC)}s，长连接流未结束）"
        except Exception as ex:
            record["error"] = f"body 读取失败: {str(ex)[:200]}"

        if raw:
            if len(raw) > MAX_BODY_CHARS:
                raw = raw[:MAX_BODY_CHARS]
                record["body_clipped"] = True
            if is_sse or raw.lstrip().startswith("data:"):
                record["stream"] = True
                parsed = _parse_llm_sse(raw)
            else:
                try:
                    obj = json.loads(raw)
                except Exception:
                    obj = None
                if isinstance(obj, dict):
                    record["_top_keys"] = [str(k) for k in list(obj.keys())[:20]]
                    parsed = _parse_llm_json(obj)
                elif isinstance(obj, list):
                    first = _as_dict(obj[0]) if obj else {}
                    record["_top_keys"] = [str(k) for k in list(first.keys())[:20]]
                    parsed = _parse_llm_json(first)
                else:
                    parsed = None
            if parsed is not None:
                if not _looks_like_llm(record, req_info):
                    async with self._lock:
                        self._skipped += 1
                    return
                record["response"] = parsed

        record["body_wait_ms"] = int((time.perf_counter() - t0) * 1000)
        self._finalize(record)

    def _blank_record(
        self, response: Any, *, context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        context = self._context_snapshot() if context is None else deepcopy(context)
        try:
            status = response.status
        except Exception:
            status = None
        try:
            url = response.url
        except Exception:
            url = ""
        try:
            method = response.request.method
        except Exception:
            method = ""
        rec: Dict[str, Any] = {
            "exchange_id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "project_id": context.get("project_id"),
            "cdp_run_id": context.get("cdp_run_id"),
            "turn": 0,
            "url": url,
            "method": method,
            "status": status,
            "stream": False,
            "request": {
                "model": None,
                "params": {},
                "system_prompt": "",
                "messages": [],
                "messages_total": 0,
                "tools": [],
            },
            "response": {
                "model": None,
                "text": "",
                "tool_calls": [],
                "finish_reason": None,
                "usage": None,
            },
            "declared": context.get("declared") or {},
            "model_mismatch": False,
            "error": None,
        }
        rec.update(_timing_ms(response))
        return rec

    def _finalize(self, record: Dict[str, Any]) -> None:
        """收尾：轮次编号、模型降级检测、截断标记、落盘。"""
        record.pop("_top_keys", None)
        resp = _as_dict(record.get("response"))
        declared_model = _as_dict(record.get("declared")).get("model")
        actual = resp.get("model")
        if declared_model and actual and not _model_matches(declared_model, actual):
            record["model_mismatch"] = True
        if resp.get("finish_reason") == "length":
            record["truncated_by_max_tokens"] = True
        if record.get("status") and int(record["status"]) >= 400:
            record["http_error"] = True

        record["turn"] = len(self._items) + 1
        self._items.append(record)
        if len(self._items) > MAX_EXCHANGES:
            self._items = self._items[-MAX_EXCHANGES:]
        try:
            from utils.observability import append_llm_exchange

            append_llm_exchange(record)
        except Exception:
            pass

    # ---------- 读取 ----------

    async def drain(self, timeout: float = 8.0) -> None:
        """等待在途的 body 抓取完成（页面操作结束后调用，再读结果）。"""
        pending = [t for t in list(self._tasks) if not t.done()]
        if not pending:
            return
        try:
            await asyncio.wait(pending, timeout=timeout)
        except Exception:
            pass

    def exchanges(self) -> List[Dict[str, Any]]:
        return list(self._items)

    def summary(self) -> Dict[str, Any]:
        models: List[str] = []
        errors = mismatches = truncated = calls = 0
        for it in self._items:
            m = (_as_dict(it.get("response")) or {}).get("model") or (_as_dict(it.get("request")) or {}).get("model")
            if m and m not in models:
                models.append(str(m))
            if it.get("error") or it.get("http_error"):
                errors += 1
            if it.get("model_mismatch"):
                mismatches += 1
            if it.get("truncated_by_max_tokens") or _as_dict(it.get("response")).get("finish_reason") == "length":
                truncated += 1
            if _as_dict(it.get("response")).get("tool_calls"):
                calls += 1
        return {
            "session_id": self.session_id,
            "exchanges": len(self._items),
            "models": models,
            "errors": errors,
            "model_mismatch": mismatches,
            "truncated": truncated,
            "with_tool_calls": calls,
            "skipped_non_llm": self._skipped,
        }


_captures: Dict[str, LlmCapture] = {}


def get_capture(session_id: str) -> Optional[LlmCapture]:
    return _captures.get(session_id)


def ensure_capture(
    page: Any,
    session_id: str,
    *,
    project_id: Optional[int] = None,
    cdp_run_id: Optional[str] = None,
    declared: Optional[Dict[str, Any]] = None,
) -> LlmCapture:
    cap = _captures.get(session_id)
    if cap is None:
        cap = LlmCapture(
            session_id, project_id=project_id, cdp_run_id=cdp_run_id, declared=declared
        )
        _captures[session_id] = cap
    else:
        cap.set_context(project_id=project_id, cdp_run_id=cdp_run_id, declared=declared)
    cap.attach(page)
    return cap


def drop_capture(session_id: str) -> None:
    cap = _captures.pop(session_id, None)
    if cap is not None:
        cap.detach()


def read_session_exchanges(
    session_id: str,
    limit: Optional[int] = None,
    *,
    project_id: Optional[int] = None,
    cdp_run_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """逐行读取，按 session 和指定的 project/run 精确过滤，再取最后 limit 条。

    不传 project/run 保持旧调用语义；指定后不包含缺失/空归属记录。
    """
    try:
        from utils.observability import llm_exchange_dir

        safe = "".join(ch for ch in str(session_id or "") if ch.isalnum() or ch in "-_")[:64]
        if not safe:
            return []
        path = llm_exchange_dir() / f"session_{safe}.jsonl"
        if not path.exists():
            return []
        # 正数 limit 时内存仅保留匹配范围内的最后 N 条；0/None 兼容旧版全量读取。
        out: deque = deque(maxlen=limit if limit and limit > 0 else None)
        matched = 0
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if not isinstance(item, dict) or item.get("session_id") != session_id:
                    continue
                if project_id is not None and item.get("project_id") != project_id:
                    continue
                if cdp_run_id is not None and item.get("cdp_run_id") != cdp_run_id:
                    continue
                matched += 1
                # 兼容旧版负数 limit 的切片语义（跳过前 -limit 条）。
                if limit and limit < 0 and matched <= -limit:
                    continue
                out.append(item)
        return list(out)
    except Exception:
        return []


def summarize_exchanges(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """对一批 exchange 出摘要：轮数、模型、错误、截断、工具调用、模型不一致。"""
    models: List[str] = []
    errors = truncated = tool_used = mismatch = 0
    for it in items or []:
        if not isinstance(it, dict):
            continue
        req = _as_dict(it.get("request"))
        resp = _as_dict(it.get("response"))
        m = resp.get("model") or req.get("model")
        if m and str(m) not in models:
            models.append(str(m))
        if it.get("error") or it.get("http_error"):
            errors += 1
        if it.get("truncated_by_max_tokens") or resp.get("finish_reason") == "length":
            truncated += 1
        if resp.get("tool_calls"):
            tool_used += 1
        if it.get("model_mismatch"):
            mismatch += 1
    return {
        "exchanges": len(items or []),
        "models": models,
        "errors": errors,
        "truncated": truncated,
        "with_tool_calls": tool_used,
        "model_mismatch": mismatch,
    }
