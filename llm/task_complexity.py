# -*- coding: utf-8 -*-
"""规则推断任务复杂度与图片意图（不调 LLM）。"""
from __future__ import annotations

import os
import re
from typing import Literal, Optional

TaskComplexity = Literal["simple", "standard", "complex"]
ImageIntent = Literal["ocr", "prototype", "react"]

_COMPLEX_KW = (
    "创建",
    "新建",
    "生成",
    "修改",
    "删除",
    "复制",
    "grep",
    "modify",
    "create",
    "delete",
    "缺陷",
    "bug",
    "badcase",
    "测试用例",
    "用例",
    "原型",
    "原型图",
    "测试点",
    "落库",
    "写入",
    "登记",
    "卡片",
    "放到卡片",
    "放进卡片",
)


def _max_chars() -> int:
    try:
        return int(os.getenv("SIMPLE_TASK_MAX_CHARS", "400"))
    except ValueError:
        return 400


def infer_task_complexity(
    *,
    channel: str,
    user_input: str = "",
    has_images: bool = False,
    image_intent: Optional[str] = None,
    has_pending_diff: bool = False,
) -> TaskComplexity:
    text = (user_input or "").strip()
    low = text.lower()
    ch = (channel or "react").strip().lower()
    intent = (image_intent or "").strip().lower()

    if has_pending_diff:
        return "complex"

    if ch == "summary":
        return "simple"

    for k in _COMPLEX_KW:
        if k in text or k in low:
            if has_images and intent in ("react", "prototype"):
                return "complex"
            if k in ("grep", "modify", "create", "delete", "创建", "修改", "删除"):
                return "complex"

    if has_images:
        if intent in ("react", "prototype"):
            return "complex"
        if intent == "ocr" and len(text) <= _max_chars():
            return "simple"

    if len(text) > _max_chars():
        return "standard" if ch == "chat" else "complex"

    if ch == "chat" and not has_images:
        return "simple"

    if ch == "react" and not has_images and len(text) <= _max_chars():
        if not any(k in text or k in low for k in _COMPLEX_KW):
            return "simple"

    return "standard"


def classify_image_intent(text: str) -> ImageIntent:
    """与 routers/agent.py 内联逻辑一致，供选模前调用。"""
    t = (text or "").strip()
    low = t.lower()
    if any(
        k in t
        for k in (
            "提炼成bug",
            "提炼成 bug",
            "创建bug",
            "新建bug",
            "生成bug",
            "放到卡片",
            "写到卡片",
            "卡片里",
            "卡片中",
            "放进卡片",
        )
    ) or any(
        k in low
        for k in (
            "create bug",
            "new bug",
            "into card",
            "to card",
            "in card",
        )
    ):
        return "react"
    if not t:
        return "ocr"
    prototype_keys = (
        "原型",
        "原型图",
        "界面原型",
        "ui",
        "页面",
        "交互",
        "按钮",
        "输入框",
        "生成测试",
        "测试用例",
        "用例",
        "用例生成",
        "测试点",
        "测试步骤",
    )
    if any(k in t for k in prototype_keys):
        return "prototype"
    ocr_keys = (
        "图片说了什么",
        "图上写了什么",
        "图里写了什么",
        "图片写了什么",
        "识别文字",
        "提取文字",
        "读字",
        "ocr",
        "识别一下",
        "这张图是什么",
    )
    if any(k in t for k in ocr_keys):
        return "ocr"
    if any(k in t for k in ("图片", "图上", "这张图", "图里")):
        return "ocr"
    return "react"
