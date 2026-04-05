# -*- coding: utf-8 -*-
"""元工具：按需返回已注册工具的完整 description（渐进式披露，省首轮 THINK token）。"""
from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from agents.tool_registry import BaseTool

if TYPE_CHECKING:
    from agents.tool_registry import ToolRegistry as _ToolRegistry


class GetToolDescriptionTool(BaseTool):
    def __init__(self, registry: "_ToolRegistry"):
        super().__init__(
            name="get_tool_description",
            description=(
                "元工具：按名称返回某个已注册工具的完整说明（参数、用法、注意点）。"
                "当系统提示里对工具仅为短索引、不确定如何填参时，先调用本工具再调用目标工具。"
                "参数：tool_name（必填），与注册名一致，如 grep、modify、create_bug 等。"
            ),
        )
        self._registry = registry

    async def execute(self, **kwargs: Any) -> Dict[str, Any]:
        name = (kwargs.get("tool_name") or kwargs.get("name") or "").strip()
        if not name:
            return {"success": False, "error": "缺少 tool_name"}
        t = self._registry.get(name)
        if t is None:
            known = ", ".join(sorted(self._registry.tools.keys())[:40])
            return {
                "success": False,
                "error": f"未知工具: {name}",
                "hint": f"已注册工具示例（节选）: {known}",
            }
        desc = (getattr(t, "description", None) or "").strip()
        return {
            "success": True,
            "tool_name": name,
            "full_description": desc,
        }
