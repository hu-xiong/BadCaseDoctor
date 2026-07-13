"""modify 预览读行：Bug 长文本字段始终全量加载。"""

from agents.tools.modify_tool import ModifyTool


def test_preview_fetch_flags_always_load_long_text():
    flags = ModifyTool._preview_fetch_flags("bug", {"status": {"new": "closed"}})
    assert flags["load_long_text"] is True

    flags2 = ModifyTool._preview_fetch_flags(
        "bug", {"expected_result": {"new": "x"}}
    )
    assert flags2["load_long_text"] is True
