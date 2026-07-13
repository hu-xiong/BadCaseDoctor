# -*- coding: utf-8 -*-
"""CDP 测试/探测失败后自动 create 预览（Bug + 必要时迭代计划）。"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .evidence import format_ref_label
from .screenshot import capture_and_upload_cdp_screenshot, format_steps_html_with_screenshot


def cdp_auto_create_enabled() -> bool:
    return (os.getenv("CDP_AUTO_CREATE_ON_FAIL", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def interaction_explore_issues(issues: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    return [i for i in (issues or []) if str(i.get("type") or "") == "click_failed"]


def build_interaction_issue_create_fields(
    issue: Dict[str, Any],
    *,
    plan_id: Optional[int] = None,
    index: int = 0,
) -> Dict[str, Any]:
    """单个 CDP 交互问题 → Bug 卡片预览字段。"""
    label = format_ref_label(
        str(issue.get("ref") or ""),
        role=issue.get("role"),
        name=issue.get("name"),
    )
    name_part = str(issue.get("name") or issue.get("role") or label or "未知元素").strip()[:40]
    msg = str(issue.get("message") or "点击交互失败").strip()
    screenshot_url = str(issue.get("screenshot_url") or "").strip() or None
    steps = format_steps_html_with_screenshot(msg, screenshot_url, alt=f"交互问题截图-{index + 1}")
    fields: Dict[str, Any] = {
        "title": f"CDP交互问题-{index + 1}：{name_part}"[:80],
        "description": msg[:2000],
        "steps_to_reproduce": steps,
        "actual_result": msg[:1000],
        "expected_result": "元素应可正常点击交互",
    }
    url = str(issue.get("url_before") or "").strip()
    if url:
        fields["environment"] = url[:500]
    if plan_id is not None:
        try:
            fields["plan_id"] = int(plan_id)
        except (TypeError, ValueError):
            pass
    return fields


def build_interaction_issue_create_decision(
    issue: Dict[str, Any],
    *,
    project_id: int,
    plan_id: Optional[int] = None,
    index: int = 0,
) -> Dict[str, Any]:
    fields = build_interaction_issue_create_fields(issue, plan_id=plan_id, index=index)
    title = str(fields.get("title") or "").strip()
    return {
        "execute": True,
        "tool": "create",
        "params": {
            "target": "bug",
            "fields": fields,
            "project_id": int(project_id),
            "confirm": False,
            "natural_query": title[:500],
        },
        "reason": "CDP 探测发现交互问题，自动生成 Bug 卡片预览供确认",
    }


def _should_emit_create(observation: Dict[str, Any]) -> bool:
    if observation.get("assertion_failed") or observation.get("has_obvious_issues"):
        return True
    if observation.get("success") is False and observation.get("cdp_test_evidence"):
        return True
    return False


def build_create_decision_from_cdp_failure(
    observation: Dict[str, Any],
    *,
    project_id: Optional[int],
    plan_id: Optional[int] = None,
    result_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """由 cdp_test_evidence 构造 create 工具决策；已预览过则返回 None。"""
    if not cdp_auto_create_enabled():
        return None
    if isinstance(result_context, dict) and result_context.get("cdp_create_preview_emitted"):
        return None
    if not isinstance(observation, dict):
        return None
    if not _should_emit_create(observation):
        return None

    bundle = observation.get("cdp_test_evidence")
    if not isinstance(bundle, dict) or not bundle.get("test_failed"):
        return None
    if not project_id:
        return None

    fields = dict(bundle.get("suggested_create_fields") or {})
    if not fields.get("title"):
        return None

    effective_plan_id = plan_id
    if effective_plan_id is None and isinstance(result_context, dict):
        effective_plan_id = result_context.get("cdp_resolved_plan_id")

    if effective_plan_id is not None:
        try:
            fields.setdefault("plan_id", int(effective_plan_id))
        except (TypeError, ValueError):
            pass

    target = str(bundle.get("suggested_create_target") or "bug").strip().lower()
    if target not in ("bug", "badcase", "testcase", "card", "plan"):
        target = "bug"

    title = str(fields.get("title") or "").strip()
    return {
        "execute": True,
        "tool": "create",
        "params": {
            "target": target,
            "fields": fields,
            "project_id": int(project_id),
            "confirm": False,
            "natural_query": title[:500],
        },
        "reason": "CDP 测试/探测失败，自动生成缺陷预览供用户确认",
    }


def build_plan_create_decision(
    suggested: Dict[str, Any],
    *,
    project_id: int,
    result_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    if not cdp_auto_create_enabled():
        return None
    if isinstance(result_context, dict) and result_context.get("cdp_plan_create_preview_emitted"):
        return None
    if not isinstance(suggested, dict):
        return None
    fields = suggested.get("fields") or suggested
    if not isinstance(fields, dict) or not fields.get("name"):
        return None
    name = str(fields.get("name") or "").strip()
    return {
        "execute": True,
        "tool": "create",
        "params": {
            "target": "plan",
            "fields": dict(fields),
            "project_id": int(project_id),
            "confirm": False,
            "natural_query": name[:500],
        },
        "reason": "CDP 探测未发现可用迭代计划，自动生成本次测试迭代计划预览",
    }


async def run_create_preview_from_cdp_failure(
    engine: Any,
    observation: Dict[str, Any],
    *,
    project_id: Optional[int],
    plan_id: Optional[int] = None,
    result_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """执行 create 预览；成功返回 observation，否则 None。"""
    decision = build_create_decision_from_cdp_failure(
        observation,
        project_id=project_id,
        plan_id=plan_id,
        result_context=result_context,
    )
    if not decision:
        return None
    create_obs = await engine._execute_tool(decision)
    if not isinstance(create_obs, dict):
        return None
    if create_obs.get("success") and create_obs.get("confirmation_required"):
        if isinstance(result_context, dict):
            result_context["cdp_create_preview_emitted"] = True
            result_context["cdp_create_preview"] = create_obs
        return create_obs
    return None


async def run_plan_create_preview_if_needed(
    engine: Any,
    *,
    project_id: Optional[int],
    plan_resolution: Dict[str, Any],
    result_context: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """无有效迭代计划时先 create plan 预览。"""
    if not plan_resolution.get("needs_plan_create"):
        return None
    suggested = plan_resolution.get("suggested_plan_create")
    decision = build_plan_create_decision(
        suggested or {},
        project_id=int(project_id or 0),
        result_context=result_context,
    )
    if not decision or not project_id:
        return None
    plan_obs = await engine._execute_tool(decision)
    if not isinstance(plan_obs, dict):
        return None
    if plan_obs.get("success") and plan_obs.get("confirmation_required"):
        if isinstance(result_context, dict):
            result_context["cdp_plan_create_preview_emitted"] = True
            result_context["cdp_plan_create_preview"] = plan_obs
        return plan_obs
    return None


async def postprocess_cdp_failure_creates(
    engine: Any,
    observation: Dict[str, Any],
    *,
    project_id: Optional[int],
    plan_id: Optional[int] = None,
    result_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    CDP 失败后的 create 链：解析 plan → 必要时 plan 预览 → bug 预览。
    返回可能附加 cdp_plan_create_preview / cdp_create_preview 的 observation。
    """
    if not isinstance(observation, dict) or not _should_emit_create(observation):
        return observation

    plan_obs = None
    bug_obs = None
    try:
        from agents.cdp.plan_resolver import resolve_plan_for_cdp_issue

        db = getattr(engine, "db", None)
        resolved = resolve_plan_for_cdp_issue(
            project_id=project_id,
            plan_id=plan_id,
            db=db,
            auto_create_plan=True,
        )
        if isinstance(result_context, dict):
            if resolved.get("plan_id"):
                result_context["cdp_resolved_plan_id"] = resolved["plan_id"]
            if resolved.get("needs_plan_create"):
                plan_obs = await run_plan_create_preview_if_needed(
                    engine,
                    project_id=project_id,
                    plan_resolution=resolved,
                    result_context=result_context,
                )
                if plan_obs:
                    observation["cdp_plan_create_preview"] = plan_obs

        effective_plan = resolved.get("plan_id") or plan_id
        bug_obs = await run_create_preview_from_cdp_failure(
            engine,
            observation,
            project_id=project_id,
            plan_id=effective_plan,
            result_context=result_context,
        )
        if bug_obs:
            observation["cdp_create_preview"] = bug_obs
    except Exception:
        pass

    return observation


