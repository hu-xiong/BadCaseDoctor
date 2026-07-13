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

from .errors import CdpError, NAVIGATION_FAILED, PLAYWRIGHT_UNAVAILABLE, SESSION_NOT_FOUND
from .settings import (
    assert_url_allowed,
    cdp_browser_idle_sec,
    cdp_default_timeout_ms,
    cdp_headless,
    cdp_max_sessions,
    cdp_session_ttl_sec,
    cdp_snapshot_max_nodes,
)
from .snapshot import AxSnapshotBuilder, PageSnapshot
from .element_actor import ElementActor

_playwright = None
_async_playwright = None


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

    async def close(self) -> None:
        try:
            if self._cdp:
                await self._cdp.detach()
        except Exception:
            pass
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
    idle_task: Optional[asyncio.Task] = None


class CdpSessionManager:
    _instance: Optional["CdpSessionManager"] = None

    def __init__(self):
        self._sessions: Dict[str, BrowserSession] = {}
        self._pw = None
        self._pw_cm = None
        self._pw_loop: Optional[asyncio.AbstractEventLoop] = None
        self._browser_pools: Dict[str, _BrowserPoolSlot] = {}
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
        browser = await pw.chromium.launch(
            headless=want,
            args=_CHROMIUM_LAUNCH_ARGS,
        )
        self._browser_pools[owner_key] = _BrowserPoolSlot(browser=browser, headless=want)
        if os.getenv("PERF_LOG") == "1":
            print(
                f"[CDP] chromium.launch {(time.perf_counter() - t0) * 1000:.0f}ms "
                f"headless={want} owner={owner_key}",
                flush=True,
            )
        return browser

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
    ) -> Dict[str, Any]:
        owner = owner_key or "anonymous"
        t0 = time.perf_counter()
        evicted: List[BrowserSession] = []
        async with self._lock:
            self._start_sweeper()
            self._cancel_browser_idle_close(owner)
            evicted = self._evict_sessions_for_owner_locked(owner)
            sid = f"sess_{uuid.uuid4().hex[:10]}"
            ctx_args: Dict[str, Any] = {}
            if storage_state_path:
                ctx_args["storage_state"] = storage_state_path
            try:
                browser, context = await self._new_browser_context(
                    owner_key=owner,
                    headless=headless,
                    ctx_args=ctx_args,
                )
                page = await context.new_page()
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
            )
            self._sessions[sid] = session
        for old in evicted:
            await old.close()
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
            "storage_state_loaded": bool(storage_state_path),
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

    async def save_storage_state(self, session_id: str) -> Dict[str, Any]:
        """登录成功后导出 cookies/storage，供后续 session create 复用。"""
        import json
        from urllib.parse import urlparse

        from agents.tools.login_state_tool import get_state_path

        session = self._get(session_id)
        await session.touch()
        try:
            url = session.page.url
            domain = urlparse(url).netloc
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
