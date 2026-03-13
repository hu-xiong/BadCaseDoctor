"""
字段级 diff 工具：对比 before/after 行字典
"""

from __future__ import annotations

from typing import Any, Dict, List


def diff_rows(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    keys = set(before.keys()) | set(after.keys())
    changed: List[str] = []
    changes: Dict[str, Dict[str, Any]] = {}
    for k in sorted(keys):
        b = before.get(k)
        a = after.get(k)
        if b != a:
            changed.append(k)
            changes[k] = {"before": b, "after": a}
    return {"changed_fields": changed, "changes": changes}

