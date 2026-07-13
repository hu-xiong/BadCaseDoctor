# -*- coding: utf-8 -*-
"""默认迭代补齐：克隆项目无 plan 时自动创建「迭代 1」。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_ensure_default_plan_creates_when_missing():
    from utils.project_clone import ensure_default_plan_for_project

    mock_plan_cls = MagicMock()
    created_row = SimpleNamespace(id=9001)

    def add_side_effect(row):
        row.id = 9001

    mock_plan_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None
    mock_plan_cls.side_effect = lambda **kw: created_row

    mock_db = MagicMock()
    mock_db.session.add = MagicMock(side_effect=lambda r: None)
    mock_db.session.flush = MagicMock()

    mock_mod = SimpleNamespace(Plan=mock_plan_cls)

    with patch("utils.flask_runtime.get_app_module", return_value=mock_mod), patch(
        "utils.flask_runtime.get_db", return_value=mock_db
    ):
        plan_id, created = ensure_default_plan_for_project(42, 7)

    assert created is True
    assert plan_id == 9001
    mock_db.session.add.assert_called_once()


def test_ensure_default_plan_skips_when_exists():
    from utils.project_clone import ensure_default_plan_for_project

    existing = SimpleNamespace(id=55)
    mock_plan_cls = MagicMock()
    mock_plan_cls.query.filter_by.return_value.order_by.return_value.first.return_value = existing
    mock_mod = SimpleNamespace(Plan=mock_plan_cls)
    mock_db = MagicMock()

    with patch("utils.flask_runtime.get_app_module", return_value=mock_mod), patch(
        "utils.flask_runtime.get_db", return_value=mock_db
    ):
        plan_id, created = ensure_default_plan_for_project(42, 7)

    assert created is False
    assert plan_id == 55
    mock_db.session.add.assert_not_called()
