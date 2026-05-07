import asyncio
import inspect
import json
from typing import Any, Dict, Iterator, List

from flask import Blueprint, Response, jsonify, request, stream_with_context

from llm.factory import get_llm
from config import Config


summary_bp = Blueprint("summary", __name__, url_prefix="/api/summary")


def _format_turns(turns: List[Dict[str, Any]]) -> str:
    """
    turns: [{"role": "user"|"assistant", "content": "..."}]
    """
    out = []
    for t in turns or []:
        role = (t.get("role") or "").strip().lower()
        content = (t.get("content") or "").strip()
        if not content:
            continue
        if role not in ("user", "assistant"):
            role = "assistant"
        label = "用户" if role == "user" else "AI"
        out.append(f"{label}：{content}")
    return "\n".join(out).strip()


def _coerce_bool(v: Any, default: bool = True) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("0", "false", "no", "off"):
        return False
    if s in ("1", "true", "yes", "on"):
        return True
    return default


def _iter_llm_text_chunks(llm, prompt: str) -> Iterator[str]:
    """
    统一从各 LLM 拉流式正文增量；总结场景不向前端透出 reasoning_delta。
    """
    if hasattr(llm, "chat_stream_with_reasoning"):
        for item in llm.chat_stream_with_reasoning(prompt, history=None):
            if not isinstance(item, dict):
                continue
            typ = item.get("type")
            if typ == "reasoning_delta":
                continue
            if typ == "content_delta":
                d = item.get("delta") or ""
                if isinstance(d, str) and d:
                    yield d
            elif typ == "done":
                break
        return
    if hasattr(llm, "chat_stream"):
        stream_fn = getattr(llm, "chat_stream")
        try:
            sig = inspect.signature(stream_fn)
            if "locale" in sig.parameters:
                it = stream_fn(prompt, history=None, locale=None)
            else:
                it = stream_fn(prompt, history=None)
        except Exception:
            it = stream_fn(prompt, history=None)
        for piece in it:
            if isinstance(piece, str) and piece:
                yield piece
        return

    chat_fn = getattr(llm, "chat", None)
    if not callable(chat_fn):
        return
    if inspect.iscoroutinefunction(chat_fn):
        text = asyncio.run(chat_fn(prompt, history=None))
    else:
        text = chat_fn(prompt, history=None)
    if isinstance(text, str) and text.strip():
        yield text


def _call_sync_full(model_to_use: str, prompt: str) -> tuple[str, str | None]:
    llm = get_llm(model=model_to_use)
    if hasattr(llm, "force_disable_thinking"):
        setattr(llm, "force_disable_thinking", True)
    chat_fn = getattr(llm, "chat", None)
    if not callable(chat_fn):
        return "", getattr(llm, "model", None)
    if inspect.iscoroutinefunction(chat_fn):
        text = asyncio.run(chat_fn(prompt, history=None))
    else:
        text = chat_fn(prompt, history=None)
    return (text or "").strip(), getattr(llm, "model", None)


@summary_bp.route("/generate", methods=["POST"])
def generate_summary():
    """
    生成「单次 query 对话切片」的总结（不带思考过程）。

    请求 JSON：
    {
      "model": "ernie-4.5-turbo-128k",
      "stream": true,
      "turns": [{"role":"user","content":"..."},{"role":"assistant","content":"..."}],
      "meta": {"status":"success","steps_count":2,"execution_time":1.23}
    }

    - stream 默认 true：返回 text/event-stream，每行 data: JSON
      {"type":"delta","delta":"..."}，最后 {"type":"done","summary":"...","model_used":"..."}
    - stream false：一次性 JSON（兼容旧客户端）
    """
    data = request.get_json(silent=True) or {}
    model_name = (data.get("model") or "").strip()
    if model_name.lower() == "auto":
        # summary 不涉及图片；auto 回退到“默认 provider 的默认模型”
        model_name = (
            Config.QIANFAN_MODEL
            if (getattr(Config, "DEFAULT_LLM", "") or "").strip().lower() == "qianfan"
            else Config.DASHSCOPE_MODEL
        )
    turns = data.get("turns") or []
    meta: Dict[str, Any] = data.get("meta") or {}
    use_stream = _coerce_bool(data.get("stream"), default=True)

    dialogue = _format_turns(turns)
    if not dialogue:
        return jsonify({"success": False, "error": "turns 不能为空"}), 400
    if not model_name:
        return jsonify({"success": False, "error": "model 不能为空（请传对话面板下拉框当前模型）"}), 400

    status = meta.get("status")
    steps_count = meta.get("steps_count")
    execution_time = meta.get("execution_time")

    prompt = (
        "你是一个软件工程助手，请对“这一轮用户请求触发的对话”写一段总结。\n"
        "要求：\n"
        "1) 必须用中文输出。\n"
        "2) 不要输出思考过程、推理过程、分析过程等任何中间链路；只输出最终总结。\n"
        "3) 总结必须覆盖：用户要求是什么、过程中做了什么、成果/输出是什么、成功与否与原因。\n"
        "4) 可以引用 AI 的最终答复与关键发现，但要整理成一段/几段可读总结，避免逐条复述。\n"
        "5) 输出格式固定为 4 段（每段以方括号标题开头）：\n"
        "[需求]\\n...\\n\\n[过程]\\n...\\n\\n[成果]\\n...\\n\\n[状态]\\n...\n\n"
        f"补充元信息（可能为空）：status={status}, steps_count={steps_count}, execution_time={execution_time}\n\n"
        "对话如下：\n"
        f"{dialogue}\n"
    )

    if not use_stream:
        try:
            text, resolved_model = _call_sync_full(model_name, prompt)
            if text.lower().startswith("error:"):
                return jsonify({"success": False, "error": text}), 500
            if text.startswith("```"):
                text = text.strip("`").strip()
            model_used = resolved_model or model_name
            return jsonify({"success": True, "summary": text, "model_used": model_used})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

    def generate_sse():
        yield ":" + " " * 2048 + "\n\n"
        llm = get_llm(model=model_name)
        if hasattr(llm, "force_disable_thinking"):
            setattr(llm, "force_disable_thinking", True)
        resolved = getattr(llm, "model", None) or model_name
        parts: List[str] = []
        try:
            for chunk in _iter_llm_text_chunks(llm, prompt):
                if not chunk:
                    continue
                parts.append(chunk)
                yield (
                    "data: "
                    + json.dumps(
                        {"type": "delta", "delta": chunk},
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
            full = "".join(parts).strip()
            if full.lower().startswith("error:"):
                yield (
                    "data: "
                    + json.dumps({"type": "error", "message": full}, ensure_ascii=False)
                    + "\n\n"
                )
                return
            if full.startswith("```"):
                full = full.strip("`").strip()
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "done",
                        "summary": full,
                        "model_used": resolved,
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )
        except Exception as e:
            yield (
                "data: "
                + json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
                + "\n\n"
            )

    resp = Response(
        stream_with_context(generate_sse()),
        mimetype="text/event-stream",
    )
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp
