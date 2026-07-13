# -*- coding: utf-8 -*-
from llm.chat_messages import (
    build_chat_messages,
    normalize_chat_messages,
    prompt_to_messages,
    split_system_user_prompt,
)


def test_split_system_user_prompt():
    combined = """<system>
规则 A
</system>

<user_request>
改标题
</user_request>
"""
    sys, user = split_system_user_prompt(combined)
    assert sys == "规则 A"
    assert "<system>" not in user
    assert "改标题" in user


def test_prompt_to_messages_roles():
    msgs = prompt_to_messages("<system>你是助手</system>\n\n用户问题")
    assert msgs[0]["role"] == "system"
    assert msgs[0]["content"] == "你是助手"
    assert msgs[1]["role"] == "user"
    assert "用户问题" in msgs[1]["content"]


def test_normalize_chat_messages_splits_user_only():
    raw = [{"role": "user", "content": "<system>静态</system>\n\n动态"}]
    out = normalize_chat_messages(raw)
    assert len(out) == 2
    assert out[0]["role"] == "system"
    assert out[1]["role"] == "user"


def test_build_chat_messages_no_system():
    msgs = build_chat_messages(user="仅用户")
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
