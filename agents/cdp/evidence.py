# -*- coding: utf-8 -*-
"""CDP 浏览器测试步骤累积与失败证据结构化（D3）。"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .screenshot import format_steps_html_with_screenshot


_SENSITIVE_KEYS = frozenset({"password", "verification_code", "text"})


def _page_from_obs(observation: Dict[str, Any]) -> Dict[str, str]:
    page = observation.get("page") if isinstance(observation.get("page"), dict) else {}
    return {
        "url": str(page.get("url") or observation.get("url") or "").strip(),
        "title": str(page.get("title") or observation.get("title") or "").strip(),
    }


def _mask_value(action: str, key: str, value: Any) -> str:
    s = str(value or "")
    if not s:
        return ""
    if key in _SENSITIVE_KEYS or "pass" in key.lower():
        if action in ("fill", "login") or key == "text":
            return "***"
    return s[:80] + ("…" if len(s) > 80 else "")


def format_ref_label(
    ref: str,
    *,
    role: Optional[str] = None,
    name: Optional[str] = None,
    observation: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> str:
    """将 @eN ref 格式化为带 role/name 的人类可读标签。"""
    ref = str(ref or "").strip()
    if not ref:
        return ""
    obs = observation or {}
    par = params or {}
    role_s = str(role if role is not None else obs.get("role") or par.get("role") or "").strip()
    name_s = str(name if name is not None else obs.get("name") or par.get("name") or "").strip()
    if role_s and name_s:
        return f"{ref} ({role_s}/{name_s})"
    if role_s:
        return f"{ref} ({role_s})"
    if name_s:
        return f"{ref} ({name_s})"
    return ref


def _action_label(action: str) -> str:
    return {
        "session": "创建会话",
        "create": "创建会话",
        "navigate": "导航",
        "snapshot": "页面快照",
        "click": "点击",
        "fill": "填入",
        "wait": "等待",
        "get_text": "读取文本",
        "login": "登录",
        "assert": "断言",
        "explore": "探测性测试",
        "close": "关闭会话",
    }.get(action, action or "操作")


def summarize_step(
    action: str,
    params: Optional[Dict[str, Any]],
    observation: Dict[str, Any],
) -> str:
    """单步人类可读摘要。"""
    params = params or {}
    page = _page_from_obs(observation)
    label = _action_label(action)
    parts = [label]

    if action in ("session", "create"):
        u = str(params.get("url") or page.get("url") or "").strip()
        if u:
            parts.append(f"打开 {u[:160]}")
    elif action == "navigate":
        u = str(params.get("url") or page.get("url") or "").strip()
        if u:
            parts.append(f"至 {u[:160]}")
    elif action == "click":
        ref = str(observation.get("ref") or params.get("ref") or params.get("selector") or "").strip()
        if ref:
            parts.append(format_ref_label(ref, observation=observation, params=params))
        if observation.get("screenshot_url"):
            parts.append("[含截图]")
    elif action == "fill":
        ref = str(observation.get("ref") or params.get("ref") or "").strip()
        preview = str(observation.get("text_preview") or _mask_value("fill", "text", params.get("text")) or "")
        if ref:
            parts.append(format_ref_label(ref, observation=observation, params=params))
        if preview:
            parts.append(f"=「{preview}」")
    elif action == "login":
        if observation.get("await_verification_code"):
            parts.append("等待用户验证码")
        elif observation.get("login_success"):
            parts.append("成功")
        elif observation.get("login_skipped"):
            parts.append("跳过（非登录页）")
        else:
            parts.append(str(observation.get("message") or "执行登录")[:80])
    elif action == "assert":
        cond = []
        if params.get("url_matches"):
            cond.append(f"url~{params.get('url_matches')}")
        if params.get("text_contains") or params.get("text"):
            cond.append(f"含「{params.get('text_contains') or params.get('text')}」")
        if params.get("ref"):
            cond.append(format_ref_label(str(params.get("ref")), params=params, observation=observation))
        if cond:
            parts.append("；".join(cond))
        if observation.get("success") is False:
            parts.append(f"失败：{str(observation.get('message') or observation.get('error') or '')[:120]}")
        else:
            parts.append("通过")
    elif action == "explore":
        phase = str(params.get("phase") or observation.get("phase") or "full")
        cnt = observation.get("element_count")
        clicks = observation.get("exploration_clicks")
        issues = observation.get("issues_found")
        parts.append(f"phase={phase}")
        if cnt is not None:
            parts.append(f"{cnt} 个可点元素")
        if clicks is not None:
            parts.append(f"点击 {clicks} 次")
        if issues:
            parts.append(f"发现 {issues} 个问题")
    elif action == "wait":
        if params.get("url_matches"):
            parts.append(f"url~{params.get('url_matches')}")
        elif params.get("text"):
            parts.append(f"文本「{params.get('text')}」")
        elif params.get("ref"):
            parts.append(format_ref_label(str(params.get("ref")), params=params, observation=observation))
    elif action == "get_text":
        ref = str(params.get("ref") or observation.get("ref") or "").strip()
        txt = str(observation.get("text") or "")[:60]
        if ref:
            parts.append(format_ref_label(ref, observation=observation, params=params))
        if txt:
            parts.append(f"→「{txt}」")

    if page.get("title") and action not in ("snapshot",):
        parts.append(f"（{page['title'][:60]}）")

    ok = observation.get("success") is not False
    if not ok and action != "assert":
        err = str(observation.get("error") or observation.get("message") or "失败")[:100]
        parts.append(f"[{err}]")

    return " ".join(p for p in parts if p).strip()


@dataclass
class CdpStepRecord:
    index: int
    action: str
    success: bool
    summary: str
    url: str = ""
    title: str = ""
    ref: str = ""
    duration_ms: Optional[int] = None
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "action": self.action,
            "success": self.success,
            "summary": self.summary,
            "url": self.url,
            "title": self.title,
            "ref": self.ref,
            "duration_ms": self.duration_ms,
        }


def build_steps_to_reproduce(records: List[CdpStepRecord], *, step_screenshots: Optional[Dict[int, str]] = None) -> str:
    if not records:
        return ""
    shots = step_screenshots or {}
    lines = []
    for r in records:
        status = "✓" if r.success else "✗"
        line = f"{r.index}. [{status}] {r.summary}"
        if r.url:
            line += f" @ {r.url[:120]}"
        shot = shots.get(r.index) or getattr(r, "screenshot_url", None)
        lines.append(line)
        if shot:
            lines.append(format_steps_html_with_screenshot("", shot, alt=f"步骤 {r.index} 截图"))
    return "\n".join(lines)


def _expected_from_assert_params(params: Optional[Dict[str, Any]]) -> str:
    params = params or {}
    parts = []
    if params.get("url_matches"):
        parts.append(f"URL 匹配 {params.get('url_matches')}")
    if params.get("text_contains") or params.get("text"):
        parts.append(f"页面含文本「{params.get('text_contains') or params.get('text')}」")
    if params.get("ref"):
        parts.append(f"元素 {params.get('ref')} 可见/含期望文本")
    return "；".join(parts) if parts else "测试断言应通过"


def build_actual_result(
    failure_observation: Dict[str, Any],
    records: List[CdpStepRecord],
    *,
    assert_params: Optional[Dict[str, Any]] = None,
) -> str:
    page = _page_from_obs(failure_observation)
    err = str(
        failure_observation.get("message")
        or failure_observation.get("error")
        or "断言未通过"
    ).strip()
    parts = [err]
    if page.get("url"):
        parts.append(f"当前 URL：{page['url'][:200]}")
    if page.get("title"):
        parts.append(f"页面标题：{page['title'][:120]}")
    expected = _expected_from_assert_params(assert_params)
    if expected:
        parts.append(f"期望：{expected}")
    failed = [r for r in records if not r.success]
    if failed:
        parts.append(f"失败步骤：{failed[-1].summary[:160]}")
    return "\n".join(parts)


def suggest_bug_title(
    failure_observation: Dict[str, Any],
    *,
    user_query: Optional[str] = None,
) -> str:
    page = _page_from_obs(failure_observation)
    if user_query and str(user_query).strip():
        q = str(user_query).strip()[:80]
        return f"UI测试失败：{q}"
    if page.get("title"):
        return f"UI测试失败：{page['title'][:60]}"
    if page.get("url"):
        path = page["url"].split("/")[-1][:40] or page["url"][:40]
        return f"UI测试失败：{path}"
    return "UI测试失败：断言未通过"


def build_create_fields_from_failure(
    failure_observation: Dict[str, Any],
    records: List[CdpStepRecord],
    *,
    assert_params: Optional[Dict[str, Any]] = None,
    user_query: Optional[str] = None,
    target: str = "bug",
) -> Dict[str, Any]:
    """生成可供 create 预览的 fields（D3 输出，D4 将自动调用 create）。"""
    steps_text = build_steps_to_reproduce(records)
    shot = str(failure_observation.get("screenshot_url") or "").strip()
    if shot:
        steps_text = format_steps_html_with_screenshot(steps_text, shot)
    actual = build_actual_result(failure_observation, records, assert_params=assert_params)
    expected = _expected_from_assert_params(assert_params)
    title = suggest_bug_title(failure_observation, user_query=user_query)
    page = _page_from_obs(failure_observation)

    fields: Dict[str, Any] = {
        "title": title,
        "steps_to_reproduce": steps_text,
        "actual_result": actual,
        "expected_result": expected,
    }
    if target == "badcase":
        fields["reproduction_steps"] = steps_text
        fields["description"] = actual[:2000]
    if page.get("url"):
        fields["environment"] = page["url"][:500]
    return fields


def build_test_evidence_bundle(
    session_id: str,
    records: List[CdpStepRecord],
    failure_observation: Dict[str, Any],
    *,
    assert_params: Optional[Dict[str, Any]] = None,
    user_query: Optional[str] = None,
) -> Dict[str, Any]:
    page = _page_from_obs(failure_observation)
    fields = build_create_fields_from_failure(
        failure_observation,
        records,
        assert_params=assert_params,
        user_query=user_query,
    )
    return {
        "session_id": session_id,
        "test_failed": True,
        "failed_at_action": "assert",
        "url": page.get("url"),
        "title": page.get("title"),
        "steps_to_reproduce": fields.get("steps_to_reproduce"),
        "actual_result": fields.get("actual_result"),
        "expected_result": fields.get("expected_result"),
        "step_log": [r.to_dict() for r in records],
        "suggested_create_fields": fields,
        "suggested_create_target": "bug",
    }


class CdpEvidenceRecorder:
    """按 session_id 累积 CDP 操作步骤。"""

    def __init__(self):
        self._logs: Dict[str, List[CdpStepRecord]] = {}

    def reset(self, session_id: str) -> None:
        self._logs[session_id] = []

    def discard(self, session_id: str) -> None:
        self._logs.pop(session_id, None)

    def get_records(self, session_id: str) -> List[CdpStepRecord]:
        return list(self._logs.get(session_id) or [])

    def record(
        self,
        session_id: str,
        action: str,
        params: Optional[Dict[str, Any]],
        observation: Dict[str, Any],
    ) -> CdpStepRecord:
        if not session_id:
            return CdpStepRecord(0, action, False, "")
        log = self._logs.setdefault(session_id, [])
        page = _page_from_obs(observation)
        rec = CdpStepRecord(
            index=len(log) + 1,
            action=action,
            success=observation.get("success") is not False,
            summary=summarize_step(action, params, observation),
            url=page.get("url", ""),
            title=page.get("title", ""),
            ref=str(observation.get("ref") or (params or {}).get("ref") or "").strip(),
            duration_ms=observation.get("duration_ms"),
        )
        log.append(rec)
        return rec

    def attach_to_observation(
        self,
        observation: Dict[str, Any],
        *,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        user_query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """记录本步并在观察结果中附带当前证据摘要。"""
        if not isinstance(observation, dict):
            return observation
        sid = str(observation.get("session_id") or (params or {}).get("session_id") or "").strip()
        if not sid:
            return observation

        self.record(sid, action, params, observation)
        records = self.get_records(sid)
        observation["cdp_step_count"] = len(records)
        observation["cdp_last_step"] = records[-1].to_dict() if records else None

        steps_preview = build_steps_to_reproduce(records)
        if steps_preview:
            observation["cdp_steps_preview"] = steps_preview[:3000]

        if observation.get("assertion_failed") or observation.get("has_obvious_issues") or (
            action == "assert" and observation.get("success") is False
        ):
            bundle = build_test_evidence_bundle(
                sid,
                records,
                observation,
                assert_params=params,
                user_query=user_query,
            )
            observation["cdp_test_evidence"] = bundle
            observation["summary"] = str(observation.get("message") or observation.get("error") or "断言失败")
            fields = bundle.get("suggested_create_fields") or {}
            if fields.get("steps_to_reproduce"):
                observation["cdp_steps_preview"] = fields["steps_to_reproduce"][:3000]

        return observation


_recorder = CdpEvidenceRecorder()


def get_cdp_evidence_recorder() -> CdpEvidenceRecorder:
    return _recorder
