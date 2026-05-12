# -*- coding: utf-8 -*-
"""
DeepSeek 官方 OpenAI 兼容 API。
思考模式见：https://api-docs.deepseek.com/zh-cn/guides/thinking_mode
- 流式/汇总：reasoning_content + content（与 Qwen 兼容层一致，供 ReAct unified）
- Function Calling：关闭 thinking，避免未回传 reasoning_content 导致 400
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterator, List, Optional, Union

from openai import OpenAI

from config import Config

from .prompt_log import maybe_log_llm_chat_kwargs
from .multimodal_content import openai_style_user_content


def _deepseek_prefix_cache_log_enabled() -> bool:
    """
    是否打印上下文前缀缓存命中（usage.prompt_cache_*）。
    默认开启（未设置 DEEPSEEK_PREFIX_CACHE_LOG 也打印）；设为 0/false/off 关闭。
    PERF_LOG=1 时等价开启（便于与其它性能日志一并打开）。
    """
    raw = (os.getenv("DEEPSEEK_PREFIX_CACHE_LOG") or "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return False
    if raw in ("1", "true", "yes", "on") or raw == "":
        return True
    return (os.getenv("PERF_LOG", "") or "").strip() == "1"


def _usage_prompt_cache_fields(usage: Any) -> Optional[Dict[str, Any]]:
    """从 chat.completions 返回的 usage 抽取前缀缓存字段（DeepSeek/OpenAI 兼容 shape）。"""
    if usage is None:
        return None
    hit = getattr(usage, "prompt_cache_hit_tokens", None)
    miss = getattr(usage, "prompt_cache_miss_tokens", None)
    pt = getattr(usage, "prompt_tokens", None)
    ct = getattr(usage, "completion_tokens", None)
    tt = getattr(usage, "total_tokens", None)
    if isinstance(usage, dict):
        hit = usage.get("prompt_cache_hit_tokens", hit)
        miss = usage.get("prompt_cache_miss_tokens", miss)
        pt = usage.get("prompt_tokens", pt)
        ct = usage.get("completion_tokens", ct)
        tt = usage.get("total_tokens", tt)
    if hit is None and miss is None:
        return None
    try:
        hi = int(hit or 0)
        mi = int(miss or 0)
    except Exception:
        return None
    # 与官方一致：可缓存的 prompt 中，命中前缀缓存的比例
    # hit_rate = prompt_cache_hit_tokens / (prompt_cache_hit_tokens + prompt_cache_miss_tokens)
    denom = hi + mi
    hit_rate = (float(hi) / float(denom)) if denom > 0 else None
    hit_rate_pct = (100.0 * float(hi) / float(denom)) if denom > 0 else None
    out: Dict[str, Any] = {
        "prompt_cache_hit_tokens": hi,
        "prompt_cache_miss_tokens": mi,
        "prompt_tokens": int(pt) if pt is not None else denom,
        "completion_tokens": int(ct) if ct is not None else None,
        "total_tokens": int(tt) if tt is not None else None,
        "prefix_cache_hit_rate": hit_rate,  # 0~1
        "prefix_cache_hit_rate_pct": hit_rate_pct,
    }
    return out


def _log_deepseek_prefix_cache_line(
    usage: Any,
    *,
    model: str,
    tag: str,
) -> None:
    if not _deepseek_prefix_cache_log_enabled():
        return
    fields = _usage_prompt_cache_fields(usage)
    if not fields:
        return
    hi = fields["prompt_cache_hit_tokens"]
    mi = fields["prompt_cache_miss_tokens"]
    ratio = fields.get("prefix_cache_hit_rate")
    pct = fields.get("prefix_cache_hit_rate_pct")
    ratio_s = f"{ratio:.6f}" if ratio is not None else "n/a"
    pct_s = f"{pct:.2f}%" if pct is not None else "n/a"
    pt = fields.get("prompt_tokens")
    ct = fields.get("completion_tokens")
    print(
        f"[DEEPSEEK][prefix_cache] model={model!r} tag={tag} "
        f"prompt_cache_hit_tokens={hi} prompt_cache_miss_tokens={mi} "
        f"hit_rate={ratio_s} (={hi}/({hi}+{mi}), {pct_s}) "
        f"prompt_tokens={pt} completion_tokens={ct}",
        flush=True,
    )


def _delta_reasoning_content(delta: Any) -> Optional[str]:
    if delta is None:
        return None
    v = getattr(delta, "reasoning_content", None)
    if v:
        return v
    if isinstance(delta, dict):
        return delta.get("reasoning_content")
    return None


def _delta_content(delta: Any) -> Optional[str]:
    if delta is None:
        return None
    v = getattr(delta, "content", None)
    if v:
        return v
    if isinstance(delta, dict):
        return delta.get("content")
    return None


class DeepSeekLLM:
    """
    DeepSeek（含 deepseek-v4-pro 思考模式）。
    FC 路径强制关闭 thinking，与现有 FcStreamAccumulator 对齐。
    """

    def __init__(self, model: Optional[str] = None):
        self.model = (model or getattr(Config, "DEEPSEEK_V4_MODEL", None) or "deepseek-v4-pro").strip()
        self.force_disable_thinking = False
        self.enable_thinking = True
        self._oa: Optional[OpenAI] = None
        self.executor = ThreadPoolExecutor(max_workers=3)
        if not (getattr(Config, "DEEPSEEK_API_KEY", None) or "").strip():
            print("[DEEPSEEK-LLM] 警告：未配置 DEEPSEEK_API_KEY，调用将失败")

    def _get_client(self) -> OpenAI:
        if self._oa is None:
            key = (getattr(Config, "DEEPSEEK_API_KEY", None) or "").strip()
            if not key:
                raise ValueError("未配置 DEEPSEEK_API_KEY")
            base = (getattr(Config, "DEEPSEEK_API_BASE_URL", None) or "https://api.deepseek.com").strip().rstrip(
                "/"
            )
            self._oa = OpenAI(api_key=key, base_url=base)
        return self._oa

    def _supports_api_thinking(self) -> bool:
        """V4 Pro 等支持官方 thinking + reasoning_effort；工具调用时仍应关闭。"""
        m = (self.model or "").lower()
        if "flash" in m:
            return False
        return "deepseek-v4" in m or "v4-pro" in m

    def _reasoning_effort(self) -> str:
        raw = (
            os.getenv("DEEPSEEK_REASONING_EFFORT")
            or getattr(Config, "DEEPSEEK_REASONING_EFFORT", None)
            or "high"
        )
        s = str(raw).strip().lower()
        return s if s in ("high", "max") else "high"

    def _temperature(self) -> float:
        try:
            return float(os.getenv("DEEPSEEK_TEMPERATURE", str(getattr(Config, "DEEPSEEK_TEMPERATURE", 0.7))))
        except Exception:
            return 0.7

    def _default_max_tokens_for_model(self) -> Optional[int]:
        """
        deepseek-v4-pro 未显式传 max_tokens 时的上限（推理+输出共用额度），抑制车轱辘话。
        DEEPSEEK_V4_PRO_MAX_TOKENS=0 或不适用型号时不添加默认。
        """
        m = (self.model or "").lower()
        if "flash" in m:
            return None
        if "v4-pro" not in m:
            return None
        try:
            raw = os.getenv("DEEPSEEK_V4_PRO_MAX_TOKENS")
            if raw is not None and str(raw).strip() != "":
                v = int(str(raw).strip())
                return None if v <= 0 else v
            v = int(getattr(Config, "DEEPSEEK_V4_PRO_MAX_TOKENS", 2048))
            return None if v <= 0 else v
        except Exception:
            return 2048

    def _merge_thinking_params(self, kwargs: Dict[str, Any], *, thinking_on: bool) -> None:
        """
        思考模式：reasoning_effort + extra_body.thinking；
        关闭时：extra_body disabled，可带 temperature。
        见 https://api-docs.deepseek.com/zh-cn/guides/thinking_mode
        """
        if thinking_on and self._supports_api_thinking() and not getattr(
            self, "force_disable_thinking", False
        ):
            kwargs["reasoning_effort"] = self._reasoning_effort()
            prev = kwargs.get("extra_body")
            body = dict(prev) if isinstance(prev, dict) else {}
            inner = dict(body.get("thinking") or {})
            inner["type"] = "enabled"
            body["thinking"] = inner
            kwargs["extra_body"] = body
            kwargs.pop("temperature", None)
            kwargs.pop("top_p", None)
        else:
            prev = kwargs.get("extra_body")
            body = dict(prev) if isinstance(prev, dict) else {}
            inner = dict(body.get("thinking") or {})
            inner["type"] = "disabled"
            body["thinking"] = inner
            kwargs["extra_body"] = body
            if "temperature" not in kwargs:
                kwargs["temperature"] = self._temperature()

    def _merge_deepseek_kv_user_id(self, kwargs: Dict[str, Any]) -> None:
        """官方可选 user_id（常见放在扩展 body）：同账号内 KV 隔离；固定值有助于前缀缓存亲和。"""
        uid = (os.getenv("DEEPSEEK_KV_USER_ID") or getattr(Config, "DEEPSEEK_KV_USER_ID", "") or "").strip()
        if not uid:
            return
        eb = dict(kwargs.get("extra_body") or {})
        eb["user_id"] = uid
        kwargs["extra_body"] = eb

    def _chat_create(
        self,
        messages: List[Dict[str, Any]],
        *,
        stream: bool,
        enable_thinking: bool,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Union[str, Dict[str, Any], None] = None,
        parallel_tool_calls: bool = False,
    ):
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        mt_use = max_tokens
        if mt_use is None or mt_use <= 0:
            mt_use = self._default_max_tokens_for_model()
        if mt_use is not None and mt_use > 0:
            kwargs["max_tokens"] = mt_use
        if tools is not None:
            kwargs["tools"] = tools
            kwargs["parallel_tool_calls"] = parallel_tool_calls
            if tool_choice is not None:
                kwargs["tool_choice"] = tool_choice
        # 流式须在末包带上 usage，才能统计 prompt_cache_hit/miss（前缀缓存命中率）
        if stream:
            kwargs["stream_options"] = {"include_usage": True}
        # FC / 非思考流：关闭 thinking；普通对话流可开启
        self._merge_thinking_params(kwargs, thinking_on=enable_thinking)
        self._merge_deepseek_kv_user_id(kwargs)
        maybe_log_llm_chat_kwargs(
            "deepseek",
            kwargs,
            tag=f"_chat_create thinking={enable_thinking}",
        )
        return self._get_client().chat.completions.create(**kwargs)

    def chat_completion_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        tool_choice: Union[str, Dict[str, Any]] = "auto",
        parallel_tool_calls: bool = False,
        max_tokens: Optional[int] = None,
    ):
        resp = self._chat_create(
            messages,
            stream=False,
            enable_thinking=False,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
        )
        _log_deepseek_prefix_cache_line(getattr(resp, "usage", None), model=self.model, tag="fc_tools_sync")
        msg = resp.choices[0].message
        out: Dict[str, Any] = {"role": "assistant", "content": getattr(msg, "content", None) or ""}
        tcs = getattr(msg, "tool_calls", None)
        if tcs:
            serialized = []
            for tc in tcs:
                fn = getattr(tc, "function", None)
                serialized.append(
                    {
                        "id": getattr(tc, "id", "") or "",
                        "type": getattr(tc, "type", None) or "function",
                        "function": {
                            "name": getattr(fn, "name", "") if fn else "",
                            "arguments": getattr(fn, "arguments", "") if fn else "",
                        },
                    }
                )
            out["tool_calls"] = serialized
        else:
            out["tool_calls"] = None
        return out

    def chat_completion_with_tools_stream(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        *,
        tool_choice: Union[str, Dict[str, Any]] = "auto",
        parallel_tool_calls: bool = False,
        max_tokens: Optional[int] = None,
    ) -> Iterator[Any]:
        stream = self._chat_create(
            messages,
            stream=True,
            enable_thinking=False,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            parallel_tool_calls=parallel_tool_calls,
        )
        for chunk in stream:
            u = getattr(chunk, "usage", None)
            if u is not None:
                _log_deepseek_prefix_cache_line(u, model=self.model, tag="fc_tools_stream")
            yield chunk

    def chat_completion_messages(self, messages: List[Dict[str, Any]]):
        resp = self._chat_create(messages, stream=False, enable_thinking=False)
        _log_deepseek_prefix_cache_line(getattr(resp, "usage", None), model=self.model, tag="completion_messages")
        return resp

    def chat_stream_with_reasoning(
        self,
        prompt: str,
        history: Optional[list] = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if history:
            messages.extend(history)
        messages.append(
            {"role": "user", "content": openai_style_user_content(prompt, images)}
        )
        thinking_on = bool(
            self.enable_thinking
            and self._supports_api_thinking()
            and not getattr(self, "force_disable_thinking", False)
        )
        if thinking_on:
            print(f"[DEEPSEEK-LLM-STREAM] thinking=enabled model={self.model}")
        else:
            print(f"[DEEPSEEK-LLM-STREAM] thinking=disabled model={self.model}")
        try:
            stream = self._chat_create(
                messages, stream=True, enable_thinking=thinking_on, max_tokens=max_tokens
            )
            for chunk in stream:
                u = getattr(chunk, "usage", None)
                if u is not None:
                    _log_deepseek_prefix_cache_line(u, model=self.model, tag="stream_reasoning")
                if not chunk.choices:
                    continue
                d = chunk.choices[0].delta
                rc = _delta_reasoning_content(d)
                if rc and isinstance(rc, str):
                    yield {"type": "reasoning_delta", "delta": rc}
                ct = _delta_content(d)
                if ct and isinstance(ct, str):
                    yield {"type": "content_delta", "delta": ct}
            yield {"type": "done"}
        except Exception as e:
            yield {"type": "content_delta", "delta": f"Error: {e}"}
            yield {"type": "done"}

    def chat_stream_fallback_chunks(
        self,
        prompt: str,
        history: Optional[list] = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if history:
            messages.extend(history)
        messages.append(
            {"role": "user", "content": openai_style_user_content(prompt, images)}
        )
        thinking_on = bool(
            self.enable_thinking
            and self._supports_api_thinking()
            and not getattr(self, "force_disable_thinking", False)
        )
        try:
            resp = self._chat_create(
                messages, stream=False, enable_thinking=thinking_on, max_tokens=max_tokens
            )
            _log_deepseek_prefix_cache_line(getattr(resp, "usage", None), model=self.model, tag="fallback_chunks")
            msg = resp.choices[0].message
            rc = getattr(msg, "reasoning_content", None)
            if rc and isinstance(rc, str) and rc.strip():
                for i in range(0, len(rc), 64):
                    yield {"type": "reasoning_delta", "delta": rc[i : i + 64]}
            ct = (getattr(msg, "content", None) or "").strip()
            for i in range(0, len(ct), 64):
                yield {"type": "content_delta", "delta": ct[i : i + 64]}
        except Exception as e:
            yield {"type": "content_delta", "delta": f"Error: {e}"}
        yield {"type": "done"}

    def chat_stream(
        self,
        prompt: str,
        history: Optional[list] = None,
        locale: Optional[str] = None,
        max_tokens: Optional[int] = None,
        images: Optional[List[Dict[str, Any]]] = None,
    ):
        from agents.locale_prompts import wrap_general_user_prompt

        p = wrap_general_user_prompt(prompt, locale)
        for item in self.chat_stream_with_reasoning(
            p, history, max_tokens=max_tokens, images=images
        ):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "reasoning_delta":
                continue
            if item.get("type") == "content_delta":
                d = item.get("delta") or ""
                if isinstance(d, str) and d:
                    yield d

    async def chat(self, prompt: str, history: Optional[list] = None) -> str:
        def _sync() -> str:
            messages: List[Dict[str, Any]] = []
            if history:
                messages.extend(history)
            messages.append({"role": "user", "content": prompt})
            resp = self._chat_create(messages, stream=False, enable_thinking=False)
            _log_deepseek_prefix_cache_line(getattr(resp, "usage", None), model=self.model, tag="chat")
            return (resp.choices[0].message.content or "").strip()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _sync)

    async def chat_with_reasoning(self, prompt: str, history: Optional[list] = None) -> Dict[str, Any]:
        def _sync() -> Dict[str, Any]:
            reasoning_parts: List[str] = []
            content_parts: List[str] = []
            try:
                for item in self.chat_stream_with_reasoning(prompt, history):
                    if not isinstance(item, dict):
                        continue
                    typ = item.get("type")
                    if typ == "reasoning_delta":
                        d = item.get("delta")
                        if isinstance(d, str) and d:
                            reasoning_parts.append(d)
                    elif typ == "content_delta":
                        d = item.get("delta") or ""
                        if d:
                            content_parts.append(d)
            except Exception as e:
                return {"content": f"Error: {e}", "reasoning_content": None}
            rc_joined = "".join(reasoning_parts).strip() or None
            ct = "".join(content_parts).strip()
            return {"content": ct, "reasoning_content": rc_joined}

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _sync)

    async def parse_intent(
        self, user_input: str, history: Optional[list] = None, locale: Optional[str] = None
    ) -> Optional[dict]:
        from agents.locale_prompts import wrap_general_user_prompt

        def _sync_parse() -> Optional[dict]:
            user_input_wrapped = wrap_general_user_prompt(user_input, locale)
            if "<system>" in user_input or "<format>" in user_input or "必须返回" in user_input:
                messages = [{"role": "user", "content": user_input_wrapped}]
                try:
                    resp = self._chat_create(messages, stream=False, enable_thinking=False)
                    _log_deepseek_prefix_cache_line(
                        getattr(resp, "usage", None), model=self.model, tag="parse_intent"
                    )
                    text = (resp.choices[0].message.content or "").strip()
                    try:
                        return json.loads(text)
                    except Exception:
                        return text
                except Exception as e:
                    print(f"[DEEPSEEK-LLM-PARSE] error: {e}")
                    return None

            prompt = user_input_wrapped
            if not ("JSON" in prompt or "json" in prompt):
                prompt += "\n请务必只返回 JSON 格式结果。"
            messages = [{"role": "user", "content": prompt}]
            try:
                resp = self._chat_create(messages, stream=False, enable_thinking=False)
                _log_deepseek_prefix_cache_line(
                    getattr(resp, "usage", None), model=self.model, tag="parse_intent_json"
                )
                text = (resp.choices[0].message.content or "").strip()
                json_match = re.search(r"\[.*\]|\{.*\}", text, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group())
                return json.loads(text)
            except Exception as e:
                print(f"[DEEPSEEK-LLM-PARSE] error: {e}")
                return {"agent": "other", "action": "other", "info": {}}

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, _sync_parse)
