# -*- coding: utf-8 -*-
"""CDP 探测性测试：元素清单 → 深度优先遍历可点击元素。"""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

from .evidence import (
    CdpStepRecord,
    build_create_fields_from_failure,
    build_steps_to_reproduce,
    format_ref_label,
    get_cdp_evidence_recorder,
)
from .screenshot import capture_and_upload_cdp_screenshot, format_steps_html_with_screenshot
from .overlay import close_overlay, overlay_close_button_nodes, overlay_is_visible

if TYPE_CHECKING:
    from .session_manager import CdpSessionManager


_CLICKABLE_ROLES = frozenset({
    "button", "link", "tab", "menuitem", "menuitemcheckbox", "menuitemradio",
    "treeitem", "option", "switch", "checkbox", "radio",
})

_FILLABLE_ROLES = frozenset({
    "textbox", "searchbox", "combobox", "spinbutton",
})

_CDP_PROBE_FILL_TEXT = "cdp_probe"

_SKIP_NAME_KEYWORDS = (
    "删除", "注销", "logout", "sign out", "退出", "登出", "destroy", "remove",
)

_ERROR_TEXT_PATTERN = re.compile(
    r"错误|失败|异常|无法访问|not found|404|500|internal server|forbidden|unauthorized",
    re.I,
)


_SEVERE_ISSUE_TYPES = frozenset({"error_url", "error_text", "error_title"})


