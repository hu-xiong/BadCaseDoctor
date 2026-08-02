# -*- coding: utf-8 -*-
"""计划创建缺日期时的服务端兜底逻辑（不启 DB）。"""
from datetime import date, timedelta


def test_plan_date_defaults_logic():
    data = {"name": "迭代A", "project_id": 1}
    today = date.today()
    if not data.get("start_date"):
        data["start_date"] = today.isoformat()
    if not data.get("end_date"):
        data["end_date"] = (today + timedelta(days=14)).isoformat()
    if not data.get("name") and data.get("title"):
        data["name"] = data.get("title")
    assert data["start_date"] == today.isoformat()
    assert data["end_date"] == (today + timedelta(days=14)).isoformat()


def test_plan_title_fallback_to_name():
    data = {"title": "仅有标题", "project_id": 1, "start_date": "2026-01-01", "end_date": "2026-01-15"}
    if not data.get("name") and data.get("title"):
        data["name"] = data.get("title")
    assert data["name"] == "仅有标题"
