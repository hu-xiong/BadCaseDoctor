"""project_testcases_api（自 app.py 拆出）。"""
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

project_testcases_bp = Blueprint("project_testcases", __name__)


def _app():
    import app as _application
    return _application


                _workflow_recipients_testcase(testcase), testcase.creator_id
            )
            try:
                TestCaseComment.query.filter_by(test_case_id=int(testcase_id)).delete(
                    synchronize_session=False
                )
            except Exception as _ce:
                print(f"[DELETE-TESTCASE] 清理 test_case_comment 失败（继续）: {_ce}")
            db.session.delete(testcase)
            db.session.commit()
            _schedule_grep_work_item_delete("testcase", testcase_id)
            _redis_cache_delete(f'testcase-detail:{testcase_id}')
            _cache_invalidate_plans(pid)
            try:
                _schedule_workflow_notify(
                    "deleted",
                    "testcase",
                    testcase_id,
                    _title,
                    pid,
                    _pn,
                    _st,
                    None,
                    _rec,
                    actor_id=current_user.id,
                    actor_name=getattr(current_user, "name", "") or "",
                )
            except Exception as _e:
                print(f"[workflow_notify] TestCase 删除通知失败: {_e}")
            
            return jsonify({
                'success': True,
                'message': '测试用例删除成功'
            })
            
        except Exception as e:
            db.session.rollback()
            print(f"删除TestCase失败: {e}")
            return jsonify({'success': False, 'error': '删除TestCase失败'}), 500


@project_testcases_bp.route('/api/testcases/<int:testcase_id>/comment', methods=['POST'])
@login_required
def api_add_testcase_comment(testcase_id):
    """测例评论：仅追加，不可修改历史评论。"""
    a = _app()
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

    testcase, access_err = _model_for_user_collaborator_access(
        TestCase, testcase_id, current_user.id
    )
    if access_err == 'not_found':
        return jsonify({'success': False, 'error': '测试用例不存在'}), 404
    if access_err == 'forbidden':
        return jsonify({'success': False, 'error': '没有项目权限'}), 403

    data = request.get_json() or {}
    content = data.get('content')
    if not content or not str(content).strip():
        return jsonify({'success': False, 'error': '评论内容不能为空'}), 400

    try:
        comment = _append_testcase_comment_row(
            testcase,
            content,
            current_user.id,
            source_message_id=data.get('message_id'),
        )
        db.session.commit()
        _invalidate_testcase_detail_cache(testcase_id)
        return jsonify({'success': True, 'comment': comment})
    except Exception as e:
        db.session.rollback()
        print(f"[API] 追加测例评论失败: {e}", flush=True)
        return jsonify({'success': False, 'error': '追加评论失败'}), 500


@project_testcases_bp.route('/api/plans/<int:plan_id>/testcases', methods=['GET'])
@login_required
