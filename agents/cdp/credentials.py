# -*- coding: utf-8 -*-
"""从项目配置或本地文件加载浏览器测试登录凭证。"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

CREDENTIALS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "tmp",
    "login_states",
    "credentials.json",
)


def load_credentials_file() -> Optional[Dict[str, str]]:
    if not os.path.exists(CREDENTIALS_PATH):
        return None
    try:
        with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
            creds = json.load(f)
        if creds.get("username") and creds.get("password"):
            return creds
    except Exception:
        pass
    return None


    return None


def _parse_login_configs_raw(raw: Any) -> List[Dict[str, Any]]:
    if not raw:
        return []
    try:
        configs = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return []
    if not isinstance(configs, list):
        return []
    return [c for c in configs if isinstance(c, dict)]


def load_project_login_configs_list(project_id: int) -> List[Dict[str, Any]]:
    """读取项目「网站登录配置」列表。"""
    try:
        from flask import has_app_context

        from utils.flask_runtime import get_app_module, get_db

        mod = get_app_module()
        Project = mod.Project
        db = get_db()

        def _read() -> List[Dict[str, Any]]:
            project = db.session.get(Project, int(project_id))
            if not project or not project.login_configs:
                return []
            return _parse_login_configs_raw(project.login_configs)

        if has_app_context():
            return _read()
        flask_app = getattr(mod, "app", None)
        if flask_app is None:
            return []
        with flask_app.app_context():
            return _read()
    except Exception:
        return []


def config_matches_url(config: Dict[str, Any], url: str) -> bool:
    if not url:
        return False
    config_url = str(config.get("url") or "").strip()
    if not config_url:
        return False
    target_domain = urlparse(url).netloc.lower()
    config_domain = urlparse(config_url).netloc.lower()
    url_l = url.lower()
    config_l = config_url.lower()
    return (
        config_domain == target_domain
        or (target_domain and target_domain in config_l)
        or config_l in url_l
        or url_l in config_l
    )


def pick_login_config_for_url(
    configs: List[Dict[str, Any]], url: str
) -> Optional[Dict[str, Any]]:
    for config in configs:
        if config_matches_url(config, url):
            username = config.get("username")
            password = config.get("password")
            if username and password:
                return {
                    "username": username,
                    "password": password,
                    "url": config.get("url"),
                    "note": config.get("note", ""),
                }
    for config in configs:
        username = config.get("username")
        password = config.get("password")
        if username and password:
            return {
                "username": username,
                "password": password,
                "url": config.get("url"),
                "note": config.get("note", ""),
            }
    return None


def infer_url_from_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    m = re.search(r"https?://[^\s<>\"']+", text, re.I)
    return m.group(0).strip() if m else None


def build_project_login_prompt_hint(
    project_id: Optional[int],
    *,
    user_input: str = "",
    url: Optional[str] = None,
    locale: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """为 LLM 提示词构建项目登录配置摘要（密码不明文，仅标记是否已配置）。"""
    if not project_id:
        return None
    try:
        pid = int(project_id)
    except (TypeError, ValueError):
        return None

    from agents.locale_prompts import is_english_locale

    en = is_english_locale(locale)
    configs = load_project_login_configs_list(pid)
    target_url = (url or infer_url_from_text(user_input) or "").strip()
    matched = pick_login_config_for_url(configs, target_url) if configs else None

    if not configs:
        summary = (
            "No website login configs for this project."
            if en
            else "本项目未配置网站登录。"
        )
        return {
            "configured": False,
            "configs_count": 0,
            "prompt_lines": [summary],
            "summary": summary,
        }

    prompt_lines: List[str] = []
    for config in configs:
        cu = str(config.get("url") or "").strip()
        u = str(config.get("username") or "").strip()
        has_pwd = bool(config.get("password"))
        note = str(config.get("note") or "").strip()
        is_match = bool(target_url and config_matches_url(config, target_url))
        tag = " ← 当前环境" if (is_match and not en) else (" ← current env" if is_match else "")
        if en:
            line = f"- url={cu[:120]} username={u[:80]} ({'password OK' if has_pwd else 'NO password'}){tag}"
        else:
            line = (
                f"- 网站 {cu[:120]} 用户名 {u[:80]}"
                f"（{'密码已配置' if has_pwd else '缺密码'}）{tag}"
            )
        if note:
            line += f" 备注={note[:40]}"
        prompt_lines.append(line)

    has_any = any(c.get("username") and c.get("password") for c in configs)
    if matched:
        mu = str(matched.get("username") or "")
        murl = str(matched.get("url") or target_url)
        if en:
            summary = (
                f"Login configured for {murl[:100]} (user {mu[:60]}); "
                f"use cdp action=login — password loaded by tool, do not pass in params."
            )
        else:
            summary = (
                f"已匹配登录配置：{murl[:100]}，用户名 {mu[:60]}；"
                f"请用 cdp action=login（密码由工具自动读取，勿在 params 明文传 password）。"
            )
    elif has_any:
        summary = (
            f"{len(configs)} login config(s); use cdp action=login after session create."
            if en
            else f"项目已配置 {len(configs)} 条网站登录；session 打开对应 url 后 action=login 自动填凭证。"
        )
    else:
        summary = (
            "Login configs incomplete (missing username/password)."
            if en
            else "有登录配置条目但用户名或密码不完整。"
        )

    return {
        "configured": has_any,
        "configs_count": len(configs),
        "matched_url": str(matched.get("url") or "") if matched else "",
        "matched_username": str(matched.get("username") or "") if matched else "",
        "password_configured": bool(matched and matched.get("password")),
        "prompt_lines": prompt_lines,
        "summary": summary,
    }


def refresh_project_login_hint_in_context(
    result_context: Optional[Dict[str, Any]],
    project_id: Optional[int],
    *,
    user_input: str = "",
    prev_tool: Optional[str] = None,
    todo: str = "",
    url: Optional[str] = None,
    locale: Optional[str] = None,
) -> None:
    """可能使用 cdp 时，把项目登录配置摘要写入 ReAct context。"""
    if not isinstance(result_context, dict) or not project_id:
        return
    try:
        from agents.prompts import prompt_likely_needs_cdp

        pt = str(prev_tool or "").lower()
        skill = str(result_context.get("matched_skill") or "").lower()
        needs = (
            pt == "cdp"
            or prompt_likely_needs_cdp(todo=todo, user_input=user_input)
            or skill in ("login-handler", "login_handler")
        )
        if not needs:
            result_context.pop("_project_login_hint", None)
            result_context.pop("project_login_summary", None)
            return
    except Exception:
        pass

    hint = build_project_login_prompt_hint(
        project_id,
        user_input=user_input,
        url=url,
        locale=locale,
    )
    if hint:
        result_context["_project_login_hint"] = hint
        result_context["project_login_summary"] = hint.get("summary")
    else:
        result_context.pop("_project_login_hint", None)
        result_context.pop("project_login_summary", None)


def load_credentials_from_project(project_id: int, url: str) -> Optional[Dict[str, str]]:
    configs = load_project_login_configs_list(project_id)
    if not configs:
        return None
    picked = pick_login_config_for_url(configs, url)
    if not picked:
        return None
    return {
        "username": picked.get("username"),
        "password": picked.get("password"),
        "note": picked.get("note", ""),
    }


def resolve_login_credentials(
    *,
    url: str,
    project_id: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    u, p = username, password
    if (not u or not p) and project_id:
        creds = load_credentials_from_project(project_id, url)
        if creds:
            u = u or creds.get("username")
            p = p or creds.get("password")
    if not u or not p:
        creds = load_credentials_file()
        if creds:
            u = u or creds.get("username")
            p = p or creds.get("password")
    return {"username": u, "password": p}


def extract_credentials_from_text(text: Optional[str]) -> Dict[str, Optional[str]]:
    """从用户对话中提取用户名与密码。"""
    if not text or not isinstance(text, str):
        return {"username": None, "password": None}
    s = text.strip()
    if not s:
        return {"username": None, "password": None}

    combined = re.search(
        r"(?:用户名|账号|帐户|邮箱|邮件|email|e-mail|username|user\s*name|account)"
        r"[:：\s]*([^\s,，;；]+(?:@[^\s,，;；]+)?)"
        r"\s*(?:密码|password|passwd|pwd)[:：\s]*(\S+)",
        s,
        re.I,
    )
    if combined:
        return {"username": combined.group(1).strip(), "password": combined.group(2).strip()}

    username = None
    password = None
    um = re.search(
        r"(?:用户名|账号|帐户|邮箱|邮件|email|e-mail|username|user\s*name|account)"
        r"[:：\s]*([^\s,，;；]+(?:@[^\s,，;；]+)?)",
        s,
        re.I,
    )
    if um:
        username = um.group(1).strip()
    pm = re.search(r"(?:密码|password|passwd|pwd)[:：\s]*(\S+)", s, re.I)
    if pm:
        password = pm.group(1).strip()
    return {"username": username, "password": password}


def save_credentials_file(username: str, password: str) -> bool:
    """用户对话提供凭证后写入本地文件，供后续测试复用。"""
    if not username or not password:
        return False
    try:
        os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)
        with open(CREDENTIALS_PATH, "w", encoding="utf-8") as f:
            json.dump({"username": username, "password": password}, f, ensure_ascii=False)
        return True
    except Exception:
        return False
