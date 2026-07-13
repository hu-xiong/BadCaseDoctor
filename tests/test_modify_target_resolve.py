# -*- coding: utf-8 -*-
from agents.modify_target_resolve import resolve_modify_target_id


_ID_UI = 718834681101411712
_ID_LOGIN = 718834681101499999


def test_user_query_beats_ui_when_title_matches_grep_hit():
    ctx = {
        "grep_result": {
            "first_badcase_id": _ID_UI,
            "navigation_ids": {"badcase": [_ID_UI, _ID_LOGIN]},
        },
        "badcase_list": [
            {"id": _ID_UI, "title": "对话有问题，问进京证不能很好答完整"},
            {"id": _ID_LOGIN, "title": "做登录bug2"},
        ],
    }
    ui = {"target": "badcase", "record_id": _ID_UI}
    uq = "问登录问题回答的不好 复现步骤改为 提问登录问题即可"
    tid = resolve_modify_target_id(
        "badcase",
        grep_result=ctx["grep_result"],
        result_context=ctx,
        ui_context=ui,
        user_input=uq,
        explicit_target_id=_ID_UI,
    )
    assert tid == _ID_LOGIN


def test_raw_grep_list_used_when_nav_list_only_ui_row():
    """导航过滤后 badcase_list 仅 UI 条，但 raw 含「登录」条时仍应改登录条。"""
    ctx = {
        "grep_result": {
            "first_badcase_id": _ID_UI,
            "navigation_ids": {"badcase": [_ID_UI]},
            "badcase_list": [{"id": _ID_UI, "title": "对话有问题，问进京证不能很好答完整"}],
        },
        "badcase_list": [{"id": _ID_UI, "title": "对话有问题，问进京证不能很好答完整"}],
        "grep_modify_raw_badcase_list": [
            {"id": _ID_UI, "title": "对话有问题，问进京证不能很好答完整"},
            {"id": _ID_LOGIN, "title": "做登录bug2"},
        ],
    }
    ui = {"target": "badcase", "record_id": _ID_UI}
    uq = "问登录问题答的不好 复现步骤修改为 提问登录问题即可45"
    tid = resolve_modify_target_id(
        "badcase",
        grep_result=ctx["grep_result"],
        result_context=ctx,
        ui_context=ui,
        user_input=uq,
        explicit_target_id=_ID_UI,
    )
    assert tid == _ID_LOGIN


def test_ui_detail_beats_llm_wrong_id_when_grep_only_other_badcase():
    """第二次常见：grep 只命中进京证，LLM 填其 id，但详情页已是登录条。"""
    _id_grep = 710034601191411712
    _id_login = 715068135836749824
    ctx = {
        "grep_result": {
            "first_badcase_id": _id_grep,
            "navigation_ids": {"badcase": [_id_grep]},
            "badcase_list": [
                {"id": _id_grep, "title": "对话有问题，问进京证不能很好答完整"},
            ],
        },
        "badcase_list": [
            {"id": _id_grep, "title": "对话有问题，问进京证不能很好答完整"},
        ],
    }
    ui = {
        "target": "badcase",
        "record_id": _id_login,
        "title": "问登录问题答的 不好",
        "view": "detail",
    }
    uq = "问登录问题答的不好 复现步骤修改为 提问登录问题即可456"
    tid = resolve_modify_target_id(
        "badcase",
        grep_result=ctx["grep_result"],
        result_context=ctx,
        ui_context=ui,
        user_input=uq,
        explicit_target_id=_id_grep,
    )
    assert tid == _id_login


def test_ui_record_when_query_ambiguous():
    ctx = {
        "grep_result": {"navigation_ids": {"badcase": [_ID_UI]}},
        "badcase_list": [{"id": _ID_UI, "title": "进京证对话"}],
    }
    ui = {"target": "badcase", "record_id": _ID_UI}
    tid = resolve_modify_target_id(
        "badcase",
        grep_result=ctx["grep_result"],
        result_context=ctx,
        ui_context=ui,
        user_input="把复现步骤改成 A",
    )
    assert tid == _ID_UI
