# -*- coding: utf-8 -*-
"""
调试：打印 LLM 请求（输入）与响应（输出）。

启用（改 .env 后须重启 python app.py）：
  LLM_LOG_PROMPTS=1          # 请求：messages / tools / payload
  REACT_PROMPT_LOG=1         # ReAct 组装后的可读 prompt（grep/modify/skill 校对）；未设时随 LLM_LOG_PROMPTS
  LLM_LOG_RESPONSE=1         # 响应；未设置时随 LLM_LOG_PROMPTS=1 一并开启
  PowerShell：$env:LLM_LOG_PROMPTS='1'; $env:LLM_LOG_RESPONSE='1'

别名：LLM_DEBUG_PROMPTS / LLM_PROMPT_DEBUG

写文件（推荐，少刷屏）：
  LLM_PROMPT_LOG_PATH=logs/llm_io.jsonl
  或 LLM_LOG_PROMPTS_FILE=logs/llm_io.jsonl

可选：
  REACT_PROMPT_LOG_ROUNDS=all  # 或 1,2,3；默认 all（每轮 unified prompt）
  LLM_LOG_PROMPTS_MAX_CHARS=200000
  LLM_LOG_PROMPTS_INCLUDE_TOOLS=1    # 请求里打印完整 tools 定义
  LLM_LOG_STREAM_OUTPUT=1            # 流式结束后打印拼接正文（默认随 LLM_LOG_RESPONSE）

标签：[LLM_PROMPT] 输入  [LLM_RESPONSE] 输出  [REACT_PROMPT] 组装 prompt
"""
from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Iterator, List, Optional

_logger = logging.getLogger("badcase.llm_prompt")
_file_lock = threading.Lock()
_llm_prompt_tag_ctx: ContextVar[str] = ContextVar("llm_prompt_tag", default="")


@contextmanager
def llm_prompt_tag_scope(tag: str) -> Iterator[None]:
    """ReAct 阶段标签：底层 LLM 请求日志 tag 会附带此前缀。"""
    token = _llm_prompt_tag_ctx.set(str(tag or "").strip())
    try:
        yield
    finally:
        _llm_prompt_tag_ctx.reset(token)


def get_llm_prompt_tag() -> str:
    return str(_llm_prompt_tag_ctx.get() or "").strip()


