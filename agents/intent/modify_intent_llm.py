# -*- coding: utf-8 -*-
"""
modify 歧义（title/description 等）时可选的一次轻量 LLM 分类。

配置见 `config.Config` / `.env`：默认开启；`MODIFY_INTENT_LLM=0|false|off` 关闭。无有效 `DEEPSEEK_API_KEY` 时不请求。

实现：直连 OpenAI 兼容接口，极短 system + max_tokens；**只要求模型输出 XML**（不用 JSON，避免花括号/转义导致解析失败）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from typing import Any, FrozenSet, Optional, Tuple

from config import Config

_VALID = frozenset({"card", "bug", "badcase", "testcase"})

_intent_llm_lock = threading.Lock()
_intent_llm_cache: dict[str, Tuple[float, str]] = {}
_INTENT_LLM_CACHE_TTL_SEC = 12.0


def modify_intent_llm_enabled() -> bool:
    raw = str(
        getattr(Config, "MODIFY_INTENT_LLM", None) or os.getenv("MODIFY_INTENT_LLM") or "1"
    ).strip().lower()
    if raw in ("0", "false", "no", "off", "disable", "disabled"):
        return False
    return True


def _raw_assistant_text(msg: Any) -> str:
    """意图分类只认正文 content；不读取 reasoning（与 extra_body thinking=disabled 一致）。"""
    return (getattr(msg, "content", None) or "").strip()


def _parse_target_xml(text: str) -> Optional[str]:
    """从模型输出中解析目标表：仅 XML，不接受 JSON。"""
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s).strip()
    # <intent target="bug"/> 或 <intent target='card' />
    m = re.search(
        r"<intent\b[^>]*\btarget\s*=\s*[\"'](card|bug|badcase|testcase)[\"']",
        s,
        re.I | re.DOTALL,
    )
    if m:
        t = m.group(1).strip().lower()
        return t if t in _VALID else None
    # <target>bug</target>（可带属性）
    m = re.search(
        r"<target\b[^>]*>\s*(card|bug|badcase|testcase)\s*</target>",
        s,
        re.I | re.DOTALL,
    )
    if m:
        t = m.group(1).strip().lower()
        return t if t in _VALID else None
    return None


def _intent_http_timeout_sec() -> float:
    try:
        v = float(getattr(Config, "MODIFY_INTENT_LLM_TIMEOUT", 8.0))
        return max(2.0, min(v, 60.0))
    except (TypeError, ValueError):
        return 8.0


def _intent_ambiguous_cache_key(
    user_input: str,
    *,
    last_grep_target: Optional[str],
    editing_surface: Optional[str],
    card_id: Optional[int],
    target_id: Optional[int],
    has_raw_bug_list: bool,
    has_raw_badcase_list: bool,
    has_raw_testcase_list: bool,
    keys: FrozenSet[str],
) -> str:
    payload = {
        "u": (user_input or "")[:800],
        "keys": sorted(keys),
        "lgt": (last_grep_target or "").strip(),
        "es": (editing_surface or "").strip(),
        "cid": card_id,
        "tid": target_id,
        "bb": int(has_raw_bug_list),
        "bd": int(has_raw_badcase_list),
        "tc": int(has_raw_testcase_list),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def llm_classify_modify_ambiguous_target(
    user_input: str,
    *,
    last_grep_target: Optional[str] = None,
    editing_surface: Optional[str] = None,
    card_id: Optional[int] = None,
    target_id: Optional[int] = None,
    has_raw_bug_list: bool = False,
    has_raw_badcase_list: bool = False,
    has_raw_testcase_list: bool = False,
    keys: FrozenSet[str],
) -> Optional[str]:
    """
    一次 chat 调用，返回 card / bug / badcase / testcase；失败返回 None。
    """
    if not modify_intent_llm_enabled():
        return None
    key = (getattr(Config, "DEEPSEEK_API_KEY", None) or "").strip()
    if not key:
        return None

    model = (getattr(Config, "MODIFY_INTENT_LLM_MODEL", None) or "deepseek-v4-flash").strip() or "deepseek-v4-flash"

    keys_s = ",".join(sorted(keys)) if keys else ""
    u = (user_input or "").strip()
    if len(u) > 500:
        u = u[:500] + "…"

    ctx_line = (
        f"last_grep={last_grep_target!r} surface={editing_surface!r} card_id={card_id!r} "
        f"target_id={target_id!r} bug_list={int(has_raw_bug_list)} badcase_list={int(has_raw_badcase_list)} "
        f"testcase_list={int(has_raw_testcase_list)} keys={keys_s!r}"
    )
    user_block = ctx_line + "\n用户：" + u

    system = (
        "只输出一行 XML，不要输出任何其它文字、不要 Markdown、不要 JSON。"
        "禁止思考过程、禁止解释、禁止推理链，只输出 XML。"
        '格式必须是：<intent target="card"/> 或 <intent target="bug"/> 或 <intent target="badcase"/> 或 <intent target="testcase"/>。'
        "card=改看板卡片展示层；bug/badcase/testcase=改对应源表记录。"
    )

    ck = _intent_ambiguous_cache_key(
        user_input,
        last_grep_target=last_grep_target,
        editing_surface=editing_surface,
        card_id=card_id,
        target_id=target_id,
        has_raw_bug_list=has_raw_bug_list,
        has_raw_badcase_list=has_raw_badcase_list,
        has_raw_testcase_list=has_raw_testcase_list,
        keys=keys,
    )
    now = time.monotonic()
    with _intent_llm_lock:
        hit = _intent_llm_cache.get(ck)
        if hit and (now - hit[0]) <= _INTENT_LLM_CACHE_TTL_SEC:
            print(
                f"[MODIFY-INTENT-LLM] cache_hit ttl_left≈{_INTENT_LLM_CACHE_TTL_SEC - (now - hit[0]):.1f}s "
                f"-> {hit[1]!r}",
                flush=True,
            )
            return hit[1]

    read_sec = _intent_http_timeout_sec()
    try:
        from openai import OpenAI

        base = (getattr(Config, "DEEPSEEK_API_BASE_URL", None) or "https://api.deepseek.com").strip().rstrip("/")
        client = OpenAI(
            api_key=key,
            base_url=base,
            timeout=read_sec,
            max_retries=0,
        )
        kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_block},
            ],
            temperature=0,
            max_tokens=128,
            stream=False,
            # 关闭 DeepSeek thinking / reasoning，且绝不传 reasoning_effort（避免网关误判开启）
            extra_body={"thinking": {"type": "disabled"}},
        )
        resp = client.chat.completions.create(**kwargs)
        ch0 = resp.choices[0] if resp.choices else None
        msg = getattr(ch0, "message", None) if ch0 else None
        raw = _raw_assistant_text(msg) if msg is not None else ""
        out = _parse_target_xml(raw)
        if out:
            print(f"[MODIFY-INTENT-LLM] model={model!r} -> {out!r}", flush=True)
            with _intent_llm_lock:
                _intent_llm_cache[ck] = (time.monotonic(), out)
        else:
            fr = getattr(ch0, "finish_reason", None) if ch0 else None
            ct0 = (getattr(msg, "content", None) or "") if msg is not None else ""
            rc0 = getattr(msg, "reasoning_content", None) if msg is not None else None
            rc_len = len(rc0) if isinstance(rc0, str) else 0
            print(
                f"[MODIFY-INTENT-LLM] model={model!r} 解析失败 finish_reason={fr!r} "
                f"content_len={len(ct0)} reasoning_len={rc_len} raw={raw[:200]!r}",
                flush=True,
            )
        return out
    except Exception as e:
        print(f"[MODIFY-INTENT-LLM] 调用失败(将回退启发式): {e}", flush=True)
        return None
