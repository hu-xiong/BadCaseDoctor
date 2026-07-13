# -*- coding: utf-8 -*-
"""chat_message 助手消息 upsert 字段映射与落库逻辑。"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from app_services.chat_message_persist import (
    apply_assistant_fields_to_message,
    assistant_fields_from_client,
    upsert_assistant_chat_message,
)


def test_assistant_fields_from_client_json_columns():
    data = {
        "content": "done",
        "steps": [{"title": "cdp", "status": "completed"}],
        "modify_navigation": {"is_create": True, "confirmation_required": True},
        "llm_model": "deepseek-chat",
    }
    fields = assistant_fields_from_client(data)
    assert fields["content"] == "done"
    assert json.loads(fields["steps"])[0]["title"] == "cdp"
    nav = json.loads(fields["modify_navigation"])
    assert nav["is_create"] is True
    assert fields["llm_model"] == "deepseek-chat"


def test_assistant_fields_from_client_accepts_pre_stringified_json():
    steps_json = json.dumps([{"title": "create"}])
    fields = assistant_fields_from_client({"steps": steps_json})
    assert fields["steps"] == steps_json


def test_upsert_assistant_creates_new_message_when_no_id():
    db = MagicMock()
    session = SimpleNamespace(user_id=7, updated_at=None)
    db.session.get.side_effect = lambda model, sid: session if sid == 3 else None

    created = []

    class ChatMessage:
        def __init__(self, **kwargs):
            self.id = 99
            for k, v in kwargs.items():
                setattr(self, k, v)
            created.append(self)

    def add(msg):
        created.append(msg)

    db.session.add = add
    db.session.commit = MagicMock()

    mid = upsert_assistant_chat_message(
        db=db,
        ChatMessage=ChatMessage,
        ChatSession=object,
        session_id=3,
        user_id=7,
        fields={"content": "处理中…", "steps": "[]"},
        message_id=None,
    )
    assert mid == 99
    assert created
    assert created[0].is_user is False
    assert created[0].session_id == 3


def test_upsert_assistant_updates_existing_message():
    db = MagicMock()
    session = SimpleNamespace(user_id=1, updated_at=None)
    msg = SimpleNamespace(
        id=42,
        session_id=5,
        is_user=False,
        content="old",
        steps=None,
    )

    def get(model, pk):
        if pk == 5:
            return session
        if pk == 42:
            return msg
        return None

    db.session.get = get
    db.session.add = MagicMock()
    db.session.commit = MagicMock()

    class ChatMessage:
        pass

    mid = upsert_assistant_chat_message(
        db=db,
        ChatMessage=ChatMessage,
        ChatSession=object,
        session_id=5,
        user_id=1,
        fields={"content": "new", "steps": "[{}]"},
        message_id=42,
    )
    assert mid == 42
    assert msg.content == "new"
    assert msg.steps == "[{}]"
    db.session.add.assert_not_called()


def test_apply_assistant_fields_to_message():
    msg = SimpleNamespace(content="", final_response="")
    apply_assistant_fields_to_message(msg, {"content": "x", "final_response": "y"})
    assert msg.content == "x"
    assert msg.final_response == "y"
