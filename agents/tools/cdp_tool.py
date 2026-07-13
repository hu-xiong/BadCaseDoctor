# -*- coding: utf-8 -*-
"""
CDP 浏览器工具（单工具多 action，对齐需求文档 cdp_* 能力）。

action: session | navigate | snapshot | click | fill | wait | get_text | login | assert | explore | close | list_sessions
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from agents.tool_registry import BaseTool
from agents.cdp.owner import resolve_cdp_owner_key
from agents.cdp.session_manager import CdpSessionManager
from agents.tools.login_state_tool import get_storage_state_for_url


class CdpTool(BaseTool):
    def __init__(self):
        super().__init__(
            name="cdp",
            description=(
                "Chrome DevTools Protocol 浏览器自动化（元素 ref 精准操控，非截图识图）。"
                "action=session(create|close|list)、navigate、snapshot、click、fill、wait、get_text、login、assert、explore。"
                "遇登录页优先 action=login（自动读项目 login_configs / 本地凭证；无凭证则暂停等用户填写）。"
                "探测性测试：explore phase=inventory 先列元素，phase=dfs|full 深度优先点击；发现明显问题可自动 create Bug 预览。"
                "流程：session create+url → login 或 snapshot 得 @e1… → click/fill/assert；或 explore phase=full。"
                "参数：session_id、url、ref、selector、text、phase、max_depth、max_clicks、plan_id、username、password、verification_code、timeout_ms。"
            ),
        )
        self._mgr = CdpSessionManager.get()

    @staticmethod
    def _owner_key(kwargs: Dict[str, Any]) -> str:
        return resolve_cdp_owner_key(**kwargs)

    async def execute(self, action: str = None, **kwargs) -> Dict[str, Any]:
        act = (action or kwargs.get("tool_action") or "").strip().lower()
        if not act:
            return {"success": False, "error": "缺少 action 参数"}

        from agents.cdp.params import inject_cdp_tool_params

        inject_cdp_tool_params(
            kwargs,
            user_input=kwargs.get("natural_query") or kwargs.get("user_query"),
            result_context=kwargs.get("result_context"),
            project_id=kwargs.get("project_id"),
        )

        if act in ("session", "cdp_session"):
            return await self._session(**kwargs)
        if act in ("navigate", "cdp_navigate"):
            return await self._navigate(**kwargs)
        if act in ("snapshot", "cdp_snapshot"):
            return await self._snapshot(**kwargs)
        if act in ("click", "cdp_click"):
            return await self._click(**kwargs)
        if act in ("fill", "cdp_fill"):
            return await self._fill(**kwargs)
        if act in ("wait", "cdp_wait"):
            return await self._wait(**kwargs)
        if act in ("get_text", "cdp_get_text"):
            return await self._get_text(**kwargs)
        if act in ("login", "cdp_login"):
            return await self._login(**kwargs)
        if act in ("assert", "cdp_assert"):
            return await self._assert(**kwargs)
        if act in ("explore", "cdp_explore", "probe"):
            return await self._explore(**kwargs)
        return {"success": False, "error": f"未知 action: {act}"}

    async def _session(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sub = (kwargs.get("sub_action") or kwargs.get("session_action") or "create").strip().lower()
        if sub in ("list", "list_sessions"):
            return self._mgr.list_sessions(owner_key=owner)
        if sub in ("close",):
            sid = kwargs.get("session_id")
            if not sid:
                return {"success": False, "error": "close 需要 session_id"}
            return await self._mgr.close(sid, owner_key=owner)
        url = kwargs.get("url")
        project_id = kwargs.get("project_id")
        storage = kwargs.get("storage_state_path")
        if url and not storage:
            storage = get_storage_state_for_url(url)
        creds_hint = None
        if url and project_id:
            from agents.cdp.credentials import resolve_login_credentials

            creds_hint = resolve_login_credentials(
                url=url,
                project_id=int(project_id) if project_id else None,
                username=kwargs.get("username"),
                password=kwargs.get("password"),
            )
        headless = kwargs.get("headless")
        if headless is not None:
            headless = str(headless).lower() in ("1", "true", "yes")
        out = await self._mgr.create(
            url=url,
            headless=headless,
            storage_state_path=storage,
            owner_key=owner,
        )
        if storage:
            out["storage_state_loaded"] = True
        if creds_hint and creds_hint.get("username"):
            out["login_credentials_available"] = True
            out["login_username"] = creds_hint["username"]
        elif url and is_login_url_hint(url):
            out["login_credentials_available"] = False
            out["hint"] = "无可用登录凭证，请使用 action=login 或在对话中提供用户名密码"
        return out

    async def _navigate(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id")
        url = kwargs.get("url")
        if not sid or not url:
            return {"success": False, "error": "navigate 需要 session_id 与 url"}
        return await self._mgr.navigate(
            sid,
            url,
            wait_until=kwargs.get("wait_until") or "domcontentloaded",
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
            owner_key=owner,
        )

    async def _snapshot(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "snapshot 需要 session_id（或先 session create）"}
        await self._ensure_on_target_url(sid, kwargs, owner_key=owner)
        out = await self._mgr.snapshot(sid, scope=kwargs.get("scope") or "interactive", owner_key=owner)
        from agents.cdp.login_flow import enrich_snapshot_with_login_hints

        return enrich_snapshot_with_login_hints(out)

    async def _click(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "click 需要 session_id"}
        return await self._mgr.actor(sid, owner_key=owner).click(
            ref=kwargs.get("ref"),
            snapshot_id=kwargs.get("snapshot_id"),
            selector=kwargs.get("selector"),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )

    async def _fill(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        text = kwargs.get("text")
        if not sid or text is None:
            return {"success": False, "error": "fill 需要 session_id 与 text"}
        return await self._mgr.actor(sid, owner_key=owner).fill(
            text=str(text),
            ref=kwargs.get("ref"),
            snapshot_id=kwargs.get("snapshot_id"),
            selector=kwargs.get("selector"),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )

    async def _wait(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "wait 需要 session_id"}
        return await self._mgr.actor(sid, owner_key=owner).wait_for(
            ref=kwargs.get("ref"),
            text=kwargs.get("text"),
            url_matches=kwargs.get("url_matches"),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )

    async def _get_text(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "get_text 需要 session_id"}
        return await self._mgr.actor(sid, owner_key=owner).get_text(
            ref=kwargs.get("ref"),
            snapshot_id=kwargs.get("snapshot_id"),
            selector=kwargs.get("selector"),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )

    async def _login(self, **kwargs) -> Dict[str, Any]:
        from agents.cdp.credentials import (
            resolve_login_credentials,
            save_credentials_file,
        )
        from agents.cdp.login_flow import (
            analyze_login_page,
            await_credentials_message,
            await_login_failed_message,
            await_verification_message,
            enrich_snapshot_with_login_hints,
            is_login_url,
            needs_user_verification_code,
        )

        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "login 需要 session_id（请先 session create）"}
        session = self._mgr.get_session(sid, owner_key=owner)
        if not session:
            return {"success": False, "error": f"会话不存在: {sid}"}

        locale = kwargs.get("ui_locale")
        project_id = kwargs.get("project_id")
        verification_code = kwargs.get("verification_code")
        creds_from_user = bool(kwargs.get("username") and kwargs.get("password"))

        snap_result = await self._mgr.snapshot(sid, scope="interactive", owner_key=owner)
        snap_result = enrich_snapshot_with_login_hints(snap_result)
        if not snap_result.get("success"):
            return snap_result

        nodes = snap_result.get("nodes") or []
        snapshot_id = snap_result.get("snapshot_id")
        page_info = snap_result.get("page") or await session.page_info()
        url = str(page_info.get("url") or snap_result.get("url") or "")
        analysis = analyze_login_page(nodes, url)

        if not analysis.is_login_page and not is_login_url(url):
            return {
                "success": True,
                "action": "login",
                "tool": "cdp_login",
                "session_id": sid,
                "login_skipped": True,
                "message": "非登录页，已跳过自动登录",
                "page": page_info,
            }

        creds = resolve_login_credentials(
            url=url,
            project_id=int(project_id) if project_id else None,
            username=kwargs.get("username"),
            password=kwargs.get("password"),
        )
        username = creds.get("username")
        password = creds.get("password")

        password_only_flow = (
            analysis.login_type == "verification_code"
            and analysis.code_ref
            and not analysis.password_ref
        )
        if (not username or not password) and not password_only_flow:
            return {
                "success": True,
                "action": "login",
                "tool": "cdp_login",
                "session_id": sid,
                "snapshot_id": snapshot_id,
                "login_type": analysis.login_type,
                "await_user_credentials": True,
                "message": await_credentials_message(locale=locale),
                "url": url,
                "page": page_info,
            }

        if creds_from_user and username and password:
            save_credentials_file(username, password)

        actor = self._mgr.actor(sid, owner_key=owner)
        steps: list = []

        async def _fill_ref(ref: Optional[str], value: str, label: str) -> Optional[Dict[str, Any]]:
            nonlocal snapshot_id, nodes, analysis
            if not ref or not value:
                return None
            res = await actor.fill(text=value, ref=ref, snapshot_id=snapshot_id)
            steps.append({"step": label, "ref": ref, "success": res.get("success")})
            if res.get("success"):
                return res
            if res.get("error_code") == "stale_ref" or res.get("suggest_tool") == "cdp_snapshot":
                snap2 = await self._mgr.snapshot(sid, scope="interactive", owner_key=owner)
                snap2 = enrich_snapshot_with_login_hints(snap2)
                if snap2.get("success"):
                    snapshot_id = snap2.get("snapshot_id")
                    nodes = snap2.get("nodes") or []
                    analysis = analyze_login_page(nodes, url)
                    ref_map = {
                        "username": analysis.username_ref,
                        "password": analysis.password_ref,
                        "code": analysis.code_ref,
                    }.get(label)
                    if ref_map:
                        res2 = await actor.fill(text=value, ref=ref_map, snapshot_id=snapshot_id)
                        steps.append({"step": f"{label}_retry", "ref": ref_map, "success": res2.get("success")})
                        return res2
            return res

        if username and analysis.username_ref:
            fill_u = await _fill_ref(analysis.username_ref, username, "username")
            if fill_u and not fill_u.get("success"):
                return {
                    "success": False,
                    "action": "login",
                    "tool": "cdp_login",
                    "session_id": sid,
                    "message": "填写用户名失败",
                    "steps": steps,
                    "page": page_info,
                }

        if password and analysis.password_ref:
            fill_p = await _fill_ref(analysis.password_ref, password, "password")
            if fill_p and not fill_p.get("success"):
                return {
                    "success": False,
                    "action": "login",
                    "tool": "cdp_login",
                    "session_id": sid,
                    "message": "填写密码失败",
                    "steps": steps,
                    "page": page_info,
                }

        if verification_code and analysis.code_ref:
            fill_c = await _fill_ref(analysis.code_ref, str(verification_code), "code")
            if fill_c and not fill_c.get("success"):
                return {
                    "success": False,
                    "action": "login",
                    "tool": "cdp_login",
                    "session_id": sid,
                    "message": "填写验证码失败",
                    "steps": steps,
                    "page": page_info,
                }
        elif needs_user_verification_code(analysis) and not verification_code:
            if analysis.send_code_ref:
                send_res = await actor.click(
                    ref=analysis.send_code_ref, snapshot_id=snapshot_id
                )
                steps.append(
                    {"step": "send_code", "ref": analysis.send_code_ref, "success": send_res.get("success")}
                )
            return {
                "success": True,
                "action": "login",
                "tool": "cdp_login",
                "session_id": sid,
                "snapshot_id": snapshot_id,
                "login_type": analysis.login_type,
                "await_verification_code": True,
                "message": await_verification_message(analysis, locale=locale),
                "url": url,
                "page": page_info,
                "steps": steps,
            }

        submit_ref = analysis.submit_ref
        if not submit_ref:
            return {
                "success": False,
                "action": "login",
                "tool": "cdp_login",
                "session_id": sid,
                "message": "未找到登录按钮，请 snapshot 后手动指定 ref",
                "page": page_info,
            }

        click_res = await actor.click(ref=submit_ref, snapshot_id=snapshot_id)
        steps.append({"step": "submit", "ref": submit_ref, "success": click_res.get("success")})
        if not click_res.get("success"):
            return {
                "success": False,
                "action": "login",
                "tool": "cdp_login",
                "session_id": sid,
                "message": "点击登录按钮失败",
                "steps": steps,
                "page": page_info,
            }

        for _ in range(32):
            page_info = await session.page_info()
            if not is_login_url(str(page_info.get("url") or "")):
                break
            await asyncio.sleep(0.25)

        from agents.cdp.page_ready import wait_for_post_login_landing

        landing = await wait_for_post_login_landing(session.page, timeout_ms=15000)
        page_info = await session.page_info()
        still_login = is_login_url(str(page_info.get("url") or ""))
        if still_login:
            snap_after = await self._mgr.snapshot(sid, scope="interactive", owner_key=owner)
            snap_after = enrich_snapshot_with_login_hints(snap_after)
            analysis2 = analyze_login_page(snap_after.get("nodes") or [], page_info.get("url", ""))
            if needs_user_verification_code(analysis2) and not verification_code:
                return {
                    "success": True,
                    "action": "login",
                    "tool": "cdp_login",
                    "session_id": sid,
                    "snapshot_id": snap_after.get("snapshot_id"),
                    "login_type": analysis2.login_type,
                    "await_verification_code": True,
                    "message": await_verification_message(analysis2, locale=locale),
                    "url": page_info.get("url"),
                    "page": page_info,
                    "steps": steps,
                }
            return {
                "success": True,
                "action": "login",
                "tool": "cdp_login",
                "session_id": sid,
                "login_failed": True,
                "await_user_credentials": True,
                "message": await_login_failed_message(locale=locale),
                "url": page_info.get("url"),
                "page": page_info,
                "steps": steps,
            }

        storage_saved = await self._mgr.save_storage_state(sid)
        self._mgr.clear_awaiting_verification(sid)
        return {
            "success": True,
            "action": "login",
            "tool": "cdp_login",
            "session_id": sid,
            "login_success": True,
            "message": "登录成功，已进入项目详情" if landing.get("on_project_detail") else "登录成功",
            "on_project_detail": landing.get("on_project_detail"),
            "project_id": landing.get("project_id"),
            "landing": landing,
            "storage_state_saved": storage_saved.get("success"),
            "storage_state_path": storage_saved.get("state_path"),
            "page": page_info,
            "steps": steps,
        }

    async def _assert(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "assert 需要 session_id"}
        out = await self._mgr.actor(sid, owner_key=owner).assert_condition(
            ref=kwargs.get("ref"),
            selector=kwargs.get("selector"),
            text_contains=kwargs.get("text_contains") or kwargs.get("text"),
            url_matches=kwargs.get("url_matches"),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )
        out["action"] = "assert"
        return out

    async def _explore(self, **kwargs) -> Dict[str, Any]:
        from agents.cdp.explore import run_exploration

        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "explore 需要 session_id（请先 session create）"}
        nav = await self._ensure_on_target_url(sid, kwargs, owner_key=owner)
        if isinstance(nav, dict) and not nav.get("success"):
            return nav
        phase = kwargs.get("phase") or kwargs.get("sub_phase") or "full"
        user_query = kwargs.get("natural_query") or kwargs.get("user_query")
        return await run_exploration(
            self._mgr,
            sid,
            phase=str(phase),
            max_depth=_int_or_none(kwargs.get("max_depth")),
            max_clicks=_int_or_none(kwargs.get("max_clicks")),
            owner_key=owner,
            user_query=str(user_query) if user_query else None,
        )

    async def _ensure_on_target_url(
        self,
        session_id: str,
        kwargs: Dict[str, Any],
        *,
        owner_key: str,
    ) -> Optional[Dict[str, Any]]:
        from agents.cdp.params import ensure_session_on_target_url, resolve_cdp_target_url

        url = resolve_cdp_target_url(
            params=kwargs,
            user_input=kwargs.get("natural_query") or kwargs.get("user_query"),
            result_context=kwargs.get("result_context"),
        )
        return await ensure_session_on_target_url(
            self._mgr,
            session_id,
            url=url,
            owner_key=owner_key,
        )


def is_login_url_hint(url: str) -> bool:
    from agents.cdp.login_flow import is_login_url

    return is_login_url(url)


def _int_or_none(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
