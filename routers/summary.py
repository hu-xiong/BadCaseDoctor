import asyncio
import json
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from llm.factory import get_llm


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


@summary_bp.route("/generate", methods=["POST"])
def generate_summary():
    """
    生成“单次 query 对话切片”的总结（不带思考过程）。

    请求 JSON：
    {
      "model": "qwen3.5-plus",
      "turns": [{"role":"user","content":"..."},{"role":"assistant","content":"..."}],
      "meta": {"status":"success","steps_count":2,"execution_time":1.23}
    }
    """
    data = request.get_json(silent=True) or {}
    model_name = data.get("model")
    turns = data.get("turns") or []
    meta: Dict[str, Any] = data.get("meta") or {}

    dialogue = _format_turns(turns)
    if not dialogue:
        return jsonify({"success": False, "error": "turns 不能为空"}), 400

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

    def _call(model_to_use: str) -> str:
        llm = get_llm(model=model_to_use)
        # 强制不带思考
        if hasattr(llm, "force_disable_thinking"):
            setattr(llm, "force_disable_thinking", True)
        text = asyncio.run(llm.chat(prompt, history=None))
        return (text or "").strip()

    try:
        # 优先用前端传入的模型；若该 provider 配置缺失/报错，则兜底到一个“稳定的不思考模型”
        tried = []
        models_to_try = [model_name, "ernie-4.5-turbo-128k"]
        last_err = None
        for m in models_to_try:
            if not m or m in tried:
                continue
            tried.append(m)
            try:
                text = _call(m)
                # 某些实现会把错误直接作为字符串返回（例如 "Error: ..."），这里按失败处理并尝试兜底模型
                if text.lower().startswith("error:"):
                    last_err = text
                    continue
                if text.startswith("```"):
                    text = text.strip("`").strip()
                return jsonify({"success": True, "summary": text, "model_used": m})
            except Exception as e:
                last_err = str(e)
                continue

        return jsonify({"success": False, "error": last_err or "summary generation failed"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

