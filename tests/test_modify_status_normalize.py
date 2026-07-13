from agents.tools.modify_tool import ModifyTool


def test_normalize_status_glued_closed_reopen_maps_to_reopened():
    tool = ModifyTool(None)
    assert tool._normalize_status("已关闭重新打开", "bug") == "reopened"
    assert tool._normalize_status("  已关闭 重新打开 ", "bug") == "reopened"


def test_normalize_status_closed_and_reopen_separate():
    tool = ModifyTool(None)
    assert tool._normalize_status("已关闭", "bug") == "closed"
    assert tool._normalize_status("重新打开", "bug") == "reopened"
