# -*- coding: utf-8 -*-
"""将 app.py 拆成 app_services/* + routers/*（每文件 <2000 行）。"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"

# (path, bp_name, start, end) 1-based, end 不含
ROUTE_BLOCKS = [
    ("routers/pages.py", "pages_bp", 1309, 1879),
    ("routers/legacy_browser_agent.py", "legacy_browser_agent_bp", 1880, 3334),
    ("routers/upload_api.py", "upload_bp", 3335, 3955),
    ("routers/auth_api.py", "auth_api_bp", 3956, 4127),
    ("routers/projects_api.py", "projects_api_bp", 4127, 5035),
    ("routers/badcases_api.py", "badcases_api_bp", 5035, 5608),
    ("routers/cards_api.py", "cards_api_bp", 5608, 6771),
    ("routers/card_history_api.py", "card_history_bp", 6771, 6814),
    ("routers/notifications_api.py", "notifications_bp", 7739, 7853),
    ("routers/teams_api.py", "teams_api_bp", 7853, 8020),
    ("routers/members_api.py", "members_api_bp", 8020, 8264),
    ("routers/bugs_api.py", "bugs_api_bp", 8264, 8809),
    ("routers/testcases_api.py", "testcases_api_bp", 8809, 9206),
    ("routers/chat_sessions_api.py", "chat_sessions_bp", 9206, 9664),
    ("routers/project_testcases_api.py", "project_testcases_bp", 9664, 9740),
]

SERVICE_BLOCKS = [
    ("app_services/workflow_notify.py", 843, 1108),
    ("app_services/permissions.py", 1110, 1171),
    ("app_services/cache.py", 1172, 1307),
    ("app_services/plan_helpers.py", 5708, 5759),
    ("app_services/db_schema.py", 6815, 7738),
]

LAZY = '''    a = _app()
    db = a.db
    Plan = a.Plan
    BadCase = a.BadCase
    Bug = a.Bug
    TestCase = a.TestCase
    Card = a.Card
    User = a.User
    Project = a.Project
    ProjectPermission = a.ProjectPermission
    Team = a.Team
    TeamMember = a.TeamMember
    ChatSession = a.ChatSession
    ChatMessage = a.ChatMessage
    CardPlanRelation = a.CardPlanRelation
    CardTypeDefinition = a.CardTypeDefinition
    WorkflowInAppNotification = a.WorkflowInAppNotification
    DiffReviewState = a.DiffReviewState
    AgentTask = a.AgentTask
    Comment = a.Comment
    BugComment = a.BugComment
    TestCaseComment = a.TestCaseComment
    has_project_permission = a.has_project_permission
    _json_snowflake_id = a._json_snowflake_id
    _json_snowflake_ids_in_list = a._json_snowflake_ids_in_list
    _schedule_grep_work_item_index = a._schedule_grep_work_item_index
    _schedule_grep_work_item_delete = a._schedule_grep_work_item_delete
    _schedule_workflow_notify = a._schedule_workflow_notify
    _redis_cache_invalidate_project = a._redis_cache_invalidate_project
    _redis_cache_get = a._redis_cache_get
    _redis_cache_set = a._redis_cache_set
    _cache_get = a._cache_get
    _cache_set = a._cache_set
    _cache_invalidate_plans = a._cache_invalidate_plans
    _cache_invalidate_cards = a._cache_invalidate_cards
    _detach_plan_work_items = a._detach_plan_work_items
    _plan_subtree_ids_for_project = a._plan_subtree_ids_for_project
    _parse_query_optional_int64 = a._parse_query_optional_int64
    _parse_query_int_optional = a._parse_query_int_optional
    _coerce_optional_bigint_json = a._coerce_optional_bigint_json
    _badcase_status_str = a._badcase_status_str
    _testcase_status_str = a._testcase_status_str
    _try_repair_badcase_plan_id_from_legacy_plan_string = a._try_repair_badcase_plan_id_from_legacy_plan_string
    ensure_badcase_card_link = a.ensure_badcase_card_link
    repair_card_source_link_if_missing = a.repair_card_source_link_if_missing
    send_email = a.send_email
    generate_verification_code = a.generate_verification_code
    upload_file_to_minio = a.upload_file_to_minio
    allowed_file = a.allowed_file
    compress_image = a.compress_image
    build_upload_image_proxy_url = a.build_upload_image_proxy_url
    get_upload_image_cache_key = a.get_upload_image_cache_key
    get_image_from_cache = a.get_image_from_cache
    set_image_to_cache = a.set_image_to_cache
    read_minio_object_bytes = a.read_minio_object_bytes
    get_minio_client = a.get_minio_client
    check_avatar_access_rate = a.check_avatar_access_rate
    get_image_cache_key = a.get_image_cache_key
    _gzip_large_json_response = a._gzip_large_json_response
    _submit_entity_comment_via_queue = a._submit_entity_comment_via_queue
    _comment_author_name = a._comment_author_name
    _append_bug_comment_row = a._append_bug_comment_row
    _append_badcase_comment_row = a._append_badcase_comment_row
    _append_testcase_comment_row = a._append_testcase_comment_row
    mail = a.mail

'''


def _router_header(bp_name: str, title: str) -> str:
    return f'''"""{title}（自 app.py 拆出）。"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import login_required, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