def react_prompt_log_enabled() -> bool:
    v = (os.getenv("REACT_PROMPT_LOG") or "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    try:
        from config import Config

        if getattr(Config, "REACT_PROMPT_LOG", False):
            return True
    except Exception:
        pass
    return llm_prompt_log_enabled()


def react_prompt_log_rounds_1based() -> Optional[set]:
    """
    哪些 unified 轮次打印组装 prompt（1-based）。
    默认 all；0/off 关闭轮次过滤（等同不打印 unified，仍可通过 phase 单独打）。
    """
    raw = (os.getenv("REACT_PROMPT_LOG_ROUNDS") or "all").strip().lower()
    if raw in ("0", "off", "false", "no", ""):
        return None
    if raw == "all":
        return set()  # 空 set 表示不过滤
    out: set = set()
    for part in raw.replace(";", ",").split(","):
        p = part.strip()
        if not p:
            continue
        try:
            out.add(int(p))
        except ValueError:
            continue
    return out if out else None


def should_log_react_round(round_idx_0based: int) -> bool:
    if not react_prompt_log_enabled():
        return False
    allowed = react_prompt_log_rounds_1based()
    if allowed is None:
        return False
    if not allowed:
        return True
    return (int(round_idx_0based) + 1) in allowed


def llm_prompt_log_enabled() -> bool:
    v = (
        os.getenv("LLM_LOG_PROMPTS")
        or os.getenv("LLM_DEBUG_PROMPTS")
        or os.getenv("LLM_PROMPT_DEBUG")
        or ""
    ).strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    try:
        from config import Config

        return bool(getattr(Config, "LLM_LOG_PROMPTS", False))
    except Exception:
        return False


def llm_prompt_log_file_path() -> Optional[str]:
    """非空则每次请求追加写入完整 JSON（可与控制台开关独立）。"""
    p = (
        os.getenv("LLM_PROMPT_LOG_PATH")
        or os.getenv("LLM_LOG_PROMPTS_FILE")
        or ""
    ).strip()
    return p or None


def llm_prompt_log_max_chars() -> int:
    try:
        return int(os.getenv("LLM_LOG_PROMPTS_MAX_CHARS", "200000") or "200000")
    except ValueError:
        return 200000


def llm_prompt_log_include_tools_full() -> bool:
    v = (os.getenv("LLM_LOG_PROMPTS_INCLUDE_TOOLS") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def llm_response_log_enabled() -> bool:
    v = (os.getenv("LLM_LOG_RESPONSE") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    return llm_prompt_log_enabled()


def llm_stream_output_log_enabled() -> bool:
    v = (os.getenv("LLM_LOG_STREAM_OUTPUT") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    return llm_response_log_enabled()


def _truncate_json_text(raw: str) -> str:
    mc = llm_prompt_log_max_chars()
    if mc > 0 and len(raw) > mc:
        return (
            raw[:mc]
            + f"\n... [LLM_IO truncated] LLM_LOG_PROMPTS_MAX_CHARS={mc} json_len={len(raw)}"
        )
    return raw


def _emit_llm_block(
    header: str,
    body: str,
    *,
    to_console: bool = True,
    to_file_path: Optional[str] = None,
) -> None:
    to_file = to_file_path or llm_prompt_log_file_path()
    if not to_console and not to_file:
        return
    if to_console:
        _logger.warning(header)
        print(header, flush=True)
        if body:
            _logger.warning("%s", body)
            print(body, flush=True)
    if to_file:
        block = "\n---\n" + header + "\n" + (body or "") + "\n"
        try:
            os.makedirs(os.path.dirname(to_file) or ".", exist_ok=True)
        except Exception:
            pass
        with _file_lock:
            with open(to_file, "a", encoding="utf-8") as fp:
                fp.write(block)
        print(f"[LLM_IO] appended -> {to_file}", flush=True)


def _usage_to_dict(usage: Any) -> Optional[Dict[str, Any]]:
    if usage is None:
        return None
    if isinstance(usage, dict):
        return dict(usage)
    keys = (
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "prompt_cache_hit_tokens",
        "prompt_cache_miss_tokens",
    )
    out: Dict[str, Any] = {}
    for k in keys:
        v = getattr(usage, k, None)
        if v is not None:
            out[k] = v
    return out or None


def _openai_message_to_dict(msg: Any) -> Dict[str, Any]:
    if msg is None:
        return {}
    if isinstance(msg, dict):
        return dict(msg)
    content = getattr(msg, "content", None) or ""
    reasoning = getattr(msg, "reasoning_content", None)
    tcs = getattr(msg, "tool_calls", None)
    out: Dict[str, Any] = {
        "content": content,
        "content_len": len(content) if isinstance(content, str) else 0,
    }
    if reasoning:
        out["reasoning_content"] = reasoning
        if isinstance(reasoning, str):
            out["reasoning_len"] = len(reasoning)
    if tcs:
        tc_rows: List[Dict[str, Any]] = []
        if not isinstance(tcs, (list, tuple)):
            tcs = [tcs]
        for tc in tcs:
            fn = getattr(tc, "function", None)
            if fn is None and isinstance(tc, dict):
                fn = tc.get("function")
            if isinstance(fn, dict):
                name = fn.get("name") or ""
                args = fn.get("arguments")
            else:
                name = getattr(fn, "name", "") if fn else ""
                args = getattr(fn, "arguments", "") if fn else ""
            if not isinstance(args, str):
                try:
                    args = json.dumps(args, ensure_ascii=False)
                except Exception:
                    args = str(args)
            tc_rows.append({"name": name, "arguments": args})
        out["tool_calls"] = tc_rows
    return out


def maybe_log_llm_response_body(
    provider: str,
    body: Dict[str, Any],
    *,
    tag: str = "",
    model: Optional[str] = None,
) -> None:
    """打印 LLM 响应快照（非流式整包或流式拼接结果）。"""
    if not llm_response_log_enabled() and not llm_prompt_log_file_path():
        return
    try:
        snap = dict(body)
        if model:
            snap.setdefault("model", model)
        raw = _truncate_json_text(json.dumps(snap, ensure_ascii=False, default=str))
        header = (
            f"[LLM_RESPONSE] provider={provider} tag={tag or '-'} "
            f"model={snap.get('model')!r}"
        )
        _emit_llm_block(
            header,
            raw,
            to_console=llm_response_log_enabled(),
            to_file_path=llm_prompt_log_file_path(),
        )
    except Exception as e:
        print(f"[LLM_RESPONSE] log_failed: {e}", flush=True)


def maybe_log_llm_openai_completion(
    provider: str,
    resp: Any,
    *,
    tag: str = "",
    model: Optional[str] = None,
) -> None:
    if not llm_response_log_enabled() and not llm_prompt_log_file_path():
        return
    try:
        choices_out: List[Dict[str, Any]] = []
        for ch in getattr(resp, "choices", None) or []:
            msg = getattr(ch, "message", None)
            choices_out.append(_openai_message_to_dict(msg))
        body: Dict[str, Any] = {
            "choices": choices_out,
            "usage": _usage_to_dict(getattr(resp, "usage", None)),
        }
        if model:
            body["model"] = model
        maybe_log_llm_response_body(provider, body, tag=tag, model=model)
    except Exception as e:
        print(f"[LLM_RESPONSE] openai_completion log_failed: {e}", flush=True)


def maybe_log_llm_stream_assembled(
    provider: str,
    *,
    tag: str = "",
    model: Optional[str] = None,
    content: str = "",
    reasoning: str = "",
    usage: Any = None,
) -> None:
    """流式结束后打印拼接的正文（便于看完整输出体积）。"""
    if not llm_stream_output_log_enabled() and not llm_prompt_log_file_path():
        return
    body: Dict[str, Any] = {
        "stream_assembled": True,
        "content": content,
        "content_len": len(content or ""),
    }
    if reasoning:
        body["reasoning_content"] = reasoning
        body["reasoning_len"] = len(reasoning)
    u = _usage_to_dict(usage)
    if u:
        body["usage"] = u
    maybe_log_llm_response_body(provider, body, tag=tag, model=model)


def maybe_log_agent_prompt(
    phase: str,
    prompt: str,
    *,
    round_idx_0based: Optional[int] = None,
    request_id: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """打印 ReAct/Skill 组装后的可读 prompt（便于 grep/modify 技能校对）。"""
    if not react_prompt_log_enabled():
        return
    if round_idx_0based is not None and not should_log_react_round(int(round_idx_0based)):
        return
    try:
        body = prompt if isinstance(prompt, str) else str(prompt or "")
        body = _truncate_json_text(body)
        meta_parts: List[str] = []
        if round_idx_0based is not None:
            meta_parts.append(f"round={int(round_idx_0based) + 1}")
        if request_id:
            meta_parts.append(f"request_id={request_id}")
        if isinstance(extra, dict):
            for k, v in extra.items():
                if v is None or v == "":
                    continue
                meta_parts.append(f"{k}={v}")
        meta = " ".join(meta_parts)
        header = f"[REACT_PROMPT] phase={phase or '-'}" + (f" {meta}" if meta else "")
        to_console = react_prompt_log_enabled()
        to_file = llm_prompt_log_file_path()
        _emit_llm_block(header, body, to_console=to_console, to_file_path=to_file)
    except Exception as e:
        print(f"[REACT_PROMPT] log_failed: {e}", flush=True)


def maybe_log_skill_workflow(
    skill_name: str,
    workflow_text: str,
    *,
    score: Optional[float] = None,
    user_input: str = "",
) -> None:
    if not react_prompt_log_enabled():
        return
    extra = {"skill": skill_name}
    if score is not None:
        extra["score"] = f"{score:.2f}"
    maybe_log_agent_prompt(
        "skill_workflow",
        workflow_text,
        extra={
            **extra,
            "user_input_preview": (user_input or "")[:200],
        },
    )


def maybe_log_llm_chat_kwargs(
    provider: str,
    kwargs: Dict[str, Any],
    *,
    tag: str = "",
) -> None:
    """在调用 OpenAI 兼容 chat.completions.create(**kwargs) 之前打印 kwargs（可截断）。"""
    to_console = llm_prompt_log_enabled()
    to_file = llm_prompt_log_file_path()
    if not to_console and not to_file:
        return
    try:
        snap: Dict[str, Any] = dict(kwargs)
        if not llm_prompt_log_include_tools_full():
            tl = snap.get("tools")
            if tl is not None:
                if isinstance(tl, list):
                    snap["tools"] = (
                        f"<{len(tl)} tool defs omitted; LLM_LOG_PROMPTS_INCLUDE_TOOLS=1 to dump>"
                    )
                else:
                    snap["tools"] = "<omitted>"
        raw = _truncate_json_text(json.dumps(snap, ensure_ascii=False, default=str))
        ctx_tag = get_llm_prompt_tag()
        eff_tag = tag or "-"
        if ctx_tag:
            eff_tag = f"{ctx_tag}|{eff_tag}" if eff_tag != "-" else ctx_tag
        header = (
            f"[LLM_PROMPT] provider={provider} tag={eff_tag} "
            f"model={snap.get('model')!r} stream={snap.get('stream', False)!r}"
        )
        _emit_llm_block(
            header,
            raw,
            to_console=to_console,
            to_file_path=to_file,
        )
    except Exception as e:
        _logger.warning("[LLM_PROMPT] log_failed: %s", e)
        print(f"[LLM_PROMPT] log_failed: {e}", flush=True)
