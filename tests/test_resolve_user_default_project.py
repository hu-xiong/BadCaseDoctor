# -*- coding: utf-8 -*-
"""resolve_user_default_project：无自有项目时应克隆，不返回仅被分享的项目。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_resolve_returns_owned_default():
    from utils.project_clone import resolve_user_default_project

    owned = SimpleNamespace(id=100, user_id=7)
    mock_project_cls = MagicMock()
    mock_project_cls.query.filter_by.return_value.order_by.return_value.first.side_effect = [
        owned,
    ]

    mock_mod = SimpleNamespace(Project=mock_project_cls)
    mock_db = MagicMock()

    with patch("utils.flask_runtime.get_app_module", return_value=mock_mod), patch(
        "utils.flask_runtime.get_db", return_value=mock_db
    ), patch("utils.project_clone.ensure_project_admin_permission", return_value=True):
        pid, created = resolve_user_default_project(7)

    assert pid == 100
    assert created is False


def test_resolve_clones_when_no_owned_even_if_shared_exists():
    from utils.project_clone import resolve_user_default_project

    mock_project_cls = MagicMock()
    # is_default query + owned query both None
    mock_project_cls.query.filter_by.return_value.order_by.return_value.first.return_value = None

    mock_mod = SimpleNamespace(Project=mock_project_cls)
    mock_db = MagicMock()

    with patch("utils.flask_runtime.get_app_module", return_value=mock_mod), patch(
        "utils.flask_runtime.get_db", return_value=mock_db
    ), patch("utils.project_clone.system_project_template_id", return_value=1), patch(
        "utils.project_clone.clone_system_project_for_user", return_value=9999
    ):
        pid, created = resolve_user_default_project(7)

    assert pid == 9999
    assert created is True