{bp_name} = Blueprint("{bp_name.replace("_bp", "")}", __name__)


def _app():
    import app as _application
    return _application


'''


def _inject_lazy(body: str, bp_name: str) -> str:
    m = re.match(
        rf"(@{bp_name}\.route[^\n]+\n(?:@login_required\n)?def \w+\([^)]*\):\n(?:    \"\"\"[^\"]*\"\"\"\n)?)",
        body,
        re.DOTALL,
    )
    if not m:
        return LAZY + body
    return m.group(1) + LAZY + body[len(m.group(1)) :]


def _write_router(rel: str, bp_name: str, chunk: list[str]) -> None:
    path = ROOT / rel
    raw = "".join(chunk).replace("@app.route", f"@{bp_name}.route")
    if rel == "routers/pages.py":
        raw = raw.replace("url_for('", "url_for('pages.")
        raw = raw.replace('url_for("', 'url_for("pages.')
    parts = re.split(rf"(?=@{bp_name}\.route)", raw)
    out = parts[0]
    for part in parts[1:]:
        out += _inject_lazy(part, bp_name) if "def " in part else part
    title = Path(rel).stem
    path.write_text(_router_header(bp_name, title) + out, encoding="utf-8")


def _write_service(rel: str, chunk: list[str]) -> None:
    path = ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    header = f'"""\n{rel}\n"""\nfrom __future__ import annotations\n\n'
    if rel == "app_services/workflow_notify.py":
        header += (
            "import random\nimport string\nimport threading\n\n"
            "from workflow_notify import (\n"
            "    build_email_body_cn,\n"
            "    build_email_subject_cn,\n"
            "    schedule_workflow_notification,\n"
            ")\n\n"
        )
    elif rel == "app_services/permissions.py":
        header += "from sqlalchemy import and_\n\n"
    elif rel == "app_services/cache.py":
        header += "import json\nimport time\nfrom collections import defaultdict\n\n"
    elif rel == "app_services/db_schema.py":
        header += (
            "import os\n\nfrom sqlalchemy import inspect, text\n"
            "from werkzeug.security import generate_password_hash\n\n"
            "from db_extensions import db\n\n"
        )
    path.write_text(header + "".join(chunk), encoding="utf-8")


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    ranges = sorted(ranges)
    merged = []
    for s, e in ranges:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


def main() -> None:
    lines = APP.read_text(encoding="utf-8").splitlines(keepends=True)

    for rel, start, end in SERVICE_BLOCKS:
        _write_service(rel, lines[start - 1 : end - 1])

    for rel, bp, start, end in ROUTE_BLOCKS:
        _write_router(rel, bp, lines[start - 1 : end - 1])

    remove = _merge_ranges([(s, e) for _, s, e in SERVICE_BLOCKS] + [(s, e) for _, _, s, e in ROUTE_BLOCKS])
    remove_set = set()
    for s, e in remove:
        for i in range(s - 1, e - 1):
            remove_set.add(i)
    new_lines = [ln for i, ln in enumerate(lines) if i not in remove_set]
    text = "".join(new_lines)

    svc = '''
