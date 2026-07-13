# -*- coding: utf-8 -*-
"""无障碍树快照与 ref 分配。"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


_INTERACTIVE_ROLES = frozenset({
    "button", "link", "textbox", "searchbox", "combobox", "checkbox", "radio",
    "menuitem", "menuitemcheckbox", "menuitemradio", "tab", "switch", "slider",
    "spinbutton", "listbox", "option", "treeitem", "gridcell", "cell",
})


_SKIP_ROLES = frozenset({"none", "presentation", "generic", "InlineTextBox", "LineBreak"})


@dataclass
class SnapshotNode:
    ref: str
    role: str
    name: str = ""
    value: str = ""
    focusable: bool = False
    disabled: bool = False
    backend_node_id: Optional[int] = None
    node_id: Optional[str] = None
    selector_hint: str = ""
    """同 role+name 在快照中的序号，供 Playwright nth 精确定位。"""
    role_name_index: int = 0


@dataclass
class PageSnapshot:
    snapshot_id: str
    url: str
    title: str
    nodes: List[SnapshotNode] = field(default_factory=list)
    truncated: bool = False
    ref_index: Dict[str, SnapshotNode] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    scope: str = "interactive"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "url": self.url,
            "title": self.title,
            "nodes": [
                {
                    "ref": n.ref,
                    "role": n.role,
                    "name": n.name,
                    "value": n.value,
                    "focusable": n.focusable,
                    "disabled": n.disabled,
                    "backendNodeId": n.backend_node_id,
                    "selector_hint": n.selector_hint,
                    "role_name_index": n.role_name_index,
                }
                for n in self.nodes
            ],
            "truncated": self.truncated,
            "stats": {"exported": len(self.nodes)},
        }


def _ax_role_value(role: Optional[Dict]) -> str:
    if not role:
        return ""
    return str(role.get("value") or "")


def _collect_descendant_names(
    node_id: str,
    *,
    by_id: Dict[str, Dict],
    children_map: Dict[str, List[str]],
    max_depth: int = 4,
) -> str:
    """从子节点 StaticText 等拼出父控件可读名称（如「➕ 新建迭代」）。"""
    parts: List[str] = []

    def walk(nid: str, depth: int) -> None:
        if depth > max_depth:
            return
        raw = by_id.get(nid)
        if not raw:
            return
        r = _ax_role_value(raw.get("role")).lower()
        name_obj = raw.get("name")
        name = ""
        if isinstance(name_obj, dict):
            name = str(name_obj.get("value") or "").strip()
        elif name_obj:
            name = str(name_obj).strip()
        if name and r in ("statictext", "text", "inlinetextbox", "labeltext"):
            parts.append(name)
        for cid in children_map.get(nid, []):
            walk(cid, depth + 1)

    for cid in children_map.get(node_id, []):
        walk(cid, 0)
    return " ".join(parts).strip()[:200]


def _ax_prop(props: Optional[List[Dict]], name: str) -> Any:
    if not props:
        return None
    for p in props:
        if p.get("name") == name:
            return p.get("value", {}).get("value") if isinstance(p.get("value"), dict) else p.get("value")
    return None


def _is_interactive(role: Optional[Dict], props: Optional[List[Dict]]) -> bool:
    r = (role or {}).get("value", "") if role else ""
    r = str(r).lower()
    if r in _INTERACTIVE_ROLES:
        return True
    if _ax_prop(props, "focusable"):
        return True
    if _ax_prop(props, "editable"):
        return True
    return False


def _should_export_node(role: Optional[Dict], name: str, interactive_only: bool) -> bool:
    r = (role or {}).get("value", "") if role else ""
    r = str(r)
    if r in _SKIP_ROLES:
        return False
    if interactive_only and not _is_interactive(role, None):
        if not name.strip():
            return False
    if not interactive_only:
        return bool(name.strip()) or r.lower() in _INTERACTIVE_ROLES
    return True


class AxSnapshotBuilder:
    """从 CDP Accessibility.getFullAXTree 构建快照。"""

    def __init__(self, max_nodes: int = 200):
        self.max_nodes = max_nodes

    def build_from_cdp_nodes(
        self,
        ax_nodes: List[Dict[str, Any]],
        *,
        url: str,
        title: str,
        scope: str = "interactive",
    ) -> PageSnapshot:
        interactive_only = scope != "all"
        by_id: Dict[str, Dict] = {n["nodeId"]: n for n in ax_nodes if n.get("nodeId")}
        children_map: Dict[str, List[str]] = {}
        for n in ax_nodes:
            nid = n.get("nodeId")
            if not nid:
                continue
            children_map[nid] = list(n.get("childIds") or [])

        roots = [n for n in ax_nodes if n.get("role", {}).get("value") == "RootWebArea"]
        if not roots and ax_nodes:
            roots = [ax_nodes[0]]

        exported: List[SnapshotNode] = []
        ref_counter = 0
        truncated = False
        seen: Set[str] = set()
        role_name_counts: Dict[tuple, int] = {}

        def walk(node_id: str, depth: int = 0) -> None:
            nonlocal ref_counter, truncated
            if truncated or node_id in seen or depth > 40:
                return
            seen.add(node_id)
            raw = by_id.get(node_id)
            if not raw:
                return

            role = raw.get("role")
            props = raw.get("properties") or []
            name_obj = raw.get("name")
            name = ""
            if isinstance(name_obj, dict):
                name = str(name_obj.get("value") or "")
            elif name_obj:
                name = str(name_obj)

            value_obj = raw.get("value")
            value = ""
            if isinstance(value_obj, dict):
                value = str(value_obj.get("value") or "")
            elif value_obj:
                value = str(value_obj)

            disabled = bool(_ax_prop(props, "disabled"))
            focusable = bool(_ax_prop(props, "focusable") or _ax_prop(props, "editable"))
            backend_id = raw.get("backendDOMNodeId")

            if _should_export_node(role, name, interactive_only):
                if len(exported) >= self.max_nodes:
                    truncated = True
                    return
                ref_counter += 1
                r_val = _ax_role_value(role) or "unknown"
                r_val_l = r_val.lower()
                if not name.strip() and r_val_l in ("button", "link", "tab", "menuitem"):
                    child_name = _collect_descendant_names(
                        node_id,
                        by_id=by_id,
                        children_map=children_map,
                    )
                    if child_name:
                        name = child_name
                r_key = (r_val_l, name[:200])
                r_idx = role_name_counts.get(r_key, 0)
                role_name_counts[r_key] = r_idx + 1
                exported.append(
                    SnapshotNode(
                        ref=f"@e{ref_counter}",
                        role=str(r_val),
                        name=name[:200],
                        value=value[:500],
                        focusable=focusable,
                        disabled=disabled,
                        backend_node_id=int(backend_id) if backend_id is not None else None,
                        node_id=node_id,
                        role_name_index=r_idx,
                    )
                )

            for cid in children_map.get(node_id, []):
                walk(cid, depth + 1)

        for root in roots:
            rid = root.get("nodeId")
            if rid:
                walk(rid)

        snap_id = f"snap_{time.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        snap = PageSnapshot(
            snapshot_id=snap_id,
            url=url,
            title=title,
            nodes=exported,
            truncated=truncated,
            scope=scope,
        )
        snap.ref_index = {n.ref: n for n in exported}
        return snap

    def build_light_from_playwright_tree(
        self,
        tree: Optional[Dict[str, Any]],
        *,
        url: str,
        title: str,
        max_nodes: int = 32,
    ) -> PageSnapshot:
        """Playwright accessibility.snapshot 轻量树（stale_ref 恢复）。"""
        exported: List[SnapshotNode] = []
        counter = 0

        def walk(node: Optional[Dict], focused_branch: bool = False) -> None:
            nonlocal counter
            if not node or counter >= max_nodes:
                return
            role = str(node.get("role") or "")
            name = str(node.get("name") or "")
            val = str(node.get("value") or "")
            is_focused = focused_branch or bool(node.get("focused"))
            interactive = role.lower() in _INTERACTIVE_ROLES or bool(node.get("focused"))

            if interactive and (name or role.lower() in _INTERACTIVE_ROLES):
                counter += 1
                exported.append(
                    SnapshotNode(
                        ref=f"@e{counter}",
                        role=role,
                        name=name[:200],
                        value=val[:200],
                        focusable=True,
                        disabled=bool(node.get("disabled")),
                    )
                )

            for ch in node.get("children") or []:
                walk(ch, is_focused)

        walk(tree)
        snap_id = f"snap_light_{uuid.uuid4().hex[:8]}"
        snap = PageSnapshot(snapshot_id=snap_id, url=url, title=title, nodes=exported, scope="light")
        snap.ref_index = {n.ref: n for n in exported}
        return snap
