# -*- coding: utf-8 -*-
"""Midscene 执行桥：Python 调用 agents/midscene_runner/smoke.mjs。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_RUNNER_DIR = Path(__file__).resolve().parents[1] / "midscene_runner"
_SMOKE_JS = _RUNNER_DIR / "smoke.mjs"
_GREMLINS_JS = _RUNNER_DIR / "gremlins_monkey.mjs"


def explore_engine() -> str:
    """combined | midscene | legacy | auto（默认 midscene：只跑 Midscene 智能巡检）。

    Gremlins 猴子测试默认关闭（耗时 60s 且产出边际价值低）；
    需要稳定性回归/排查偶发崩溃时设 CDP_EXPLORE_ENGINE=combined 启用。
    """
    return (os.getenv("CDP_EXPLORE_ENGINE", "midscene") or "midscene").strip().lower()


def midscene_model_configured() -> bool:
    key = (os.getenv("MIDSCENE_MODEL_API_KEY") or "").strip()
    name = (os.getenv("MIDSCENE_MODEL_NAME") or "").strip()
    return bool(key and name)


def midscene_runner_ready() -> bool:
    if not _SMOKE_JS.is_file():
        return False
    node_modules = _RUNNER_DIR / "node_modules" / "@midscene" / "web"
    return node_modules.is_dir()


# ---- Midscene 实时进度：stderr → Python → 引擎 progress_queue 的行前缀协议 ----
CDP_STEP_PROGRESS_PREFIX = "__CDP_STEP__"   # 前缀 + JSON（结构化步骤快照）
CDP_TEXT_PROGRESS_PREFIX = "__CDP_TEXT__"   # 前缀 + 文本（阶段进度提示）

# 动作英文名 → 中文标签（实时进度与最终子步骤共用）
_ACTION_LABEL = {
    "tap": "点击",
    "click": "点击",
    "input": "输入",
    "scroll": "滚动",
    "hover": "悬停",
    "navigate": "导航",
    "select": "选择",
    "type": "输入",
    "press": "按键",
    "doubleclick": "双击",
    "rightclick": "右击",
}


def _push_cdp_progress(progress_queue: Any, prefix: str, payload: Any) -> None:
    """把一条实时进度放进引擎侧队列（未注入队列时静默跳过）。"""
    if progress_queue is None:
        return
    try:
        if isinstance(payload, str):
            progress_queue.put_nowait(prefix + payload)
        else:
            progress_queue.put_nowait(prefix + json.dumps(payload, ensure_ascii=False))
    except Exception:
        pass


def _sanitize_midscene_step(step: Dict[str, Any]) -> None:
    """剥离大字段（如 base64 截图），防止 SSE / 日志载荷爆炸。"""
    data = step.get("data")
    if not isinstance(data, dict):
        return
    for key in ("screenshot", "screenshots", "image", "imageBase64"):
        value = data.get(key)
        if isinstance(value, str) and len(value) > 2048:
            data.pop(key, None)


def _midscene_action_info(data: Dict[str, Any]) -> Dict[str, Any]:
    """从事件 data 提取动作信息 → {action, target, description}。"""
    action = data.get("action") if isinstance(data.get("action"), dict) else {}
    name = str(action.get("name") or "").strip()
    target = str(action.get("target") or "").strip()
    label = _ACTION_LABEL.get(name.lower(), name or "操作")
    desc = f'{label}"{target}"' if target else label
    return {"action": label, "target": target, "description": desc}


class _MidsceneLiveTracker:
    """把 Midscene [step] 事件累积成前端可渲染的「意图分组 + 动作行」结构。

    行类型：
    - kind=plan   ：一轮规划的意图标题行（plan_thinking → plan_planned 原地更新）
    - kind=action ：具体动作行（plan_action 新增，action_done/action_failed 原地收口）
    - kind=result ：整体完成行（complete）
    """

    _MAX_ROWS = 240
    _THOUGHT_MAX = 180

    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    def snapshot(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self.rows]

    def _find_plan_row(self, plan_index: Optional[int]) -> Optional[Dict[str, Any]]:
        for row in reversed(self.rows):
            if row.get("kind") == "plan" and row.get("plan_index") == plan_index:
                return row
        return None

    def _upsert_plan_row(
        self,
        plan_index: Optional[int],
        *,
        status: str,
        icon: str,
        description: str,
    ) -> None:
        row = self._find_plan_row(plan_index)
        if row is None:
            row = {"kind": "plan", "plan_index": plan_index}
            self.rows.append(row)
        row.update({"status": status, "icon": icon, "description": description})

    def _finish_last_action(
        self,
        plan_index: Optional[int],
        status: str,
        *,
        duration_ms: Any = None,
        error: str = "",
    ) -> bool:
        for row in reversed(self.rows):
            if (
                row.get("kind") == "action"
                and row.get("plan_index") == plan_index
                and row.get("status") == "running"
            ):
                row["status"] = status
                row["icon"] = "✓" if status == "done" else "✗"
                if isinstance(duration_ms, (int, float)) and duration_ms >= 0:
                    row["duration_ms"] = int(duration_ms)
                    row["description"] = (
                        f'{row.get("description") or ""}（{max(1, int(duration_ms / 1000))}s）'
                    )
                if status == "error" and error:
                    row["description"] = f'{row.get("description") or ""}：{error[:160]}'
                return True
        return False

    def apply(self, step: Dict[str, Any]) -> bool:
        """处理一条 [step] 事件；返回 True 表示行有变化。"""
        if not isinstance(step, dict):
            return False
        phase = str(step.get("phase") or "").strip()
        data = step.get("data") if isinstance(step.get("data"), dict) else {}
        raw_pi = data.get("planIndex")
        try:
            plan_index = int(raw_pi) if raw_pi is not None else None
        except (TypeError, ValueError):
            plan_index = None

        if phase == "plan_thinking":
            self._upsert_plan_row(plan_index, status="thinking", icon="💭", description="规划中…")
            return True
        if phase == "plan_planned":
            thought = str(data.get("thought") or data.get("log") or "").strip()
            if len(thought) > self._THOUGHT_MAX:
                thought = thought[: self._THOUGHT_MAX] + "…"
            self._upsert_plan_row(
                plan_index, status="done", icon="🎯", description=thought or "规划完成"
            )
            return True
        if phase == "plan_action":
            if plan_index is not None and self._find_plan_row(plan_index) is None:
                self._upsert_plan_row(
                    plan_index, status="done", icon="🎯", description="执行计划"
                )
            self.rows.append(
                {
                    "kind": "action",
                    "plan_index": plan_index,
                    "status": "running",
                    "icon": "▶",
                    **_midscene_action_info(data),
                }
            )
            if len(self.rows) > self._MAX_ROWS:
                del self.rows[: len(self.rows) - self._MAX_ROWS]
            return True
        if phase == "action_running":
            return False  # 与 plan_action 同时双发，避免重复行
        if phase == "action_done":
            return self._finish_last_action(plan_index, "done", duration_ms=data.get("durationMs"))
        if phase == "action_failed":
            return self._finish_last_action(
                plan_index,
                "error",
                duration_ms=data.get("durationMs"),
                error=str(data.get("error") or "").strip(),
            )
        if phase == "plan_failed":
            err = str(data.get("error") or "").strip()
            self._upsert_plan_row(
                plan_index,
                status="error",
                icon="⚠️",
                description=f"规划失败：{err[:160]}" if err else "规划失败",
            )
            return True
        if phase == "complete":
            out = str(data.get("output") or "").strip()
            if len(out) > self._THOUGHT_MAX:
                out = out[: self._THOUGHT_MAX] + "…"
            self.rows.append(
                {
                    "kind": "result",
                    "plan_index": plan_index,
                    "status": "done",
                    "icon": "🏁",
                    "description": f"巡检执行完成：{out}" if out else "巡检执行完成",
                }
            )
            return True
        return False


def _format_midscene_action_steps(
    raw_steps: Any,
) -> List[Dict[str, str]]:
    """将 Midscene execution_steps 转为前端可渲染的子步骤数组（无实时追踪时的兜底）。"""
    if not isinstance(raw_steps, list):
        return []
    out: List[Dict[str, str]] = []
    for step in raw_steps:
        if not isinstance(step, dict):
            continue
        phase = str(step.get("phase") or "").strip()
        data = step.get("data") or {}
        action = data.get("action") or {}
        action_name = str(action.get("name") or "").strip() if isinstance(action, dict) else str(action)
        target_raw = action.get("target") if isinstance(action, dict) else None
        target_text = ""
        if isinstance(target_raw, dict):
            target_text = str(target_raw.get("text") or target_raw.get("name") or "").strip()
        elif isinstance(target_raw, str):
            target_text = target_raw

        action_label = _ACTION_LABEL.get(action_name.lower(), action_name)
        desc = action_label
        if target_text:
            desc = f"{action_label}\"{target_text}\""

        # 根据 phase 映射成前端状态
        if phase == "action_done":
            status = "done"
            icon = "✓"
        elif phase == "action_failed":
            status = "error"
            icon = "✗"
        elif phase == "action_running":
            status = "running"
            icon = "⋯"
        elif phase == "plan_action":
            status = "pending"
            icon = "→"
        elif phase == "plan_thinking":
            status = "thinking"
            icon = "💭"
        else:
            status = phase
            icon = "·"

        out.append({
            "icon": icon,
            "status": status,
            "action": action_label,
            "target": target_text,
            "description": desc,
        })
    return out


def gremlins_runner_ready() -> bool:
    if not _GREMLINS_JS.is_file():
        return False
    gremlins_dist = _RUNNER_DIR / "node_modules" / "gremlins.js" / "dist" / "gremlins.min.js"
    return gremlins_dist.is_file()


def default_smoke_goal(user_query: str = "") -> str:
    q = (user_query or "").strip()
    base = (
        "你是一名认真的手工测试同学。请像正常人一样先把这个 Web 系统的主要界面功能走一遍："
        "若出现隐私政策/协议/Cookie 弹窗，先点击「同意」/「接受」；"
        "确认页面可打开；浏览导航/侧栏/Tab；空状态则尝试新建并保存主业务对象；"
        "尝试搜索/筛选/打开详情；不要点删除/注销/退出；日期与下拉用正常点选。"
        "若页面要求登录而无法登录，如实说明被登录阻塞，不要虚构已测内容；"
        "遇到登录页不要猜测或输入任何账号密码、不要注册新账号，"
        "记录当前已测内容后尽快结束探索并报告被登录阻塞（系统会自动处理登录）。"
        "最后停留在可观察结果的页面。"
    )
    if q:
        return f"{base}\n用户补充意图：{q[:500]}"
    return base


def map_midscene_result_to_explore_observation(raw: Dict[str, Any], *, url: str = "") -> Dict[str, Any]:
    """把 runner JSON 映射为与 legacy explore 兼容的 observation 字段。"""
    if not isinstance(raw, dict):
        return {
            "success": False,
            "engine": "midscene",
            "error": "invalid midscene result",
            "fallback_legacy": True,
        }

    if raw.get("fallback_legacy"):
        return {
            "success": False,
            "engine": "midscene",
            "error": raw.get("error") or "midscene unavailable",
            "fallback_legacy": True,
            "message": raw.get("error"),
        }

    failed = raw.get("failed") if isinstance(raw.get("failed"), list) else []
    passed = raw.get("passed") if isinstance(raw.get("passed"), list) else []
    tested = raw.get("tested_flows") if isinstance(raw.get("tested_flows"), list) else []
    blocking = bool(raw.get("has_blocking_bug"))
    raw_error = str(raw.get("error") or "").strip()
    # 中断场景（超时/异常）没有结构化台账，但流式收集的 execution_steps 里可能已有真实动作，
    # 用于区分「AI 完全没动」与「跑了一半被打断」，避免把后者误报为「未测到任何操作」
    _exec_steps = raw.get("execution_steps") if isinstance(raw.get("execution_steps"), list) else []
    action_done_cnt = sum(
        1
        for s in _exec_steps
        if isinstance(s, dict) and str(s.get("phase") or "") == "action_done"
    )
    issues: List[Dict[str, Any]] = []
    for item in failed:
        if isinstance(item, dict):
            step = str(item.get("step") or "操作失败")
            reason = str(item.get("reason") or "")
            msg = f"{step}：{reason}".strip("：")
        else:
            msg = str(item)
        issues.append(
            {
                "type": "midscene_failed",
                "message": msg[:500],
                "severity": "high" if blocking else "medium",
            }
        )

    # success 语义 = 巡检「有效完成」；failed 列表是巡检产出（发现的失败点），
    # 不再因存在非阻塞 failed 项而否决整次巡检（是否阻塞由 has_blocking_bug 单独表达）
    success = bool(raw.get("success")) and not blocking and not raw_error
    report_missing = bool(raw.get("report_missing"))
    # AI 未留下任何可核实的巡检动作（无已测/通过/失败，且执行步骤里也没有完成的动作）时，不能自称完成
    no_progress = (not tested) and (not passed) and (not failed) and action_done_cnt == 0
    if no_progress:
        if success:
            success = False
        if not any(str(i.get("type")) == "midscene_no_progress" for i in issues):
            issues.append(
                {
                    "type": "midscene_no_progress",
                    "message": "Midscene 未测到任何入口（可能被隐私弹窗/登录/加载异常阻塞），本次巡检未有效开展",
                    "severity": "low",
                }
            )

    # 弹窗二次校验：AI agent 执行后隐私弹窗仍可见 → 报告很可能是 AI 幻觉，降级处理
    consent_check = raw.get("consent_post_check") if isinstance(raw.get("consent_post_check"), dict) else {}
    modal_still_visible = bool(consent_check.get("modal_still_visible"))
    if modal_still_visible:
        success = False
        blocking = True
        issues.append(
            {
                "type": "midscene_consent_blocked",
                "message": "隐私政策/协议弹窗未关闭，AI agent 未成功点击「同意」，后续报告可能为幻觉，需人工确认",
                "severity": "high",
            }
        )

    summary = str(raw.get("summary") or "").strip()
    if not summary:
        parts = [
            "Midscene 界面巡检已完成。" if success else "Midscene 界面巡检未完成。",
            f"页面：{raw.get('url') or url or ''}",
            f"已测入口 {len(tested)} 个，通过 {len(passed)}，失败 {len(failed)}。",
        ]
        if raw_error and not raw.get("fallback_legacy"):
            parts.append(f"原因：{raw_error[:600]}")
        if no_progress and not success:
            parts.append("未测到任何有效操作：页面可能被隐私弹窗、登录或加载错误阻塞，请人工确认。")
        elif action_done_cnt and not (tested or passed or failed):
            parts.append(
                f"巡检中断前已执行 {action_done_cnt} 步页面操作（结构化汇总缺失），结果可能不完整。"
            )
        if tested:
            parts.append("已测：" + "；".join(str(x) for x in tested[:8]))
        if passed:
            parts.append("通过：" + "；".join(str(x) for x in passed[:8]))
        if failed:
            parts.append("失败：" + "；".join(
                (f"{i.get('step')}:{i.get('reason')}" if isinstance(i, dict) else str(i))
                for i in failed[:5]
            ))
        summary = "\n".join(parts)

    # 失败原因准确化：避免上游把失败一律呈报为「未测到任何入口/被弹窗阻塞」之类的误导话术
    out_error = raw_error
    if not out_error and not success:
        if modal_still_visible:
            out_error = "隐私政策/协议弹窗未关闭，巡检未能有效开展"
        elif blocking:
            out_error = "Midscene 巡检发现阻塞性缺陷，主流程无法正常推进"
        elif no_progress:
            out_error = (
                "Midscene 未测到任何有效操作记录（可能被隐私弹窗/登录/加载异常阻塞），"
                "本次巡检未有效开展"
            )
        elif report_missing:
            out_error = "Midscene 未能生成结构化巡检报告（AI 报告缺失），本次巡检结果不可用"

    out: Dict[str, Any] = {
        "success": success,
        "engine": "midscene",
        "action": "explore",
        "phase": "midscene_smoke",
        "summary": summary[:2000],
        "tested_flows": tested,
        "passed": passed,
        "failed": failed,
        "has_blocking_bug": blocking,
        "has_obvious_issues": blocking or any(
            str(i.get("severity")) == "high" for i in issues
        ),
        "exploration_issues": issues,
        "issues_found": len(issues),
        "element_count": len(tested) or len(passed),
        "exploration_clicks": None,
        "exploration_fills": None,
        "midscene_report_file": raw.get("report_file") or "",
        "empty_state_seen": bool(raw.get("empty_state_seen")),
        "http_status": raw.get("http_status"),
        "consent_dismissed": raw.get("consent_dismissed") or [],
        "consent_post_check": raw.get("consent_post_check") if isinstance(raw.get("consent_post_check"), dict) else {},
        "execution_steps": raw.get("execution_steps") if isinstance(raw.get("execution_steps"), list) else [],
        # 优先用实时追踪器产出的「意图分组 + 动作行」；无法实时跟踪时回退到逐事件展开
        "midscene_action_steps": (
            raw.get("midscene_action_steps")
            if isinstance(raw.get("midscene_action_steps"), list) and raw.get("midscene_action_steps")
            else _format_midscene_action_steps(raw.get("execution_steps"))
        ),
        "duration_ms": raw.get("duration_ms"),
        "page": {
            "url": raw.get("url") or url,
            "title": raw.get("page_title") or "",
        },
        "error": out_error or None,
        "message": (out_error or summary)[:500],
    }
    if issues and (blocking or out["has_obvious_issues"]):
        actual = "\n".join(str(i.get("message") or "") for i in issues)[:2000]
        out["cdp_test_evidence"] = {
            "test_failed": True,
            "failed_at_action": "midscene_explore",
            "issues": issues,
            "steps_to_reproduce": summary[:3000],
            "actual_result": actual,
            "expected_result": "主界面功能可正常使用，无阻塞性错误",
            "suggested_create_target": "bug",
            "suggested_create_fields": {
                "title": (issues[0].get("message") or "Midscene 巡检失败")[:120],
                "description": summary[:2000],
                "steps_to_reproduce": summary[:3000],
                "actual_result": actual,
                "expected_result": "主界面功能可正常使用，无阻塞性错误",
            },
        }
    return out


def map_gremlins_result_to_explore_observation(raw: Dict[str, Any], *, url: str = "") -> Dict[str, Any]:
    """把 Gremlins runner JSON 映射为与 explore 兼容的 observation 字段。"""
    if not isinstance(raw, dict):
        return {
            "success": False,
            "engine": "gremlins",
            "error": "invalid gremlins result",
        }

    issues: List[Dict[str, Any]] = []
    for item in (raw.get("exploration_issues") or []):
        if isinstance(item, dict):
            issues.append(item)
        else:
            issues.append({
                "type": "gremlins_issue",
                "message": str(item)[:500],
                "severity": "medium",
            })

    blocking = bool(raw.get("has_blocking_bug"))
    console_errs = int(raw.get("console_errors") or 0)
    page_errs = int(raw.get("page_errors") or 0)
    actions = int(raw.get("actions_count") or 0)
    raw_error = str(raw.get("error") or "").strip()
    success = (
        bool(raw.get("success")) and not raw_error
        if not (blocking or page_errs > 0)
        else False
    )
    summary = str(raw.get("summary") or "").strip()
    if not summary:
        if raw_error:
            summary = f"Gremlins 猴子测试未完成：{raw_error[:800]}"
        else:
            summary = (
                f"Gremlins 猴子测试完成。"
                f"{actions} 次随机操作，页面错误 {page_errs} 个，"
                f"控制台错误 {console_errs} 个。"
            )

    out: Dict[str, Any] = {
        "success": success,
        "engine": "gremlins",
        "action": "explore",
        "phase": "gremlins_monkey",
        "summary": summary[:2000],
        "tested_flows": [f"随机操作 x{actions}"],
        "passed": [],
        "failed": issues[:10],
        "has_blocking_bug": blocking or page_errs > 0,
        "has_obvious_issues": blocking or console_errs > 3 or page_errs > 0,
        "exploration_issues": issues,
        "issues_found": len(issues),
        "element_count": actions,
        "exploration_clicks": None,
        "exploration_fills": None,
        "empty_state_seen": bool(raw.get("empty_state_seen")),
        "http_status": raw.get("http_status"),
        "duration_ms": raw.get("duration_ms"),
        "page": {
            "url": raw.get("url") or url,
            "title": raw.get("page_title") or "",
        },
        "error": raw.get("error"),
        "message": raw.get("error") or summary[:500],
    }
    if issues and (blocking or out["has_obvious_issues"]):
        actual = "\n".join(str(i.get("message") or "") for i in issues)[:2000]
        out["cdp_test_evidence"] = {
            "test_failed": True,
            "failed_at_action": "gremlins_monkey",
            "issues": issues,
            "steps_to_reproduce": "触发 Gremlins 猴子随机操作后观察到异常",
            "actual_result": actual,
            "expected_result": "随机操作过程中无页面崩溃、无控制台异常",
            "suggested_create_target": "bug",
            "suggested_create_fields": {
                "title": (issues[0].get("message") or "猴子测试发现异常")[:120],
                "description": summary[:2000],
                "steps_to_reproduce": f"1. 打开 {url}\n2. 运行猴子随机操作 {actions} 次\n3. 观察异常"[:3000],
                "actual_result": actual,
                "expected_result": "随机操作过程中无页面崩溃、无控制台异常",
            },
        }
    return out


def _resolve_node_bin() -> Optional[str]:
    return shutil.which("node") or shutil.which("node.exe")


def _local_mode_requires_cdp_ws(
    cdp_ws_url: Optional[str], *, engine: str
) -> Optional[Dict[str, Any]]:
    """local（强制本机）模式下必须携带网关 cdp_ws_url：禁止 runner 自起云端浏览器
    造成内网站点假完成（设计 §8.5）；launch/auto 模式不受限制。"""
    try:
        from agents.cdp.settings import cdp_connection_mode

        if cdp_connection_mode() != "local":
            return None
    except Exception:
        return None
    if (cdp_ws_url or "").strip():
        return None
    return {
        "success": False,
        "engine": engine,
        "error": (
            "CDP_CONNECTION_MODE=local 但未提供 cdp_ws_url："
            "禁止 midscene/gremlins 自行启动云端浏览器（防内网站点假完成）"
        ),
    }


async def run_midscene_smoke(
    *,
    url: str,
    goal: Optional[str] = None,
    headless: Optional[bool] = None,
    timeout_sec: Optional[int] = None,
    cdp_ws_url: Optional[str] = None,
    progress_queue: Optional[Any] = None,
) -> Dict[str, Any]:
    """子进程执行 Midscene smoke，返回原始 JSON。

    progress_queue：可选的引擎侧进度队列（``queue.Queue``），每发生一步就推送
    结构化快照（``__CDP_STEP__``）与阶段文本（``__CDP_TEXT__``），供 SSE 实时展示。
    """
    guard = _local_mode_requires_cdp_ws(cdp_ws_url, engine="midscene")
    if guard is not None:
        return guard
    if not midscene_runner_ready():
        return {
            "success": False,
            "engine": "midscene",
            "error": (
                "Midscene runner 未就绪：请在 agents/midscene_runner 执行 "
                "npm install && npx playwright install chromium"
            ),
            "fallback_legacy": True,
        }
    if not midscene_model_configured():
        return {
            "success": False,
            "engine": "midscene",
            "error": (
                "未配置 Midscene 模型：请设置 MIDSCENE_MODEL_API_KEY / "
                "MIDSCENE_MODEL_NAME / MIDSCENE_MODEL_BASE_URL / MIDSCENE_MODEL_FAMILY"
            ),
            "fallback_legacy": True,
        }
    node = _resolve_node_bin()
    if not node:
        return {
            "success": False,
            "engine": "midscene",
            "error": "未找到 node 可执行文件",
            "fallback_legacy": True,
        }

    if headless is None:
        # 与 CDP 会话浏览器默认保持一致（settings.cdp_headless：默认有头可见；CDP_HEADLESS=1 无头），
        # 避免主会话可见、Midscene/Gremlins 却跑在隐藏的无头浏览器里
        try:
            from agents.cdp.settings import cdp_headless

            headless = cdp_headless()
        except Exception:
            headless = (os.getenv("CDP_HEADLESS", "0") or "0").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
    try:
        timeout_sec = int(timeout_sec or os.getenv("MIDSCENE_SMOKE_TIMEOUT_SEC", "300"))
    except (TypeError, ValueError):
        timeout_sec = 300

    payload = {
        "url": url,
        "goal": goal or default_smoke_goal(),
        "headless": bool(headless),
        "cdp_ws_url": (cdp_ws_url or "").strip() or None,
    }

    with tempfile.TemporaryDirectory(prefix="bcd_midscene_") as td:
        input_path = Path(td) / "input.json"
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        env = os.environ.copy()
        env["MIDSCENE_SMOKE_INPUT"] = str(input_path)
        # Midscene reports under runner cwd
        env.setdefault("PW_TEST_SCREENSHOT_NO_FONTS_READY", "1")

        proc = await asyncio.create_subprocess_exec(
            node,
            str(_SMOKE_JS),
            cwd=str(_RUNNER_DIR),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # Midscene 可能打出超长单行（>64KB），提高 StreamReader 上限
            limit=16 * 1024 * 1024,
        )

        # ---- 流式读取 stderr（步骤信息），同时收集 stdout（最终 JSON）----
        execution_steps: List[Dict[str, Any]] = []
        tracker = _MidsceneLiveTracker()
        stderr_lines: List[str] = []
        _MAX_STDERR_LINES = 4000
        _MAX_LINE_CHARS = 2000

        def _collect_stderr_line(raw_line: bytes) -> None:
            text = raw_line.decode("utf-8", errors="replace").rstrip()
            if text.startswith("[step]"):
                try:
                    step_data = json.loads(text[6:])
                except json.JSONDecodeError:
                    step_data = None
                if isinstance(step_data, dict):
                    _sanitize_midscene_step(step_data)
                    execution_steps.append(step_data)
                    # 实时：跟踪器合并后把整份快照推给引擎侧（行数有限，体积可控）
                    if tracker.apply(step_data):
                        _push_cdp_progress(
                            progress_queue, CDP_STEP_PROGRESS_PREFIX, tracker.snapshot()
                        )
                    return
            # 阶段日志（runner 自带的 [midscene] 前缀）实时透传
            if progress_queue is not None and text.startswith("[midscene]"):
                _push_cdp_progress(progress_queue, CDP_TEXT_PROGRESS_PREFIX, text[:400])
            # 单行截断：stderr 仅用于错误摘要，无需保留超长行
            if len(text) > _MAX_LINE_CHARS:
                text = text[:_MAX_LINE_CHARS] + f"…[截断，原长 {len(text)} 字符]"
            stderr_lines.append(text)
            if len(stderr_lines) > _MAX_STDERR_LINES:
                del stderr_lines[: len(stderr_lines) - _MAX_STDERR_LINES]

        async def _read_stderr():
            """一点点读 stderr（小块流式），按换行逐行消费。

            不用 readline()：Midscene 可能输出超长单行，会触发 asyncio
            "Separator is not found, and chunk exceed the limit" 异常。
            """
            max_buf = 1024 * 1024
            buf = b""
            while True:
                try:
                    chunk = await proc.stderr.read(65536)
                except Exception as ex:  # noqa: BLE001 - 读流不可恢复时终止
                    stderr_lines.append(f"[stderr-read-error] {ex}")
                    break
                if not chunk:
                    break
                buf += chunk
                while True:
                    nl = buf.find(b"\n")
                    if nl < 0:
                        break
                    _collect_stderr_line(buf[:nl])
                    buf = buf[nl + 1 :]
                # 无换行但缓冲超限：强制截断处理，防止无限增长
                if len(buf) > max_buf:
                    _collect_stderr_line(buf[:max_buf])  # 行内截断标记由 _collect_stderr_line 补
                    buf = b""
            if buf:
                _collect_stderr_line(buf)

        async def _read_stdout():
            """一次性读取 stdout（最终 JSON）"""
            return (await proc.stdout.read()).decode("utf-8", errors="replace")

        stderr_task = asyncio.create_task(_read_stderr())
        stdout_task = asyncio.create_task(_read_stdout())

        try:
            await asyncio.wait_for(
                asyncio.gather(stderr_task, stdout_task),
                timeout=timeout_sec,
            )
        except asyncio.CancelledError:
            # 上游取消（引擎超时/用户停止）：杀掉子进程后继续向上抛，避免泄漏
            stderr_task.cancel()
            stdout_task.cancel()
            try:
                proc.kill()
            except Exception:
                pass
            raise
        except asyncio.TimeoutError:
            stderr_task.cancel()
            stdout_task.cancel()
            try:
                proc.kill()
            except Exception:
                pass
            return {
                "success": False,
                "engine": "midscene",
                "error": f"Midscene 超时（>{timeout_sec}s）",
                "fallback_legacy": False,
                "execution_steps": execution_steps,
            }
        except Exception as ex:
            # 读流异常（如 StreamReader 限制）：杀掉子进程，返回结构化错误而非向上冒泡
            stderr_task.cancel()
            stdout_task.cancel()
            try:
                proc.kill()
            except Exception:
                pass
            return {
                "success": False,
                "engine": "midscene",
                "error": f"Midscene 读取失败: {type(ex).__name__}: {ex}"[:500],
                "fallback_legacy": False,
                "execution_steps": execution_steps,
            }

        err_text = "\n".join(stderr_lines)
        out_text = stdout_task.result().strip()
        if err_text:
            logger.info("[midscene] stderr (tail): %s", err_text[-2000:])

        if not out_text:
            return {
                "success": False,
                "engine": "midscene",
                "error": f"Midscene 无输出，exit={proc.returncode}; stderr={err_text[-800:]}",
                "fallback_legacy": "Cannot find module" in err_text or "ERR_MODULE" in err_text,
            }

        # stdout 应为纯 JSON；若混入日志，取最后一个 {…}
        try:
            raw = json.loads(out_text)
        except json.JSONDecodeError:
            start = out_text.rfind("{")
            end = out_text.rfind("}")
            if start >= 0 and end > start:
                try:
                    raw = json.loads(out_text[start : end + 1])
                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "engine": "midscene",
                        "error": f"无法解析 Midscene JSON: {out_text[:500]}",
                        "fallback_legacy": False,
                    }
            else:
                return {
                    "success": False,
                    "engine": "midscene",
                    "error": f"无法解析 Midscene JSON: {out_text[:500]}",
                    "fallback_legacy": False,
                }
        if isinstance(raw, dict):
            # 注入流式收集的步骤信息（与子进程最终 JSON 的 execution_steps 合并去重）
            raw_steps = raw.get("execution_steps")
            if isinstance(raw_steps, list) and execution_steps:
                seen = {(s.get("sequence"), s.get("phase")) for s in execution_steps}
                for s in raw_steps:
                    key = (s.get("sequence"), s.get("phase"))
                    if key not in seen:
                        execution_steps.append(s)
                        seen.add(key)
                raw["execution_steps"] = execution_steps
            elif not raw_steps and execution_steps:
                raw["execution_steps"] = execution_steps
            # 实时追踪器合并结果（意图分组 + 动作行）作为最终可视步骤：与执行中展示完全一致
            live_steps = tracker.snapshot()
            if live_steps:
                raw["midscene_action_steps"] = live_steps
            return raw
        return {
            "success": False,
            "engine": "midscene",
            "error": "midscene result not object",
            "fallback_legacy": False,
        }


async def run_gremlins_monkey(
    *,
    url: str,
    duration_sec: int = 60,
    headless: Optional[bool] = None,
    cdp_ws_url: Optional[str] = None,
    progress_queue: Optional[Any] = None,
) -> Dict[str, Any]:
    """子进程执行 Gremlins monkey test，返回原始 JSON。

    progress_queue：可选进度队列，流式推送 ``[gremlins]`` 阶段日志（``__CDP_TEXT__``）。
    """
    guard = _local_mode_requires_cdp_ws(cdp_ws_url, engine="gremlins")
    if guard is not None:
        return guard
    if not gremlins_runner_ready():
        return {
            "success": False,
            "engine": "gremlins",
            "error": (
                "Gremlins runner 未就绪：请在 agents/midscene_runner 执行 "
                "npm install gremlins.js"
            ),
        }
    node = _resolve_node_bin()
    if not node:
        return {
            "success": False,
            "engine": "gremlins",
            "error": "未找到 node 可执行文件",
        }

    if headless is None:
        # 与 CDP 会话浏览器默认保持一致（settings.cdp_headless：默认有头可见；CDP_HEADLESS=1 无头），
        # 避免主会话可见、Midscene/Gremlins 却跑在隐藏的无头浏览器里
        try:
            from agents.cdp.settings import cdp_headless

            headless = cdp_headless()
        except Exception:
            headless = (os.getenv("CDP_HEADLESS", "0") or "0").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
    duration = max(10, min(int(duration_sec), 300))

    payload = {
        "url": url,
        "duration_sec": duration,
        "headless": bool(headless),
        "cdp_ws_url": (cdp_ws_url or "").strip() or None,
    }

    with tempfile.TemporaryDirectory(prefix="bcd_gremlins_") as td:
        input_path = Path(td) / "input.json"
        input_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        env = os.environ.copy()
        env["GREMLINS_INPUT"] = str(input_path)

        proc = await asyncio.create_subprocess_exec(
            node,
            str(_GREMLINS_JS),
            cwd=str(_RUNNER_DIR),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            # 超大单行（如注入脚本回显）兜底
            limit=16 * 1024 * 1024,
        )
        timeout_sec = max(duration + 30, 120)

        # ---- 流式读取 stderr（阶段文本进度），stdout 收集最终 JSON ----
        stderr_lines: List[str] = []
        _MAX_STDERR_LINES = 2000
        _MAX_LINE_CHARS = 2000

        def _collect_gremlins_line(raw_line: bytes) -> None:
            text = raw_line.decode("utf-8", errors="replace").rstrip()
            if progress_queue is not None and (
                text.startswith("[gremlins]") or text.startswith("[midscene]")
            ):
                _push_cdp_progress(progress_queue, CDP_TEXT_PROGRESS_PREFIX, text[:400])
            if len(text) > _MAX_LINE_CHARS:
                text = text[:_MAX_LINE_CHARS] + f"…[截断，原长 {len(text)} 字符]"
            stderr_lines.append(text)
            if len(stderr_lines) > _MAX_STDERR_LINES:
                del stderr_lines[: len(stderr_lines) - _MAX_STDERR_LINES]

        async def _read_gremlins_stderr() -> None:
            max_buf = 1024 * 1024
            buf = b""
            while True:
                try:
                    chunk = await proc.stderr.read(65536)
                except Exception as ex:  # noqa: BLE001 - 读流不可恢复时终止
                    stderr_lines.append(f"[stderr-read-error] {ex}")
                    break
                if not chunk:
                    break
                buf += chunk
                while True:
                    nl = buf.find(b"\n")
                    if nl < 0:
                        break
                    _collect_gremlins_line(buf[:nl])
                    buf = buf[nl + 1 :]
                if len(buf) > max_buf:
                    _collect_gremlins_line(buf[:max_buf])
                    buf = b""
            if buf:
                _collect_gremlins_line(buf)

        async def _read_gremlins_stdout() -> str:
            return (await proc.stdout.read()).decode("utf-8", errors="replace")

        _err_task = asyncio.create_task(_read_gremlins_stderr())
        _out_task = asyncio.create_task(_read_gremlins_stdout())
        try:
            await asyncio.wait_for(
                asyncio.gather(_err_task, _out_task), timeout=timeout_sec
            )
        except asyncio.CancelledError:
            _err_task.cancel()
            _out_task.cancel()
            try:
                proc.kill()
            except Exception:
                pass
            raise
        except asyncio.TimeoutError:
            _err_task.cancel()
            _out_task.cancel()
            try:
                proc.kill()
            except Exception:
                pass
            return {
                "success": False,
                "engine": "gremlins",
                "error": f"Gremlins 超时（>{timeout_sec}s）",
            }

        err_text = "\n".join(stderr_lines)
        out_text = _out_task.result().strip()
        if err_text:
            logger.info("[gremlins] stderr (tail): %s", err_text[-2000:])

        if not out_text:
            return {
                "success": False,
                "engine": "gremlins",
                "error": f"Gremlins 无输出，exit={proc.returncode}; stderr={err_text[-800:]}",
            }

        try:
            raw = json.loads(out_text)
        except json.JSONDecodeError:
            start = out_text.rfind("{")
            end = out_text.rfind("}")
            if start >= 0 and end > start:
                try:
                    raw = json.loads(out_text[start : end + 1])
                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "engine": "gremlins",
                        "error": f"无法解析 Gremlins JSON: {out_text[:500]}",
                    }
            else:
                return {
                    "success": False,
                    "engine": "gremlins",
                    "error": f"无法解析 Gremlins JSON: {out_text[:500]}",
                }
        if isinstance(raw, dict):
            return raw
        return {
            "success": False,
            "engine": "gremlins",
            "error": "gremlins result not object",
        }


async def run_midscene_exploration(
    *,
    url: str,
    user_query: str = "",
    headless: Optional[bool] = None,
    cdp_ws_url: Optional[str] = None,
    progress_queue: Optional[Any] = None,
) -> Dict[str, Any]:
    _push_cdp_progress(progress_queue, CDP_TEXT_PROGRESS_PREFIX, "开始 Midscene 智能巡检…")
    raw = await run_midscene_smoke(
        url=url,
        goal=default_smoke_goal(user_query),
        headless=headless,
        cdp_ws_url=cdp_ws_url,
        progress_queue=progress_queue,
    )
    return map_midscene_result_to_explore_observation(raw, url=url)


async def run_combined_exploration(
    *,
    url: str,
    user_query: str = "",
    headless: Optional[bool] = None,
    cdp_ws_url: Optional[str] = None,
    gremlins_duration_sec: int = 60,
    progress_queue: Optional[Any] = None,
) -> Dict[str, Any]:
    """组合探测：先 Midscene 智能巡检，再 Gremlins 猴子测试，合并结果。"""
    start_ts = time.time()
    result: Dict[str, Any] = {
        "success": True,
        "engine": "combined",
        "action": "explore",
        "phase": "combined_explore",
        "summary": "",
        "tested_flows": [],
        "passed": [],
        "failed": [],
        "has_blocking_bug": False,
        "has_obvious_issues": False,
        "exploration_issues": [],
        "issues_found": 0,
        "element_count": 0,
        "empty_state_seen": False,
        "duration_ms": 0,
        "page": {"url": url, "title": ""},
        "sub_results": [],
    }
    all_issues: List[Dict[str, Any]] = []

    # ---- Phase 1: Midscene 智能巡检 ----
    _push_cdp_progress(progress_queue, CDP_TEXT_PROGRESS_PREFIX, "开始 Midscene 智能巡检…")
    mid_raw = await run_midscene_smoke(
        url=url,
        goal=default_smoke_goal(user_query),
        headless=headless,
        cdp_ws_url=cdp_ws_url,
        progress_queue=progress_queue,
    )
    mid_obs = map_midscene_result_to_explore_observation(mid_raw, url=url)
    mid_obs["_phase"] = "midscene"
    result["sub_results"].append(mid_obs)

    # 目标页不可访问/被弹窗或登录阻塞：整个巡检不成立，不再让 Gremlins 空跑错误页
    mid_failed = (not bool(mid_raw.get("fallback_legacy"))) and (mid_obs.get("success") is False)
    gremlins_obs: Optional[Dict[str, Any]] = None

    if mid_raw.get("fallback_legacy"):
        logger.info("[explore] midscene fallback, 跳过")
    elif mid_failed:
        result["error"] = (
            str(mid_obs.get("error") or "").strip()
            or "Midscene 界面巡检未完成（未取得有效巡检报告）"
        )
        # 失败时也保留台账（已测/通过/页面/摘要），避免总结只剩一句兜底话术
        for k in ("tested_flows", "passed"):
            v = mid_obs.get(k)
            if isinstance(v, list) and v:
                result[k] = list(v)
        for issue in (mid_obs.get("exploration_issues") or []):
            if isinstance(issue, dict):
                all_issues.append(issue)
        if mid_obs.get("has_blocking_bug"):
            result["has_blocking_bug"] = True
        if mid_obs.get("has_obvious_issues"):
            result["has_obvious_issues"] = True
        if isinstance(mid_obs.get("page"), dict) and mid_obs["page"].get("title"):
            result["page"]["title"] = mid_obs["page"]["title"]
        if mid_obs.get("empty_state_seen"):
            result["empty_state_seen"] = True
        logger.info("[explore] midscene failed, skip gremlins: %s", result["error"][:200])
    else:
        for k in ("tested_flows", "passed"):
            v = mid_obs.get(k)
            if isinstance(v, list):
                result[k].extend(v)
        for issue in (mid_obs.get("exploration_issues") or []):
            if isinstance(issue, dict):
                all_issues.append(issue)
        if mid_obs.get("has_blocking_bug"):
            result["has_blocking_bug"] = True
        if mid_obs.get("page", {}).get("title"):
            result["page"]["title"] = mid_obs["page"]["title"]
        if mid_obs.get("empty_state_seen"):
            result["empty_state_seen"] = True

    # ---- Phase 2: Gremlins 猴子测试（仅在 Midscene 巡检就绪时执行）----
    if not mid_failed:
        _push_cdp_progress(
            progress_queue,
            CDP_TEXT_PROGRESS_PREFIX,
            f"Midscene 巡检完成，开始 Gremlins 猴子测试（{gremlins_duration_sec}s）…",
        )
        gremlins_raw = await run_gremlins_monkey(
            url=url,
            duration_sec=gremlins_duration_sec,
            headless=headless,
            cdp_ws_url=cdp_ws_url,
            progress_queue=progress_queue,
        )
        gremlins_obs = map_gremlins_result_to_explore_observation(gremlins_raw, url=url)
        gremlins_obs["_phase"] = "gremlins"
        result["sub_results"].append(gremlins_obs)
        for issue in (gremlins_obs.get("exploration_issues") or []):
            if isinstance(issue, dict):
                all_issues.append(issue)
        if gremlins_obs.get("has_blocking_bug"):
            result["has_blocking_bug"] = True
        if gremlins_obs.get("has_obvious_issues"):
            result["has_obvious_issues"] = True
        result["element_count"] = (result["element_count"] or 0) + (gremlins_obs.get("element_count") or 0)

    # ---- 合并 summary ----
    mid_summary = (mid_obs.get("summary") or "").strip()
    gremlins_summary = (gremlins_obs.get("summary") or "").strip() if gremlins_obs else ""
    parts = [s for s in [mid_summary, gremlins_summary] if s]
    if mid_failed:
        parts.append("Gremlins 猴子测试已跳过：目标页面巡检未就绪。")
    result["summary"] = "\n---\n".join(parts)[:3000]

    result["exploration_issues"] = all_issues
    result["issues_found"] = len(all_issues)
    result["success"] = (
        (not result["has_blocking_bug"])
        and (not result["has_obvious_issues"])
        and (not mid_failed)
    )

    if mid_obs.get("failed"):
        result["failed"].extend(
            m for m in (mid_obs["failed"] if isinstance(mid_obs["failed"], list) else [])
        )
    if gremlins_obs and gremlins_obs.get("failed"):
        result["failed"].extend(
            m for m in (gremlins_obs["failed"] if isinstance(gremlins_obs["failed"], list) else [])
        )

    if all_issues and result["has_obvious_issues"]:
        actual = "\n".join(str(i.get("message") or "") for i in all_issues)[:2000]
        result["cdp_test_evidence"] = {
            "test_failed": True,
            "failed_at_action": "combined_explore",
            "issues": all_issues,
            "steps_to_reproduce": result["summary"][:3000],
            "actual_result": actual,
            "expected_result": "界面功能正常，无阻塞性错误和崩溃",
            "suggested_create_target": "bug",
            "suggested_create_fields": {
                "title": (all_issues[0].get("message") or "探测发现异常")[:120],
                "description": result["summary"][:2000],
                "steps_to_reproduce": result["summary"][:3000],
                "actual_result": actual,
                "expected_result": "界面功能正常，无阻塞性错误和崩溃",
            },
        }

    result["duration_ms"] = int((time.time() - start_ts) * 1000)

    # 合并子结果的步骤信息
    all_steps: List[Dict[str, Any]] = []
    for sub in result.get("sub_results") or []:
        steps = sub.get("execution_steps")
        if isinstance(steps, list):
            all_steps.extend(steps)
    if all_steps:
        result["execution_steps"] = all_steps
    # 优先使用实时追踪器合并出的「意图分组 + 动作行」结构（与执行中展示一致）
    live_steps = mid_obs.get("midscene_action_steps")
    if isinstance(live_steps, list) and live_steps:
        result["midscene_action_steps"] = live_steps
    elif all_steps:
        result["midscene_action_steps"] = _format_midscene_action_steps(all_steps)

    return result
