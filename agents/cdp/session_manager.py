# -*- coding: utf-8 -*-
"""浏览器会话：Playwright + CDP，TTL / 最大会话数。"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .owner import resolve_cdp_owner_key
from .channel import ensure_local_channel, issue_route, owner_user_id, tunnel_status_async

from .errors import (
    CdpError,
    LOCAL_CHANNEL_UNAVAILABLE,
    NAVIGATION_FAILED,
    PLAYWRIGHT_UNAVAILABLE,
    SESSION_NOT_FOUND,
)
from .settings import (
    assert_url_allowed,
    cdp_browser_idle_sec,
    cdp_connection_mode,
    cdp_default_timeout_ms,
    cdp_headless,
    cdp_max_sessions,
    cdp_session_ttl_sec,
    cdp_snapshot_max_nodes,
    is_private_url,
)
from .snapshot import AxSnapshotBuilder, PageSnapshot
from .element_actor import ElementActor

_playwright = None
_async_playwright = None


def _cdp_error_with_browser_card(
    e: CdpError, *, url: Optional[str] = None, headless: Optional[bool] = None
) -> Dict[str, Any]:
    """本地代理通道离线时，在错误结果上附带本机浏览器唤起卡片（前端 client_action kind=browser_local）。"""
    out = e.to_dict()
    if e.code == LOCAL_CHANNEL_UNAVAILABLE:
        out["browser_pause_for_client"] = True
        out["client_browser"] = {
            "action": "start",
            "url": str(url or "").strip(),
            "headless": bool(headless),
        }
    return out


def _ensure_playwright():
    global _playwright, _async_playwright
    if _async_playwright is not None:
        return _async_playwright
    try:
        from playwright.async_api import async_playwright

        _async_playwright = async_playwright
        return _async_playwright
    except ImportError as e:
        raise CdpError(
            PLAYWRIGHT_UNAVAILABLE,
            "未安装 playwright，请执行: pip install playwright && playwright install chromium",
        ) from e


@dataclass
class BrowserSession:
    session_id: str
    playwright: Any
    browser: Any
    context: Any
    page: Any
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    last_snapshot: Optional[PageSnapshot] = None
    _snapshots: Dict[str, PageSnapshot] = field(default_factory=dict)
    _cdp: Any = None
    awaiting_verification: bool = False
    awaiting_verification_snapshot_id: Optional[str] = None
    awaiting_verification_project_id: Optional[int] = None
    owns_browser: bool = False
    owner_key: str = "anonymous"
    local_mode: bool = False  # True=本机浏览器（隧道网关连接）：close 不关 context/browser
    owns_page: bool = False  # local 模式下本会话新建的 tab（close 时释放；复用的 tab 保留）
    llm_capture: Any = None  # LLM 报文采集器（见 llm_capture.py）

    async def touch(self) -> None:
        self.last_used_at = time.time()

    async def cdp_session(self):
        if self._cdp is None:
            self._cdp = await self.context.new_cdp_session(self.page)
            await self._cdp.send("Accessibility.enable")
        return self._cdp

    def get_snapshot(self, snapshot_id: Optional[str]) -> Optional[PageSnapshot]:
        if snapshot_id and snapshot_id in self._snapshots:
            return self._snapshots[snapshot_id]
        if self.last_snapshot and (
            not snapshot_id or self.last_snapshot.snapshot_id == snapshot_id
        ):
            return self.last_snapshot
        return None

    async def page_info(self) -> Dict[str, str]:
        return {"url": self.page.url, "title": await self.page.title()}

    def list_pages(self) -> List[Any]:
        try:
            return list(self.context.pages)
        except Exception:
            return [self.page] if self.page else []

    async def switch_page(self, index: int) -> None:
        pages = self.list_pages()
        if index < 0 or index >= len(pages):
            raise CdpError(SESSION_NOT_FOUND, f"tab index 越界: {index} (n={len(pages)})")
        self.page = pages[index]
        self._cdp = None
        self.last_snapshot = None
        await self.page.bring_to_front()
        if self.llm_capture is not None:
            try:
                self.llm_capture.attach(self.page)
            except Exception:
                pass
        await self.touch()

    async def close(self) -> None:
        try:
            if self._cdp:
                await self._cdp.detach()
        except Exception:
            pass
        if self.local_mode:
            # 本机共享浏览器（D6/D7）：仅释放本会话——不关 context（登录态留存本机 profile）、
            # 不关浏览器（生命周期归本机 go 代理）；仅当 tab 由本会话新建时才关闭
            if self.owns_page and self.page is not None:
                try:
                    await self.page.close()
                except Exception:
                    pass
            return
        try:
            await self.context.close()
        except Exception:
            pass
        if self.owns_browser:
            try:
                await self.browser.close()
            except Exception:
                pass


_CHROMIUM_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
]


def _find_free_port() -> int:
    """分配一个本机空闲端口，供 Chromium remote-debugging 暴露 DevTools 端点。"""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _fetch_ws_endpoint(port: int) -> Optional[str]:
    """读取本机 Chromium DevTools HTTP 端点的 webSocketDebuggerUrl（Playwright 自身不暴露 ws）。"""
    import json as _json
    import urllib.request

    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{int(port)}/json/version", timeout=3
        ) as resp:
            data = _json.loads(resp.read().decode("utf-8", errors="replace"))
        ws = str((data or {}).get("webSocketDebuggerUrl") or "").strip()
        return ws or None
    except Exception:
        return None


def _launch_channel_candidates() -> List[Optional[str]]:
    """
    Playwright 自带 Chromium 可能因 PLAYWRIGHT_BROWSERS_PATH（如 Cursor sandbox 缓存）
    不完整而 launch 失败；优先显式 channel，再回退本机 Chrome/Edge。
    """
    raw = (os.getenv("CDP_BROWSER_CHANNEL") or os.getenv("CDP_CHROME_CHANNEL") or "").strip()
    out: List[Optional[str]] = []
    if raw:
        out.append(raw)
    # None = Playwright 自带 chromium
    out.append(None)
    for ch in ("chrome", "msedge", "chrome-beta", "msedge-beta"):
        if ch not in out:
            out.append(ch)
    return out


def _is_missing_browser_executable_error(ex: BaseException) -> bool:
    msg = str(ex).lower()
    return "executable doesn't exist" in msg or (
        "doesn't exist" in msg and "launch" in msg
    )


async def _launch_chromium(pw: Any, *, headless: bool, debug_port: Optional[int] = None) -> Any:
    last_ex: Optional[BaseException] = None
    for channel in _launch_channel_candidates():
        args = list(_CHROMIUM_LAUNCH_ARGS)
        if debug_port:
            # 暴露本机 DevTools 端点，让 Midscene/Gremlins 子进程 connectOverCDP 复用同一浏览器
            args.append(f"--remote-debugging-port={int(debug_port)}")
        kwargs: Dict[str, Any] = {
            "headless": headless,
            "args": args,
        }
        if channel:
            kwargs["channel"] = channel
        try:
            browser = await pw.chromium.launch(**kwargs)
            if channel:
                print(f"[CDP] chromium.launch ok channel={channel!r} headless={headless}", flush=True)
            return browser
        except Exception as ex:
            last_ex = ex
            if channel is None and _is_missing_browser_executable_error(ex):
                print(
                    f"[CDP] Playwright 自带 Chromium 不可用，尝试本机 Chrome/Edge: {ex}",
                    flush=True,
                )
                continue
            if channel and _is_missing_browser_executable_error(ex):
                continue
            # 非「缺可执行文件」类错误：仍尝试下一 channel，最后汇总
            print(
                f"[CDP] chromium.launch 失败 channel={channel!r}: {type(ex).__name__}: {ex}",
                flush=True,
            )
            continue
    hint = (
        "无法启动浏览器。请安装 Google Chrome / Microsoft Edge，"
        "或执行: python -m playwright install chromium"
        "（并检查 PLAYWRIGHT_BROWSERS_PATH 是否指向不完整缓存）。"
    )
    raise CdpError(
        PLAYWRIGHT_UNAVAILABLE,
        f"{hint} 最后错误: {last_ex}",
    ) from last_ex


def _is_stale_browser_error(ex: BaseException) -> bool:
    msg = str(ex).lower()
    return any(
        k in msg
        for k in (
            "nonetype",
            "has no attribute 'send'",
            "browser has been closed",
            "connection closed",
            "target closed",
            "browser.new_context",
            "browser closed",
        )
    )


@dataclass
class _BrowserPoolSlot:
    browser: Any
    headless: bool
    debug_port: Optional[int] = None
    idle_task: Optional[asyncio.Task] = None


@dataclass
class LocalBrowserSlot:
    """本机浏览器连接槽（经隧道网关 connect_over_cdp），按 owner_key 缓存。"""

    browser: Any
    ws_url: str
    connected_at: float = field(default_factory=time.time)


class CdpSessionManager:
    _instance: Optional["CdpSessionManager"] = None

    def __init__(self):
        self._sessions: Dict[str, BrowserSession] = {}
        self._pw = None
        self._pw_cm = None
        self._pw_loop: Optional[asyncio.AbstractEventLoop] = None
        self._browser_pools: Dict[str, _BrowserPoolSlot] = {}
        self._local_slots: Dict[str, LocalBrowserSlot] = {}
        self._lock = asyncio.Lock()
        self._sweeper_started = False

    @classmethod
    def get(cls) -> "CdpSessionManager":
        if cls._instance is None:
            cls._instance = CdpSessionManager()
        return cls._instance

    def _start_sweeper(self) -> None:
        if self._sweeper_started:
            return
        self._sweeper_started = True

        async def _loop():
            while True:
                await asyncio.sleep(60)
                try:
                    await self._sweep_idle()
                except Exception:
                    pass

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_loop())
        except RuntimeError:
            pass

    async def _ensure_pw(self):
        loop = asyncio.get_running_loop()
        if self._pw is not None and self._pw_loop is loop:
            return self._pw
        if self._pw is not None and self._pw_loop is not loop:
            await self._teardown_playwright_unlocked()
        apw = _ensure_playwright()
        self._pw_cm = apw()
        self._pw = await self._pw_cm.__aenter__()
        self._pw_loop = loop
        return self._pw

    async def _teardown_playwright_unlocked(self) -> None:
        """Playwright / Browser 与当前事件循环不匹配或连接失效时整池重建。"""
        for key in list(self._browser_pools.keys()):
            await self._close_browser_pool_unlocked(key)
        self._local_slots.clear()  # CDP 连接随 Playwright 实例失效，下次 ensure 时重建
        self._sessions.clear()
        if self._pw_cm is not None:
            try:
                await self._pw_cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._pw = None
        self._pw_cm = None
        self._pw_loop = None

    async def ensure_browser_warm(
        self,
        *,
        headless: Optional[bool] = None,
        owner_key: str = "anonymous",
    ) -> None:
        """预启动指定用户的共享 Chromium（供服务启动预热，默认 anonymous）。"""
        if cdp_connection_mode() == "local":
            # local 强制本机通道：浏览器生命周期归本机代理（D7），不做云端预热
            return
        async with self._lock:
            await self._ensure_browser(owner_key=owner_key, headless=headless)

    async def _ensure_browser(self, *, owner_key: str, headless: Optional[bool] = None):
        want = headless if headless is not None else cdp_headless()
        slot = self._browser_pools.get(owner_key)
        if slot is not None:
            connected = True
            try:
                connected = bool(slot.browser.is_connected())
            except Exception:
                connected = False
            if connected and slot.headless == want and slot.browser is not None:
                return slot.browser
            await self._close_browser_pool_unlocked(owner_key)
        pw = await self._ensure_pw()
        t0 = time.perf_counter()
        debug_port = _find_free_port()
        browser = await _launch_chromium(pw, headless=want, debug_port=debug_port)
        self._browser_pools[owner_key] = _BrowserPoolSlot(
            browser=browser, headless=want, debug_port=debug_port
        )
        if os.getenv("PERF_LOG") == "1":
            print(
                f"[CDP] chromium.launch {(time.perf_counter() - t0) * 1000:.0f}ms "
                f"headless={want} owner={owner_key}",
                flush=True,
            )
        return browser

    async def _resolve_connection_mode(self, *, owner_key: str, url: Optional[str]) -> str:
        """决策本次会话连接模式（``local``/``launch``）；本机不可用且禁止降级时抛 CdpError。

        - CDP_CONNECTION_MODE=launch：始终云端 launch（回归安全）。
        - =local：强制本机；通道可用性由 _ensure_local_browser 的 ensure（带等待）把关。
        - =auto：隧道在线 → local；离线时私网 URL 显式失败（D8，不降级）、公网/未定回退 launch。
        """
        mode = cdp_connection_mode()
        if mode == "launch":
            return "launch"
        user_id = owner_user_id(owner_key)
        if user_id is None:
            if mode == "local":
                raise CdpError(
                    LOCAL_CHANNEL_UNAVAILABLE,
                    f"本机通道需要登录用户归属（owner={owner_key}），无法定位本机代理隧道",
                )
            return "launch"
        if mode == "local":
            return "local"
        status = await tunnel_status_async(user_id)
        if status.online:
            return "local"
        if url and is_private_url(url):
            raise CdpError(
                LOCAL_CHANNEL_UNAVAILABLE,
                "目标为内网地址且本机代理通道离线：请先启动本机代理"
                "（可经 browser_local 卡片唤起），云端浏览器无法访问内网",
            )
        return "launch"

    async def _ensure_local_browser(
        self, owner_key: str, *, force_reconnect: bool = False
    ) -> LocalBrowserSlot:
        """建立/复用本机浏览器 CDP 连接（经隧道网关）；失败重试一次后显式报错。

        force_reconnect：隧道抖动后旧 ws 已失效时强制重建（不信任 is_connected 缓存）。
        """
        slot = self._local_slots.get(owner_key)
        if slot is not None and not force_reconnect:
            try:
                if bool(slot.browser.is_connected()):
                    return slot
            except Exception:
                pass
            self._local_slots.pop(owner_key, None)
        elif slot is not None:
            try:
                await slot.browser.close()
            except Exception:
                pass
            self._local_slots.pop(owner_key, None)
        last_ex: Optional[BaseException] = None
        for attempt in range(2):
            ws_url = await ensure_local_channel(owner_key)
            if not ws_url:
                raise CdpError(
                    LOCAL_CHANNEL_UNAVAILABLE,
                    "本机代理通道不可用：请启动本机代理后重试"
                    "（客户端唤起流程可自动拉起，见 browser_local 卡片）",
                )
            try:
                pw = await self._ensure_pw()
                t0 = time.perf_counter()
                browser = await pw.chromium.connect_over_cdp(ws_url)
                new_slot = LocalBrowserSlot(browser=browser, ws_url=ws_url)
                self._local_slots[owner_key] = new_slot
                print(
                    f"[CDP] mode=local owner={owner_key} 已连接本机浏览器 "
                    f"{(time.perf_counter() - t0) * 1000:.0f}ms",
                    flush=True,
                )
                return new_slot
            except Exception as ex:
                last_ex = ex
                if attempt == 0:
                    print(
                        f"[CDP] mode=local 连接本机浏览器失败，重试一次: {type(ex).__name__}: {ex}",
                        flush=True,
                    )
                    continue
        raise CdpError(LOCAL_CHANNEL_UNAVAILABLE, f"连接本机浏览器失败: {last_ex}")

    @staticmethod
    def _local_context(browser: Any):
        """D6：复用本机浏览器的默认 context（contexts[0]，保留登录态），不 new_context。"""
        try:
            contexts = list(browser.contexts)
        except Exception:
            contexts = []
        return contexts[0] if contexts else None

    @staticmethod
    async def _choose_local_page(context: Any, url: Optional[str]):
        """选择会话页：host 匹配的已有 tab 优先（延续登录态），否则新建；返回 (page, owns_page)。"""
        from urllib.parse import urlparse

        def _host(raw: str) -> str:
            try:
                return (urlparse(str(raw or "").strip()).hostname or "").lower()
            except Exception:
                return ""

        target_host = _host(url or "")
        if target_host:
            try:
                pages = list(context.pages)
            except Exception:
                pages = []
            for p in pages:
                try:
                    if _host(p.url) == target_host:
                        return p, False
                except Exception:
                    continue
        return await context.new_page(), True

    async def _recover_local_session(
        self, session: "BrowserSession", *, url: Optional[str] = None
    ) -> None:
        """local 会话因隧道抖动断线后就地重建连接/页面（session_id 不变，D6 语义保持）。

        url：重建后偏好复用的目标地址（host 匹配的已有 tab 优先）。
        """
        print(
            f"[CDP] mode=local 会话断线，重建本机连接 sid={session.session_id}",
            flush=True,
        )
        slot = await self._ensure_local_browser(session.owner_key, force_reconnect=True)
        context = self._local_context(slot.browser)
        if context is None:
            context = await slot.browser.new_context()
        if session.owns_page and session.page is not None:
            try:
                await session.page.close()
            except Exception:
                pass
        page, owns_page = await self._choose_local_page(context, url)
        session.browser = slot.browser
        session.context = context
        session.page = page
        session.owns_page = owns_page
        session._cdp = None
        session.last_snapshot = None
        if session.llm_capture is not None:
            session.llm_capture.attach(page)

    async def get_browser_ws_endpoint(self, *, owner_key: str = "anonymous") -> Optional[str]:
        """返回可被 Midscene/Gremlins 子进程复用的浏览器 CDP WebSocket URL。

        - local 模式：每次重新申领 route key（网关 ws，指向本机浏览器，登录态/内网可达）；
        - launch 模式：读共享浏览器池 ``--remote-debugging-port`` 的 /json/version
          （Playwright Browser 不暴露 ws）；失败返回 None（调用方回退自起浏览器）。
        """
        local_slot = self._local_slots.get(owner_key)
        if local_slot is not None:
            try:
                connected = bool(local_slot.browser.is_connected())
            except Exception:
                connected = False
            if connected:
                user_id = owner_user_id(owner_key)
                if user_id is not None:
                    lease = await asyncio.to_thread(issue_route, user_id)
                    if lease is not None:
                        print(f"[CDP] mode=local ws={lease.ws_url[:60]}...", flush=True)
                        return lease.ws_url
                return None
            self._local_slots.pop(owner_key, None)
        slot = self._browser_pools.get(owner_key)
        if slot is None or not slot.debug_port:
            return None
        try:
            connected = bool(slot.browser.is_connected())
        except Exception:
            connected = False
        if not connected:
            return None
        try:
            return await asyncio.to_thread(_fetch_ws_endpoint, int(slot.debug_port))
        except Exception:
            return None

    async def _new_browser_context(
        self,
        *,
        owner_key: str,
        headless: Optional[bool],
        ctx_args: Dict[str, Any],
    ):
        last_ex: Optional[BaseException] = None
        for attempt in range(2):
            try:
                browser = await self._ensure_browser(owner_key=owner_key, headless=headless)
                context = await browser.new_context(**ctx_args)
                return browser, context
            except Exception as ex:
                last_ex = ex
                if attempt == 0 and _is_stale_browser_error(ex):
                    if os.getenv("PERF_LOG") == "1":
                        print(
                            f"[CDP] new_context stale owner={owner_key} retry: {ex}",
                            flush=True,
                        )
                    await self._close_browser_pool_unlocked(owner_key)
                    loop = asyncio.get_running_loop()
                    if self._pw_loop is not None and self._pw_loop is not loop:
                        await self._teardown_playwright_unlocked()
                    continue
                raise
        assert last_ex is not None
        raise last_ex

    async def _close_browser_pool_unlocked(self, owner_key: str) -> None:
        slot = self._browser_pools.pop(owner_key, None)
        if slot is None:
            return
        if slot.idle_task is not None:
            slot.idle_task.cancel()
        try:
            await slot.browser.close()
        except Exception:
            pass

    def _cancel_browser_idle_close(self, owner_key: str) -> None:
        slot = self._browser_pools.get(owner_key)
        if slot is None or slot.idle_task is None:
            return
        slot.idle_task.cancel()
        slot.idle_task = None

    def _owner_has_sessions(self, owner_key: str) -> bool:
        return any(s.owner_key == owner_key for s in self._sessions.values())

    def _schedule_browser_idle_close(self, owner_key: str) -> None:
        idle_sec = cdp_browser_idle_sec()
        slot = self._browser_pools.get(owner_key)
        if idle_sec <= 0 or self._owner_has_sessions(owner_key) or slot is None:
            return
        self._cancel_browser_idle_close(owner_key)

        async def _wait_and_close() -> None:
            try:
                await asyncio.sleep(idle_sec)
                async with self._lock:
                    if not self._owner_has_sessions(owner_key):
                        await self._close_browser_pool_unlocked(owner_key)
            except asyncio.CancelledError:
                pass

        try:
            loop = asyncio.get_running_loop()
            slot.idle_task = loop.create_task(_wait_and_close())
        except RuntimeError:
            pass

    def _evict_sessions_for_owner_locked(self, owner_key: str) -> List[BrowserSession]:
        """调用方须已持有 self._lock。"""
        max_n = cdp_max_sessions()
        owned = sorted(
            [(sid, s) for sid, s in self._sessions.items() if s.owner_key == owner_key],
            key=lambda x: x[1].last_used_at,
        )
        if len(owned) < max_n:
            return []
        victims: List[BrowserSession] = []
        n_drop = len(owned) - max_n + 1
        for sid, _ in owned[:n_drop]:
            s = self._sessions.pop(sid, None)
            if s is not None:
                victims.append(s)
        return victims

    async def create(
        self,
        url: Optional[str] = None,
        *,
        headless: Optional[bool] = None,
        storage_state_path: Optional[str] = None,
        owner_key: Optional[str] = None,
        project_id: Optional[int] = None,
        cdp_run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        owner = owner_key or "anonymous"
        t0 = time.perf_counter()
        evicted: List[BrowserSession] = []
        async with self._lock:
            self._start_sweeper()
            self._cancel_browser_idle_close(owner)
            evicted = self._evict_sessions_for_owner_locked(owner)
            sid = f"sess_{uuid.uuid4().hex[:10]}"
            try:
                conn_mode = await self._resolve_connection_mode(owner_key=owner, url=url)
            except CdpError as e:
                return _cdp_error_with_browser_card(e, url=url, headless=headless) | {
                    "tool": "cdp",
                    "action": "create",
                    "owner_key": owner,
                }
            try:
                if conn_mode == "local":
                    if storage_state_path:
                        print(
                            "[CDP] mode=local 忽略 storage_state（登录态留存本机浏览器 profile）",
                            flush=True,
                        )
                    slot = await self._ensure_local_browser(owner)
                    context = self._local_context(slot.browser)
                    if context is None:
                        context = await slot.browser.new_context()
                    page, owns_page = await self._choose_local_page(context, url)
                    browser = slot.browser
                else:
                    ctx_args: Dict[str, Any] = {}
                    if storage_state_path:
                        ctx_args["storage_state"] = storage_state_path
                    browser, context = await self._new_browser_context(
                        owner_key=owner,
                        headless=headless,
                        ctx_args=ctx_args,
                    )
                    page = await context.new_page()
                    owns_page = False
            except CdpError as e:
                return _cdp_error_with_browser_card(e, url=url, headless=headless) | {
                    "tool": "cdp",
                    "action": "create",
                    "owner_key": owner,
                }
            except Exception as ex:
                return {
                    "success": False,
                    "error_code": "browser_context_failed",
                    "error": str(ex),
                    "message": str(ex),
                    "tool": "cdp",
                    "action": "create",
                    "owner_key": owner,
                }
            session = BrowserSession(
                session_id=sid,
                playwright=self._pw,
                browser=browser,
                context=context,
                page=page,
                owns_browser=False,
                owner_key=owner,
                local_mode=(conn_mode == "local"),
                owns_page=owns_page,
            )
            self._sessions[sid] = session
        for old in evicted:
            await old.close()
        try:
            await self.ensure_console_hook(sid, owner_key=owner)
        except Exception:
            pass
        try:
            await self.ensure_llm_capture(
                sid, owner_key=owner, project_id=project_id, cdp_run_id=cdp_run_id
            )
        except Exception:
            pass
        if url:
            nav = await self.navigate(sid, url, owner_key=owner)
            if not nav.get("success"):
                await self.close(sid)
                return nav
        out = {
            "success": True,
            "action": "create",
            "session_id": sid,
            "page": await session.page_info(),
            "storage_state_loaded": bool(storage_state_path) and conn_mode != "local",
            "connection_mode": conn_mode,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "owner_key": owner,
        }
        if os.getenv("PERF_LOG") == "1":
            print(
                f"[CDP] session.create {out['duration_ms']}ms sid={sid} "
                f"owner={owner} url={bool(url)}",
                flush=True,
            )
        return out

    async def navigate(
        self,
        session_id: str,
        url: str,
        *,
        wait_until: str = "domcontentloaded",
        timeout_ms: Optional[int] = None,
        owner_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        session = self._get(session_id, owner_key=owner_key)
        await session.touch()
        try:
            assert_url_allowed(url)
        except ValueError as e:
            return {"success": False, "error_code": "url_denied", "message": str(e)}
        timeout = timeout_ms or cdp_default_timeout_ms()
        t0 = time.perf_counter()
        try:
            await session.page.goto(url, wait_until=wait_until, timeout=timeout)
            session.last_snapshot = None
            return {
                "success": True,
                "tool": "cdp_navigate",
                "session_id": session_id,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "page": await session.page_info(),
            }
        except Exception as ex:
            if session.local_mode and _is_stale_browser_error(ex):
                # 隧道抖动/浏览器断开：就地重建一次后重试（设计第 10 节：断线自动恢复）
                try:
                    await self._recover_local_session(session, url=url)
                    await session.page.goto(url, wait_until=wait_until, timeout=timeout)
                    session.last_snapshot = None
                    return {
                        "success": True,
                        "tool": "cdp_navigate",
                        "session_id": session_id,
                        "duration_ms": int((time.perf_counter() - t0) * 1000),
                        "page": await session.page_info(),
                        "recovered": True,
                    }
                except Exception as ex2:
                    ex = ex2
            return CdpError(NAVIGATION_FAILED, str(ex)).to_dict() | {
                "tool": "cdp_navigate",
                "session_id": session_id,
            }

    async def snapshot(
        self,
        session_id: str,
        *,
        scope: str = "interactive",
        owner_key: Optional[str] = None,
        _retry: bool = True,
    ) -> Dict[str, Any]:
        session = self._get(session_id, owner_key=owner_key)
        await session.touch()
        t0 = time.perf_counter()
        try:
            client = await session.cdp_session()
            result = await client.send("Accessibility.getFullAXTree")
            nodes = result.get("nodes") or []
            builder = AxSnapshotBuilder(max_nodes=cdp_snapshot_max_nodes())
            snap = builder.build_from_cdp_nodes(
                nodes,
                url=session.page.url,
                title=await session.page.title(),
                scope=scope,
            )
            session.last_snapshot = snap
            session._snapshots[snap.snapshot_id] = snap
            out = snap.to_dict()
            out["success"] = True
            out["tool"] = "cdp_snapshot"
            out["session_id"] = session_id
            out["duration_ms"] = int((time.perf_counter() - t0) * 1000)
            return out
        except Exception as ex:
            if _retry and session.local_mode and _is_stale_browser_error(ex):
                # 隧道抖动/浏览器断开：重建并回到原地址后重试一次（防探测假完成）
                try:
                    recover_url = str(
                        getattr(session.last_snapshot, "url", "") or ""
                    ).strip() or None
                    await self._recover_local_session(session, url=recover_url)
                    if recover_url:
                        try:
                            await session.page.goto(
                                recover_url,
                                wait_until="domcontentloaded",
                                timeout=cdp_default_timeout_ms(),
                            )
                        except Exception:
                            pass
                    return await self.snapshot(
                        session_id, scope=scope, owner_key=owner_key, _retry=False
                    )
                except Exception:
                    pass
            # 回退 Playwright accessibility.snapshot
            try:
                tree = await session.page.accessibility.snapshot(interesting_only=(scope == "interactive"))
                builder = AxSnapshotBuilder(max_nodes=cdp_snapshot_max_nodes())
                snap = builder.build_light_from_playwright_tree(
                    tree,
                    url=session.page.url,
                    title=await session.page.title(),
                    max_nodes=cdp_snapshot_max_nodes(),
                )
                snap.scope = scope
                session.last_snapshot = snap
                session._snapshots[snap.snapshot_id] = snap
                out = snap.to_dict()
                out["success"] = True
                out["tool"] = "cdp_snapshot"
                out["session_id"] = session_id
                out["duration_ms"] = int((time.perf_counter() - t0) * 1000)
                out["fallback"] = "playwright_accessibility"
                return out
            except Exception as ex2:
                return {
                    "success": False,
                    "error_code": "snapshot_failed",
                    "message": f"{ex}; fallback: {ex2}",
                    "tool": "cdp_snapshot",
                }

    def actor(self, session_id: str, *, owner_key: Optional[str] = None) -> ElementActor:
        return ElementActor(self._get(session_id, owner_key=owner_key))

    async def list_tabs(
        self, session_id: str, *, owner_key: Optional[str] = None
    ) -> Dict[str, Any]:
        session = self._get(session_id, owner_key=owner_key)
        await session.touch()
        tabs = []
        for i, p in enumerate(session.list_pages()):
            try:
                tabs.append(
                    {
                        "index": i,
                        "tabId": f"t{i}",
                        "url": p.url,
                        "title": await p.title(),
                        "active": p is session.page,
                    }
                )
            except Exception as ex:
                tabs.append({"index": i, "tabId": f"t{i}", "error": str(ex)[:120]})
        return {
            "success": True,
            "tool": "cdp_tabs",
            "session_id": session_id,
            "tabs": tabs,
            "tabCount": len(tabs),
        }

    async def open_tab(
        self,
        session_id: str,
        url: Optional[str] = None,
        *,
        owner_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        session = self._get(session_id, owner_key=owner_key)
        await session.touch()
        page = await session.context.new_page()
        session.page = page
        session._cdp = None
        session.last_snapshot = None
        if session.llm_capture is not None:
            try:
                session.llm_capture.attach(page)
            except Exception:
                pass
        if url:
            try:
                assert_url_allowed(url)
                await page.goto(url, wait_until="domcontentloaded", timeout=cdp_default_timeout_ms())
            except Exception as ex:
                return {"success": False, "tool": "cdp_open", "error": str(ex), "session_id": session_id}
        return {
            "success": True,
            "tool": "cdp_open",
            "session_id": session_id,
            "page": await session.page_info(),
            "tabs": (await self.list_tabs(session_id, owner_key=owner_key)).get("tabs"),
        }

    async def focus_tab(
        self,
        session_id: str,
        *,
        index: Optional[int] = None,
        tab_id: Optional[str] = None,
        owner_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        session = self._get(session_id, owner_key=owner_key)
        idx = index
        if idx is None and tab_id:
            s = str(tab_id).strip().lower()
            if s.startswith("t") and s[1:].isdigit():
                idx = int(s[1:])
            elif s.isdigit():
                idx = int(s)
        if idx is None:
            return {"success": False, "error": "focus 需要 index 或 tabId(t0)"}
        try:
            await session.switch_page(int(idx))
        except CdpError as e:
            return e.to_dict() | {"tool": "cdp_focus"}
        return {
            "success": True,
            "tool": "cdp_focus",
            "session_id": session_id,
            "index": idx,
            "page": await session.page_info(),
        }

    async def close_tab(
        self,
        session_id: str,
        *,
        index: Optional[int] = None,
        owner_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        session = self._get(session_id, owner_key=owner_key)
        pages = session.list_pages()
        if len(pages) <= 1:
            return {"success": False, "error": "仅剩一个标签，请用 session close 关闭整会话"}
        idx = 0 if index is None else int(index)
        if idx < 0 or idx >= len(pages):
            return {"success": False, "error": f"tab index 越界: {idx}"}
        target = pages[idx]
        await target.close()
        remain = session.list_pages()
        session.page = remain[-1]
        session._cdp = None
        session.last_snapshot = None
        await session.touch()
        return {
            "success": True,
            "tool": "cdp_close_tab",
            "session_id": session_id,
            "closed_index": idx,
            "page": await session.page_info(),
            "tabCount": len(remain),
        }

    async def screenshot(
        self,
        session_id: str,
        *,
        full_page: bool = False,
        owner_key: Optional[str] = None,
        tag: str = "shot",
    ) -> Dict[str, Any]:
        session = self._get(session_id, owner_key=owner_key)
        await session.touch()
        from .screenshot import upload_png_bytes
        from .vision_understand import (
            agent_loop_hint,
            cdp_screenshot_vision_enabled,
            describe_png_for_agent,
        )

        try:
            png = await session.page.screenshot(type="png", full_page=bool(full_page))
            url = upload_png_bytes(
                png,
                folder="cdp",
                filename=(
                    f"cdp_{'full_' if full_page else ''}"
                    f"{session_id[:12]}_{tag}_{int(time.time())}.png"
                ),
            )
            page_info = await session.page_info()
            out: Dict[str, Any] = {
                "success": True,
                "tool": "cdp_screenshot",
                "session_id": session_id,
                "screenshot_url": url,
                "full_page": full_page,
                "page": page_info,
            }
            # OpenClaw：截图后视觉理解，以文本回传 Agent（主模型可据此闭环决策）
            if cdp_screenshot_vision_enabled() and png:
                ctx = ""
                try:
                    ctx = f"url={page_info.get('url') or ''} title={page_info.get('title') or ''}"
                except Exception:
                    ctx = "browser screenshot"
                desc = await describe_png_for_agent(png, context=ctx)
                if desc:
                    out["vision_description"] = desc
                    out["screenshot_vision"] = True
                    out["agent_hint"] = agent_loop_hint(
                        has_vision=True, kind="screenshot"
                    )
                else:
                    out["screenshot_vision"] = False
                    out["agent_hint"] = agent_loop_hint(
                        has_vision=False, kind="screenshot"
                    )
            return out
        except Exception as ex:
            return {"success": False, "tool": "cdp_screenshot", "error": str(ex)}

    async def pdf(
        self, session_id: str, *, owner_key: Optional[str] = None
    ) -> Dict[str, Any]:
        session = self._get(session_id, owner_key=owner_key)
        await session.touch()
        try:
            data = await session.page.pdf(format="A4", print_background=True)
            from .screenshot import upload_png_bytes

            # 复用上传：以 .pdf 扩展名存 MinIO（同一上传函数按 filename）
            path_url = None
            try:
                from io import BytesIO

                buf = BytesIO(data)
                buf.filename = f"cdp_{session_id[:12]}_{int(time.time())}.pdf"  # type: ignore
                try:
                    from app_services.minio_storage import upload_file_to_minio
                except ImportError:
                    from app import upload_file_to_minio  # type: ignore
                result = upload_file_to_minio(buf, folder_path="cdp")
                if isinstance(result, dict) and result.get("success"):
                    path_url = result.get("url")
            except Exception:
                path_url = None
            return {
                "success": True,
                "tool": "cdp_pdf",
                "session_id": session_id,
                "pdf_url": path_url,
                "bytes": len(data),
                "page": await session.page_info(),
            }
        except Exception as ex:
            return {"success": False, "tool": "cdp_pdf", "error": str(ex)}

    async def extract_readable(
        self,
        session_id: str,
        *,
        query: Optional[str] = None,
        selector: Optional[str] = None,
        max_chars: int = 12000,
        owner_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """对齐 OpenClaw extract：抽取可读文本；有 query 时返回文本供上层 LLM 回答。"""
        session = self._get(session_id, owner_key=owner_key)
        await session.touch()
        try:
            if selector:
                loc = session.page.locator(selector)
                text = await loc.inner_text(timeout=cdp_default_timeout_ms())
            else:
                text = await session.page.inner_text("body", timeout=cdp_default_timeout_ms())
            text = (text or "").strip()
            if max_chars > 0 and len(text) > max_chars:
                text = text[:max_chars] + "…(truncated)"
            out: Dict[str, Any] = {
                "success": True,
                "tool": "cdp_extract",
                "session_id": session_id,
                "text": text,
                "chars": len(text),
                "page": await session.page_info(),
            }
            if query:
                out["query"] = query
                out["hint"] = "请用 text 字段内容回答 query；本层不强制二次调模型"
            return out
        except Exception as ex:
            return {"success": False, "tool": "cdp_extract", "error": str(ex)}

    async def console_messages(
        self,
        session_id: str,
        *,
        limit: int = 50,
        owner_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        session = self._get(session_id, owner_key=owner_key)
        await session.touch()
        # Playwright 无内置历史缓冲；用 evaluate 抓 performance/console 代理不可靠。
        # 返回最近通过 page.on 未接线时的空列表 + 提示；同时抓 document 错误。
        try:
            errs = await session.page.evaluate(
                """() => (window.__badcaseConsole || []).slice(-80)"""
            )
            if not isinstance(errs, list):
                errs = []
            return {
                "success": True,
                "tool": "cdp_console",
                "session_id": session_id,
                "messages": errs[-max(1, int(limit)) :],
                "note": "若为空，会话创建 后会注入 console hook（见 ensure_console_hook）",
                "page": await session.page_info(),
            }
        except Exception as ex:
            return {"success": False, "tool": "cdp_console", "error": str(ex)}

    async def ensure_console_hook(
        self, session_id: str, *, owner_key: Optional[str] = None
    ) -> None:
        session = self._get(session_id, owner_key=owner_key)
        try:
            await session.page.add_init_script(
                """
                (() => {
                  if (window.__badcaseConsoleHooked) return;
                  window.__badcaseConsoleHooked = true;
                  window.__badcaseConsole = [];
                  const push = (level, args) => {
                    try {
                      window.__badcaseConsole.push({
                        level,
                        text: Array.from(args).map(a => {
                          try { return typeof a === 'string' ? a : JSON.stringify(a); }
                          catch { return String(a); }
                        }).join(' ').slice(0, 500),
                        t: Date.now(),
                      });
                      if (window.__badcaseConsole.length > 200) window.__badcaseConsole.shift();
                    } catch (e) {}
                  };
                  ['log','info','warn','error'].forEach(level => {
                    const orig = console[level].bind(console);
                    console[level] = (...args) => { push(level, args); return orig(...args); };
                  });
                })();
                """
            )
        except Exception:
            pass

    async def ensure_llm_capture(
        self,
        session_id: str,
        *,
        project_id: Optional[int] = None,
        cdp_run_id: Optional[str] = None,
        declared: Optional[Dict[str, Any]] = None,
        owner_key: Optional[str] = None,
    ) -> Any:
        """挂 LLM 报文采集：采集被测系统的对话原始报文（模型/参数/输出/工具调用/时延）。

        declared 为项目里填写的模型与参数（申报值），用于「申报 vs 实际」对比检测模型降级。
        """
        session = self._get(session_id, owner_key=owner_key)
        from .llm_capture import ensure_capture

        session.llm_capture = ensure_capture(
            session.page,
            session_id,
            project_id=project_id,
            cdp_run_id=cdp_run_id,
            declared=declared,
        )
        return session.llm_capture

    async def close(self, session_id: str, *, owner_key: Optional[str] = None) -> Dict[str, Any]:
        owner: Optional[str] = None
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is not None:
                if owner_key and session.owner_key != owner_key:
                    self._sessions[session_id] = session
                    return {
                        "success": False,
                        "error_code": SESSION_NOT_FOUND,
                        "message": session_id,
                    }
                owner = session.owner_key
        if not session:
            return {"success": False, "error_code": SESSION_NOT_FOUND, "message": session_id}
        await session.close()
        try:
            from .llm_capture import drop_capture

            drop_capture(session_id)
        except Exception:
            pass
        if owner:
            async with self._lock:
                self._schedule_browser_idle_close(owner)
        return {"success": True, "action": "close", "session_id": session_id}

    def get_session(
        self, session_id: str, *, owner_key: Optional[str] = None
    ) -> Optional[BrowserSession]:
        s = self._sessions.get(session_id)
        if s is None:
            return None
        if owner_key and s.owner_key != owner_key:
            return None
        return s

    def latest_session_id(self, *, owner_key: Optional[str] = None) -> Optional[str]:
        items = [
            (sid, s)
            for sid, s in self._sessions.items()
            if owner_key is None or s.owner_key == owner_key
        ]
        if not items:
            return None
        sid, _ = max(items, key=lambda x: x[1].last_used_at)
        return sid

    def list_sessions(self, *, owner_key: Optional[str] = None) -> Dict[str, Any]:
        rows = [
            (sid, s)
            for sid, s in self._sessions.items()
            if owner_key is None or s.owner_key == owner_key
        ]
        return {
            "success": True,
            "sessions": [
                {
                    "session_id": sid,
                    "url": s.page.url if s.page else "",
                    "last_used_at": s.last_used_at,
                    "owner_key": s.owner_key,
                }
                for sid, s in rows
            ],
            "count": len(rows),
        }

    def assert_owned(self, session_id: str, *, owner_key: str) -> BrowserSession:
        """显式校验调用方归属，校验前不得更新采集上下文。"""
        return self._get(session_id, owner_key=owner_key or "anonymous")

    def _get(self, session_id: str, *, owner_key: Optional[str] = None) -> BrowserSession:
        s = self._sessions.get(session_id)
        if not s:
            raise CdpError(SESSION_NOT_FOUND, f"会话不存在: {session_id}")
        if owner_key and s.owner_key != owner_key:
            raise CdpError(SESSION_NOT_FOUND, f"会话不存在: {session_id}")
        return s

    async def _sweep_idle(self) -> None:
        ttl = cdp_session_ttl_sec()
        now = time.time()
        stale = [sid for sid, s in self._sessions.items() if now - s.last_used_at > ttl]
        for sid in stale:
            await self.close(sid)

    def mark_awaiting_verification(
        self,
        session_id: str,
        *,
        snapshot_id: Optional[str] = None,
        project_id: Optional[int] = None,
    ) -> None:
        s = self._sessions.get(session_id)
        if not s:
            return
        s.awaiting_verification = True
        s.awaiting_verification_snapshot_id = snapshot_id
        s.awaiting_verification_project_id = project_id

    def clear_awaiting_verification(self, session_id: str) -> None:
        s = self._sessions.get(session_id)
        if not s:
            return
        s.awaiting_verification = False
        s.awaiting_verification_snapshot_id = None
        s.awaiting_verification_project_id = None

    def find_session_awaiting_verification(
        self, project_id: Optional[int] = None
    ) -> Optional[str]:
        candidates = [
            (sid, s)
            for sid, s in self._sessions.items()
            if s.awaiting_verification
        ]
        if project_id is not None:
            pid = int(project_id)
            scoped = [
                (sid, s)
                for sid, s in candidates
                if s.awaiting_verification_project_id in (None, pid)
            ]
            if scoped:
                candidates = scoped
        if not candidates:
            return None
        sid, _ = max(candidates, key=lambda x: x[1].last_used_at)
        return sid

    async def save_storage_state(
        self, session_id: str, *, url: Optional[str] = None
    ) -> Dict[str, Any]:
        """登录成功后导出 cookies/storage，供后续 session create 复用。

        url：可选，按指定地址的域名保存（巡检结束页可能在子页/第三方页时，用目标站更稳）；默认取当前页面地址。
        """
        import json
        from urllib.parse import urlparse

        from agents.tools.login_state_tool import get_state_path

        session = self._get(session_id)
        await session.touch()
        if getattr(session, "local_mode", False):
            # local 模式登录态天然留存本机浏览器 profile：不导出（§8.4）
            return {
                "success": True,
                "skipped": True,
                "reason": "local 模式登录态留存本机浏览器，无需导出 storage_state",
            }
        try:
            target = str(url or "").strip() or session.page.url
            domain = urlparse(target).netloc
            if not domain:
                return {"success": False, "error": "无法解析页面域名"}
            state_path = get_state_path(domain)
            storage_state = await session.context.storage_state()
            os.makedirs(os.path.dirname(state_path), exist_ok=True)
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(storage_state, f, ensure_ascii=False, indent=2)
            return {
                "success": True,
                "domain": domain,
                "state_path": state_path,
                "cookies_count": len(storage_state.get("cookies") or []),
            }
        except Exception as ex:
            return {"success": False, "error": str(ex)}
