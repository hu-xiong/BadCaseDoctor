# -*- coding: utf-8 -*-
"""隧道 token：Flask 签发 / 桥服务验签（HMAC-SHA256，无状态）。

- 格式：base64url(payload_json) + "." + base64url(hmac_sig)
- payload：{"uid": int, "iat": int, "exp": int}
- 密钥：BADCASE_TUNNEL_SECRET（Flask 与桥服务共享；未配置时签发明确报错）
- 关联设计：docs/技术设计_本机浏览器CDP通道.md §6.2 / §11
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any, Dict, Optional

_DEFAULT_TTL_SEC = 7 * 24 * 3600


def tunnel_secret() -> str:
    return (os.getenv("BADCASE_TUNNEL_SECRET") or os.getenv("TUNNEL_SECRET") or "").strip()


def tunnel_token_ttl_sec() -> int:
    raw = (os.getenv("BADCASE_TUNNEL_TOKEN_TTL") or "").strip()
    try:
        n = int(raw)
        return n if n > 0 else _DEFAULT_TTL_SEC
    except ValueError:
        return _DEFAULT_TTL_SEC


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64u_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _sign(payload_b64: str, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _b64u_encode(sig)


def issue_tunnel_token(user_id: int, *, ttl_sec: Optional[int] = None) -> Dict[str, Any]:
    """签发隧道 token；未配置密钥时抛 RuntimeError（调用方转为 503 并给用户明确提示）。"""
    secret = tunnel_secret()
    if not secret:
        raise RuntimeError("BADCASE_TUNNEL_SECRET 未配置，隧道 token 不可签发")
    now = int(time.time())
    ttl = int(ttl_sec) if ttl_sec and int(ttl_sec) > 0 else tunnel_token_ttl_sec()
    payload = {"uid": int(user_id), "iat": now, "exp": now + ttl}
    payload_b64 = _b64u_encode(
        json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    )
    return {
        "token": payload_b64 + "." + _sign(payload_b64, secret),
        "expires_at": payload["exp"],
    }


def verify_tunnel_token(token: str) -> Optional[Dict[str, Any]]:
    """验签 + 过期校验；失败返回 None。"""
    secret = tunnel_secret()
    if not secret:
        return None
    raw = (token or "").strip()
    if "." not in raw:
        return None
    payload_b64, _, sig_b64 = raw.partition(".")
    expect = _sign(payload_b64, secret)
    if not hmac.compare_digest(expect, sig_b64):
        return None
    try:
        payload = json.loads(_b64u_decode(payload_b64).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    try:
        uid = int(payload.get("uid"))
        exp = int(payload.get("exp"))
    except (TypeError, ValueError):
        return None
    if exp <= int(time.time()):
        return None
    return {"uid": uid, "exp": exp, "iat": int(payload.get("iat") or 0)}
