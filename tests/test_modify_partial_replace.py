# -*- coding: utf-8 -*-
from agents.tools.modify_tool import ModifyTool


def _tool():
    return ModifyTool(db_session=None)


def test_partial_replace_in_reproduction_steps():
    tool = _tool()
    cur = "步骤1\n问登录问题答的不好\n步骤3"
    out, ok = tool._apply_partial_text_replace(
        cur, "问登录问题答的不好", "提问登录问题即可45", field="reproduction_steps"
    )
    assert ok
    assert out == "步骤1\n提问登录问题即可45\n步骤3"


def test_resolve_modification_uses_anchor_from_user_query():
    tool = _tool()
    original = {"reproduction_steps": "问进京证问题\n问登录问题答的不好"}
    uq = "问登录问题答的不好 复现步骤修改为 提问登录问题即可45"
    resolved = tool._resolve_modification_field_value(
        "reproduction_steps",
        {"new": "提问登录问题即可45"},
        original,
        natural_query=uq,
    )
    assert "问进京证问题" in resolved
    assert "提问登录问题即可45" in resolved
    assert "问登录问题答的不好" not in resolved
