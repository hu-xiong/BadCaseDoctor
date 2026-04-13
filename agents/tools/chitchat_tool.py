# agents/tools/chitchat_tool.py
"""闲聊工具：在用户无项目操作意图时由模型调用，生成自然语言回复。"""
from __future__ import annotations

import asyncio
import os
from typing import Any, AsyncIterator, Dict

from agents.tool_registry import BaseTool

_STREAM_END = object()


def _sync_next_chunk(gen_iter):
    try:
        return next(gen_iter)
    except StopIteration:
        return _STREAM_END


class ChitchatTool(BaseTool):
    """不查库、不改数据，仅基于对话模型回复日常闲聊或通用问答。"""

    def __init__(self, llm=None):
        super().__init__(
            name="chitchat",
            description=(
                "闲聊/通用对话工具：当用户只是在打招呼、聊天、问常识、与当前项目 Bug/计划无关的泛泛问题时使用。"
                "必须参数：message（用户想聊的内容或问题，字符串）。"
                "不要用于需要检索项目内 Bug、修改数据、执行 grep/modify 等场景。"
            ),
        )
        self.llm = llm

    def _prepare_prompt(self, text: str) -> tuple[str | None, str | None]:
        """返回 (裁剪后用户正文, 错误提示)；无错误时 error 为 None。"""
        t = (text or "").strip()
        if not t:
            return None, "缺少参数 message（或 user_message）"
        try:
            max_in = int((os.getenv("CHITCHAT_USER_MESSAGE_MAX_CHARS") or "4000").strip())
        except ValueError:
            max_in = 4000
        max_in = max(200, min(max_in, 16000))
        if len(t) > max_in:
            t = t[: max_in - 1] + "…"
        if self.llm is None:
            return None, "LLM 未初始化"
        system_hint = (
            "你是 BadCase Doctor 产品里的助手。用户当前在「项目 Agent」模式下发起了一段与具体缺陷操作无关的对话。"
            "请用简洁、友好的中文直接回答；不要输出 XML、不要假装调用了 grep/modify；不要编造本系统未提供的功能。"
        )
        prompt = f"{system_hint}\n\n用户说：\n{t}"
        return prompt, None

    async def stream_execute(
        self,
        message: str = None,
        user_message: str = None,
        topic: str = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        闲聊 SSE：优先走底层 ``chat_stream`` 逐段 yield；否则 ``execute`` 整包后本地切片（与 REACT_CHAT_REPLY_STREAM 一致）。
        """
        raw = (
            message
            or user_message
            or topic
            or kwargs.get("query")
            or kwargs.get("content")
            or ""
        )
        prompt, err = self._prepare_prompt(str(raw).strip())
        if err or not prompt:
            return
        try:
            max_out = int((os.getenv("CHITCHAT_REPLY_MAX_CHARS") or "8000").strip())
        except ValueError:
            max_out = 8000
        max_out = max(500, min(max_out, 32000))

        stream_fn = getattr(self.llm, "chat_stream", None)
        if callable(stream_fn):
            loop = asyncio.get_running_loop()
            it = iter(stream_fn(prompt, history=None))
            n = 0
            while True:
                chunk = await loop.run_in_executor(None, _sync_next_chunk, it)
                if chunk is _STREAM_END:
                    break
                if not isinstance(chunk, str) or not chunk:
                    continue
                rest = max_out - n
                if rest <= 0:
                    break
                if len(chunk) > rest:
                    chunk = chunk[:rest]
                yield chunk
                n += len(chunk)
                if n >= max_out:
                    break
            return

        obs = await self.execute(
            message=message,
            user_message=user_message,
            topic=topic,
            **kwargs,
        )
        body = ""
        if isinstance(obs, dict) and obs.get("success"):
            body = (obs.get("summary") or obs.get("message") or "").strip()
        if not body:
            return
        try:
            step = max(1, int((os.getenv("REACT_CHAT_REPLY_STREAM_CHARS") or "2").strip()))
        except Exception:
            step = 2
        raw_stream = (os.getenv("REACT_CHAT_REPLY_STREAM") or "1").strip().lower()
        if raw_stream in ("0", "false", "no", "off"):
            yield body[:max_out]
            return
        for i in range(0, min(len(body), max_out), step):
            yield body[i : i + step]

    async def execute(
        self,
        message: str = None,
        user_message: str = None,
        topic: str = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        text = (message or user_message or topic or kwargs.get("query") or kwargs.get("content") or "").strip()
        prompt, prep_err = self._prepare_prompt(text)
        if prep_err:
            return {
                "success": False,
                "error": prep_err,
                "message": "请传入用户想聊的内容" if "缺少" in prep_err else "当前无法调用对话模型",
            }

        try:
            chat_fn = getattr(self.llm, "chat", None)
            if callable(chat_fn):
                reply = await chat_fn(prompt, history=None)
            else:
                return {
                    "success": False,
                    "error": "当前 LLM 不支持 chat 接口",
                    "message": "请更换模型后重试",
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"闲聊生成失败：{e}",
            }

        reply = (reply or "").strip()
        if not reply:
            return {
                "success": False,
                "error": "模型返回空内容",
                "message": "未生成回复",
            }

        try:
            max_out = int((os.getenv("CHITCHAT_REPLY_MAX_CHARS") or "8000").strip())
        except ValueError:
            max_out = 8000
        max_out = max(500, min(max_out, 32000))
        if len(reply) > max_out:
            reply = reply[: max_out - 1] + "…"

        return {
            "success": True,
            "message": reply,
            "summary": reply,
            "tool_used": "chitchat",
        }
