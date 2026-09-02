# -*- coding: utf-8 -*-
"""元素操作：ref / selector → 点击、输入、等待、读文本。"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .errors import CdpError, AMBIGUOUS_SELECTOR, STALE_REF, TIMEOUT

if TYPE_CHECKING:
    from .session_manager import BrowserSession
from .settings import cdp_default_timeout_ms, cdp_stale_ref_auto_snapshot
from .snapshot import AxSnapshotBuilder, PageSnapshot, SnapshotNode

_INTERACTIVE_CLICK_ROLES = frozenset({
    "button", "link", "tab", "menuitem", "menuitemcheckbox", "menuitemradio",
    "checkbox", "radio", "switch", "treeitem", "option",
})

# 无障碍 name 与 title/文案不一致时的别名（如 PlansPanel「新建迭代」/ title「新增迭代」）
_NAME_CLICK_ALIASES: Dict[str, List[str]] = {
    "新建迭代": ["新增迭代", "Add iteration"],
    "新增迭代": ["新建迭代", "Add iteration"],
}


def _click_name_variants(name: Optional[str]) -> List[str]:
    base = (name or "").strip()
    if not base:
        return []
    out: List[str] = [base]
    for alias in _NAME_CLICK_ALIASES.get(base, []):
        if alias not in out:
            out.append(alias)
    for key, aliases in _NAME_CLICK_ALIASES.items():
        if key in base:
            for alias in aliases:
                if alias not in out:
                    out.append(alias)
    return out


class ElementActor:
    def __init__(self, session: "BrowserSession"):
        self.session = session

    async def resolve_ref(
        self,
        ref: Optional[str],
        snapshot_id: Optional[str],
        selector: Optional[str] = None,
    ) -> SnapshotNode:
        if selector:
            return await self._resolve_unique_selector(selector)
        if not ref:
            raise CdpError("invalid_action", "需要 ref 或 selector")
        snap = self.session.get_snapshot(snapshot_id) or self.session.last_snapshot
        if not snap:
            raise CdpError(STALE_REF, "无可用快照，请先 cdp_snapshot", suggest_tool="cdp_snapshot")
        node = snap.ref_index.get(ref)
        if not node:
            raise CdpError(
                STALE_REF,
                f"ref {ref} 不在快照 {snap.snapshot_id} 中",
                snapshot_id=snap.snapshot_id,
                suggest_tool="cdp_snapshot",
            )
        return node

    async def _resolve_unique_selector(self, selector: str) -> SnapshotNode:
        page = self.session.page
        count = await page.locator(selector).count()
        if count == 0:
            raise CdpError(STALE_REF, f"selector 未匹配元素: {selector}", suggest_tool="cdp_snapshot")
        if count > 1:
            raise CdpError(AMBIGUOUS_SELECTOR, f"selector 匹配 {count} 个元素", selector=selector)
        return SnapshotNode(ref="", role="", name="", selector_hint=selector)

    async def _stale_ref_recovery(self, err: CdpError) -> Dict[str, Any]:
        from .vision_understand import agent_loop_hint

        extra: Dict[str, Any] = {"stale_ref_recovered": False}
        if not cdp_stale_ref_auto_snapshot():
            extra["agent_hint"] = agent_loop_hint(stale=True, has_vision=False)
            return extra
        try:
            tree = await self.session.page.accessibility.snapshot(interesting_only=True)
            light = AxSnapshotBuilder(max_nodes=32).build_light_from_playwright_tree(
                tree,
                url=self.session.page.url,
                title=await self.session.page.title(),
            )
            self.session.last_snapshot = light
            extra["stale_ref_recovered"] = True
            extra["new_snapshot_id"] = light.snapshot_id
            extra["focus_hints"] = [
                {"ref": n.ref, "role": n.role, "name": n.name}
                for n in light.nodes[:12]
            ]
            extra["suggest_tool"] = "cdp_snapshot"
            extra["agent_hint"] = agent_loop_hint(stale=True, has_vision=False)
        except Exception:
            extra["agent_hint"] = agent_loop_hint(stale=True, has_vision=False)
        return extra

    async def _attach_failure_vision(
        self,
        out: Dict[str, Any],
        *,
        tag: str,
        stale: bool = False,
        context: str = "",
    ) -> None:
        """失败时截图 + 视觉描述，供 Agent 闭环决策（OpenClaw 风格）。"""
        try:
            from .vision_understand import attach_vision_fields

            await attach_vision_fields(
                out,
                self.session.page,
                context=context or f"action failed tag={tag}",
                stale=stale,
                upload=True,
                session_id=self.session.session_id,
                tag=tag,
            )
        except Exception:
            pass

    def _wrap_stale(self, err: CdpError) -> CdpError:
        if err.code != STALE_REF:
            return err
        return err

    async def click(
        self,
        *,
        ref: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        selector: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        timeout = timeout_ms or cdp_default_timeout_ms()
        steps: List[Dict[str, Any]] = []
        node: Optional[SnapshotNode] = None
        try:
            node = await self.resolve_ref(ref, snapshot_id, selector)
            await self._perform_click(node, steps, timeout)
            await self.session.touch()
            dur = int((time.perf_counter() - t0) * 1000)
            snap = self.session.last_snapshot
            return {
                "success": True,
                "tool": "cdp_click",
                "session_id": self.session.session_id,
                "snapshot_id": snap.snapshot_id if snap else snapshot_id,
                "ref": ref,
                "role": node.role,
                "name": node.name,
                "selector": selector or node.selector_hint,
                "steps": steps,
                "duration_ms": dur,
                "page": await self.session.page_info(),
            }
        except CdpError as e:
            extra = {}
            stale = e.code == STALE_REF
            if stale:
                extra = await self._stale_ref_recovery(e)
            out = e.to_dict()
            out.update(extra)
            out["tool"] = "cdp_click"
            out["duration_ms"] = int((time.perf_counter() - t0) * 1000)
            if node is not None:
                out["role"] = node.role
                out["name"] = node.name
            if out.get("success") is False:
                ctx = (
                    f"click failed ref={ref or ''} role={out.get('role') or ''} "
                    f"name={out.get('name') or ''} err={out.get('message') or out.get('error') or ''}"
                )
                await self._attach_failure_vision(
                    out,
                    tag=str(ref or (node.ref if node else None) or "click"),
                    stale=stale or bool(out.get("stale_ref_recovered")),
                    context=ctx,
                )
            return out

    async def _perform_click(self, node: SnapshotNode, steps: List[Dict], timeout: int) -> None:
        """点击策略：selector → option/checkbox → 有 name 的 role → box model → JS click → 别名/heuristic。"""
        if node.selector_hint:
            await self.session.page.locator(node.selector_hint).click(timeout=timeout)
            steps.append({"method": "playwright.locator.click", "selector": node.selector_hint, "ok": True})
            return

        role_lower = node.role.lower()
        if role_lower == "option" and (node.name or node.value):
            await self._click_option_node(node, steps, timeout)
            return
        if role_lower == "checkbox":
            if await self._try_toggle_checkbox(node, steps, timeout):
                return

        has_name = bool((node.name or "").strip())
        if has_name and role_lower in ("button", "link", "tab", "menuitem"):
            if await self._try_click_by_role_name(node, steps, timeout):
                return

        if node.backend_node_id is not None:
            if await self._try_click_backend_node(node.backend_node_id, steps, timeout):
                return
            if await self._try_click_backend_js(node.backend_node_id, steps):
                return

        if await self._try_click_by_role_name(node, steps, timeout):
            return

        if await self._try_click_css_heuristics(node, steps, timeout):
            return

        await self._click_by_role_name(node, steps, timeout)

    async def _try_click_backend_node(self, backend_node_id: int, steps: List[Dict], timeout: int) -> bool:
        client = await self.session.cdp_session()
        try:
            try:
                await client.send("DOM.scrollIntoViewIfNeeded", {"backendNodeId": backend_node_id})
            except Exception:
                pass
            model = await client.send("DOM.getBoxModel", {"backendNodeId": backend_node_id})
            quad = model["model"]["content"]
            x = sum(quad[i] for i in range(0, 8, 2)) / 4
            y = sum(quad[i] for i in range(1, 8, 2)) / 4
            page = self.session.page
            try:
                await page.mouse.click(x, y, timeout=min(timeout, 5000))
                steps.append({"method": "playwright.mouse.click", "ok": True, "x": x, "y": y})
                return True
            except Exception:
                pass
            for typ in ("mousePressed", "mouseReleased"):
                await client.send(
                    "Input.dispatchMouseEvent",
                    {
                        "type": typ,
                        "x": x,
                        "y": y,
                        "button": "left",
                        "clickCount": 1,
                    },
                )
            steps.append({"cdp_method": "Input.dispatchMouseEvent", "ok": True, "x": x, "y": y})
            return True
        except Exception as ex:
            steps.append({"cdp_method": "Input.dispatchMouseEvent", "ok": False, "error": str(ex)[:200]})
            return False

    async def _try_click_backend_js(self, backend_node_id: int, steps: List[Dict]) -> bool:
        """getBoxModel 失败时，对 ref 对应 DOM 直接 dispatch click（手动能点、坐标算不出时用）。"""
        client = await self.session.cdp_session()
        try:
            resolved = await client.send("DOM.resolveNode", {"backendNodeId": backend_node_id})
            oid = resolved.get("object", {}).get("objectId")
            if not oid:
                return False
            result = await client.send(
                "Runtime.callFunctionOn",
                {
                    "objectId": oid,
                    "functionDeclaration": (
                        "function() {"
                        "  const el = this;"
                        "  if (!el) return false;"
                        "  if (typeof el.click === 'function') { el.click(); return true; }"
                        "  el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));"
                        "  return true;"
                        "}"
                    ),
                    "returnByValue": True,
                },
            )
            ok = bool((result.get("result") or {}).get("value"))
            steps.append({"method": "cdp.js.click", "ok": ok, "backendNodeId": backend_node_id})
            return ok
        except Exception as ex:
            steps.append({"method": "cdp.js.click", "ok": False, "error": str(ex)[:200]})
            return False

    async def _try_click_css_heuristics(self, node: SnapshotNode, steps: List[Dict], timeout: int) -> bool:
        """无可靠 name/backend 时的页面级兜底（如 PlansPanel 新建迭代）。"""
        page = self.session.page
        name = (node.name or "").strip()
        candidates: List[str] = []
        if "新建迭代" in name or "新增迭代" in name or name in ("", "➕", "➕ 新建迭代"):
            candidates.extend([
                'button.action-icon-btn[aria-label="新建迭代"]',
                'button.action-icon-btn:has-text("新建迭代")',
                'button[title*="迭代"]',
                'button.action-icon-btn',
            ])
        if not candidates:
            return False
        idx = max(0, int(node.role_name_index or 0))
        for sel in candidates:
            try:
                loc = page.locator(sel)
                cnt = await loc.count()
                if cnt > idx:
                    await loc.nth(idx).click(timeout=timeout)
                    steps.append({"method": "playwright.css_heuristic", "selector": sel, "index": idx, "ok": True})
                    return True
            except Exception as ex:
                steps.append({"method": "playwright.css_heuristic", "selector": sel, "ok": False, "error": str(ex)[:120]})
        return False

    async def _try_toggle_checkbox(self, node: SnapshotNode, steps: List[Dict], timeout: int) -> bool:
        page = self.session.page
        name = node.name or None
        try:
            loc = page.get_by_role("checkbox", name=name) if name else page.get_by_role("checkbox")
            if await loc.count() == 0:
                return False
            target = loc.first
            if await target.is_checked():
                await target.uncheck(timeout=timeout)
                steps.append({"method": "playwright.uncheck", "name": name, "ok": True})
            else:
                await target.check(timeout=timeout)
                steps.append({"method": "playwright.check", "name": name, "ok": True})
            return True
        except Exception as ex:
            steps.append({"method": "playwright.check", "ok": False, "error": str(ex)[:200]})
            return False

    async def _click_option_node(self, node: SnapshotNode, steps: List[Dict], timeout: int) -> None:
        """原生 select / combobox 的 option：用 select_option 或先展开再点。"""
        page = self.session.page
        label = (node.name or node.value or "").strip()
        if not label:
            raise CdpError(STALE_REF, "option 无可用名称", suggest_tool="cdp_snapshot")

        last_err: Optional[Exception] = None
        selects = page.locator("select")
        count = await selects.count()
        for i in range(count):
            sel = selects.nth(i)
            for kw in ("label", "value"):
                try:
                    await sel.select_option(**{kw: label}, timeout=timeout)
                    steps.append({"method": "playwright.select_option", kw: label, "ok": True})
                    return
                except Exception as ex:
                    last_err = ex

        try:
            combo = page.get_by_role("combobox")
            if await combo.count() > 0:
                await combo.first.click(timeout=timeout)
                await page.get_by_role("option", name=label).first.click(timeout=timeout)
                steps.append({"method": "playwright.combobox+option", "label": label, "ok": True})
                return
        except Exception as ex:
            last_err = ex

        raise CdpError(
            STALE_REF,
            f"option 选择失败: {last_err}",
            suggest_tool="cdp_snapshot",
        ) from last_err

    async def _try_click_by_role_name(self, node: SnapshotNode, steps: List[Dict], timeout: int) -> bool:
        page = self.session.page
        role = node.role.lower()
        name = (node.name or "").strip() or None
        idx = max(0, int(node.role_name_index or 0))
        names_to_try = _click_name_variants(name) if name else ([None] if role not in _INTERACTIVE_CLICK_ROLES else [])

        for try_name in names_to_try:
            try:
                if try_name and role in ("button", "link", "tab", "menuitem"):
                    for alt in (
                        lambda n=try_name: page.get_by_role(role, name=n),
                        lambda n=try_name: page.get_by_label(n, exact=False),
                        lambda n=try_name: page.get_by_title(n, exact=False),
                        lambda n=try_name: page.locator(f'[aria-label="{n}"]'),
                        lambda n=try_name: page.get_by_role(role).filter(has_text=n),
                    ):
                        try:
                            loc = alt()
                            cnt = await loc.count()
                            if cnt > idx:
                                await loc.nth(idx).click(timeout=timeout)
                                steps.append({
                                    "method": "playwright.role_or_attr",
                                    "role": role,
                                    "name": try_name,
                                    "index": idx,
                                    "ok": True,
                                })
                                return True
                        except Exception:
                            continue
                if not try_name and role in _INTERACTIVE_CLICK_ROLES:
                    continue
                loc = page.get_by_role(role, name=try_name) if try_name else page.get_by_role(role)
                cnt = await loc.count()
                if cnt <= idx:
                    continue
                await loc.nth(idx).click(timeout=timeout)
                steps.append({"method": "playwright.get_by_role", "role": role, "name": try_name, "index": idx, "ok": True})
                return True
            except Exception as ex:
                steps.append({
                    "method": "playwright.get_by_role",
                    "role": role,
                    "name": try_name,
                    "index": idx,
                    "ok": False,
                    "error": str(ex)[:200],
                })
        return False

    async def _click_by_role_name(self, node: SnapshotNode, steps: List[Dict], timeout: int) -> None:
        if await self._try_click_by_role_name(node, steps, timeout):
            return
        role = node.role.lower()
        name = node.name or None
        raise CdpError(
            STALE_REF,
            f"role/name 点击失败: {role}/{name or ''}",
            suggest_tool="cdp_snapshot",
        )

    async def fill(
        self,
        *,
        text: str,
        ref: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        selector: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        timeout = timeout_ms or cdp_default_timeout_ms()
        display_text = "***" if len(text) > 0 and "pass" in (ref or selector or "").lower() else text
        steps: List[Dict[str, Any]] = []
        try:
            node = await self.resolve_ref(ref, snapshot_id, selector)
            await self._perform_fill(node, text, steps, timeout)
            await self.session.touch()
            dur = int((time.perf_counter() - t0) * 1000)
            snap = self.session.last_snapshot
            return {
                "success": True,
                "tool": "cdp_fill",
                "session_id": self.session.session_id,
                "ref": ref,
                "role": node.role,
                "name": node.name,
                "text_length": len(text),
                "text_preview": (display_text[:20] + "…") if len(display_text) > 20 else display_text,
                "duration_ms": dur,
                "snapshot_id": snap.snapshot_id if snap else snapshot_id,
                "steps": steps,
                "page": await self.session.page_info(),
            }
        except CdpError as e:
            extra = {}
            stale = e.code == STALE_REF
            if stale:
                extra = await self._stale_ref_recovery(e)
            out = e.to_dict()
            out.update(extra)
            out["tool"] = "cdp_fill"
            out["duration_ms"] = int((time.perf_counter() - t0) * 1000)
            if out.get("success") is False:
                ctx = (
                    f"fill failed ref={ref or ''} "
                    f"err={out.get('message') or out.get('error') or ''}"
                )
                await self._attach_failure_vision(
                    out,
                    tag=str(ref or "fill"),
                    stale=stale or bool(out.get("stale_ref_recovered")),
                    context=ctx,
                )
            return out

    async def _perform_fill(self, node: SnapshotNode, text: str, steps: List[Dict], timeout: int) -> None:
        page = self.session.page
        if node.selector_hint:
            loc = page.locator(node.selector_hint)
            await loc.click(timeout=timeout)
            await loc.fill(text, timeout=timeout)
            steps.append({"method": "playwright.locator.fill", "selector": node.selector_hint, "ok": True})
            return

        role = node.role.lower()
        name = (node.name or "").strip() or None
        idx = max(0, int(node.role_name_index or 0))
        fill_roles = frozenset({"textbox", "searchbox", "combobox", "spinbutton"})

        if role in fill_roles or node.focusable:
            locators = []
            if role in fill_roles:
                if name:
                    locators.extend([
                        page.get_by_role(role, name=name),
                        page.get_by_label(name, exact=False),
                        page.get_by_placeholder(name, exact=False),
                    ])
                else:
                    locators.append(page.get_by_role(role))
            if name:
                locators.extend([
                    page.get_by_label(name, exact=False),
                    page.get_by_placeholder(name, exact=False),
                ])
            for loc in locators:
                try:
                    cnt = await loc.count()
                    if cnt > idx:
                        target = loc.nth(idx)
                        await target.click(timeout=timeout)
                        await target.fill(text, timeout=timeout)
                        steps.append({"method": "playwright.fill", "role": role, "name": name, "index": idx, "ok": True})
                        return
                except Exception:
                    continue

        if node.backend_node_id is not None:
            if await self._try_click_backend_node(node.backend_node_id, steps, timeout):
                await page.keyboard.type(text, delay=20)
                steps.append({"method": "keyboard.type", "ok": True, "length": len(text)})
                return

        raise CdpError(
            STALE_REF,
            f"无法填写: {role}/{name or ''}",
            suggest_tool="cdp_snapshot",
        )

    async def get_text(
        self,
        *,
        ref: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        selector: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        timeout = timeout_ms or cdp_default_timeout_ms()
        try:
            node = await self.resolve_ref(ref, snapshot_id, selector)
            if node.value:
                text = node.value
            elif node.selector_hint:
                text = await self.session.page.locator(node.selector_hint).inner_text(timeout=timeout)
            else:
                loc = self.session.page.get_by_role(node.role.lower(), name=node.name or None).first
                text = await loc.inner_text(timeout=timeout)
            await self.session.touch()
            return {
                "success": True,
                "tool": "cdp_get_text",
                "text": text,
                "ref": ref,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "page": await self.session.page_info(),
            }
        except CdpError as e:
            out = e.to_dict()
            out["tool"] = "cdp_get_text"
            return out

    async def wait_for(
        self,
        *,
        ref: Optional[str] = None,
        selector: Optional[str] = None,
        text: Optional[str] = None,
        url_matches: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        timeout = timeout_ms or cdp_default_timeout_ms()
        page = self.session.page
        try:
            if url_matches:
                import re

                deadline = time.perf_counter() + timeout / 1000.0
                while time.perf_counter() < deadline:
                    if re.search(url_matches, page.url):
                        await self.session.touch()
                        return {
                            "success": True,
                            "tool": "cdp_wait",
                            "matched": "url",
                            "duration_ms": int((time.perf_counter() - t0) * 1000),
                            "page": await self.session.page_info(),
                        }
                    await asyncio.sleep(0.15)
                raise CdpError(TIMEOUT, f"URL 未匹配 {url_matches}", error_code=TIMEOUT)
            if text:
                await page.get_by_text(text, exact=False).first.wait_for(state="visible", timeout=timeout)
            elif selector:
                await page.locator(selector).wait_for(state="visible", timeout=timeout)
            elif ref:
                node = await self.resolve_ref(ref, None)
                if node.selector_hint:
                    await page.locator(node.selector_hint).wait_for(state="visible", timeout=timeout)
                else:
                    await page.get_by_role(node.role.lower(), name=node.name or None).first.wait_for(
                        state="visible", timeout=timeout
                    )
            await self.session.touch()
            return {
                "success": True,
                "tool": "cdp_wait",
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "page": await self.session.page_info(),
            }
        except CdpError as e:
            out = e.to_dict()
            out["tool"] = "cdp_wait"
            return out
        except Exception as ex:
            return CdpError(TIMEOUT, str(ex), error_code=TIMEOUT).to_dict() | {
                "tool": "cdp_wait",
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            }

    async def assert_condition(
        self,
        *,
        ref: Optional[str] = None,
        selector: Optional[str] = None,
        text_contains: Optional[str] = None,
        text: Optional[str] = None,
        url_matches: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """断言页面状态；失败时带 assertion_failed 供证据链与自动 create 预览。"""
        t0 = time.perf_counter()
        timeout = timeout_ms or cdp_default_timeout_ms()
        expect_text = (text_contains or text or "").strip()
        page = self.session.page
        deadline = time.perf_counter() + timeout / 1000.0
        last_err = "断言未通过"

        while time.perf_counter() < deadline:
            try:
                if url_matches:
                    import re

                    if re.search(url_matches, page.url):
                        await self.session.touch()
                        return {
                            "success": True,
                            "tool": "cdp_assert",
                            "assertion_passed": True,
                            "matched": "url",
                            "session_id": self.session.session_id,
                            "duration_ms": int((time.perf_counter() - t0) * 1000),
                            "page": await self.session.page_info(),
                        }
                    last_err = f"URL 未匹配 {url_matches}（当前 {page.url[:120]}）"
                if expect_text:
                    if await page.get_by_text(expect_text, exact=False).count() > 0:
                        await self.session.touch()
                        return {
                            "success": True,
                            "tool": "cdp_assert",
                            "assertion_passed": True,
                            "matched": "text",
                            "session_id": self.session.session_id,
                            "duration_ms": int((time.perf_counter() - t0) * 1000),
                            "page": await self.session.page_info(),
                        }
                    last_err = f"页面未找到文本「{expect_text[:80]}」"
                if ref or selector:
                    node = await self.resolve_ref(ref, None, selector)
                    loc = (
                        page.locator(node.selector_hint)
                        if node.selector_hint
                        else page.get_by_role(node.role.lower(), name=node.name or None).first
                    )
                    await loc.wait_for(state="visible", timeout=500)
                    await self.session.touch()
                    return {
                        "success": True,
                        "tool": "cdp_assert",
                        "assertion_passed": True,
                        "matched": "ref",
                        "ref": ref,
                        "session_id": self.session.session_id,
                        "duration_ms": int((time.perf_counter() - t0) * 1000),
                        "page": await self.session.page_info(),
                    }
            except CdpError as e:
                last_err = str(e.message or e)
            except Exception as ex:
                last_err = str(ex)
            await asyncio.sleep(0.15)

        page_info = await self.session.page_info()
        return {
            "success": False,
            "tool": "cdp_assert",
            "assertion_failed": True,
            "message": last_err,
            "error": last_err,
            "session_id": self.session.session_id,
            "ref": ref,
            "duration_ms": int((time.perf_counter() - t0) * 1000),
            "page": page_info,
        }

    # —— 以下动作对齐 OpenClaw Browser act kinds（Playwright 实现）——

    async def hover(
        self,
        *,
        ref: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        selector: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        timeout = timeout_ms or cdp_default_timeout_ms()
        try:
            node = await self.resolve_ref(ref, snapshot_id, selector)
            loc = await self._locator_for_node(node)
            await loc.hover(timeout=timeout)
            await self.session.touch()
            return {
                "success": True,
                "tool": "cdp_hover",
                "ref": ref,
                "session_id": self.session.session_id,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "page": await self.session.page_info(),
            }
        except CdpError as e:
            return e.to_dict() | {"tool": "cdp_hover"}
        except Exception as ex:
            return {"success": False, "tool": "cdp_hover", "error": str(ex)}

    async def scroll_into_view(
        self,
        *,
        ref: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        selector: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        timeout = timeout_ms or cdp_default_timeout_ms()
        try:
            node = await self.resolve_ref(ref, snapshot_id, selector)
            if node.backend_node_id is not None:
                client = await self.session.cdp_session()
                await client.send(
                    "DOM.scrollIntoViewIfNeeded", {"backendNodeId": node.backend_node_id}
                )
            else:
                loc = await self._locator_for_node(node)
                await loc.scroll_into_view_if_needed(timeout=timeout)
            await self.session.touch()
            return {
                "success": True,
                "tool": "cdp_scroll",
                "ref": ref,
                "session_id": self.session.session_id,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "page": await self.session.page_info(),
            }
        except CdpError as e:
            return e.to_dict() | {"tool": "cdp_scroll"}
        except Exception as ex:
            return {"success": False, "tool": "cdp_scroll", "error": str(ex)}

    async def press(
        self,
        *,
        key: str,
        ref: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        selector: Optional[str] = None,
        delay_ms: Optional[int] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        timeout = timeout_ms or cdp_default_timeout_ms()
        k = (key or "").strip()
        if not k:
            return {"success": False, "error": "press 需要 key"}
        try:
            page = self.session.page
            if ref or selector:
                node = await self.resolve_ref(ref, snapshot_id, selector)
                loc = await self._locator_for_node(node)
                await loc.press(k, delay=delay_ms or 0, timeout=timeout)
            else:
                await page.keyboard.press(k, delay=delay_ms or 0)
            await self.session.touch()
            return {
                "success": True,
                "tool": "cdp_press",
                "key": k,
                "session_id": self.session.session_id,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "page": await self.session.page_info(),
            }
        except CdpError as e:
            return e.to_dict() | {"tool": "cdp_press"}
        except Exception as ex:
            return {"success": False, "tool": "cdp_press", "error": str(ex)}

    async def type_text(
        self,
        *,
        text: str,
        ref: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        selector: Optional[str] = None,
        slowly: bool = False,
        submit: bool = False,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """对齐 OpenClaw act:type（可 slowly / submit）。"""
        t0 = time.perf_counter()
        timeout = timeout_ms or cdp_default_timeout_ms()
        try:
            node = await self.resolve_ref(ref, snapshot_id, selector)
            loc = await self._locator_for_node(node)
            await loc.click(timeout=timeout)
            if slowly:
                await loc.type(str(text), delay=40, timeout=timeout)
            else:
                await loc.fill(str(text), timeout=timeout)
            if submit:
                await loc.press("Enter", timeout=timeout)
            await self.session.touch()
            return {
                "success": True,
                "tool": "cdp_type",
                "ref": ref,
                "slowly": slowly,
                "submit": submit,
                "session_id": self.session.session_id,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "page": await self.session.page_info(),
            }
        except CdpError as e:
            return e.to_dict() | {"tool": "cdp_type"}
        except Exception as ex:
            return {"success": False, "tool": "cdp_type", "error": str(ex)}

    async def select_option(
        self,
        *,
        values: Optional[List[str]] = None,
        ref: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        selector: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        timeout = timeout_ms or cdp_default_timeout_ms()
        vals = [str(v) for v in (values or []) if str(v).strip()]
        if not vals:
            return {"success": False, "error": "select 需要 values"}
        try:
            node = await self.resolve_ref(ref, snapshot_id, selector)
            loc = await self._locator_for_node(node)
            await loc.select_option(vals if len(vals) > 1 else vals[0], timeout=timeout)
            await self.session.touch()
            return {
                "success": True,
                "tool": "cdp_select",
                "values": vals,
                "ref": ref,
                "session_id": self.session.session_id,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "page": await self.session.page_info(),
            }
        except CdpError as e:
            return e.to_dict() | {"tool": "cdp_select"}
        except Exception as ex:
            return {"success": False, "tool": "cdp_select", "error": str(ex)}

    async def drag(
        self,
        *,
        start_ref: Optional[str] = None,
        end_ref: Optional[str] = None,
        snapshot_id: Optional[str] = None,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        timeout = timeout_ms or cdp_default_timeout_ms()
        if not start_ref or not end_ref:
            return {"success": False, "error": "drag 需要 start_ref 与 end_ref"}
        try:
            a = await self.resolve_ref(start_ref, snapshot_id, None)
            b = await self.resolve_ref(end_ref, snapshot_id, None)
            loc_a = await self._locator_for_node(a)
            loc_b = await self._locator_for_node(b)
            await loc_a.drag_to(loc_b, timeout=timeout)
            await self.session.touch()
            return {
                "success": True,
                "tool": "cdp_drag",
                "start_ref": start_ref,
                "end_ref": end_ref,
                "session_id": self.session.session_id,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "page": await self.session.page_info(),
            }
        except CdpError as e:
            return e.to_dict() | {"tool": "cdp_drag"}
        except Exception as ex:
            return {"success": False, "tool": "cdp_drag", "error": str(ex)}

    async def click_coords(
        self,
        *,
        x: float,
        y: float,
        double_click: bool = False,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        try:
            page = self.session.page
            if double_click:
                await page.mouse.dblclick(float(x), float(y))
            else:
                await page.mouse.click(float(x), float(y))
            await self.session.touch()
            return {
                "success": True,
                "tool": "cdp_click_coords",
                "x": x,
                "y": y,
                "double_click": double_click,
                "session_id": self.session.session_id,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "page": await self.session.page_info(),
            }
        except Exception as ex:
            return {
                "success": False,
                "tool": "cdp_click_coords",
                "error": str(ex),
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            }

    async def evaluate_js(
        self,
        *,
        fn: str,
        timeout_ms: Optional[int] = None,
    ) -> Dict[str, Any]:
        """对齐 OpenClaw act:evaluate — 在页面执行 JS（表达式或函数体）。"""
        t0 = time.perf_counter()
        code = (fn or "").strip()
        if not code:
            return {"success": False, "error": "evaluate 需要 fn"}
        try:
            page = self.session.page
            # 允许传箭头函数或表达式
            result = await page.evaluate(code)
            await self.session.touch()
            return {
                "success": True,
                "tool": "cdp_evaluate",
                "result": result,
                "session_id": self.session.session_id,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
                "page": await self.session.page_info(),
            }
        except Exception as ex:
            return {
                "success": False,
                "tool": "cdp_evaluate",
                "error": str(ex),
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            }

    async def resize_viewport(
        self,
        *,
        width: int,
        height: int,
    ) -> Dict[str, Any]:
        t0 = time.perf_counter()
        try:
            w = max(200, min(int(width), 3840))
            h = max(200, min(int(height), 2160))
            await self.session.page.set_viewport_size({"width": w, "height": h})
            await self.session.touch()
            return {
                "success": True,
                "tool": "cdp_resize",
                "width": w,
                "height": h,
                "session_id": self.session.session_id,
                "duration_ms": int((time.perf_counter() - t0) * 1000),
            }
        except Exception as ex:
            return {"success": False, "tool": "cdp_resize", "error": str(ex)}

    async def _locator_for_node(self, node: SnapshotNode):
        page = self.session.page
        if node.selector_hint:
            return page.locator(node.selector_hint).first
        role = (node.role or "generic").lower()
        name = node.name or None
        return page.get_by_role(role, name=name).first
