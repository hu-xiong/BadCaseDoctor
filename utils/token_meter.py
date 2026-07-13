# -*- coding: utf-8
"""Token 预算 preflight / postflight（P0 轻量实现）。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict


def _session_soft_limit() -> int:
    try:
        return int(os.getenv("PROMPT_SESSION_TOKEN_SOFT_LIMIT", "8000000"))
    except ValueError:
        return 8_000_000


def _request_prefill_limit() -> int:
    try:
        return int(os.getenv("PROMPT_REQUEST_PREFILL_TOKEN_LIMIT", "21000"))
    except ValueError:
        return 21_000


@dataclass
class TokenMeter:
    _session_used: Dict[str, int] = field(default_factory=dict)

    def preflight(
        self,
        *,
        estimate_tokens: int,
        session_id: str = "",
        user_id: str = "",
    ) -> Dict[str, Any]:
        sid = (session_id or "").strip() or "_anonymous"
        used = self._session_used.get(sid, 0)
        soft = _session_soft_limit()
        req_limit = _request_prefill_limit()
        allowed = estimate_tokens <= req_limit and (used + estimate_tokens) <= soft
        return {
            "allowed": allowed,
            "session_tokens_used": used,
            "session_soft_limit": soft,
            "request_prefill_limit": req_limit,
            "request_token_estimate": estimate_tokens,
            "user_id": user_id or "",
        }

    def postflight(self, *, session_id: str = "", prefill_tokens: int = 0) -> None:
        sid = (session_id or "").strip() or "_anonymous"
        self._session_used[sid] = self._session_used.get(sid, 0) + max(0, int(prefill_tokens))

    def reset_session(self, session_id: str) -> None:
        sid = (session_id or "").strip() or "_anonymous"
        self._session_used.pop(sid, None)
