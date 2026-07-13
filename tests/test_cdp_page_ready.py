# -*- coding: utf-8 -*-
import re

from agents.cdp.page_ready import is_project_detail_url, project_id_from_url


def test_is_project_detail_url():
    assert is_project_detail_url("http://localhost:5173/#/project-detail/2")
    assert not is_project_detail_url("http://localhost:5173/#/login")


def test_project_id_from_url():
    assert project_id_from_url("http://localhost:5173/#/project-detail/42") == 42