def _cdp_explore_interaction_create_limit() -> int:
    try:
        return max(1, min(20, int(os.getenv("CDP_EXPLORE_INTERACTION_CREATE_LIMIT", "8"))))
    except (TypeError, ValueError):
        return 8


def cdp_explore_auto_confirm() -> bool:
    """探测交互问题默认直接落库（当前对话项目下），不再仅生成不可见的预览。"""
    return (os.getenv("CDP_EXPLORE_AUTO_CONFIRM", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


async def _execute_cdp_create(
    engine: Any,
    decision: Dict[str, Any],
    *,
    confirm: bool,
    project_id: int,
) -> Dict[str, Any]:
    payload = dict(decision)
    params = dict(payload.get("params") or {})
    params["confirm"] = confirm
    params["project_id"] = int(project_id)
    payload["params"] = params
    obs = await engine._execute_tool(payload)
    return obs if isinstance(obs, dict) else {"success": False, "error": "create 无响应"}


async def postprocess_cdp_explore_interaction_creates(
    engine: Any,
    observation: Dict[str, Any],
    *,
    project_id: Optional[int],
    plan_id: Optional[int] = None,
    result_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    探测性测试 click_failed：在当前对话项目下创建迭代计划（如需）+ Bug 卡片。
    默认 confirm=true 直接落库，便于自测时在列表中看到记录。
    """
    if not cdp_auto_create_enabled() or not isinstance(observation, dict):
        return observation
    if observation.get("has_obvious_issues"):
        return observation
    if isinstance(result_context, dict) and result_context.get("cdp_interaction_creates_done"):
        return observation

    interaction = interaction_explore_issues(observation.get("exploration_issues"))
    if not interaction:
        return observation

    try:
        from agents.cdp.plan_resolver import (
            cdp_explore_force_new_plan,
            resolve_cdp_project_plan_ids,
            resolve_plan_for_cdp_issue,
        )

        pid, plid = resolve_cdp_project_plan_ids(
            project_id=project_id,
            plan_id=plan_id,
            engine=engine,
            result_context=result_context,
            observation=observation,
        )
        if not pid:
            observation["cdp_auto_create_skipped"] = "缺少 project_id，无法在当前项目下落库"
            return observation

        if isinstance(result_context, dict):
            result_context["project_id"] = pid

        confirm = cdp_explore_auto_confirm()
        db = getattr(engine, "db", None)
        plan_hint = None if cdp_explore_force_new_plan() else plid
        resolved = resolve_plan_for_cdp_issue(
            project_id=pid,
            plan_id=plan_hint,
            db=db,
            auto_create_plan=True,
        )
        effective_plan = resolved.get("plan_id")
        created_items: List[Dict[str, Any]] = []
        previews: List[Dict[str, Any]] = []

        if resolved.get("needs_plan_create"):
            plan_decision = build_plan_create_decision(
                resolved.get("suggested_plan_create") or {},
                project_id=int(pid),
                result_context=result_context if confirm else result_context,
            )
            if plan_decision:
                plan_obs = await _execute_cdp_create(
                    engine, plan_decision, confirm=confirm, project_id=int(pid)
                )
                if plan_obs.get("created_id"):
                    effective_plan = int(plan_obs["created_id"])
                    created_items.append({
                        "target": "plan",
                        "created_id": effective_plan,
                        "title": (plan_obs.get("fields") or {}).get("name"),
                        "observation": plan_obs,
                    })
                elif plan_obs.get("confirmation_required"):
                    observation["cdp_plan_create_preview"] = plan_obs
                    previews.append({"kind": "plan", "data": plan_obs})
                if isinstance(result_context, dict) and effective_plan:
                    result_context["cdp_resolved_plan_id"] = effective_plan

        if not effective_plan and isinstance(result_context, dict):
            effective_plan = result_context.get("cdp_resolved_plan_id")

        limit = _cdp_explore_interaction_create_limit()
        bug_previews: List[Dict[str, Any]] = []
        for idx, issue in enumerate(interaction[:limit]):
            decision = build_interaction_issue_create_decision(
                issue,
                project_id=int(pid),
                plan_id=effective_plan,
                index=idx,
            )
            bug_obs = await _execute_cdp_create(
                engine, decision, confirm=confirm, project_id=int(pid)
            )
            if bug_obs.get("created_id"):
                fields = bug_obs.get("fields") or decision["params"].get("fields") or {}
                created_items.append({
                    "target": "bug",
                    "created_id": bug_obs["created_id"],
                    "plan_id": effective_plan,
                    "title": fields.get("title"),
                    "observation": bug_obs,
                })
            elif bug_obs.get("success") and bug_obs.get("confirmation_required"):
                previews.append({"kind": "bug", "issue_index": idx, "data": bug_obs})
                bug_previews.append(bug_obs)

        if created_items:
            observation["cdp_auto_created"] = {
                "project_id": pid,
                "plan_id": effective_plan,
                "items": created_items,
            }
            observation["cdp_interaction_issues_recorded"] = sum(
                1 for x in created_items if x.get("target") == "bug"
            )
            n_bug = observation["cdp_interaction_issues_recorded"]
            plan_note = f"迭代计划 #{effective_plan}" if effective_plan else "迭代计划"
            observation["summary"] = (
                f"探测完成，已在当前项目 #{pid} 的{plan_note}下创建 {n_bug} 条 Bug 记录"
                f"（共发现 {len(interaction)} 个交互问题）"
            )[:2000]

        if previews:
            observation["cdp_create_previews"] = previews
            if bug_previews:
                observation["cdp_create_preview"] = bug_previews[0]
            observation["cdp_interaction_issue_previews"] = bug_previews
            if not created_items:
                observation["cdp_interaction_issues_recorded"] = len(bug_previews)

        if isinstance(result_context, dict):
            result_context["cdp_interaction_creates_done"] = True
    except Exception:
        pass

    return observation
