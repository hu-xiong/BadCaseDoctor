# -*- coding: utf-8 -*-
from utils.entity_id import (
    coerce_plausible_entity_pk,
    is_plausible_entity_pk,
    sanitize_tool_entity_ids,
)


def test_reject_small_legacy_ids():
    assert not is_plausible_entity_pk(9)
    assert not is_plausible_entity_pk(11)
    assert coerce_plausible_entity_pk(9) is None


def test_accept_snowflake_like_ids():
    sid = 1745123456789012345
    assert is_plausible_entity_pk(sid)
    assert coerce_plausible_entity_pk(sid) == sid


def test_sanitize_copy_strips_hallucinated_id_and_uses_ui_context():
    ui = {"target": "bug", "record_id": "1745123456789012345", "title": "登录问题"}
    params = {"target": "bug", "source_id": 9, "project_id": 1}
    sanitize_tool_entity_ids("copy", params, ui_context=ui)
    assert params["source_id"] == 1745123456789012345


def test_sanitize_create_strips_invalid_copy_from_bug_id():
    fields = {"copy_from_bug_id": 9, "title": "新 Bug"}
    params = {"target": "bug", "fields": fields}
    gr = {"first_bug_id": 1745123456789012999}
    sanitize_tool_entity_ids("create", params, grep_result=gr, result_context=gr)
    assert fields["copy_from_bug_id"] == 1745123456789012999
