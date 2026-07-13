# -*- coding: utf-8 -*-
"""默认项目 owner 权限补齐。"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_ensure_project_admin_permission_creates_row_for_owner():
    from utils.project_clone import ensure_project_admin_permission

    proj = SimpleNamespace(user_id=7)
    mock_perm_cls = MagicMock()
    mock_perm_cls.query.filter_by.return_value.first.return_value = None

    mock_db = MagicMock()
    mock_mod = SimpleNamespace(Project=MagicMock(), ProjectPermission=mock_perm_cls)
    mock_mod.Project = MagicMock(return_value=proj)
    mock_db.session.get.return_value = proj

    with patch("utils.flask_runtime.get_app_module", return_value=mock_mod), patch(
        "utils.flask_runtime.get_db", return_value=mock_db
    ):
        ok = ensure_project_admin_permission(42, 7)

    assert ok is True
    mock_db.session.add.assert_called_once()
    mock_db.session.flush.assert_called_once()


def test_ensure_project_admin_permission_skips_non_owner():
    from utils.project_clone import ensure_project_admin_permission

    proj = SimpleNamespace(user_id=99)
    mock_db = MagicMock()
    mock_db.session.get.return_value = proj
    mock_mod = SimpleNamespace(Project=MagicMock(), ProjectPermission=MagicMock())

    with patch("utils.flask_runtime.get_app_module", return_value=mock_mod), patch(
        "utils.flask_runtime.get_db", return_value=mock_db
    ):
        ok = ensure_project_admin_permission(42, 7)

    assert ok is False
    mock_db.session.add.assert_not_called()


def test_ensure_project_admin_permission_upgrades_viewer_role():
    from utils.project_clone import ensure_project_admin_permission

    proj = SimpleNamespace(user_id=7)
    existing = SimpleNamespace(role="viewer")
    mock_perm_cls = MagicMock()
    mock_perm_cls.query.filter_by.return_value.first.return_value = existing

    mock_db = MagicMock()
    mock_db.session.get.return_value = proj
    mock_mod = SimpleNamespace(Project=MagicMock(), ProjectPermission=mock_perm_cls)

    with patch("utils.flask_runtime.get_app_module", return_value=mock_mod), patch(
        "utils.flask_runtime.get_db", return_value=mock_db
    ):
        ok = ensure_project_admin_permission(42, 7)

    assert ok is True
    assert existing.role == "admin"
    mock_db.session.flush.assert_called_once()