def severe_explore_issues(issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """页面级明显错误；click_failed 等交互问题不算严重。"""
    return [i for i in issues if str(i.get("type") or "") in _SEVERE_ISSUE_TYPES]


def cdp_explore_max_depth() -> int:
    try:
        return max(1, int(os.getenv("CDP_EXPLORE_MAX_DEPTH", "2")))
    except (TypeError, ValueError):
        return 2


def cdp_explore_max_clicks() -> int:
    try:
        return max(1, int(os.getenv("CDP_EXPLORE_MAX_CLICKS", "15")))
    except (TypeError, ValueError):
        return 15


def filter_explorable_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """从快照节点中筛出适合 DFS 探测的可点击元素。"""
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        if n.get("disabled"):
            continue
        role = str(n.get("role") or "").lower()
        if role not in _CLICKABLE_ROLES:
            continue
        ref = str(n.get("ref") or "").strip()
        if not ref or ref in seen:
            continue
        name = str(n.get("name") or "").strip()
        name_l = name.lower()
        if any(k in name_l or k in name for k in _SKIP_NAME_KEYWORDS):
            continue
        seen.add(ref)
        out.append(n)
    return out


def filter_fillable_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """可填写输入框（含弹窗内）。"""
    out: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        if n.get("disabled"):
            continue
        role = str(n.get("role") or "").lower()
        if role not in _FILLABLE_ROLES:
            continue
        ref = str(n.get("ref") or "").strip()
        if not ref or ref in seen:
            continue
        seen.add(ref)
        out.append(n)
    return out


def build_element_inventory(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    explorable = filter_explorable_nodes(nodes)
    return [
        {
            "ref": n.get("ref"),
            "role": n.get("role"),
            "name": n.get("name"),
            "disabled": n.get("disabled"),
        }
        for n in explorable
    ]


def _issue_from_click_failure(
    *,
    ref: str,
    node: Dict[str, Any],
    click_res: Dict[str, Any],
    before_url: str,
    before_title: str,
) -> Dict[str, Any]:
    err = str(
        click_res.get("message") or click_res.get("error") or "点击失败"
    ).strip()
    role = node.get("role") or click_res.get("role")
    name = node.get("name") or click_res.get("name")
    screenshot_url = click_res.get("screenshot_url")
    label = format_ref_label(ref, role=role, name=name)
    return {
        "type": "click_failed",
        "ref": ref,
        "role": role,
        "name": name,
        "screenshot_url": screenshot_url,
        "message": f"点击 {label} 失败：{err}" if label else f"点击失败：{err}",
        "url_before": before_url,
        "title_before": before_title,
        "url_after": before_url,
        "severity": "low",
    }


async def _detect_obvious_page_issue(page: Any, *, before_url: str) -> Optional[Dict[str, Any]]:
    """检测点击后页面是否出现明显错误信号。"""
    try:
        url = page.url
        title = await page.title()
    except Exception:
        return None

    if url != before_url:
        if _ERROR_TEXT_PATTERN.search(url):
            return {
                "type": "error_url",
                "message": f"导航至疑似错误 URL：{url[:200]}",
                "url_before": before_url,
                "url_after": url,
                "title_after": title,
                "severity": "high",
            }

    try:
        body = page.locator("body")
        text = (await body.inner_text(timeout=3000))[:4000]
    except Exception:
        text = ""

    if text and _ERROR_TEXT_PATTERN.search(text):
        snippet = _ERROR_TEXT_PATTERN.search(text)
        matched = snippet.group(0) if snippet else "错误"
        return {
            "type": "error_text",
            "message": f"页面含明显错误文案：{matched}",
            "url_before": before_url,
            "url_after": url,
            "title_after": title,
            "text_snippet": text[:300],
            "severity": "medium",
        }

    if title and _ERROR_TEXT_PATTERN.search(title):
        return {
            "type": "error_title",
            "message": f"页面标题含错误：{title[:120]}",
            "url_before": before_url,
            "url_after": url,
            "title_after": title,
            "severity": "medium",
        }
    return None


def _attach_explore_evidence(
    observation: Dict[str, Any],
    *,
    records: List[CdpStepRecord],
    issues: List[Dict[str, Any]],
    user_query: Optional[str] = None,
) -> Dict[str, Any]:
    observation["exploration_issues"] = issues
    observation["issues_found"] = len(issues)
    severe = severe_explore_issues(issues)
    observation["exploration_severe_issues"] = severe

    if not severe:
        if issues:
            lines = [
                f"{idx + 1}. {str(issue.get('message') or '')[:180]}"
                for idx, issue in enumerate(issues)
            ]
            observation["exploration_issues_summary"] = "\n".join(lines)
            observation["summary"] = (
                f"探测完成，发现 {len(issues)} 个交互问题（已继续完成探测）：\n"
                + observation["exploration_issues_summary"]
            )[:2000]
        return observation

    primary = severe[0]
    failure_obs = {
        "success": False,
        "assertion_failed": True,
        "message": primary.get("message") or "探测发现明显问题",
        "page": {
            "url": primary.get("url_after") or primary.get("url_before") or "",
            "title": primary.get("title_after") or "",
        },
        "session_id": observation.get("session_id"),
    }
    fields = build_create_fields_from_failure(
        failure_obs,
        records,
        user_query=user_query,
    )
    shot_by_msg: Dict[str, str] = {}
    for i in issues:
        msg = str(i.get("message") or "").strip()
        url = str(i.get("screenshot_url") or "").strip()
        if msg and url:
            shot_by_msg[msg] = url
    steps_base = str(fields.get("steps_to_reproduce") or "")
    if shot_by_msg:
        extra_shots = []
        for msg, url in list(shot_by_msg.items())[:5]:
            extra_shots.append(format_steps_html_with_screenshot(msg, url, alt="探测失败截图"))
        fields["steps_to_reproduce"] = (steps_base + "\n" + "\n".join(extra_shots)).strip()[:8000]
    fields["description"] = (
        f"探测性测试发现 {len(severe)} 个页面级问题（共记录 {len(issues)} 项）。\n"
        + "\n".join(f"- [{i.get('type')}] {i.get('message', '')[:200]}" for i in severe[:5])
    )[:2000]
    observation["has_obvious_issues"] = True
    observation["cdp_test_evidence"] = {
        "session_id": observation.get("session_id"),
        "test_failed": True,
        "failed_at_action": "explore",
        "issues": severe,
        "all_exploration_issues": issues,
        "steps_to_reproduce": fields.get("steps_to_reproduce"),
        "actual_result": fields.get("actual_result"),
        "expected_result": "页面交互应正常，无错误提示或点击失败",
        "step_log": [r.to_dict() for r in records],
        "suggested_create_fields": fields,
        "suggested_create_target": "bug",
    }
    observation["cdp_steps_preview"] = fields.get("steps_to_reproduce", "")[:3000]
    observation["summary"] = primary.get("message") or "探测发现明显问题"
    return observation


async def run_exploration(
    mgr: "CdpSessionManager",
    session_id: str,
    *,
    phase: str = "full",
    max_depth: Optional[int] = None,
    max_clicks: Optional[int] = None,
    owner_key: Optional[str] = None,
    user_query: Optional[str] = None,
) -> Dict[str, Any]:
    """
    探测性测试主入口。

    phase:
      - inventory: 仅 snapshot 并返回可交互元素清单
      - dfs: 在当前页深度优先点击探测（需已有会话）
      - full: inventory + dfs
    """
    phase = (phase or "full").strip().lower()
    if phase not in ("inventory", "dfs", "full"):
        return {"success": False, "error": f"未知 phase: {phase}"}

    session = mgr.get_session(session_id, owner_key=owner_key)
    if not session:
        return {"success": False, "error": f"会话不存在: {session_id}"}

    from .page_ready import is_project_detail_url, wait_for_project_detail_ready

    page = session.page
    try:
        cur_url = page.url or ""
    except Exception:
        cur_url = ""
    if is_project_detail_url(cur_url):
        await wait_for_project_detail_ready(page, timeout_ms=8000)
    elif "project-detail" in cur_url.lower() or "#/project" in cur_url.lower():
        await wait_for_project_detail_ready(page, timeout_ms=8000)

    t0 = time.perf_counter()
    depth_limit = max_depth if max_depth is not None else cdp_explore_max_depth()
    click_limit = max_clicks if max_clicks is not None else cdp_explore_max_clicks()

    snap = await mgr.snapshot(session_id, scope="interactive", owner_key=owner_key)
    if not snap.get("success"):
        return snap

    nodes = snap.get("nodes") or []
    inventory = build_element_inventory(nodes)
    recorder = get_cdp_evidence_recorder()
    recorder.reset(session_id)

    recorder.record(
        session_id,
        "snapshot",
        {"scope": "interactive", "session_id": session_id},
        snap,
    )

    if phase == "inventory":
        dur = int((time.perf_counter() - t0) * 1000)
        return {
            "success": True,
            "action": "explore",
            "tool": "cdp_explore",
            "phase": "inventory",
            "session_id": session_id,
            "snapshot_id": snap.get("snapshot_id"),
            "element_count": len(inventory),
            "element_inventory": inventory,
            "truncated": snap.get("truncated"),
            "page": snap.get("page") or {"url": snap.get("url"), "title": snap.get("title")},
            "duration_ms": dur,
            "hint": "元素清单已就绪；继续 action=explore phase=dfs 或 phase=full 进行深度优先探测",
        }

    actor = mgr.actor(session_id, owner_key=owner_key)
    page = session.page
    issues: List[Dict[str, Any]] = []
    clicks = 0
    fills = 0
    visited_refs: Set[str] = set()
    visited_fill_refs: Set[str] = set()

    async def _record(action: str, params: Dict[str, Any], obs: Dict[str, Any]) -> None:
        recorder.record(session_id, action, params, obs)

    async def _try_go_back(before_url: str) -> None:
        if page.url == before_url:
            return
        try:
            await page.go_back(wait_until="domcontentloaded", timeout=8000)
            await asyncio.sleep(0.2)
            await mgr.snapshot(session_id, scope="interactive", owner_key=owner_key)
        except Exception:
            try:
                await page.goto(before_url, wait_until="domcontentloaded", timeout=10000)
                await mgr.snapshot(session_id, scope="interactive", owner_key=owner_key)
            except Exception:
                pass

    async def _explore_overlay_if_open(depth: int) -> None:
        """弹窗已打开时：在 overlay 内继续 DFS，再关闭弹窗。"""
        if not await overlay_is_visible(page):
            return
        if depth < depth_limit:
            await dfs(depth + 1, page.url)
        modal_snap = await mgr.snapshot(session_id, scope="interactive", owner_key=owner_key)
        closed = False
        if modal_snap.get("success"):
            for cn in overlay_close_button_nodes(filter_explorable_nodes(modal_snap.get("nodes") or []))[:2]:
                if clicks >= click_limit:
                    break
                cr = await actor.click(ref=str(cn.get("ref") or ""), snapshot_id=modal_snap.get("snapshot_id"))
                clicks += 1
                await _record(
                    "click",
                    {"ref": cn.get("ref"), "role": cn.get("role"), "name": cn.get("name"), "overlay_close": True},
                    cr,
                )
                await asyncio.sleep(0.2)
                if not await overlay_is_visible(page):
                    closed = True
                    break
        if not closed:
            await close_overlay(page)
        await asyncio.sleep(0.2)

    async def _probe_fillables(snap_id: Optional[str]) -> None:
        nonlocal fills
        cur_snap = await mgr.snapshot(session_id, scope="interactive", owner_key=owner_key)
        if not cur_snap.get("success"):
            return
        sid = snap_id or cur_snap.get("snapshot_id")
        for node in filter_fillable_nodes(cur_snap.get("nodes") or []):
            ref = str(node.get("ref") or "")
            if not ref or ref in visited_fill_refs:
                continue
            visited_fill_refs.add(ref)
            fill_res = await actor.fill(
                ref=ref,
                text=_CDP_PROBE_FILL_TEXT,
                snapshot_id=sid,
            )
            fills += 1
            await _record(
                "fill",
                {"ref": ref, "role": node.get("role"), "name": node.get("name"), "session_id": session_id},
                fill_res,
            )
            if not fill_res.get("success"):
                issues.append({
                    "type": "fill_failed",
                    "ref": ref,
                    "role": node.get("role"),
                    "name": node.get("name"),
                    "message": str(fill_res.get("message") or fill_res.get("error") or "填写失败"),
                    "severity": "low",
                })

    async def dfs(depth: int, start_url: str) -> None:
        nonlocal clicks
        if depth > depth_limit or clicks >= click_limit:
            return

        cur_snap = await mgr.snapshot(session_id, scope="interactive", owner_key=owner_key)
        if not cur_snap.get("success"):
            return
        await _probe_fillables(cur_snap.get("snapshot_id"))
        for node in filter_explorable_nodes(cur_snap.get("nodes") or []):
            if clicks >= click_limit:
                return
            ref = str(node.get("ref") or "")
            visit_key = f"{page.url}|{ref}"
            if visit_key in visited_refs:
                continue
            visited_refs.add(visit_key)

            before_url = page.url
            try:
                before_title = await page.title()
            except Exception:
                before_title = ""

            overlay_before = await overlay_is_visible(page)

            click_res = await actor.click(
                ref=ref,
                snapshot_id=cur_snap.get("snapshot_id"),
            )
            clicks += 1
            await _record(
                "click",
                {
                    "ref": ref,
                    "role": node.get("role"),
                    "name": node.get("name"),
                    "session_id": session_id,
                    "explore_depth": depth,
                },
                click_res,
            )

            overlay_after = await overlay_is_visible(page)
            if not click_res.get("success") and overlay_after and not overlay_before:
                click_res = dict(click_res)
                click_res["success"] = True
                click_res["click_recovered"] = "overlay_opened"

            if not click_res.get("success"):
                issues.append(
                    _issue_from_click_failure(
                        ref=ref,
                        node=node,
                        click_res=click_res,
                        before_url=before_url,
                        before_title=before_title,
                    )
                )
                continue

            await asyncio.sleep(0.35)

            if overlay_after or await overlay_is_visible(page):
                await _explore_overlay_if_open(depth)
                continue

            page_issue = await _detect_obvious_page_issue(page, before_url=before_url)
            if page_issue:
                try:
                    shot = await capture_and_upload_cdp_screenshot(
                        page,
                        session_id=session_id,
                        tag=str(node.get("ref") or "page_issue"),
                    )
                    if shot:
                        page_issue["screenshot_url"] = shot
                except Exception:
                    pass
                page_issue["ref"] = ref
                page_issue["role"] = node.get("role")
                page_issue["name"] = node.get("name")
                issues.append(page_issue)
                await _try_go_back(before_url)
                continue

            after_url = page.url
            if after_url != before_url and depth < depth_limit:
                await dfs(depth + 1, after_url)
                await _try_go_back(before_url)

    await dfs(0, page.url)

    dur = int((time.perf_counter() - t0) * 1000)
    records = recorder.get_records(session_id)
    out: Dict[str, Any] = {
        "success": True,
        "action": "explore",
        "tool": "cdp_explore",
        "phase": phase,
        "session_id": session_id,
        "snapshot_id": snap.get("snapshot_id"),
        "element_count": len(inventory),
        "element_inventory": inventory,
        "exploration_clicks": clicks,
        "exploration_fills": fills,
        "exploration_depth_limit": depth_limit,
        "issues_found": len(issues),
        "exploration_issues": issues,
        "exploration_severe_issues": severe_explore_issues(issues),
        "has_obvious_issues": bool(severe_explore_issues(issues)),
        "cdp_step_count": len(records),
        "cdp_steps_preview": build_steps_to_reproduce(records)[:3000],
        "page": await session.page_info(),
        "duration_ms": dur,
    }
    if issues:
        out = _attach_explore_evidence(out, records=records, issues=issues, user_query=user_query)
        if severe_explore_issues(issues):
            out["success"] = False
        else:
            out["success"] = True
    return out
