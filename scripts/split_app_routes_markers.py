# -*- coding: utf-8 -*-
"""按标记注释拆分 app.py 路由（避免硬编码行号）。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"

# (文件, bp名, 起始标记含, 结束标记含|None)
SECTIONS = [
    ("routers/pages.py", "pages_bp", "# 路由\n@app.route('/')\n", "# ==================== Browser-use"),
    ("routers/legacy_browser_agent.py", "legacy_browser_agent_bp", "# ==================== Browser-use", "@app.route('/upload'"),
    ("routers/upload_api.py", "upload_bp", "@app.route('/upload', methods=['POST'])", "# API端点 - 用户认证"),
    ("routers/auth_api.py", "auth_api_bp", "# API端点 - 用户认证", "# API端点 - 项目管理"),
    ("routers/projects_api.py", "projects_api_bp", "# API端点 - 项目管理", "# API端点 - BadCase管理"),
    ("routers/badcases_api.py", "badcases_api_bp", "# API端点 - BadCase管理", "# API端点 - 卡片管理"),
    ("routers/cards_api.py", "cards_api_bp", "# API端点 - 卡片管理", "# CORS已在上面配置"),
    ("routers/notifications_api.py", "notifications_bp", '@app.route("/api/notifications"', "# 团队管理API"),
    ("routers/teams_api.py", "teams_api_bp", "# 团队管理API", "# Bug相关API"),
    ("routers/bugs_api.py", "bugs_api_bp", "# Bug相关API", "# TestCase相关API"),
    ("routers/testcases_api.py", "testcases_api_bp", "# TestCase相关API", "# ==================== Chat Session"),
    ("routers/chat_sessions_api.py", "chat_sessions_bp", "# ==================== Chat Session", "if __name__ == '__main__':"),
]

LAZY = "    a = _app()\n    db = a.db\n    Plan = a.Plan\n    User = a.User\n    Project = a.Project\n    has_project_permission = a.has_project_permission\n    _json_snowflake_id = a._json_snowflake_id\n\n"


def _extract(start: str, end: str | None, text: str) -> str:
    i = text.index(start)
    j = text.index(end, i + len(start)) if end else len(text)
    return text[i:j]


def _write_bp(path: str, bp: str, body: str) -> None:
    body = body.replace("@app.route", f"@{bp}.route")
    if path.endswith("pages.py"):
        body = re.sub(r"url_for\(['\"](\w+)['\"]", r"url_for('pages.\1'", body)
    header = f'''"""{Path(path).stem}（自 app.py 拆出）。"""
from __future__ import annotations

import json, os, time
from datetime import datetime, timedelta, timezone
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

{bp} = Blueprint("{bp.replace('_bp','')}", __name__)

def _app():
    import app as _application
    return _application

'''
    out = header + body
    (ROOT / path).write_text(out, encoding="utf-8")


def main() -> None:
    text = APP.read_text(encoding="utf-8")
    if "from db_extensions import db" not in text:
        import subprocess
        subprocess.check_call(["python", str(ROOT / "scripts" / "apply_app_split.py")])
        subprocess.check_call(["python", str(ROOT / "scripts" / "extract_plans_routes.py")])
        text = APP.read_text(encoding="utf-8")

    removed = []
    for path, bp, start, end in SECTIONS:
        chunk = _extract(start, end, text)
        _write_bp(path, bp, chunk)
        removed.append((start, end))
        text = text.replace(chunk, f"# moved to {path}\n", 1)

    APP.write_text(text, encoding="utf-8")

    # 注册 blueprint
    t = APP.read_text(encoding="utf-8")
    for path, bp, _, _ in SECTIONS:
        mod = path.replace("/", ".").replace(".py", "")
        imp = f"from {mod} import {bp}"
        reg = f"app.register_blueprint({bp})"
        if imp not in t:
            t = t.replace("from routers.plans_api import plans_bp", f"from routers.plans_api import plans_bp\n{imp}")
            t = t.replace("app.register_blueprint(plans_bp)", f"app.register_blueprint(plans_bp)\n{reg}")
    t = t.replace("login_manager.login_view = 'login'", "login_manager.login_view = 'pages.login'")
    t = t.replace("return redirect(url_for('login'))", "return redirect(url_for('pages.login'))")
    APP.write_text(t, encoding="utf-8")
    print(f"app.py -> {len(t.splitlines())} lines")


if __name__ == "__main__":
    main()
