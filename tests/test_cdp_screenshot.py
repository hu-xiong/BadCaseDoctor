# -*- coding: utf-8 -*-
from agents.cdp.auto_create import build_interaction_issue_create_fields
from agents.cdp.screenshot import format_steps_html_with_screenshot


def test_format_steps_html_with_screenshot():
    html = format_steps_html_with_screenshot(
        "点击 @e1 (button/编辑) 失败",
        "/api/uploads/image/cdp/test.png",
    )
    assert "点击 @e1" in html
    assert '<img src="/api/uploads/image/cdp/test.png"' in html
    assert "rte-inline-img" in html


def test_interaction_issue_fields_include_screenshot():
    fields = build_interaction_issue_create_fields(
        {
            "message": "点击 @e27 (option/全部类型) 失败：box model",
            "screenshot_url": "/api/uploads/image/cdp/s1.png",
            "role": "option",
            "name": "全部类型",
        },
        plan_id=2,
        index=0,
    )
    assert "box model" in fields["steps_to_reproduce"]
    assert "/api/uploads/image/cdp/s1.png" in fields["steps_to_reproduce"]
    assert fields["plan_id"] == 2
