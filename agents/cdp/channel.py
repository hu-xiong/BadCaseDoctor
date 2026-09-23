# -*- coding: utf-8 -*-
"""本机浏览器 CDP 通道：桥服务 internal API 客户端 + ensure（设计 §8.2）。

职责：
  - owner_key → 登录 user_id（隧道按用户注册，见 local_browser_bridge.py）；
  - 查询隧道在线状态（tunnel_status）与申领 route key（issue_route）；
  - ``ensure_local_channel``：在线立即申领新 ws（ws://127.0.0.1:{gateway}/cdp/{key}）；
    离线时按需轮询等待（前端被唤起拉起代理的场景），超时返回 None 交由调用方
    走 client_browser 卡片流程（browser_local），不静默降级云端 launch（D8）。

环境变量（见 settings.py）：
  CDP_CONNECTION_MODE       auto|local|launch（launch 时本模块不会被调用）
  BADCASE_BRIDGE_BASE_URL   桥服务基址，默认 http://127.0.0.1:${BADCASE_CDP_GATEWAY_PORT|9888}
  BADCASE_BRIDGE_INTERNAL_KEY  internal API 的 X-Bridge-Key
  CDP_CHANNEL_WAIT_SEC      ensure 等待上限，默认 20s
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .settings import (
    cdp_bridge_base_url,
    cdp_bridge_internal_key,
    cdp_bridge_timeout_sec,
    cdp_channel_wait_sec,
)

_ENSURE_POLL_INTERVAL_SEC = 2.0


@dataclass
class TunnelStatus:
    online: bool = False
    device: Dict[str, str] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteLease:
    route_key: str
    ws_url: str
    expires_at: int = 0


def owner_user_id(owner_key: Optional[str]) -> Optional[int]:
    """owner_key（``user:{id}``）→ 隧道 user_id；anonymous / project:* 无隧道归属。"""
    raw = str(owner_key or "").strip()
    if raw.startswith("user:"):
        tail = raw[5:].strip()
        if tail.isdigit():
            return int(tail)
    return None


def _request_json(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """环回请求桥服务 internal API；任何失败返回 None（调用方按离线处理）。"""
    url = cdp_bridge_base_url() + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    key = cdp_bridge_internal_key()
    if key:
        req.add_header("X-Bridge-Key", key)
    try:
        with urllib.request.urlopen(req, timeout=cdp_bridge_timeout_sec()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def tunnel_status(user_id: int) -> TunnelStatus:
    """查询指定用户的本机代理隧道是否在线。"""
    obj = _request_json("GET", f"/internal/tunnel_status?user_id={int(user_id)}")
    if not obj:
        return TunnelStatus()
    device_raw = obj.get("device") if isinstance(obj.get("device"), dict) else {}
    device = {str(k): str(v) for k, v in device_raw.items() if str(v).strip()}
    return TunnelStatus(online=bool(obj.get("online")), device=device, raw=obj)


def issue_route(user_id: int) -> Optional[RouteLease]:
    """申领一个网关 route key（TTL 由桥侧控制），返回 Playwright 可直连的 ws URL。"""
    obj = _request_json("POST", "/internal/routes", {"user_id": int(user_id)})
    if not obj or not str(obj.get("ws_url") or "").strip():
        return None
    try:
        expires = int(obj.get("expires_at") or 0)
    except (TypeError, ValueError):
        expires = 0
    return RouteLease(
        route_key=str(obj.get("route_key") or ""),
        ws_url=str(obj["ws_url"]).strip(),
        expires_at=expires,
    )


async def tunnel_status_async(user_id: int) -> TunnelStatus:
    return await asyncio.to_thread(tunnel_status, int(user_id))


async def ensure_local_channel(
    owner_key: Optional[str], *, wait_sec: Optional[float] = None
) -> Optional[str]:
    """确保本机通道可用并返回网关 ws；不可用返回 None。

    - 在线：立即申领 route key 返回新 ws（每次调用都是新 key）。
    - 离线：轮询等待 ``wait_sec``（默认 settings.cdp_channel_wait_sec，0 只查一次），
      供「前端被卡片唤起拉起代理」的时间窗使用；超时返回 None。
    """
    user_id = owner_user_id(owner_key)
    if user_id is None:
        return None
    total = cdp_channel_wait_sec() if wait_sec is None else max(0.0, float(wait_sec))
    deadline = time.monotonic() + total
    waited = False
    while True:
        status = await tunnel_status_async(user_id)
        if status.online:
            lease = await asyncio.to_thread(issue_route, user_id)
            if lease is not None:
                if waited:
                    print(f"[CDP] mode=local 通道恢复 owner={owner_key}", flush=True)
                return lease.ws_url
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        if not waited:
            print(
                f"[CDP] mode=local 通道离线，等待本机代理上线（≤{int(total)}s）owner={owner_key}",
                flush=True,
            )
            waited = True
        await asyncio.sleep(min(_ENSURE_POLL_INTERVAL_SEC, remaining))
