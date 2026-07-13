# -*- coding: utf-8 -*-
from agents.cdp.auto_create import cdp_explore_auto_confirm
from agents.cdp.plan_resolver import resolve_cdp_project_plan_ids


class _Engine:
    project_id = 2
    plan_id = 5


def test_resolve_cdp_project_plan_ids_from_engine():
    pid, plid = resolve_cdp_project_plan_ids(engine=_Engine())
    assert pid == 2
    assert plid == 5


def test_resolve_cdp_project_plan_ids_from_page_url():
    pid, _ = resolve_cdp_project_plan_ids(
        observation={"page": {"url": "http://localhost:5173/#/project-detail/2"}},
    )
    assert pid == 2


def test_cdp_explore_auto_confirm_default_on():
    assert cdp_explore_auto_confirm() is True
