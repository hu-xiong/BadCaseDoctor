# -*- coding: utf-8 -*-
from agents.cdp.snapshot import AxSnapshotBuilder, _collect_descendant_names


def test_collect_descendant_names_from_button_children():
    by_id = {
        "b1": {"nodeId": "b1", "role": {"value": "button"}, "name": {"value": ""}, "childIds": ["t1", "t2"]},
        "t1": {"nodeId": "t1", "role": {"value": "StaticText"}, "name": {"value": "➕"}, "childIds": []},
        "t2": {"nodeId": "t2", "role": {"value": "StaticText"}, "name": {"value": "新建迭代"}, "childIds": []},
    }
    children_map = {"b1": ["t1", "t2"], "t1": [], "t2": []}
    name = _collect_descendant_names("b1", by_id=by_id, children_map=children_map)
    assert "新建迭代" in name


def test_snapshot_builder_merges_child_text_into_button_name():
    ax_nodes = [
        {"nodeId": "root", "role": {"value": "RootWebArea"}, "name": {"value": ""}, "childIds": ["b1"]},
        {
            "nodeId": "b1",
            "role": {"value": "button"},
            "name": {"value": ""},
            "backendDOMNodeId": 42,
            "childIds": ["t1"],
            "properties": [{"name": "focusable", "value": {"value": True}}],
        },
        {"nodeId": "t1", "role": {"value": "StaticText"}, "name": {"value": "新建迭代"}, "childIds": []},
    ]
    snap = AxSnapshotBuilder(max_nodes=50).build_from_cdp_nodes(
        ax_nodes, url="http://x", title="T", scope="interactive"
    )
    btn = next(n for n in snap.nodes if n.role == "button")
    assert "新建迭代" in btn.name
