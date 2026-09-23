# -*- coding: utf-8 -*-
"""本机浏览器 CDP 通道 —— 云端桥服务（独立 asyncio 进程，aiohttp）。

职责（见 docs/技术设计_本机浏览器CDP通道.md）：
  1. Tunnel Hub：接受 go-local-proxy 反连（/api/local-proxy/tunnel），
     tunnel-token 认证后按 user_id 注册；新连接顶掉旧连接。
  2. CDP 网关：Playwright / midscene 经环回 ws://127.0.0.1:{gateway_port}/cdp/{key} 连入，
     经隧道透传到本机 Chrome DevTools ws（仅环回监听，绝不对外暴露）。
  3. Internal API：环回 HTTP，供 Flask/Agent 查询隧道状态、申领 route key。

帧协议：
  - 控制帧：text JSON（hello / hello_ack / cdp_open / cdp_open_ack / cdp_close / error）
  - 数据帧：binary = [4B sid 大端][CDP ws 消息原始字节]

环境变量：
  BADCASE_BRIDGE_BIND          默认 127.0.0.1
  BADCASE_BRIDGE_TUNNEL_PORT   默认 9889（经 nginx 暴露 /api/local-proxy/tunnel）
  BADCASE_CDP_GATEWAY_PORT     默认 9888（仅环回；/cdp/{key} 与 /internal/*）
  BADCASE_TUNNEL_SECRET        隧道 token HMAC 密钥（必填；与 Flask 共享）
  BADCASE_BRIDGE_INTERNAL_KEY  internal API 头校验密钥（可选，空则仅校验环回来源）
  BADCASE_CDP_ROUTE_TTL_SEC    route key TTL，默认 600

启动：venv/bin/python local_browser_bridge.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import struct
import time
from typing import Any, Dict, Optional

from aiohttp import WSMsgType, web

from app_services.tunnel_token import verify_tunnel_token

log = logging.getLogger("local_browser_bridge")

SID_STRUCT = struct.Struct(">I")
MAX_FRAME = 8 * 1024 * 1024  # 8MB 单帧上限（设计 §5.2）
HELLO_TIMEOUT_SEC = 10.0
OPEN_ACK_TIMEOUT_SEC = 12.0
MAX_STREAMS_PER_TUNNEL = 16


def _env_int(name: str, default: int) -> int:
    try:
        n = int((os.getenv(name) or "").strip())
        return n if n > 0 else default
    except ValueError:
        return default


def _sanitize_device(raw: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(raw, dict):
        return out
    for k in ("platform", "hostname", "proxy_version"):
        v = str(raw.get(k) or "").strip()
        if v:
            out[k] = v[:200]
    return out


def _peer_is_loopback(request: web.Request) -> bool:
    peer = (request.remote or "").strip()
    return peer in ("127.0.0.1", "::1", "localhost") or peer.startswith("127.")


class CdpStream:
    """一条 CDP 流：网关侧 Playwright ws ↔ 隧道 sid 的桥接单元。"""

    __slots__ = ("sid", "queue", "opened", "error", "closed")

    def __init__(self, sid: int):
        self.sid = sid
        self.queue: asyncio.Queue = asyncio.Queue()
        self.opened = asyncio.Event()
        self.error: Optional[str] = None
        self.closed = False

    def feed(self, payload: bytes) -> None:
        if not self.closed:
            self.queue.put_nowait(payload)

    def fail(self, reason: str) -> None:
        if self.error is None:
            self.error = reason
        self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.queue.put_nowait(None)  # 哨兵：唤醒消费端


class TunnelConn:
    """一条在线隧道（一个用户的一台本机代理）。"""

    def __init__(self, ws: web.WebSocketResponse, user_id: int, device: Dict[str, str]):
        self.ws = ws
        self.user_id = int(user_id)
        self.device = device
        self.connected_at = time.time()
        self.streams: Dict[int, CdpStream] = {}
        self._ack_waiters: Dict[int, asyncio.Future] = {}
        self._write_lock = asyncio.Lock()
        self._sid_seq = 0
        self.closed = False

    @property
    def stream_count(self) -> int:
        return len(self.streams)

    def _next_sid(self) -> int:
        self._sid_seq += 1
        return self._sid_seq

    async def send_control(self, obj: Dict[str, Any]) -> None:
        async with self._write_lock:
            await self.ws.send_json(obj)

    async def send_data(self, sid: int, payload: bytes) -> None:
        async with self._write_lock:
            await self.ws.send_bytes(SID_STRUCT.pack(sid) + payload)

    async def open_stream(self, *, timeout: float = OPEN_ACK_TIMEOUT_SEC) -> CdpStream:
        """向本机代理申请一条 browser-level CDP 流；失败返回 error 非空的 stream。"""
        if self.closed:
            st = CdpStream(0)
            st.fail("tunnel_closed")
            return st
        if self.stream_count >= MAX_STREAMS_PER_TUNNEL:
            st = CdpStream(0)
            st.fail("too_many_streams")
            return st
        sid = self._next_sid()
        st = CdpStream(sid)
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._ack_waiters[sid] = fut
        self.streams[sid] = st
        try:
            await self.send_control({"op": "cdp_open", "sid": sid})
        except Exception as ex:
            self.streams.pop(sid, None)
            self._ack_waiters.pop(sid, None)
            st.fail(f"send_failed: {ex}")
            return st
        try:
            ok, err = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            ok, err = False, "ack_timeout"
        except Exception as ex:
            ok, err = False, str(ex)
        self._ack_waiters.pop(sid, None)
        if ok:
            st.opened.set()
        else:
            self.streams.pop(sid, None)
            st.fail(err or "open_failed")
        return st

    async def handle_text(self, text: str) -> None:
        try:
            msg = json.loads(text)
        except Exception:
            return
        if not isinstance(msg, dict):
            return
        op = str(msg.get("op") or "")
        try:
            sid = int(msg.get("sid") or 0)
        except (TypeError, ValueError):
            sid = 0
        if op == "cdp_open_ack":
            fut = self._ack_waiters.get(sid)
            if fut is not None and not fut.done():
                fut.set_result((bool(msg.get("ok")), str(msg.get("error") or "")))
            return
        if op == "cdp_close":
            st = self.streams.pop(sid, None)
            if st is not None:
                st.close()
            return
        if op == "error":
            st = self.streams.pop(sid, None)
            if st is not None:
                st.fail(str(msg.get("message") or "tunnel_error"))
            return

    async def handle_binary(self, data: bytes) -> None:
        if len(data) < SID_STRUCT.size:
            return
        sid, = SID_STRUCT.unpack_from(data, 0)
        st = self.streams.get(sid)
        if st is not None:
            st.feed(data[SID_STRUCT.size:])

    async def shutdown(self, reason: str) -> None:
        self.closed = True
        for st in list(self.streams.values()):
            st.fail(reason)
        self.streams.clear()
        for fut in list(self._ack_waiters.values()):
            if not fut.done():
                fut.set_result((False, reason))
        self._ack_waiters.clear()
        try:
            await self.ws.close()
        except Exception:
            pass


class TunnelRegistry:
    def __init__(self) -> None:
        self._tunnels: Dict[int, TunnelConn] = {}

    def get(self, user_id: int) -> Optional[TunnelConn]:
        conn = self._tunnels.get(int(user_id))
        if conn is not None and conn.closed:
            return None
        return conn

    def online(self, user_id: int) -> bool:
        return self.get(int(user_id)) is not None

    def register(self, conn: TunnelConn) -> Optional[TunnelConn]:
        """注册新连接；返回被顶掉的旧连接（如有）。"""
        old = self._tunnels.get(conn.user_id)
        self._tunnels[conn.user_id] = conn
        if old is not None and old is not conn:
            return old
        return None

    def unregister(self, conn: TunnelConn) -> None:
        if self._tunnels.get(conn.user_id) is conn:
            self._tunnels.pop(conn.user_id, None)

    def count(self) -> int:
        return len(self._tunnels)


class RouteTable:
    """route key → user_id（TTL），供网关校验 Playwright 侧连接。"""

    def __init__(self, ttl_sec: int):
        self._ttl = max(30, int(ttl_sec))
        self._routes: Dict[str, Dict[str, Any]] = {}

    def issue(self, user_id: int) -> Dict[str, Any]:
        key = secrets.token_urlsafe(24)
        exp = time.time() + self._ttl
        self._routes[key] = {"user_id": int(user_id), "expires_at": exp}
        return {"route_key": key, "expires_at": int(exp)}

    def resolve(self, key: str) -> Optional[int]:
        row = self._routes.get(key)
        if row is None:
            return None
        if float(row["expires_at"]) <= time.time():
            self._routes.pop(key, None)
            return None
        return int(row["user_id"])

    def sweep(self) -> int:
        now = time.time()
        dead = [k for k, v in self._routes.items() if float(v["expires_at"]) <= now]
        for k in dead:
            self._routes.pop(k, None)
        return len(dead)

    def count(self) -> int:
        return len(self._routes)


class BridgeState:
    def __init__(self) -> None:
        self.tunnels = TunnelRegistry()
        self.routes = RouteTable(_env_int("BADCASE_CDP_ROUTE_TTL_SEC", 600))
        self.gateway_ws_base = f"ws://127.0.0.1:{_env_int('BADCASE_CDP_GATEWAY_PORT', 9888)}"


# ---------------------------------------------------------------- tunnel 入口

def _make_tunnel_handler(state: BridgeState):
    async def handle_tunnel(request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30.0, max_msg_size=MAX_FRAME, autoping=True)
        await ws.prepare(request)

        # 首帧 hello（限时，防僵尸连接占用）
        try:
            first = await asyncio.wait_for(ws.receive(), timeout=HELLO_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            await ws.close(code=4001, message=b"hello_timeout")
            return ws
        token = ""
        device_raw: Any = {}
        if first.type == WSMsgType.TEXT:
            try:
                hello = json.loads(first.data)
            except Exception:
                hello = {}
            if isinstance(hello, dict) and str(hello.get("op") or "") == "hello":
                token = str(hello.get("token") or "")
                device_raw = hello.get("device")
        auth = verify_tunnel_token(token)
        if auth is None:
            log.warning("[bridge] tunnel auth failed peer=%s", request.remote)
            await ws.close(code=4001, message=b"auth_failed")
            return ws

        uid = int(auth["uid"])
        conn = TunnelConn(ws=ws, user_id=uid, device=_sanitize_device(device_raw))
        old = state.tunnels.register(conn)
        if old is not None:
            log.warning(
                "[bridge] tunnel replaced user=%s old_connected_at=%.0f",
                uid,
                old.connected_at,
            )
            await old.shutdown("replaced_by_new_device")
        try:
            await conn.send_control(
                {"op": "hello_ack", "ok": True, "user_id": uid, "heartbeat_sec": 30}
            )
        except Exception as ex:
            state.tunnels.unregister(conn)
            log.warning("[bridge] hello_ack failed user=%s: %s", uid, ex)
            return ws
        log.info(
            "[bridge] tunnel online user=%s device=%s peer=%s",
            uid,
            conn.device or "-",
            request.remote,
        )
        try:
            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    await conn.handle_text(m.data)
                elif m.type == WSMsgType.BINARY:
                    await conn.handle_binary(m.data)
                elif m.type == WSMsgType.ERROR:
                    break
        finally:
            state.tunnels.unregister(conn)
            await conn.shutdown("tunnel_closed")
            log.info("[bridge] tunnel offline user=%s", uid)
        return ws

    return handle_tunnel


# ---------------------------------------------------------------- CDP 网关

def _make_gateway_handler(state: BridgeState):
    async def handle_gateway(request: web.Request) -> web.WebSocketResponse:
        key = str(request.match_info.get("key") or "")
        uid = state.routes.resolve(key)
        if uid is None:
            raise web.HTTPNotFound(text="route key invalid or expired")
        tunnel = state.tunnels.get(uid)
        if tunnel is None:
            raise web.HTTPServiceUnavailable(text="local proxy tunnel offline")

        ws = web.WebSocketResponse(heartbeat=30.0, max_msg_size=MAX_FRAME, autoping=True)
        await ws.prepare(request)

        st = await tunnel.open_stream()
        if st.error:
            log.warning("[bridge] cdp_open failed user=%s error=%s", uid, st.error)
            await ws.close(code=1011, message=b"cdp_open_failed")
            return ws
        log.info("[bridge] cdp stream open user=%s sid=%s peer=%s", uid, st.sid, request.remote)

        send_lock = asyncio.Lock()

        async def pump_playwright_to_tunnel() -> None:
            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    await tunnel.send_data(st.sid, m.data.encode("utf-8"))
                elif m.type == WSMsgType.BINARY:
                    await tunnel.send_data(st.sid, m.data)
                elif m.type == WSMsgType.ERROR:
                    break

        async def pump_tunnel_to_playwright() -> None:
            while True:
                payload = await st.queue.get()
                if payload is None:
                    break
                async with send_lock:
                    try:
                        await ws.send_str(payload.decode("utf-8"))
                    except UnicodeDecodeError:
                        await ws.send_bytes(payload)

        t1 = asyncio.create_task(pump_playwright_to_tunnel())
        t2 = asyncio.create_task(pump_tunnel_to_playwright())
        try:
            await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for t in (t1, t2):
                if not t.done():
                    t.cancel()
            tunnel.streams.pop(st.sid, None)
            st.close()
            try:
                await tunnel.send_control(
                    {"op": "cdp_close", "sid": st.sid, "reason": "gateway_closed"}
                )
            except Exception:
                pass
            try:
                await ws.close()
            except Exception:
                pass
            log.info("[bridge] cdp stream closed user=%s sid=%s", uid, st.sid)
        return ws

    return handle_gateway


# ---------------------------------------------------------------- internal API

def _guard_internal(request: web.Request) -> None:
    if not _peer_is_loopback(request):
        raise web.HTTPForbidden(text="loopback only")
    expect = (os.getenv("BADCASE_BRIDGE_INTERNAL_KEY") or "").strip()
    if expect and request.headers.get("X-Bridge-Key", "") != expect:
        raise web.HTTPForbidden(text="bad bridge key")


def _make_internal_handlers(state: BridgeState):
    async def health(request: web.Request) -> web.Response:
        return web.json_response(
            {"ok": True, "tunnels": state.tunnels.count(), "routes": state.routes.count()}
        )

    async def tunnel_status(request: web.Request) -> web.Response:
        _guard_internal(request)
        try:
            uid = int(request.query.get("user_id") or 0)
        except ValueError:
            uid = 0
        if uid <= 0:
            raise web.HTTPBadRequest(text="user_id required")
        conn = state.tunnels.get(uid)
        return web.json_response(
            {
                "ok": True,
                "online": conn is not None,
                "device": dict(conn.device) if conn is not None else {},
                "streams": conn.stream_count if conn is not None else 0,
            }
        )

    async def issue_route(request: web.Request) -> web.Response:
        _guard_internal(request)
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            uid = int((body or {}).get("user_id") or 0)
        except (TypeError, ValueError):
            uid = 0
        if uid <= 0:
            raise web.HTTPBadRequest(text="user_id required")
        if not state.tunnels.online(uid):
            return web.json_response({"ok": False, "error": "tunnel_offline"}, status=409)
        row = state.routes.issue(uid)
        key = str(row["route_key"])
        return web.json_response(
            {
                "ok": True,
                "route_key": key,
                "ws_url": f"{state.gateway_ws_base}/cdp/{key}",
                "expires_at": row["expires_at"],
            }
        )

    return health, tunnel_status, issue_route


# ---------------------------------------------------------------- 启动

async def _route_sweeper(state: BridgeState, interval: float = 60.0) -> None:
    while True:
        await asyncio.sleep(interval)
        n = state.routes.sweep()
        if n:
            log.debug("[bridge] routes swept: %d", n)


async def _amain() -> None:
    bind = (os.getenv("BADCASE_BRIDGE_BIND") or "127.0.0.1").strip() or "127.0.0.1"
    tunnel_port = _env_int("BADCASE_BRIDGE_TUNNEL_PORT", 9889)
    gateway_port = _env_int("BADCASE_CDP_GATEWAY_PORT", 9888)

    state = BridgeState()
    health, tunnel_status, issue_route = _make_internal_handlers(state)

    tunnel_app = web.Application()
    tunnel_app.router.add_get("/api/local-proxy/tunnel", _make_tunnel_handler(state))
    tunnel_app.router.add_get("/health", lambda r: web.json_response({"ok": True}))

    gateway_app = web.Application()
    gateway_app.router.add_get("/cdp/{key}", _make_gateway_handler(state))
    gateway_app.router.add_get("/internal/health", health)
    gateway_app.router.add_get("/internal/tunnel_status", tunnel_status)
    gateway_app.router.add_post("/internal/routes", issue_route)

    runner_tunnel = web.AppRunner(tunnel_app, access_log=None)
    runner_gateway = web.AppRunner(gateway_app, access_log=None)
    await runner_tunnel.setup()
    await runner_gateway.setup()
    try:
        await web.TCPSite(runner_tunnel, bind, tunnel_port).start()
        await web.TCPSite(runner_gateway, bind, gateway_port).start()
    except OSError as ex:
        log.error("[bridge] listen failed bind=%s tunnel=%s gateway=%s: %s", bind, tunnel_port, gateway_port, ex)
        await runner_tunnel.cleanup()
        await runner_gateway.cleanup()
        raise

    log.info(
        "[bridge] listen tunnel=%s:%s (nginx → /api/local-proxy/tunnel)  gateway=%s:%s (loopback only)",
        bind,
        tunnel_port,
        bind,
        gateway_port,
    )
    if not (os.getenv("BADCASE_TUNNEL_SECRET") or os.getenv("TUNNEL_SECRET") or "").strip():
        log.warning("[bridge] BADCASE_TUNNEL_SECRET 未配置：所有隧道 hello 都会被拒绝")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in ("SIGINT", "SIGTERM"):
        try:
            import signal as _signal

            loop.add_signal_handler(getattr(_signal, sig), stop_event.set)
        except (NotImplementedError, AttributeError, ValueError):
            pass

    sweeper = asyncio.create_task(_route_sweeper(state))
    try:
        await stop_event.wait()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        sweeper.cancel()
        await runner_tunnel.cleanup()
        await runner_gateway.cleanup()
        log.info("[bridge] stopped")


def main() -> int:
    logging.basicConfig(
        level=os.getenv("BADCASE_BRIDGE_LOG_LEVEL", "INFO").upper(),
        format="[%(asctime)s] %(levelname)s %(message)s",
    )
    try:
        asyncio.run(_amain())
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
