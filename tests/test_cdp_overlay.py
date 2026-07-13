# -*- coding: utf-8 -*-
"""CDP 弹窗 overlay 辅助逻辑。"""

from agents.cdp.overlay import overlay_close_button_nodes


def test_overlay_close_button_nodes_prefers_cancel():
    nodes = [
        {"ref": "@e1", "role": "button", "name": "确定"},
        {"ref": "@e2", "role": "button", "name": "取消"},
        {"ref": "@e3", "role": "button", "name": "✕"},
        {"ref": "@e4", "role": "textbox", "name": "计划名称"},
    ]
    out = overlay_close_button_nodes(nodes)
    refs = [n["ref"] for n in out]
    assert "@e2" in refs
    assert "@e3" in refs
    assert "@e1" not in refs
    assert "@e4" not in refs
