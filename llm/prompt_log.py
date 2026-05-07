# -*- coding: utf-8 -*-
"""
调试：打印发往 LLM 的完整请求体（messages / tools 等）。

启用方式 A — 控制台打印整段 JSON（体积大）：
  项目根 .env：LLM_LOG_PROMPTS=1  （改完后必须重启 python app.py）
  PowerShell：$env:LLM_LOG_PROMPTS='1'
  别名：LLM_DEBUG_PROMPTS=1 / LLM_PROMPT_DEBUG=1

启用方式 B — 推荐：只写文件，终端仍有一行确认（不易刷屏、不依赖控制台缓冲）：
  LLM_PROMPT_LOG_PATH=logs/llm_prompt.jsonl
  或 LLM_LOG_PROMPTS_FILE=logs/llm_prompt.jsonl
  路径相对项目启动时的当前工作目录；可先 mkdir logs

可选：
  LLM_LOG_PROMPTS_MAX_CHARS=200000   # 整段 JSON 最大字符，0 表示不截断
  LLM_LOG_PROMPTS_INCLUDE_TOOLS=1    # 默认省略 tools 定义（太长）；设为 1 则打印完整 tools

说明：输出同时使用 logging.warning 与 print；写文件时用线程锁追加。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, Optional

_logger = logging.getLogger("badcase.llm_prompt")
_file_lock = threading.Lock()


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
        # stream_options / extra_body 等保留，便于对齐官方文档
        raw = json.dumps(snap, ensure_ascii=False, default=str)
        mc = llm_prompt_log_max_chars()
        if mc > 0 and len(raw) > mc:
            total_len = len(raw)
            raw = (
                raw[:mc]
                + f"\n... [LLM_PROMPT truncated] LLM_LOG_PROMPTS_MAX_CHARS={mc} json_len={total_len}"
            )
        header = (
            f"[LLM_PROMPT] provider={provider} tag={tag or '-'} "
            f"model={snap.get('model')!r} stream={snap.get('stream', False)!r}"
        )
        if to_console:
            _logger.warning(header)
            print(header, flush=True)
            _logger.warning("%s", raw)
            print(raw, flush=True)
        if to_file:
            block = "\n---\n" + header + "\n" + raw + "\n"
            try:
                os.makedirs(os.path.dirname(to_file) or ".", exist_ok=True)
            except Exception:
                pass
            with _file_lock:
                with open(to_file, "a", encoding="utf-8") as fp:
                    fp.write(block)
            msg = f"[LLM_PROMPT] appended {len(raw)} chars -> {to_file}"
            _logger.warning(msg)
            print(msg, flush=True)
    except Exception as e:
        _logger.warning("[LLM_PROMPT] log_failed: %s", e)
        print(f"[LLM_PROMPT] log_failed: {e}", flush=True)
