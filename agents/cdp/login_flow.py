# -*- coding: utf-8 -*-
"""登录页识别与自动填表；验证码场景暂停等待用户输入。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

_LOGIN_URL_MARKERS = ("/login", "#/login", "/signin", "#/signin", "/sign-in", "#/sign-in")

_USERNAME_HINTS = re.compile(
    r"邮箱|邮件|email|e-mail|用户名|账号|帐户|手机|电话|phone|mobile|username|user\s*name|account",
    re.I,
)
_PASSWORD_HINTS = re.compile(r"密码|password|passwd|pwd", re.I)
_CODE_HINTS = re.compile(
    r"验证码|校验码|动态码|短信码|邮箱码|verification\s*code|verify\s*code|auth\s*code|otp|sms\s*code|one[- ]time",
    re.I,
)
_SEND_CODE_HINTS = re.compile(
    r"发送验证码|获取验证码|发送校验码|获取校验码|send\s*code|get\s*code|resend",
    re.I,
)
_SUBMIT_HINTS = re.compile(r"^登录$|^登\s*录$|^login$|^sign\s*in$|^submit$|^确认$|^进入$", re.I)
_CAPTCHA_HINTS = re.compile(r"图形验证码|验证码图片|captcha|滑块|人机验证|recaptcha", re.I)


@dataclass
class LoginPageAnalysis:
    is_login_page: bool = False
    login_type: str = "unknown"  # password | verification_code | captcha | mixed
    username_ref: Optional[str] = None
    password_ref: Optional[str] = None
    code_ref: Optional[str] = None
    send_code_ref: Optional[str] = None
    submit_ref: Optional[str] = None
    has_captcha: bool = False
    hints: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_login_page": self.is_login_page,
            "login_type": self.login_type,
            "username_ref": self.username_ref,
            "password_ref": self.password_ref,
            "code_ref": self.code_ref,
            "send_code_ref": self.send_code_ref,
            "submit_ref": self.submit_ref,
            "has_captcha": self.has_captcha,
            "hints": self.hints,
        }


def is_login_url(url: str) -> bool:
    u = (url or "").lower()
    return any(m in u for m in _LOGIN_URL_MARKERS)


def _node_text(node: Dict[str, Any]) -> str:
    name = str(node.get("name") or "").strip()
    value = str(node.get("value") or "").strip()
    role = str(node.get("role") or "").strip().lower()
    return f"{role} {name} {value}".strip()


def _pick_ref(nodes: List[Dict[str, Any]], pattern: re.Pattern, *, role: Optional[str] = None) -> Optional[str]:
    for n in nodes:
        if role and str(n.get("role") or "").lower() != role:
            continue
        text = _node_text(n)
        if pattern.search(text):
            ref = str(n.get("ref") or "").strip()
            if ref:
                return ref
    return None


def analyze_login_page(nodes: List[Dict[str, Any]], url: str = "") -> LoginPageAnalysis:
    """从 snapshot nodes 推断登录页形态与关键 ref。"""
    analysis = LoginPageAnalysis()
    if not nodes:
        return analysis

    interactive = [n for n in nodes if isinstance(n, dict)]
    url_login = is_login_url(url)

    analysis.username_ref = _pick_ref(interactive, _USERNAME_HINTS, role="textbox")
    if not analysis.username_ref:
        analysis.username_ref = _pick_ref(interactive, _USERNAME_HINTS)

    analysis.password_ref = _pick_ref(interactive, _PASSWORD_HINTS, role="textbox")
    if not analysis.password_ref:
        analysis.password_ref = _pick_ref(interactive, _PASSWORD_HINTS)

    analysis.code_ref = _pick_ref(interactive, _CODE_HINTS, role="textbox")
    if not analysis.code_ref:
        analysis.code_ref = _pick_ref(interactive, _CODE_HINTS)

    for n in interactive:
        if str(n.get("role") or "").lower() != "button":
            continue
        name = str(n.get("name") or "").strip()
        ref = str(n.get("ref") or "").strip()
        if not ref:
            continue
        if _SEND_CODE_HINTS.search(name) and not analysis.send_code_ref:
            analysis.send_code_ref = ref
        elif _SUBMIT_HINTS.search(name) and not analysis.submit_ref:
            analysis.submit_ref = ref

    if not analysis.submit_ref:
        for n in interactive:
            if str(n.get("role") or "").lower() != "button":
                continue
            name = str(n.get("name") or "").strip()
            ref = str(n.get("ref") or "").strip()
            if ref and ("登录" in name or name.lower() == "login"):
                analysis.submit_ref = ref
                break

    analysis.has_captcha = any(
        _CAPTCHA_HINTS.search(_node_text(n)) for n in interactive
    )

    has_password_flow = bool(analysis.password_ref or analysis.username_ref)
    has_code_flow = bool(analysis.code_ref or analysis.send_code_ref)

    if url_login or (has_password_flow and analysis.submit_ref) or (has_code_flow and analysis.submit_ref):
        analysis.is_login_page = True

    if analysis.has_captcha:
        analysis.login_type = "captcha"
        analysis.hints.append("检测到图形验证码/滑块，需用户协助")
    elif has_code_flow and has_password_flow:
        analysis.login_type = "mixed"
        analysis.hints.append("账号密码 + 验证码登录")
    elif has_code_flow:
        analysis.login_type = "verification_code"
        analysis.hints.append("验证码登录（手机/邮箱 + 验证码）")
    elif has_password_flow:
        analysis.login_type = "password"
    else:
        analysis.login_type = "unknown"

    return analysis


def await_verification_message(analysis: LoginPageAnalysis, *, locale: Optional[str] = None) -> str:
    from agents.locale_prompts import is_english_locale

    if is_english_locale(locale):
        if analysis.has_captcha:
            return (
                "This page requires a CAPTCHA or slider verification. "
                "Please complete it in the browser or tell me the verification code, then send it in chat."
            )
        return (
            "Verification code required. Click «Send code» if needed, then reply with the code "
            "(digits only). I will continue login and testing with the same browser session."
        )
    if analysis.has_captcha:
        return (
            "当前页面需要图形验证码或滑块验证。"
            "请先在浏览器中完成验证，或将验证码发给我，我将继续登录并测试。"
        )
    return (
        "当前页面需要短信/邮箱验证码。"
        "请先点击「发送验证码」收取验证码，然后在对话中直接发送验证码（纯数字），"
        "我将用同一浏览器会话继续完成登录并测试。"
    )


def needs_user_verification_code(analysis: LoginPageAnalysis) -> bool:
    if not analysis.is_login_page:
        return False
    if analysis.has_captcha:
        return True
    if analysis.code_ref or analysis.send_code_ref:
        return True
    return False


def await_credentials_message(*, locale: Optional[str] = None) -> str:
    from agents.locale_prompts import is_english_locale

    if is_english_locale(locale):
        return (
            "Login credentials are required. Please reply with username and password, e.g. "
            '"username admin@example.com password your_password". '
            "I will use the same browser session to continue login."
        )
    return (
        "当前页面需要登录，但未找到可用账号密码（项目 login_configs / 本地凭证文件均无）。"
        "请在对话中提供用户名和密码，例如：「用户名 admin@test.com 密码 123456」。"
        "我将使用同一浏览器会话继续完成登录。"
    )


def await_login_failed_message(*, locale: Optional[str] = None) -> str:
    from agents.locale_prompts import is_english_locale

    if is_english_locale(locale):
        return (
            "Login failed — still on the login page. Please check username/password "
            "or send updated credentials in chat."
        )
    return (
        "登录失败，页面仍在登录页。请检查用户名密码是否正确，"
        "或在对话中重新提供正确的账号密码。"
    )


def extract_verification_code_from_text(text: Optional[str]) -> Optional[str]:
    """从用户回复中提取验证码。"""
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if not s:
        return None
    m = re.search(r"(?:验证码|校验码|code)[:：\s]*([0-9]{4,8})", s, re.I)
    if m:
        return m.group(1)
    m = re.fullmatch(r"[0-9]{4,8}", s)
    if m:
        return m.group(0)
    return None


def resolve_login_pending(
    *,
    result_context: Optional[Dict[str, Any]],
    chat_session_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """合并内存上下文、文件持久化、活跃浏览器会话中的待续登录状态。"""
    pending = None
    if isinstance(result_context, dict):
        p = result_context.get("cdp_login_pending")
        if isinstance(p, dict) and p.get("session_id"):
            pending = dict(p)
    if not pending:
        from agents.cdp.login_pending_store import load_login_pending

        pending = load_login_pending(
            chat_session_id=chat_session_id,
            project_id=project_id,
        )
    if not pending or not pending.get("session_id"):
        from agents.cdp.session_manager import CdpSessionManager

        sid = CdpSessionManager.get().find_session_awaiting_verification(project_id)
        if sid:
            pending = {"session_id": sid}
    return pending


def inject_cdp_login_resume_params(
    tool_params: Dict[str, Any],
    *,
    result_context: Optional[Dict[str, Any]],
    user_input: Optional[str],
    chat_session_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> None:
    """续登：从上下文恢复 session，并从用户消息提取验证码。"""
    pending = resolve_login_pending(
        result_context=result_context,
        chat_session_id=chat_session_id,
        project_id=project_id,
    )
    if not pending:
        return
    if isinstance(result_context, dict):
        result_context["cdp_login_pending"] = pending
    tool_params.setdefault("action", "login")
    if not tool_params.get("session_id") and pending.get("session_id"):
        tool_params["session_id"] = pending["session_id"]
    if not tool_params.get("verification_code"):
        code = extract_verification_code_from_text(user_input)
        if code:
            tool_params["verification_code"] = code
    if not tool_params.get("username") or not tool_params.get("password"):
        from agents.cdp.credentials import extract_credentials_from_text

        creds = extract_credentials_from_text(user_input)
        if creds.get("username") and not tool_params.get("username"):
            tool_params["username"] = creds["username"]
        if creds.get("password") and not tool_params.get("password"):
            tool_params["password"] = creds["password"]


def should_auto_resume_verification_login(
    user_input: Optional[str],
    *,
    result_context: Optional[Dict[str, Any]],
    chat_session_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> bool:
    code = extract_verification_code_from_text(user_input)
    if not code:
        return False
    pending = resolve_login_pending(
        result_context=result_context,
        chat_session_id=chat_session_id,
        project_id=project_id,
    )
    return bool(pending and pending.get("session_id"))


def should_auto_resume_credentials_login(
    user_input: Optional[str],
    *,
    result_context: Optional[Dict[str, Any]],
    chat_session_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> bool:
    from agents.cdp.credentials import extract_credentials_from_text

    pending = resolve_login_pending(
        result_context=result_context,
        chat_session_id=chat_session_id,
        project_id=project_id,
    )
    if not pending or not pending.get("session_id"):
        return False
    if pending.get("await_type") not in (None, "credentials"):
        return False
    creds = extract_credentials_from_text(user_input)
    if creds.get("username") and creds.get("password"):
        return True
    if pending.get("await_type") == "credentials" and creds.get("password"):
        return True
    return False


def should_auto_resume_cdp_login(
    user_input: Optional[str],
    *,
    result_context: Optional[Dict[str, Any]],
    chat_session_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> bool:
    return should_auto_resume_verification_login(
        user_input,
        result_context=result_context,
        chat_session_id=chat_session_id,
        project_id=project_id,
    ) or should_auto_resume_credentials_login(
        user_input,
        result_context=result_context,
        chat_session_id=chat_session_id,
        project_id=project_id,
    )


def update_login_pending_context(
    result_context: Dict[str, Any],
    observation: Dict[str, Any],
    *,
    chat_session_id: Optional[int] = None,
    project_id: Optional[int] = None,
) -> None:
    from agents.cdp.login_pending_store import (
        clear_login_pending,
        save_login_pending,
    )
    from agents.cdp.session_manager import CdpSessionManager

    sid = str(observation.get("session_id") or "").strip()
    if observation.get("await_verification_code") is True:
        pending = {
            "session_id": observation.get("session_id"),
            "snapshot_id": observation.get("snapshot_id"),
            "login_type": observation.get("login_type"),
            "await_type": "verification_code",
            "url": observation.get("url")
            or (observation.get("page") or {}).get("url"),
        }
        result_context["cdp_login_pending"] = pending
        save_login_pending(
            chat_session_id=chat_session_id,
            project_id=project_id,
            pending=pending,
        )
        if sid:
            CdpSessionManager.get().mark_awaiting_verification(
                sid,
                snapshot_id=observation.get("snapshot_id"),
                project_id=project_id,
            )
        return
    if observation.get("await_user_credentials") is True:
        pending = {
            "session_id": observation.get("session_id"),
            "snapshot_id": observation.get("snapshot_id"),
            "login_type": observation.get("login_type"),
            "await_type": "credentials",
            "url": observation.get("url")
            or (observation.get("page") or {}).get("url"),
        }
        result_context["cdp_login_pending"] = pending
        save_login_pending(
            chat_session_id=chat_session_id,
            project_id=project_id,
            pending=pending,
        )
        return
    if observation.get("login_success") is True:
        result_context.pop("cdp_login_pending", None)
        clear_login_pending(chat_session_id=chat_session_id, project_id=project_id)
        if sid:
            CdpSessionManager.get().clear_awaiting_verification(sid)


def enrich_snapshot_with_login_hints(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """为 snapshot 结果附加 login_page 元数据。"""
    if not isinstance(snapshot, dict) or not snapshot.get("success"):
        return snapshot
    nodes = snapshot.get("nodes")
    if not isinstance(nodes, list):
        return snapshot
    url = str(snapshot.get("url") or "").strip()
    if not url:
        page = snapshot.get("page")
        if isinstance(page, dict):
            url = str(page.get("url") or "").strip()
    analysis = analyze_login_page(nodes, url)
    if analysis.is_login_page:
        snapshot["login_page"] = analysis.to_dict()
        if needs_user_verification_code(analysis):
            snapshot["login_needs_verification_code"] = True
    return snapshot
