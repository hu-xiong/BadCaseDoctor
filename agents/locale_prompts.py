# -*- coding: utf-8 -*-
"""UI 语言与 LLM 提示词包装：中英切换时约束模型输出语言。"""
from __future__ import annotations

from typing import Optional

_EN_HEADER_REACT = """[UI Language: English]
The user is using the application in English. For every natural-language segment YOU write
(planning explanation, thoughts, summaries, findings, user-facing messages), use clear **English**.
Keep required XML tags, tool names (grep, modify, create, …), and structured fields exactly as specified.
Todo text inside <item> should remain executable (tool keywords as required); you may describe intent in English.
If the user wrote in Chinese or another language, still explain in English.

---

"""

_EN_HEADER_GENERAL = """[UI Language: English]
Reply in English for all user-visible explanations. The user may write in any language.

---

"""


def normalize_locale(locale: Optional[str]) -> str:
    """返回 'zh' 或 'en'。"""
    if not locale:
        return "zh"
    s = str(locale).strip().lower().replace("_", "-")
    if s.startswith("en"):
        return "en"
    return "zh"


def is_english_locale(locale: Optional[str]) -> bool:
    return normalize_locale(locale) == "en"


def wrap_react_user_prompt(prompt: str, locale: Optional[str]) -> str:
    """套在 ReAct think/decide/observe 等长提示前，英文 UI 时要求模型用英文写面向用户的说明。"""
    if not prompt:
        return prompt
    if not is_english_locale(locale):
        return prompt
    return _EN_HEADER_REACT + prompt


def wrap_general_user_prompt(prompt: str, locale: Optional[str]) -> str:
    """普通聊天 / 路由类单轮提示。"""
    if not prompt:
        return prompt
    if not is_english_locale(locale):
        return prompt
    return _EN_HEADER_GENERAL + prompt


def vision_prototype_prompt(locale: Optional[str]) -> str:
    """原型图 → 测试用例 的视觉提示。"""
    if is_english_locale(locale):
        return """You are a UI wireframe analyst. The user uploaded a wireframe image for test-case generation.

Describe the image using this structure:
1. **Page type** (login, list, form, etc.)
2. **Interactive elements**: type (button/input/link/…), order, labels or placeholders
3. **User flows** the tester should cover
4. **Notes**: required fields, validation, etc.

Output in English, structured and clear for downstream test-case generation."""
    return """你是一个 UI 原型图分析助手。用户上传了一张原型图，需要根据它生成测试用例。

请按以下结构描述图片内容：
1. **页面类型**：如登录页、列表页、表单页等
2. **可交互元素**：
   - 类型（按钮/输入框/链接/下拉/单选/多选等）
   - 位置/顺序
   - 文案或占位符
3. **业务流程**：用户可能进行的操作路径
4. **注意事项**：如必填项、校验规则等（如有）

输出要求：清晰、结构化，便于后续模型生成测试用例。"""


def vision_image_block_labels(locale: Optional[str]) -> tuple[str, str, str]:
    """返回 (图片描述前缀, 用户标签, 空输入时的默认用户句)。"""
    if is_english_locale(locale):
        return (
            "[Image description]",
            "[User]",
            "Please handle my intent based on the image descriptions above.",
        )
    return (
        "[图片描述]",
        "[用户]",
        "请根据上述图片描述处理我的意图。",
    )


def react_phase_wait_message(kind: str, locale: Optional[str]) -> str:
    if kind == "decision_xml_parse":
        return "Parsing decision…" if is_english_locale(locale) else "正在解析决策结构…"
    if kind == "result_xml_parse":
        return "Parsing analysis…" if is_english_locale(locale) else "正在解析分析结果…"
    return "…"


def react_observe_section_header(locale: Optional[str]) -> str:
    return "\n\n[Observation]\n" if is_english_locale(locale) else "\n\n【观察】\n"


def react_fallback_decision_line(tool: str, execute, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"Decision: tool `{tool or '?'}`, execute={execute!r}."
    return f"决策：工具 `{tool or '?'}`，execute={execute!r}。"


def summary_prompt_technical(locale: Optional[str], payload: str) -> str:
    if is_english_locale(locale):
        return (
            "You are a technical assistant. Summarize the execution results below into concise, "
            "human-readable key findings.\n\n"
            f"{payload}"
        )
    return (
        f"""你是一个技术助手，需要将下面的技术执行结果总结为简洁、人类可读的关键发现。

{payload}"""
    )


def summary_prompt_cursor_style(locale: Optional[str], payload: str) -> str:
    if is_english_locale(locale):
        return (
            "Summarize the execution results below in one short paragraph (2–4 sentences), "
            "like a Cursor Thought summary: concise and natural.\n\n"
            f"{payload}"
        )
    return (
        f"""将以下执行结果总结为一段话，2-4 句即可，像 Cursor 的 Thought 总结那样简洁自然。

{payload}"""
    )


def react_findings_bulleted_summary_prompt(locale: Optional[str], numbered_findings: str) -> str:
    """主循环结束后：条目化关键发现（带 emoji）。"""
    if is_english_locale(locale):
        return (
            "You are a technical assistant. Turn the raw execution results below into "
            "3–5 concise key findings in English.\n\n"
            f"Raw results:\n{numbered_findings}\n\n"
            "Requirements:\n"
            "1. Pick the 3–5 most important points\n"
            "2. Short English, each line at most ~50 characters worth of content\n"
            "3. Prefer business wording over jargon\n"
            "4. Start each line with an emoji (🔍/🐛/🎯/📊)\n"
            "5. Output the list only, no extra commentary\n\n"
            "Example:\n"
            "🔍 Found 5 login-related bugs\n"
            "🐛 Two high-priority defects located"
        )
    return (
        f"""你是一个技术助手，需要将下面的技术执行结果总结为简洁、人类可读的关键发现。

原始结果：
{numbered_findings}

要求：
1. 提取最重要的 3-5 条关键信息
2. 用简洁的中文表述，每条不超过50字
3. 避免技术术语，使用业务语言
4. 每条以emoji开头（🔍/🐛/🎯/📊）
5. 直接输出列表，不需要额外说明

格式示例：
🔍 查询到 5 个登录相关的Bug
🐛 定位 2 条高优先级缺陷
🎯 建议将 3 个Bug调整到登录计划"""
    )


def react_unified_final_summary_prompt(
    locale: Optional[str], findings_lines: str, steps_count: int, duration_sec: float
) -> str:
    """一段话统一总结（Cursor 式）。"""
    if is_english_locale(locale):
        return (
            "Summarize the execution below in one short paragraph (2–4 sentences), like a Cursor Thought summary: "
            "natural English, no emoji, no bullet symbols.\n\n"
            f"Key findings / results:\n{findings_lines}\n\n"
            f"Stats: {steps_count} step(s) completed in {duration_sec:.2f}s."
        )
    return (
        f"""将以下执行结果总结为一段话，2-4 句即可，像 Cursor 的 Thought 总结那样简洁自然。

关键发现/执行结果：
{findings_lines}

执行统计：完成 {steps_count} 步，耗时 {duration_sec:.2f}s。

要求：纯中文、无 emoji、无列表符号，直接一段话。"""
    )
