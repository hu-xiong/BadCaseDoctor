# -*- coding: utf-8 -*-
from agents.react_simplified import (
    _gather_skip_project_plan_lookup,
    _resolved_gather_name_hints,
)


def test_gather_skip_when_hints_complete():
    assert _gather_skip_project_plan_lookup(1, 2, "项目A", "计划B") is True
    assert _gather_skip_project_plan_lookup(1, 2, "", "计划B") is False
    assert _gather_skip_project_plan_lookup(0, 0, "", "") is True


def test_resolved_hints_from_ui_context():
    hp, hpl = _resolved_gather_name_hints(
        None,
        None,
        {"project_display_name": "P1", "plan_title": "迭代1"},
    )
    assert hp == "P1"
    assert hpl == "迭代1"
