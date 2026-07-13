# -*- coding: utf-8 -*-
"""聊天会话从系统模板项目迁移到用户默认克隆项目。"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_migrate_skips_when_no_template():
    with patch("utils.flask_runtime.get_app_module") as gam, patch(
        "utils.flask_runtime.get_db"
    ) as gdb:
        gam.return_value = SimpleNamespace(ChatSession=MagicMock(), Project=MagicMock())
        gdb.return_value.session.get.return_value = SimpleNamespace(
            cloned_from_template_id=None
        )
        from utils.project_clone import migrate_user_chat_sessions_from_template

        assert migrate_user_chat_sessions_from_template(2, 99) == 0


def test_migrate_moves_sessions_on_template():
    with patch("utils.flask_runtime.get_app_module") as gam, patch(
        "utils.flask_runtime.get_db"
    ) as gdb:
        ChatSession = MagicMock()
        gam.return_value = SimpleNamespace(ChatSession=ChatSession, Project=MagicMock())
        gdb.return_value.session.get.return_value = SimpleNamespace(
            cloned_from_template_id=1
        )
        q = ChatSession.query.filter_by.return_value
        q.update.return_value = 3

        from utils.project_clone import migrate_user_chat_sessions_from_template

        moved = migrate_user_chat_sessions_from_template(2, 99)
        assert moved == 3
        ChatSession.query.filter_by.assert_called_once_with(project_id=1, user_id=99)
        q.update.assert_called_once_with({"project_id": 2}, synchronize_session=False)
