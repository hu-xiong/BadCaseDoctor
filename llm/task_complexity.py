# -*- coding: utf-8 -*-
"""
规则推断任务复杂度与图片意图（不调 LLM，低延迟）。

AUTO_SMART=1（默认）时用多信号评分；关闭则走精简启发式。
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import List, Literal, Optional

TaskComplexity = Literal["simple", "standard", "complex"]
ImageIntent = Literal["ocr", "prototype", "react"]

# 写库 / 工具链：抬升复杂度
_MUTATE_KW = (
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
    "落库",
    "写入",
    "登记",
    "更新状态",
    "改成",
    "改为",
    "标为",
    "关闭缺陷",
    "解决bug",
    "解决 bug",
)

_ENTITY_KW = (
    "缺陷",
    "bug",
    "badcase",
    "测试用例",
    "用例",
    "卡片",
    "计划",
    "迭代",
)

_TOOLCHAIN_KW = (
    "终端",
    "命令行",
    "bash",
    "powershell",
    "cmd ",
    "shell",
    "cdp",
    "浏览器",
    "打开页面",
    "跑用例",
    "执行用例",
    "自动化",
    "本地代理",
    "git ",
    "npm ",
    "pip ",
    "docker",
)

_MULTI_STEP_RE = re.compile(
    r"(然后|接着|再|同时|并且|以及|下一步|随后|after that|then |and then|also )",
    re.I,
)

_FAQ_RE = re.compile(
    r"^(怎么|如何|怎样|什么是|为什么|是否|能否|可以吗|吗\？|\?|what |how |why |is |can )",
    re.I,
)

_FOLLOWUP_MARKERS = (
    "【本机终端",
    "[Client terminal",
    "【续作中断任务】",
    "【本机浏览器执行结果】",
)


@dataclass
class ComplexityAssessment:
    complexity: TaskComplexity
    score: int = 0
    signals: List[str] = field(default_factory=list)
    prefer_quality: bool = False
    prefer_cheap: bool = False
    block_downgrade: bool = False


def _max_chars() -> int:
    try:
        return int(os.getenv("SIMPLE_TASK_MAX_CHARS", "400"))
    except ValueError:
        return 400


def _smart_enabled() -> bool:
    v = (os.getenv("AUTO_SMART") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _clamp(n: int) -> int:
    return max(0, min(100, n))


def assess_task_complexity(
    *,
    channel: str,
    user_input: str = "",
    has_images: bool = False,
    image_intent: Optional[str] = None,
    has_pending_diff: bool = False,
    conversation_turns: int = 0,
    has_client_terminal_results: bool = False,
    is_resume: bool = False,
) -> ComplexityAssessment:
    """多信号评分；供 Auto 路由使用。"""
    text = (user_input or "").strip()
    low = text.lower()
    ch = (channel or "react").strip().lower()
    intent = (image_intent or "").strip().lower()
    signals: List[str] = []
    score = 40  # 中性起点

    if has_pending_diff:
        return ComplexityAssessment(
            complexity="complex",
            score=90,
            signals=["pending_diff"],
            prefer_quality=True,
            block_downgrade=True,
        )

    if ch == "summary":
        return ComplexityAssessment(
            complexity="simple",
            score=10,
            signals=["channel_summary"],
            prefer_cheap=True,
        )

    # --- 抬升 ---
    if any(m in text for m in _FOLLOWUP_MARKERS) or has_client_terminal_results:
        score += 18
        signals.append("client_followup")
    if is_resume:
        score += 22
        signals.append("resume_run")

    mutate_hits = [k for k in _MUTATE_KW if k in text or k in low]
    if mutate_hits:
        score += 32
        signals.append("mutate:" + mutate_hits[0])

    entity_hits = [k for k in _ENTITY_KW if k in text or k in low]
    if entity_hits and mutate_hits:
        score += 12
        signals.append("entity+mutate")
    elif entity_hits and ch == "react":
        score += 6
        signals.append("entity")

    tool_hits = [k for k in _TOOLCHAIN_KW if k in text or k in low]
    if tool_hits:
        score += 20
        signals.append("toolchain:" + tool_hits[0].strip())

    if _MULTI_STEP_RE.search(text):
        score += 12
        signals.append("multi_step")

    if has_images:
        if intent in ("react", "prototype"):
            score += 30
            signals.append(f"image_{intent}")
        elif intent == "ocr":
            score -= 8
            signals.append("image_ocr")
        else:
            score += 10
            signals.append("image")

    n = len(text)
    if n > _max_chars() * 2:
        score += 22
        signals.append("very_long")
    elif n > _max_chars():
        score += 12
        signals.append("long")

    if conversation_turns >= 6:
        score += 10
        signals.append("deep_thread")
    elif conversation_turns >= 3:
        score += 5
        signals.append("multi_turn")

    # --- 压低 ---
    if ch == "chat" and not has_images and not mutate_hits:
        score -= 18
        signals.append("chat_qa")

    if n <= 40 and not mutate_hits and not tool_hits and not has_images:
        score -= 16
        signals.append("short")

    if _FAQ_RE.search(text) and not mutate_hits and not tool_hits:
        score -= 14
        signals.append("faq_shape")

    if ch == "react" and not has_images and n <= _max_chars() and not mutate_hits and not tool_hits:
        score -= 10
        signals.append("react_light")

    score = _clamp(score)

    if score >= 62:
        complexity: TaskComplexity = "complex"
    elif score <= 28:
        complexity = "simple"
    else:
        complexity = "standard"

    prefer_quality = (
        complexity == "complex"
        or bool(mutate_hits and tool_hits)
        or has_pending_diff
        or (bool(tool_hits) and score >= 55)
    )
    prefer_cheap = complexity == "simple" and not prefer_quality
    block_downgrade = (
        prefer_quality
        or is_resume
        or has_client_terminal_results
        or bool(mutate_hits)
        or bool(tool_hits)
    )

    return ComplexityAssessment(
        complexity=complexity,
        score=score,
        signals=signals,
        prefer_quality=prefer_quality,
        prefer_cheap=prefer_cheap,
        block_downgrade=block_downgrade,
    )


def infer_task_complexity(
    *,
    channel: str,
    user_input: str = "",
    has_images: bool = False,
    image_intent: Optional[str] = None,
    has_pending_diff: bool = False,
    conversation_turns: int = 0,
    has_client_terminal_results: bool = False,
    is_resume: bool = False,
) -> TaskComplexity:
    """兼容旧接口：只返回档位。"""
    if not _smart_enabled():
        return _infer_legacy(
            channel=channel,
            user_input=user_input,
            has_images=has_images,
            image_intent=image_intent,
            has_pending_diff=has_pending_diff,
        )
    return assess_task_complexity(
        channel=channel,
        user_input=user_input,
        has_images=has_images,
        image_intent=image_intent,
        has_pending_diff=has_pending_diff,
        conversation_turns=conversation_turns,
        has_client_terminal_results=has_client_terminal_results,
        is_resume=is_resume,
    ).complexity


def _infer_legacy(
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
    for k in _MUTATE_KW:
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
        if not any(k in text or k in low for k in _MUTATE_KW):
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
