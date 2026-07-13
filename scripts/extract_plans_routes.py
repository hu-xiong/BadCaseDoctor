# -*- coding: utf-8 -*-
"""从 app.py 拆出 plans 相关路由到 routers/plans_api.py。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
OUT_PATH = ROOT / "routers" / "plans_api.py"

HEADER = '''"""计划相关 REST API（自 app.py 拆出）。"""
from __future__ import annotations

import time
from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user

plans_bp = Blueprint("plans", __name__)


def _app():
    """延迟导入 app 模块（注册 blueprint 时 app 已加载完成）。"""
    import app as _application
    return _application


'''

LAZY_IMPORT = '''    a = _app()
    db = a.db
    Plan = a.Plan
    BadCase = a.BadCase
    Bug = a.Bug
    TestCase = a.TestCase
    has_project_permission = a.has_project_permission
    _json_snowflake_id = a._json_snowflake_id
    _schedule_grep_work_item_index = a._schedule_grep_work_item_index
    _schedule_grep_work_item_delete = a._schedule_grep_work_item_delete
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_get = a._redis_cache_get
    _redis_cache_set = a._redis_cache_set
    _cache_get = a._cache_get
    _cache_set = a._cache_set
    _detach_plan_work_items = a._detach_plan_work_items

'''


def _inject_lazy_import(body: str) -> str:
    """在 route handler 的 docstring 之后注入延迟 import。"""
    m = re.match(
        r'(@plans_bp\.route[^\n]+\n@login_required\ndef \w+\([^)]*\):\n(?:    """[^"]*"""\n)?)',
        body,
        re.DOTALL,
    )
    if not m:
        return LAZY_IMPORT + body
    prefix = m.group(1)
    rest = body[len(prefix) :]
    return prefix + LAZY_IMPORT + rest


def main() -> None:
    lines = APP_PATH.read_text(encoding="utf-8").splitlines(keepends=True)

    # 计划 API 块（含 _plan_api_status_and_type）
    block1_start = next(i for i, l in enumerate(lines) if l.strip() == "# 计划相关API接口")
    block1_end = next(i for i, l in enumerate(lines) if l.strip() == "# 团队管理API接口")
    block2_start = next(i for i, l in enumerate(lines) if "@app.route('/api/plans/<int:plan_id>/testcases'" in l)
    block2_end = next(
        i for i, l in enumerate(lines) if l.strip() == "# ==================== Chat Session API ===================="
    )

    chunks = lines[block1_start:block1_end] + ["\n"] + lines[block2_start:block2_end]
    raw = "".join(chunks)
    raw = raw.replace("@app.route", "@plans_bp.route")

    # 每个 @login_required def 注入 lazy import
    parts = re.split(r"(?=@plans_bp\.route)", raw)
    transformed = parts[0]
    for part in parts[1:]:
        if "@login_required" in part and "def " in part:
            transformed += _inject_lazy_import(part)
        else:
            transformed += part

    OUT_PATH.write_text(HEADER + transformed, encoding="utf-8")

    # 从 app.py 删除已迁出块
    new_lines = lines[:block1_start] + lines[block1_end:block2_start] + lines[block2_end:]
    APP_PATH.write_text("".join(new_lines), encoding="utf-8")

    # 注册 blueprint（若尚未注册）
    app_text = APP_PATH.read_text(encoding="utf-8")
    if "from routers.plans_api import plans_bp" not in app_text:
        app_text = app_text.replace(
            "from routers.models import models_bp\n",
            "from routers.models import models_bp\nfrom routers.plans_api import plans_bp\n",
        )
        app_text = app_text.replace(
            "app.register_blueprint(models_bp)\n",
            "app.register_blueprint(models_bp)\napp.register_blueprint(plans_bp)\n",
        )
        APP_PATH.write_text(app_text, encoding="utf-8")

    print(f"Wrote {OUT_PATH}, removed plan routes from app.py")


if __name__ == "__main__":
    main()
