# -*- coding: utf-8 -*-
"""BadCase modify 字段映射：steps 须归 reproduction_steps。"""
from unittest.mock import MagicMock

from agents.tools.modify_tool import ModifyTool


def test_badcase_steps_maps_to_reproduction_steps():
    tool = ModifyTool(MagicMock())
    assert tool._map_field_name("steps", "badcase") == "reproduction_steps"
    assert tool._map_field_name("测试步骤", "badcase") == "reproduction_steps"
    assert tool._map_field_name("复现步骤", "badcase") == "reproduction_steps"
    assert tool._map_field_name("steps", "testcase") == "steps"
    assert tool._map_field_name("steps", "bug") == "steps_to_reproduce"
