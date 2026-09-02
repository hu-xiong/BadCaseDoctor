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
                "浏览器自动化（Playwright + CDP；explore 默认 Midscene 真人式巡检，可回退 legacy DFS）。"
                "action="
                "session|tabs|open|focus|close_tab|navigate|snapshot|"
                "click|click_coords|type|press|hover|scroll|drag|select|fill|"
                "wait|get_text|screenshot|pdf|evaluate|extract|resize|console|"
                "login|assert|explore|batch|run_step|run_testcase。"
                "闭环："
                "① session create+url → 测站/探测会自动 explore（Midscene）；"
                "② 精细操作仍用 snapshot→@eN→click/fill；UI 变化后重新 snapshot；"
                "③ 登录页用 login；验证码等用户。"
                "用例：run_step/run_testcase；验证用 assert/extract/screenshot。"
                "explore：phase=full 走 Midscene；phase=dfs|inventory|legacy 走旧探测。"
                "参数：session_id、url、ref、selector、text、key、values、x、y、fn、query、"
                "start_ref、end_ref、index/tabId、actions(batch)、timeout_ms、"
                "step、expected、steps、testcase_id、step_index。"
            ),
        )
        self._mgr = CdpSessionManager.get()

    @staticmethod
    def _owner_key(kwargs: Dict[str, Any]) -> str:
        return resolve_cdp_owner_key(**kwargs)

    async def execute(self, action: str = None, **kwargs) -> Dict[str, Any]:
        act = (action or kwargs.get("tool_action") or kwargs.get("kind") or "").strip().lower()
        if not act:
            return {"success": False, "error": "缺少 action 参数"}

        from agents.cdp.params import inject_cdp_tool_params

        inject_cdp_tool_params(
            kwargs,
            user_input=kwargs.get("natural_query") or kwargs.get("user_query"),
            result_context=kwargs.get("result_context"),
            project_id=kwargs.get("project_id"),
        )

        # OpenClaw 兼容别名
        alias = {
            "start": "session",
            "stop": "session",
            "scrollintoview": "scroll",
            "clickcoords": "click_coords",
            "closetab": "close_tab",
            "print": "pdf",
            "act": "batch",
        }
        act = alias.get(act, act)

        if act in ("session", "cdp_session"):
            return await self._session(**kwargs)
        if act in ("tabs", "list_tabs"):
            return await self._tabs(**kwargs)
        if act in ("open", "open_tab", "new_tab"):
            return await self._open_tab(**kwargs)
        if act in ("focus", "focus_tab"):
            return await self._focus_tab(**kwargs)
        if act in ("close_tab",):
            return await self._close_tab(**kwargs)
        if act in ("navigate", "cdp_navigate"):
            return await self._navigate(**kwargs)
        if act in ("snapshot", "cdp_snapshot"):
            return await self._snapshot(**kwargs)
        if act in ("click", "cdp_click"):
            return await self._click(**kwargs)
        if act in ("click_coords",):
            return await self._click_coords(**kwargs)
        if act in ("type", "cdp_type"):
            return await self._type(**kwargs)
        if act in ("press", "cdp_press"):
            return await self._press(**kwargs)
        if act in ("hover", "cdp_hover"):
            return await self._hover(**kwargs)
        if act in ("scroll", "cdp_scroll"):
            return await self._scroll(**kwargs)
        if act in ("drag", "cdp_drag"):
            return await self._drag(**kwargs)
        if act in ("select", "cdp_select"):
            return await self._select(**kwargs)
        if act in ("fill", "cdp_fill"):
            return await self._fill(**kwargs)
        if act in ("wait", "cdp_wait"):
            return await self._wait(**kwargs)
        if act in ("get_text", "cdp_get_text"):
            return await self._get_text(**kwargs)
        if act in ("screenshot", "cdp_screenshot"):
            return await self._screenshot(**kwargs)
        if act in ("pdf", "cdp_pdf"):
            return await self._pdf(**kwargs)
        if act in ("evaluate", "cdp_evaluate"):
            return await self._evaluate(**kwargs)
        if act in ("extract", "cdp_extract"):
            return await self._extract(**kwargs)
        if act in ("resize", "cdp_resize"):
            return await self._resize(**kwargs)
        if act in ("console", "cdp_console"):
            return await self._console(**kwargs)
        if act in ("login", "cdp_login"):
            return await self._login(**kwargs)
        if act in ("assert", "cdp_assert"):
            return await self._assert(**kwargs)
        if act in ("explore", "cdp_explore", "probe"):
            return await self._explore(**kwargs)
        if act in ("batch",):
            return await self._batch(**kwargs)
        if act in ("run_step", "testcase_step", "cdp_run_step"):
            return await self._run_step(**kwargs)
        if act in ("run_testcase", "testcase_run", "cdp_run_testcase"):
            return await self._run_testcase(**kwargs)
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
        auto_login = str(kwargs.get("auto_login", "1")).lower() not in (
            "0",
            "false",
            "no",
            "off",
        )
        if creds_hint and creds_hint.get("username") and creds_hint.get("password"):
            out["login_credentials_available"] = True
            out["login_username"] = creds_hint["username"]
            # 有项目登录配置时默认自动登录（勿仅 open URL 就结束）
            if auto_login and out.get("success") and out.get("session_id"):
                login_kw = {
                    **kwargs,
                    "session_id": out["session_id"],
                    "project_id": project_id,
                    "username": creds_hint.get("username"),
                    "password": creds_hint.get("password"),
                    "return_url": url,
                }
                try:
                    login_out = await self._login(**login_kw)
                    out["auto_login"] = login_out
                    if login_out.get("login_success"):
                        out["login_success"] = True
                        out["page"] = login_out.get("page") or out.get("page")
                    elif login_out.get("await_user_credentials") or login_out.get(
                        "await_verification_code"
                    ):
                        out["hint"] = login_out.get("message") or out.get("hint")
                except Exception as ex:
                    out["auto_login_error"] = str(ex)[:240]
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

    async def _tabs(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "tabs 需要 session_id"}
        return await self._mgr.list_tabs(sid, owner_key=owner)

    async def _open_tab(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "open 需要 session_id"}
        return await self._mgr.open_tab(sid, url=kwargs.get("url"), owner_key=owner)

    async def _focus_tab(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "focus 需要 session_id"}
        return await self._mgr.focus_tab(
            sid,
            index=_int_or_none(kwargs.get("index")),
            tab_id=kwargs.get("tabId") or kwargs.get("tab_id") or kwargs.get("targetId"),
            owner_key=owner,
        )

    async def _close_tab(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "close_tab 需要 session_id"}
        return await self._mgr.close_tab(
            sid, index=_int_or_none(kwargs.get("index")), owner_key=owner
        )

    async def _click_coords(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "click_coords 需要 session_id"}
        try:
            x = float(kwargs.get("x"))
            y = float(kwargs.get("y"))
        except (TypeError, ValueError):
            return {"success": False, "error": "click_coords 需要数值 x,y"}
        return await self._mgr.actor(sid, owner_key=owner).click_coords(
            x=x,
            y=y,
            double_click=bool(kwargs.get("doubleClick") or kwargs.get("double_click")),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )

    async def _type(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        text = kwargs.get("text")
        if not sid or text is None:
            return {"success": False, "error": "type 需要 session_id 与 text"}
        return await self._mgr.actor(sid, owner_key=owner).type_text(
            text=str(text),
            ref=kwargs.get("ref"),
            snapshot_id=kwargs.get("snapshot_id"),
            selector=kwargs.get("selector"),
            slowly=bool(kwargs.get("slowly")),
            submit=bool(kwargs.get("submit")),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )

    async def _press(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "press 需要 session_id"}
        return await self._mgr.actor(sid, owner_key=owner).press(
            key=str(kwargs.get("key") or ""),
            ref=kwargs.get("ref"),
            snapshot_id=kwargs.get("snapshot_id"),
            selector=kwargs.get("selector"),
            delay_ms=_int_or_none(kwargs.get("delayMs") or kwargs.get("delay_ms")),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )

    async def _hover(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "hover 需要 session_id"}
        return await self._mgr.actor(sid, owner_key=owner).hover(
            ref=kwargs.get("ref"),
            snapshot_id=kwargs.get("snapshot_id"),
            selector=kwargs.get("selector"),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )

    async def _scroll(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "scroll 需要 session_id"}
        return await self._mgr.actor(sid, owner_key=owner).scroll_into_view(
            ref=kwargs.get("ref"),
            snapshot_id=kwargs.get("snapshot_id"),
            selector=kwargs.get("selector"),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )

    async def _drag(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "drag 需要 session_id"}
        return await self._mgr.actor(sid, owner_key=owner).drag(
            start_ref=kwargs.get("start_ref") or kwargs.get("startRef"),
            end_ref=kwargs.get("end_ref") or kwargs.get("endRef"),
            snapshot_id=kwargs.get("snapshot_id"),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )

    async def _select(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "select 需要 session_id"}
        values = kwargs.get("values")
        if isinstance(values, str):
            values = [values]
        return await self._mgr.actor(sid, owner_key=owner).select_option(
            values=values,
            ref=kwargs.get("ref"),
            snapshot_id=kwargs.get("snapshot_id"),
            selector=kwargs.get("selector"),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )

    async def _screenshot(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "screenshot 需要 session_id"}
        return await self._mgr.screenshot(
            sid,
            full_page=bool(kwargs.get("fullPage") or kwargs.get("full_page")),
            owner_key=owner,
            tag=str(kwargs.get("tag") or "shot"),
        )

    async def _pdf(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "pdf 需要 session_id"}
        return await self._mgr.pdf(sid, owner_key=owner)

    async def _evaluate(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "evaluate 需要 session_id"}
        return await self._mgr.actor(sid, owner_key=owner).evaluate_js(
            fn=str(kwargs.get("fn") or kwargs.get("code") or ""),
            timeout_ms=_int_or_none(kwargs.get("timeout_ms")),
        )

    async def _extract(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "extract 需要 session_id"}
        max_chars = _int_or_none(kwargs.get("maxChars") or kwargs.get("max_chars")) or 12000
        return await self._mgr.extract_readable(
            sid,
            query=kwargs.get("query"),
            selector=kwargs.get("selector"),
            max_chars=max_chars,
            owner_key=owner,
        )

    async def _resize(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "resize 需要 session_id"}
        w = _int_or_none(kwargs.get("width"))
        h = _int_or_none(kwargs.get("height"))
        if not w or not h:
            return {"success": False, "error": "resize 需要 width 与 height"}
        return await self._mgr.actor(sid, owner_key=owner).resize_viewport(width=w, height=h)

    async def _console(self, **kwargs) -> Dict[str, Any]:
        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "console 需要 session_id"}
        lim = _int_or_none(kwargs.get("limit")) or 50
        return await self._mgr.console_messages(sid, limit=lim, owner_key=owner)

    async def _run_step(self, **kwargs) -> Dict[str, Any]:
        """执行单条自然语言用例步骤（可带 expected 断言）。"""
        from agents.cdp.step_driver import run_testcase_step

        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        step = kwargs.get("step")
        if step is None and kwargs.get("step_index") is not None and kwargs.get("steps"):
            try:
                idx = int(kwargs["step_index"])
                steps = kwargs.get("steps") or []
                step = steps[idx] if 0 <= idx < len(steps) else None
            except (TypeError, ValueError, IndexError):
                step = None
        owner_kw = {
            k: kwargs[k]
            for k in ("project_id", "user_id", "plan_id", "ui_locale", "natural_query", "user_query")
            if k in kwargs and kwargs[k] is not None
        }
        out = await run_testcase_step(
            self,
            step=step,
            step_text=str(kwargs.get("step_text") or kwargs.get("text") or ""),
            expected=str(kwargs.get("expected") or ""),
            session_id=sid,
            assert_expected=kwargs.get("assert_expected", True) is not False,
            owner_kwargs=owner_kw,
        )
        out["tool"] = "cdp_run_step"
        return out

    async def _run_testcase(self, **kwargs) -> Dict[str, Any]:
        """按库内用例或传入 steps 顺序执行。"""
        from agents.cdp.step_driver import run_testcase_steps

        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        steps = kwargs.get("steps")
        tc_id = kwargs.get("testcase_id") or kwargs.get("test_case_id")
        if (not steps) and tc_id is not None:
            steps = self._load_testcase_steps(tc_id, project_id=kwargs.get("project_id"))
            if steps is None:
                return {"success": False, "error": f"未找到测试用例 {tc_id} 或无步骤"}
        if not isinstance(steps, list) or not steps:
            # 尝试从当前 cdp_test_run spec 取第一条用例
            rctx = kwargs.get("result_context")
            if isinstance(rctx, dict):
                run = rctx.get("cdp_test_run") or {}
                spec = run.get("spec_json") if isinstance(run, dict) else None
                if not isinstance(spec, dict):
                    # run may already be to_dict with nested testcases
                    spec = (run.get("spec") if isinstance(run, dict) else None) or {}
                tcs = []
                if isinstance(spec, dict):
                    tcs = spec.get("testcases") or []
                if not tcs and isinstance(run, dict):
                    tcs = run.get("testcases") or []
                if isinstance(tcs, list) and tcs:
                    first = tcs[0] if isinstance(tcs[0], dict) else {}
                    steps = first.get("steps") or []
                    if tc_id is None and first.get("id") is not None:
                        try:
                            tc_id = int(first["id"])
                        except (TypeError, ValueError):
                            pass
        if not isinstance(steps, list) or not steps:
            return {
                "success": False,
                "error": "run_testcase 需要 steps 或 testcase_id（或已开启含用例的 cdp_test_run）",
            }
        owner_kw = {
            k: kwargs[k]
            for k in ("project_id", "user_id", "plan_id", "ui_locale", "natural_query", "user_query")
            if k in kwargs and kwargs[k] is not None
        }
        out = await run_testcase_steps(
            self,
            steps,
            session_id=sid,
            stop_on_fail=kwargs.get("stop_on_fail", True) is not False,
            owner_kwargs=owner_kw,
            testcase_id=int(tc_id) if tc_id is not None else None,
        )
        return out

    @staticmethod
    def _load_testcase_steps(testcase_id: Any, project_id: Any = None) -> Optional[list]:
        try:
            tid = int(testcase_id)
        except (TypeError, ValueError):
            return None
        try:
            from flask import has_app_context

            if not has_app_context():
                return None
            from models.orm import TestCase
            from db_extensions import db

            q = db.session.query(TestCase).filter(TestCase.id == tid)
            if project_id is not None:
                try:
                    q = q.filter(TestCase.project_id == int(project_id))
                except (TypeError, ValueError):
                    pass
            row = q.first()
            if not row:
                return None
            return row.steps if isinstance(row.steps, list) else []
        except Exception:
            return None

    async def _batch(self, **kwargs) -> Dict[str, Any]:
        """对齐 OpenClaw act:batch — 顺序执行 actions 列表。"""
        actions = kwargs.get("actions") or kwargs.get("request", {}).get("actions")
        if not isinstance(actions, list) or not actions:
            # 兼容单 kind 扁平参数
            kind = kwargs.get("kind")
            if kind:
                actions = [kwargs]
            else:
                return {"success": False, "error": "batch 需要 actions 列表"}
        stop_on_error = kwargs.get("stopOnError", kwargs.get("stop_on_error", True))
        results = []
        for i, step in enumerate(actions):
            if not isinstance(step, dict):
                results.append({"ok": False, "error": "action 非对象", "index": i})
                if stop_on_error:
                    break
                continue
            step_kw = dict(kwargs)
            step_kw.update(step)
            step_kw.pop("actions", None)
            sub = (
                step.get("action")
                or step.get("kind")
                or step.get("tool_action")
                or ""
            )
            out = await self.execute(action=str(sub), **step_kw)
            ok = bool(out.get("success"))
            results.append({"ok": ok, "index": i, "action": sub, "result": out})
            if not ok and stop_on_error:
                break
        return {
            "success": all(r.get("ok") for r in results) if results else False,
            "tool": "cdp_batch",
            "results": results,
            "count": len(results),
        }

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
        return_url = str(kwargs.get("return_url") or "").strip()

        snap_result = await self._mgr.snapshot(sid, scope="interactive", owner_key=owner)
        snap_result = enrich_snapshot_with_login_hints(snap_result)
        if not snap_result.get("success"):
            return snap_result

        nodes = snap_result.get("nodes") or []
        snapshot_id = snap_result.get("snapshot_id")
        page_info = snap_result.get("page") or await session.page_info()
        url = str(page_info.get("url") or snap_result.get("url") or "")
        # SPA 路由守卫可能稍后才跳到 #/login，稍等再判
        if not is_login_url(url):
            for _ in range(12):
                await asyncio.sleep(0.25)
                page_info = await session.page_info()
                url = str(page_info.get("url") or "")
                if is_login_url(url):
                    snap_result = await self._mgr.snapshot(
                        sid, scope="interactive", owner_key=owner
                    )
                    snap_result = enrich_snapshot_with_login_hints(snap_result)
                    nodes = snap_result.get("nodes") or []
                    snapshot_id = snap_result.get("snapshot_id")
                    break

        analysis = analyze_login_page(nodes, url)
        creds = resolve_login_credentials(
            url=url or return_url,
            project_id=int(project_id) if project_id else None,
            username=kwargs.get("username"),
            password=kwargs.get("password"),
        )
        username = creds.get("username")
        password = creds.get("password")
        login_page_url = str(creds.get("url") or "").strip()

        # 仍在业务页且未识别登录表单：跳到项目配置的登录 URL 再填表
        if not analysis.is_login_page and not is_login_url(url):
            if login_page_url and username and password:
                if not return_url and url and not is_login_url(url):
                    return_url = url
                nav = await self._mgr.navigate(
                    sid,
                    login_page_url,
                    wait_until="domcontentloaded",
                    owner_key=owner,
                )
                if not nav.get("success"):
                    return {
                        "success": False,
                        "action": "login",
                        "tool": "cdp_login",
                        "session_id": sid,
                        "message": f"跳转登录页失败: {nav.get('error') or login_page_url}",
                        "page": page_info,
                    }
                await asyncio.sleep(0.6)
                snap_result = await self._mgr.snapshot(
                    sid, scope="interactive", owner_key=owner
                )
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
                    "message": "非登录页，已跳过自动登录（无匹配登录配置或未识别登录表单）",
                    "page": page_info,
                }

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
        # 从业务页被带到登录页时：登完再回到原目标 URL
        if return_url and not is_login_url(return_url):
            try:
                nav_back = await self._mgr.navigate(
                    sid,
                    return_url,
                    wait_until="domcontentloaded",
                    owner_key=owner,
                )
                steps.append(
                    {
                        "step": "return_url",
                        "url": return_url,
                        "success": bool(nav_back.get("success")),
                    }
                )
                if nav_back.get("success"):
                    page_info = await session.page_info()
                    landing = await wait_for_post_login_landing(
                        session.page, timeout_ms=8000
                    )
            except Exception as ex:
                steps.append({"step": "return_url", "url": return_url, "error": str(ex)[:120]})
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
            "return_url": return_url or None,
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
        from agents.cdp.midscene_bridge import explore_engine, run_midscene_exploration
        from agents.cdp.params import resolve_cdp_target_url

        owner = self._owner_key(kwargs)
        sid = kwargs.get("session_id") or self._mgr.latest_session_id(owner_key=owner)
        if not sid:
            return {"success": False, "error": "explore 需要 session_id（请先 session create）"}
        nav = await self._ensure_on_target_url(sid, kwargs, owner_key=owner)
        if isinstance(nav, dict) and not nav.get("success"):
            return nav
        phase = kwargs.get("phase") or kwargs.get("sub_phase") or "full"
        user_query = kwargs.get("natural_query") or kwargs.get("user_query")
        eng = explore_engine()
        force_legacy = str(phase).lower() in ("dfs", "inventory", "legacy")
        if eng != "legacy" and not force_legacy:
            url = resolve_cdp_target_url(
                params=kwargs,
                user_input=user_query,
                result_context=kwargs.get("result_context"),
            )
            if not url:
                try:
                    sess = self._mgr.get_session(sid, owner_key=owner)
                    page_info = await sess.page_info() if sess else {}
                    url = str((page_info or {}).get("url") or "")
                except Exception:
                    url = ""
            if url:
                print(f"[CDP] explore engine={eng} via midscene url={url}", flush=True)
                mid = await run_midscene_exploration(
                    url=url,
                    user_query=str(user_query or ""),
                )
                if mid.get("fallback_legacy") and eng in ("auto", "midscene"):
                    # midscene 明确要求时可回退；auto 必回退；纯 midscene 也回退以免阻断
                    print(
                        f"[CDP] midscene fallback legacy: {mid.get('error')}",
                        flush=True,
                    )
                elif not mid.get("fallback_legacy"):
                    mid["session_id"] = sid
                    return mid
            else:
                print("[CDP] midscene skip: no url, fallback legacy explore", flush=True)

        return await run_exploration(
            self._mgr,
            sid,
            phase=str(phase) if str(phase).lower() != "legacy" else "full",
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