from app_services.workflow_notify import (
    _badcase_status_str,
    _persist_workflow_inapp_rows,
    _schedule_grep_work_item_index,
    _schedule_grep_work_item_delete,
    _schedule_workflow_notify,
    _testcase_status_str,
    _try_repair_badcase_plan_id_from_legacy_plan_string,
    generate_verification_code,
)
from app_services.permissions import (
    _model_for_user_collaborator_access,
    _project_for_user_collaborator_access,
    has_project_permission,
)
from app_services.cache import (
    _cache_get,
    _cache_invalidate_cards,
    _cache_invalidate_plans,
    _cache_set,
    _coerce_optional_bigint_json,
    _parse_query_int_optional,
    _parse_query_optional_int64,
    _redis_cache_delete,
    _redis_cache_get,
    _redis_cache_invalidate_project,
    _redis_cache_invalidate_projects,
    _redis_cache_set,
)
from app_services.plan_helpers import _detach_plan_work_items, _plan_subtree_ids_for_project
from app_services.db_schema import (
    cleanup_diff_review_duplicates,
    create_performance_indexes,
    drop_mysql_foreign_key_constraints,
    reset_agent_tasks_stuck_running,
    sync_database_schema,
)
'''
    if "from app_services.workflow_notify import" not in text:
        text = text.replace("db.init_app(app)\n", "db.init_app(app)\n" + svc)

    imports_regs = []
    for rel, bp, _, _ in ROUTE_BLOCKS:
        mod = rel.replace("/", ".").replace(".py", "")
        if f"from {mod} import {bp}" not in text:
            imports_regs.append((f"from {mod} import {bp}", f"app.register_blueprint({bp})"))

    anchor = "from routers.plans_api import plans_bp"
    for imp, reg in imports_regs:
        if imp not in text:
            text = text.replace(anchor, anchor + "\n" + imp)
            text = text.replace(
                "app.register_blueprint(plans_bp)",
                "app.register_blueprint(plans_bp)\n" + reg,
            )

    if "login_manager.login_view = 'pages.login'" not in text:
        text = text.replace(
            "login_manager.login_view = 'login'",
            "login_manager.login_view = 'pages.login'",
        )
    text = text.replace(
        "return redirect(url_for('login'))",
        "return redirect(url_for('pages.login'))",
    )
    # 清理误删函数体后残留的 docstring 行
    text = re.sub(
        r"\n    与历史 edit-context[^\n]*\n    返回 \(project\|None[^\n]*\n",
        "\n",
        text,
    )
    text = re.sub(r"\n_PROJECT_CTX_CACHE = \{\}\n\n\n# 路由\n\n\n# API[^\n]*\n\n", "\n", text)

    APP.write_text(text, encoding="utf-8")
    n = len(text.splitlines())
    print(f"app.py -> {n} lines")
    for rel, _, _, _ in [(r, b, s, e) for r, b, s, e in ROUTE_BLOCKS]:
        p = ROOT / rel
        if p.exists():
            print(f"  {rel}: {len(p.read_text(encoding='utf-8').splitlines())} lines")
    for rel, _, _ in SERVICE_BLOCKS:
        p = ROOT / rel
        if p.exists():
            print(f"  {rel}: {len(p.read_text(encoding='utf-8').splitlines())} lines")


if __name__ == "__main__":
    main()
