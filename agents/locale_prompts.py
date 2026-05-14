# -*- coding: utf-8 -*-
"""UI 语言与 LLM 提示词包装：中英切换时约束模型输出语言。"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

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


def react_tools_chat_fallback_message(locale: Optional[str] = None) -> str:
    """大模型判定为纯对话但未生成 message 时的兜底（非关键词词典）。"""
    if is_english_locale(locale):
        return (
            "Hi! Glad you're here. I'm your assistant for tests and defects: I can help you search, "
            "review, edit, or create Bugs, test cases, and BadCases in this project. "
            "What would you like to do—in one sentence is enough."
        )
    return (
        "你好，很高兴为你服务。我是本项目的测试与缺陷助手，可以帮你查询、浏览、修改或新建 Bug、"
        "测试用例和 BadCase。你可以用一句话说说接下来想做什么，例如要查某条缺陷或改某个用例的状态。"
    )


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


def react_think_prelude_after_gate(locale: Optional[str]) -> str:
    """
    独立门控已判定走工具链之后、首轮 THINK 流式首 token 之前，下发一行可见 reasoning，
    缩短「仅零宽占位 → 首段模型输出」的主观空窗。
    """
    if is_english_locale(locale):
        return "Generating the task plan…\n"
    return "正在生成任务规划…\n"


def react_think_prelude_merge_intent(locale: Optional[str]) -> str:
    """合并门控进首轮 THINK 时，在模型输出 [GATE] 首 token 前推一行可见 reasoning。"""
    if is_english_locale(locale):
        return "Analyzing intent and planning…\n"
    return "正在分析意图并生成规划…\n"


def react_unified_duplicate_action_stall_message(
    locale: Optional[str],
    *,
    tool: str,
    window: int,
) -> str:
    if is_english_locale(locale):
        return (
            f"Stopped: the same tool call (`{tool}`) with identical parameters was repeated "
            f"{window} times in a row with no progress. Please change parameters or split the task."
        )
    return (
        f"已中断：连续 {window} 次使用相同工具「{tool}」且参数未变，判定为卡死。"
        "请调整参数或拆分任务后重试。"
    )


def react_unified_partial_max_rounds_message(locale: Optional[str], *, max_rounds: int) -> str:
    if is_english_locale(locale):
        return (
            f"Reached the maximum number of rounds ({max_rounds}). "
            "Partial results are shown below."
        )
    return f"已达到最大轮次上限（{max_rounds}），以下为部分完成结果。"


def react_unified_plan_step_skip_failures_message(
    locale: Optional[str],
    *,
    step_index_1based: int,
    max_retries: int,
) -> str:
    if is_english_locale(locale):
        return (
            f"Plan step {step_index_1based} failed {max_retries} times in a row; "
            "skipping to the next step."
        )
    return f"计划第 {step_index_1based} 步已连续失败 {max_retries} 次，已跳过并尝试后续步骤。"


def react_unified_strict_format_retry_suffix(locale: Optional[str]) -> str:
    """统一流解析失败时追加到 prompt 末尾，要求模型严格重输出三段式 XML。"""
    if is_english_locale(locale):
        return (
            "\n\n<system_reminder>\n"
            "Your previous reply was not structurally valid: missing a closing </decision> or any "
            "parsable <execute>/<tool>/<params> fields. Output again using exactly three segments: "
            "<observation>...</observation>, <thinking>...</thinking>, <decision>...</decision>, "
            "with every tag paired and <params> containing valid JSON only.\n"
            "</system_reminder>\n"
        )
    return (
        "\n\n<system_reminder>\n"
        "你上一段输出无法被解析：缺少闭合的 </decision>，或决策子标签不完整。"
        "请**重新完整输出**三段式：<observation>…</observation>、<thinking>…</thinking>、"
        "<decision>…</decision>；所有标签必须成对出现，<params> 内为合法 JSON。\n"
        "</system_reminder>\n"
    )


def react_phase_wait_message(kind: str, locale: Optional[str]) -> str:
    if kind == "decision_xml_parse":
        return "Parsing decision…" if is_english_locale(locale) else "正在解析决策结构…"
    if kind == "decision_function_call":
        return (
            "Resolving tool call…"
            if is_english_locale(locale)
            else "正在通过函数调用解析决策…"
        )
    if kind == "result_xml_parse":
        return "Parsing analysis…" if is_english_locale(locale) else "正在解析分析结果…"
    if kind == "tools_intent_gate":
        return (
            "Checking whether tools are needed…"
            if is_english_locale(locale)
            else "正在理解任务意图…"
        )
    if kind == "unified_round_think":
        return (
            "Waiting for the model…"
            if is_english_locale(locale)
            else "正在思考…"
        )
    return "…"


def react_unified_sse_xml_markers(locale: Optional[str]) -> Dict[str, str]:
    """
    统一流对外 SSE：不再输出语义标记（【观察开始】等），直接输出正文内容。
    标记保留为空字符串以兼容现有逻辑，但不对前端可见。
    """
    return {
        "thinking_start": "",
        "thinking_end": "",
        "observation_start": "",
        "observation_end": "",
        "decision_start": "",
        "decision_end": "",
        "task_plan_start": "",
        "task_plan_end": "",
    }


def react_decide_fc_first_token_hint(locale: Optional[str]) -> str:
    """
    FC 决策为整包返回，首包前无流式 token；先推一条可见占位到 agent_thought，避免 Thought 区空白数秒。
    """
    if is_english_locale(locale):
        return "Deciding next action…\n\n"
    return "正在决策下一步…\n\n"


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
            "You are a technical assistant. The UI language is English — write every line in English.\n"
            "Turn the raw execution results below into "
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

【语言】必须用简体中文写每一条（工具名可保留英文）。

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
            "You MUST write the entire summary in clear English (the UI language is English).\n"
            "Summarize the execution below in one short paragraph (2–4 sentences), like a Cursor Thought summary: "
            "natural English, no emoji, no bullet symbols.\n\n"
            f"Key findings / results:\n{findings_lines}\n\n"
            f"Stats: {steps_count} step(s) completed in {duration_sec:.2f}s."
        )
    return (
        f"""【语言】界面为中文：你必须用简体中文写完整总结，不要用英文写正文（工具名 grep/modify 等可保留英文）。

请将以下执行结果总结为一段话，2-4 句即可，像 Cursor 的 Thought 总结那样简洁自然。

关键发现/执行结果：
{findings_lines}

执行统计：完成 {steps_count} 步，耗时 {duration_sec:.2f}s。

要求：纯中文、无 emoji、无列表符号，直接一段话。"""
    )


# --- modify / grep 工具：用户可见文案（随 UI locale）---

_ZH_FIELD_LABELS: Dict[str, str] = {
    "title": "标题",
    "description": "描述",
    "status": "状态",
    "priority": "优先级",
    "severity": "严重程度",
    "reproduce_steps": "复现步骤",
    "expected_result": "期望结果",
    "actual_result": "实际结果",
    "assignee_id": "负责人",
    "assignee": "负责人",
    "owner": "负责人",
    "steps_to_reproduce": "复现步骤",
    "reproduction_steps": "复现步骤",
    "answer": "答案",
    "correct_answer": "正确答案",
    "badcase_result": "BadCase结果",
    "base_problem": "相似问题",
    "solution": "解决方式",
    "problem_reason": "问题原因",
    "case_type": "用例类型",
    "test_type": "测试类型",
    "preconditions": "前置条件",
    "steps": "测试步骤",
    "remark": "备注",
    "execution_result": "执行结果",
    "executed_by": "执行人",
    "estimated_time": "预估工时",
    "actual_time": "实际工时",
    "baseline": "基线",
}

_EN_FIELD_LABELS: Dict[str, str] = {
    "title": "Title",
    "description": "Description",
    "status": "Status",
    "priority": "Priority",
    "severity": "Severity",
    "reproduce_steps": "Steps to reproduce",
    "expected_result": "Expected result",
    "actual_result": "Actual result",
    "assignee_id": "Assignee",
    "assignee": "Assignee",
    "owner": "Assignee",
    "steps_to_reproduce": "Steps to reproduce",
    "reproduction_steps": "Reproduction steps",
    "answer": "Answer",
    "correct_answer": "Correct answer",
    "badcase_result": "BadCase result",
    "base_problem": "Related problem",
    "solution": "Solution",
    "problem_reason": "Root cause",
    "case_type": "Case type",
    "test_type": "Test type",
    "preconditions": "Preconditions",
    "steps": "Test steps",
    "remark": "Remark",
    "execution_result": "Execution result",
    "executed_by": "Executed by",
    "estimated_time": "Estimated time",
    "actual_time": "Actual time",
    "baseline": "Baseline",
}


def modify_field_label(field: str, locale: Optional[str]) -> str:
    fn = str(field)
    d = _EN_FIELD_LABELS if is_english_locale(locale) else _ZH_FIELD_LABELS
    return d.get(fn, fn)


def modify_assignee_unassigned(locale: Optional[str]) -> str:
    return "Unassigned" if is_english_locale(locale) else "未指派"


def modify_modifiable_fields_rows(target: str, locale: Optional[str]) -> List[Dict[str, str]]:
    d = _EN_FIELD_LABELS if is_english_locale(locale) else _ZH_FIELD_LABELS
    bug_keys = [
        "title",
        "description",
        "status",
        "priority",
        "severity",
        "assignee",
        "steps_to_reproduce",
        "expected_result",
        "actual_result",
    ]
    badcase_keys = [
        "title",
        "status",
        "priority",
        "assignee",
        "base_problem",
        "reproduction_steps",
        "answer",
        "correct_answer",
        "badcase_result",
        "solution",
        "problem_reason",
    ]
    testcase_keys = [
        "title",
        "status",
        "priority",
        "assignee",
        "preconditions",
        "steps",
        "remark",
        "baseline",
        "case_type",
        "test_type",
        "execution_result",
        "estimated_time",
        "actual_time",
    ]
    if target == "bug":
        keys = bug_keys
    elif target == "badcase":
        keys = badcase_keys
    elif target == "testcase":
        keys = testcase_keys
    else:
        return []
    return [{"field": k, "label": d.get(k, k)} for k in keys]


def modify_modifications_kv_summary(modifications: Dict[str, Any], locale: Optional[str]) -> str:
    if not modifications:
        return ""
    sep = ", " if is_english_locale(locale) else "、"
    parts = []
    for k, v in modifications.items():
        parts.append(f"{modify_field_label(str(k), locale)}:{v}")
    return sep.join(parts)


def modify_target_display_name(target: str, locale: Optional[str]) -> str:
    t = (target or "").strip().lower()
    if is_english_locale(locale):
        if t == "bug":
            return "Bug"
        if t == "testcase":
            return "test case"
        if t == "badcase":
            return "BadCase"
        if t == "card":
            return "Card"
        if t == "plan":
            return "Plan"
        return t or "record"
    if t == "bug":
        return "Bug"
    if t == "testcase":
        return "测试用例"
    if t == "badcase":
        return "BadCase"
    if t == "card":
        return "卡片"
    if t == "plan":
        return "迭代计划"
    return t or "记录"


def modify_tool_progress(key: str, locale: Optional[str], **kw: Any) -> str:
    if is_english_locale(locale):
        m = {
            "init": "Initializing modify…",
            "natural_query_lookup": "Resolving target via natural language…",
            "orm_fallback": "Text2SQL missed; trying ORM title match…",
            "located_validate": "Target located: target_id={target_id}, validating changes…",
            "fields_mapped": "Fields mapped: {keys}",
            "status_norm": "Status normalized: {orig} -> {norm}",
            "sandbox_enter": "Sandbox preview: loading original row…",
            "db_fetch": "Querying database for current row…",
            "sandbox_diff": "Original row loaded; building diff / preview…",
            "sandbox_sql": "Generating sandbox SQL preview…",
            "sandbox_wait_confirm": "Sandbox preview ready; waiting for confirmation…",
            "commit_start": "Applying changes: resolving users / assignee, writing ORM…",
            "commit_ok": "Changes saved",
            "commit_fail": "Save failed",
            "text2sql_load": "Fetching original row via Text2SQL…",
            "orm_load": "Fetching original row via ORM…",
            "querying_bug": "Loading Bug row…",
            "querying_badcase": "Loading BadCase row…",
            "querying_testcase": "Loading test case row…",
            "querying_card": "Loading Card row…",
            "readonly_snapshot": "Read-only snapshot: loading current row…",
        }
    else:
        m = {
            "init": "初始化 modify 参数…",
            "natural_query_lookup": "根据自然语言查询定位目标记录…",
            "orm_fallback": "Text2SQL 未定位到记录，尝试 ORM 标题模糊匹配…",
            "located_validate": "已定位目标: target_id={target_id}，开始校验修改内容…",
            "fields_mapped": "字段映射完成：{keys}",
            "status_norm": "状态值归一化：{orig} -> {norm}",
            "sandbox_enter": "进入沙箱预览：读取原始数据…",
            "db_fetch": "正在查询数据库获取当前记录…",
            "sandbox_diff": "已读取原始数据，正在生成 diff 与预览…",
            "sandbox_sql": "正在生成沙箱 SQL 预览…",
            "sandbox_wait_confirm": "沙箱预览完成，等待确认…",
            "commit_start": "开始落库：解析用户/负责人字段并写入 ORM…",
            "commit_ok": "落库完成",
            "commit_fail": "落库失败",
            "text2sql_load": "通过 Text2SQL 查询原始数据…",
            "orm_load": "通过 ORM 查询原始数据…",
            "querying_bug": "正在查询 Bug 记录…",
            "querying_badcase": "正在查询 BadCase 记录…",
            "querying_testcase": "正在查询测试用例记录…",
            "querying_card": "正在查询卡片（Card）记录…",
            "readonly_snapshot": "只读快照：加载当前记录…",
        }
    tmpl = m.get(key)
    if tmpl is None:
        return (
            f"Progress: {key}"
            if is_english_locale(locale)
            else f"进度：{key}"
        )
    try:
        return str(tmpl).format(**kw)
    except (KeyError, ValueError):
        return str(tmpl)


def modify_text2sql_row_question(table_name: str, target_id: int, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"Select the row from table {table_name} where id = {target_id}"
    return f"查询{table_name}表中ID为{target_id}的记录"


def modify_error_target_id_bad(target_id: Any, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"Invalid target_id format: {target_id}"
    return f"target_id 格式错误: {target_id}"


def modify_error_missing_params(
    target_id: Any, modifications: Any, target: str, project_id: Any, locale: Optional[str]
) -> tuple[str, str]:
    if is_english_locale(locale):
        err = f"Missing required parameters: target_id={target_id} or modifications={modifications}"
        hint = "Run grep first to locate rows, then call modify with a concrete target_id and modifications dict."
        if not target_id:
            hint += (
                "\n\nExample:\n"
                f"1. grep(target=\"{target}\", project_id={project_id})\n"
                "2. Read target_id from grep results\n"
                f"3. modify(target=\"{target}\", target_id=<id from grep>, modifications={{...}})"
            )
    else:
        err = f"缺少必要参数：target_id={target_id}或modifications={modifications}"
        hint = "请先使用 grep 工具查询并定位目标记录，然后再使用 modify 工具修改。"
        if not target_id:
            hint += (
                f"\n\n示例流程：\n1. 使用 grep 工具查询 {target}：grep(target=\"{target}\", project_id={project_id})\n"
                "2. 从 grep 结果中获取 target_id\n"
                f"3. 使用 modify 工具修改：modify(target=\"{target}\", target_id=<从grep获取的ID>, modifications={modifications})"
            )
    return err, hint


def modify_error_immutable_fields(locale: Optional[str]) -> tuple[str, str]:
    if is_english_locale(locale):
        hint = "You can edit status, title, priority, steps, assignee, expected/actual result, etc."
        msg = f"System fields such as type are fixed and cannot be modified. {hint}"
    else:
        hint = "可修改的字段包括：状态、期望结果、标题、优先级、复现步骤、负责人等。"
        msg = f"「类型」(type) 等字段为系统固定，不可修改。{hint}"
    return msg, hint


def modify_error_row_not_found(target: str, target_id: int, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"No {target} row found for ID={target_id}"
    return f"未找到{target} ID={target_id}"


def modify_message_sandbox_done(locale: Optional[str]) -> str:
    return (
        "Sandbox preview is ready. Confirm below to apply."
        if is_english_locale(locale)
        else "沙箱预览完成，请确认是否应用修改："
    )


def modify_summary_preview(target: str, target_id: int, mod_summary: str, locale: Optional[str]) -> str:
    name = modify_target_display_name(target, locale)
    if is_english_locale(locale):
        return f"Preview change to {name} (ID={target_id}): {mod_summary}"
    return f"预览修改{name}(ID={target_id})：{mod_summary}"


def modify_message_apply_ok(target: str, target_id: int, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"Successfully updated {target} ID={target_id}"
    return f"已成功修改{target} ID={target_id}"


def modify_message_apply_fail(locale: Optional[str]) -> str:
    return "Modification failed" if is_english_locale(locale) else "修改失败"


def modify_summary_applied(target: str, target_id: int, mod_summary: str, locale: Optional[str]) -> str:
    name = modify_target_display_name(target, locale)
    if is_english_locale(locale):
        return f"Updated {name} (ID={target_id}): {mod_summary}"
    return f"已修改{name}(ID={target_id})：{mod_summary}"


def modify_error_apply_exception(message: str, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"Modification failed: {message}"
    return f"修改失败: {message}"


def modify_error_batch_requires_modifications(locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return "Batch modify requires a non-empty modifications map for each item."
    return "批量修改时必须提供非空的 modifications（字段变更内容）。"


def modify_message_readonly_no_modifications(locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return "No field changes requested; showing current record as read-only."
    return "未指定要修改的字段，以下为当前记录的只读快照。"


def modify_summary_readonly_snapshot(target: str, target_id: int, locale: Optional[str]) -> str:
    name = modify_target_display_name(target, locale)
    if is_english_locale(locale):
        return f"Read-only snapshot: {name} (ID={target_id})"
    return f"只读快照：{name}（ID={target_id}）"


def grep_tool_progress(key: str, locale: Optional[str], **kw: Any) -> str:
    if is_english_locale(locale):
        m = {
            "init": "Initializing grep…",
            "phase1_plan_tree": "Phase 1: loading plan tree…",
            "phase1_plan_ready": "Phase 1: plan tree ready",
            "plan_material_read": "Loading records under current iteration plan…",
            "plan_material_ready": "Iteration plan materials ready",
            "phase1_badcase": "Phase 1: loading BadCase candidates…",
            "phase1_badcase_done": "BadCase candidates: {n}",
            "phase1_bug": "Phase 1: loading Bug candidates…",
            "phase1_bug_done": "Bug candidates: {n}",
            "phase1_tc": "Phase 1: loading test case candidates…",
            "phase1_tc_done": "Test case candidates: {n}",
            "phase1_card": "Phase 1: loading card candidates…",
            "phase1_card_done": "Card candidates: {n}",
            "phase2_assoc": "Phase 2: analyzing ownership / links…",
            "phase2_done": "Phase 2: analysis done",
            "phase3_compare": "Phase 3: building comparison report…",
            "phase3_done": "Phase 3: report ready",
            "nav_build": "Building navigation hints…",
            "locate_done_nav": "Locate finished; navigation ready",
            "assoc_start": "associate: three-way association…",
            "assoc_done": "associate: done",
            "compare_start": "compare: building comparison…",
            "compare_done": "compare: done",
            "locate_fail": "Locate failed: {err}",
        }
    else:
        m = {
            "init": "初始化 grep 参数…",
            "phase1_plan_tree": "阶段1：获取计划树…",
            "phase1_plan_ready": "阶段1：计划树已就绪",
            "plan_material_read": "读取当前迭代计划下的记录材料…",
            "plan_material_ready": "迭代计划材料已就绪",
            "phase1_badcase": "阶段1：检索 BadCase 候选…",
            "phase1_badcase_done": "BadCase 候选获取完成：{n} 条",
            "phase1_bug": "阶段1：检索 Bug 候选…",
            "phase1_bug_done": "Bug 候选获取完成：{n} 条",
            "phase1_tc": "阶段1：检索 TestCase 候选…",
            "phase1_tc_done": "TestCase 候选获取完成：{n} 条",
            "phase1_card": "阶段1：检索卡片候选…",
            "phase1_card_done": "卡片候选获取完成：{n} 条",
            "phase2_assoc": "阶段2：分析关联归属…",
            "phase2_done": "阶段2：关联分析完成",
            "phase3_compare": "阶段3：生成对比报告…",
            "phase3_done": "阶段3：对比报告生成完成",
            "nav_build": "生成导航指令…",
            "locate_done_nav": "定位完成，导航已生成",
            "assoc_start": "associate：开始三向关联分析…",
            "assoc_done": "associate：关联分析完成",
            "compare_start": "compare：开始生成对比报告…",
            "compare_done": "compare：对比报告生成完成",
            "locate_fail": "定位失败：{err}",
        }
    tmpl = m.get(key)
    if tmpl is None:
        # grep_tool 新增阶段键时若文案表未同步，勿让整次定位失败；重启服务后会走正常文案
        return (
            f"Progress: {key}"
            if is_english_locale(locale)
            else f"进度：{key}"
        )
    try:
        return str(tmpl).format(**kw)
    except (KeyError, ValueError):
        return str(tmpl)


def grep_plan_material_progress(key: str, locale: Optional[str], **kw: Any) -> str:
    if is_english_locale(locale):
        m = {
            "load_plans": "Plan materials: loading all plans for project…",
            "query_under_plans": "Plan materials: querying BadCase/Bug/TestCase under {n} plans (may take a few seconds)…",
            "assemble": "Plan materials: fetched BadCase={bc} Bug={b} TestCase={tc}, assembling tree…",
        }
    else:
        m = {
            "load_plans": "计划材料：加载项目下全部计划…",
            "query_under_plans": "计划材料：在 {n} 个相关计划下查询 BadCase/Bug/TestCase（数据量大时可能需数秒）…",
            "assemble": "计划材料：已取库 BadCase={bc} Bug={b} TestCase={tc}，正在组装树…",
        }
    return str(m[key]).format(**kw)


def grep_generate_locate_summary(
    locale: Optional[str],
    *,
    keywords: str,
    badcase_count: int,
    bug_count: int,
    testcase_count: int,
    related_badcase_count: int,
    related_bug_count: int,
    related_testcase_count: int,
    attribution_count: int,
    bug_location: Optional[List[Dict[str, Any]]],
    card_count: int = 0,
    related_card_count: int = 0,
    total_plans: int = 0,
    plan_material_loaded: bool = False,
    plan_material_root_name: Optional[str] = None,
) -> str:
    parts: List[str] = []
    is_query_all = not keywords or str(keywords).strip() == "" or keywords == "*"
    en = is_english_locale(locale)
    # 与 grep_tool 入参对齐；卡片/计划材料由 data 与 enrich 展示，此处不单列，避免与「相关计划」重复、贴近历史 grep 摘要
    _ = (card_count, related_card_count, total_plans, plan_material_loaded, plan_material_root_name)

    if badcase_count > 0:
        if is_query_all:
            parts.append(f"🔍 Found {badcase_count} BadCase record(s)" if en else f"🔍 找到 {badcase_count} 条BadCase")
        elif related_badcase_count > 0:
            parts.append(
                f"🔍 Located {related_badcase_count} BadCase (keywords: {keywords})"
                if en
                else f"🔍 定位 {related_badcase_count} 条BadCase（关键词：{keywords}）"
            )
        else:
            parts.append(
                f"🔍 Located {badcase_count} BadCase (keywords: {keywords})"
                if en
                else f"🔍 定位 {badcase_count} 条BadCase（关键词：{keywords}）"
            )

    if bug_count > 0:
        if related_bug_count > 0:
            if bug_location and len(bug_location) > 0:
                plan_name = bug_location[0].get("plan_name", "")
                if plan_name:
                    parts.append(
                        f"🐛 Located {related_bug_count} Bug; keywords “{keywords}”; plan: {plan_name}"
                        if en
                        else f"🐛 定位 {related_bug_count} 条Bug，关键词为“{keywords}”，位于计划【{plan_name}】"
                    )
                else:
                    parts.append(
                        f"🐛 Located {related_bug_count} Bug (keywords: {keywords})"
                        if en
                        else f"🐛 定位 {related_bug_count} 条Bug（关键词：{keywords}）"
                    )
            else:
                parts.append(
                    f"🐛 Located {related_bug_count} Bug (keywords: {keywords})"
                    if en
                    else f"🐛 定位 {related_bug_count} 条Bug（关键词：{keywords}）"
                )
        else:
            parts.append(
                f"🐛 Located {bug_count} Bug (keywords: {keywords})"
                if en
                else f"🐛 定位 {bug_count} 条Bug（关键词：{keywords}）"
            )

    if testcase_count > 0:
        if is_query_all:
            parts.append(f"📋 Found {testcase_count} test case(s)" if en else f"📋 找到 {testcase_count} 条测试用例")
        elif related_testcase_count > 0:
            parts.append(
                f"📋 Located {related_testcase_count} test case(s) (keywords: {keywords})"
                if en
                else f"📋 定位 {related_testcase_count} 条测试用例（关键词：{keywords}）"
            )
        else:
            parts.append(
                f"📋 Located {testcase_count} test case(s) (keywords: {keywords})"
                if en
                else f"📋 定位 {testcase_count} 条测试用例（关键词：{keywords}）"
            )

    if attribution_count > 0:
        parts.append(
            f"🎯 Generated {attribution_count} plan attribution suggestion(s)"
            if en
            else f"🎯 生成 {attribution_count} 条计划归属调整建议"
        )

    if parts:
        return "\n".join(parts)
    return "No matching records" if en else "未找到相关记录"


def grep_associate_summary(count: int, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"Established {count} association group(s)"
    return f"共建立 {count} 组关联关系"


def grep_compare_summary(count: int, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"{count} change item(s)"
    return f"共 {count} 项变更"


def react_batch_modify_preview_message(n: int, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"Batch change preview ({n} item(s)) — confirm in the sandbox below"
    return f"变更修改预览 {n} 条，请在下方确认"


def react_batch_modify_summary(
    n: int, target_type: str, modifications: Dict[str, Any], locale: Optional[str]
) -> str:
    name = modify_target_display_name(target_type, locale)
    part = modify_modifications_kv_summary(modifications, locale)
    if is_english_locale(locale):
        return f"Batch modify {n} {name}(s): {part}"
    return f"批量修改{n}条{name}：{part}"


def react_summarize_observation_nl_skipped_gate(why: str, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"Step skipped (stability gate): {why}. The scheduler will re-decide with better parameters."
    return f"步骤已跳过（稳定性门控）：{why}。调度将进入下一轮决策补参或改工具。"


def react_summarize_observation_nl_skipped_generic(locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return "Step skipped (params not ready or stability gate). The scheduler will re-decide."
    return "步骤已跳过（参数未就绪或稳定性门控）。调度将进入下一轮决策补参或改工具。"


def react_summarize_observation_nl_tool_failed(tool: Optional[str], err: str, locale: Optional[str]) -> str:
    t = tool or "tool"
    if is_english_locale(locale):
        return f"{t} failed: {err[:300]}. The scheduler will retry or switch tools."
    return f"{t} 执行失败：{err[:300]}。调度将基于错误信息自动重试或改道。"


def react_summarize_observation_nl_tool_failed_short(tool: Optional[str], locale: Optional[str]) -> str:
    t = tool or "tool"
    if is_english_locale(locale):
        return f"{t} failed. The scheduler will re-decide (retry / new params / different tool)."
    return f"{t} 执行失败。调度将进入下一轮决策（重试/改参/换工具）。"


def react_summarize_grep_done_empty(locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return "grep finished: no matching rows. Try different keywords or target."
    return "grep 完成：未命中相关记录。调度建议：收窄/改写关键词，或切换 target 后重查。"


def react_summarize_grep_done_hits(n: int, bug_n: int, bc_n: int, tc_n: int, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return (
            f"grep finished: ~{n} hit(s) (bug {bug_n} / badcase {bc_n} / testcase {tc_n}). "
            "Next: modify or create."
        )
    return (
        f"grep 完成：命中约 {n} 条（bug {bug_n} / badcase {bc_n} / testcase {tc_n}）。"
        "调度将据此定位下一步 modify/create。"
    )


def react_summarize_modify_done(ok: Any, confirmation_required: Any, diff_n: int, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return (
            f"modify finished: success={ok}, confirmation_required={confirmation_required}, "
            f"~{diff_n} diff line group(s)."
        )
    return (
        f"modify 完成：success={ok}，需确认={confirmation_required}，"
        f"变更项约 {diff_n} 条。"
    )


def react_summarize_tool_done_ok(tool: Optional[str], ok: Any, locale: Optional[str]) -> str:
    t = tool or "tool"
    if is_english_locale(locale):
        return f"{t} finished: success={ok}"
    return f"{t} 执行完成：success={ok}"


def react_executing_modify_about_to(
    target: Optional[str],
    target_id: Any,
    mods_preview: str,
    field_keys_hint: str,
    locale: Optional[str],
) -> str:
    """field_keys_hint: short list of raw keys for zh「字段：」行；mods_preview: Assignee:foo 等本地化摘要。"""
    if is_english_locale(locale):
        parts = []
        if target:
            parts.append(f"target={target}")
        if target_id not in (None, ""):
            parts.append(f"id={target_id}")
        head = "About to run modify"
        if parts:
            head += f" ({', '.join(parts)})"
        if mods_preview:
            return f"{head} — {mods_preview}…"
        return f"{head}…"
    parts = []
    if target:
        parts.append(f"目标：{target}")
    if target_id not in (None, ""):
        parts.append(f"ID：{target_id}")
    if field_keys_hint:
        parts.append(f"字段：{field_keys_hint}")
    detail = "；".join(parts)
    return f"即将执行 modify（{detail}）…" if detail else "即将执行 modify…"


def react_retry_grep_for_modify(locale: Optional[str]) -> str:
    return "Running grep to locate target rows…" if is_english_locale(locale) else "正在执行 grep 工具定位目标记录..."


def react_modify_executing_fallback_reason(locale: Optional[str]) -> str:
    return "In progress" if is_english_locale(locale) else "执行中"


def react_modify_single_record_reason(locale: Optional[str]) -> str:
    return "Single-record modify" if is_english_locale(locale) else "单个修改"


def react_modify_progress_wait(seconds: float, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"Modifying… waited {seconds:.0f}s"
    return f"修改中…已等待 {seconds:.0f}s"


def react_tool_missing_error(tool_name: str, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"Tool not found: {tool_name}"
    return f"工具不存在：{tool_name}"


def react_modify_timeout(seconds: int, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        return f"modify timed out (>{seconds}s). Check DB or network and retry."
    return f"modify 工具执行超时（>{seconds}s），请检查后端数据库或网络状态后重试。"


def react_executing_grep_about_to(
    keywords: Any, target: Any, mode: Any, locale: Optional[str]
) -> str:
    if is_english_locale(locale):
        parts = []
        if keywords:
            parts.append(f"keywords={keywords}")
        if target:
            parts.append(f"target={target}")
        if mode:
            parts.append(f"mode={mode}")
        detail = ", ".join(parts)
        return f"About to run grep ({detail})…" if detail else "About to run grep…"
    parts = []
    if keywords:
        parts.append(f"关键词：{keywords}")
    if target:
        parts.append(f"目标：{target}")
    if mode:
        parts.append(f"模式：{mode}")
    detail = "；".join(parts)
    return f"即将执行 grep（{detail}）…" if detail else "即将执行 grep…"


def react_executing_create_about_to(target: Any, natural_query: Any, locale: Optional[str]) -> str:
    if is_english_locale(locale):
        parts = []
        if target:
            parts.append(f"target={target}")
        if natural_query:
            parts.append(f"note={str(natural_query)[:80]}")
        detail = ", ".join(parts)
        return f"About to run create ({detail})…" if detail else "About to run create…"
    parts = []
    if target:
        parts.append(f"目标：{target}")
    if natural_query:
        parts.append(f"描述：{str(natural_query)[:80]}")
    detail = "；".join(parts)
    return f"即将执行 create（{detail}）…" if detail else "即将执行 create…"


def react_executing_database_query_about_to(
    natural_query: Any, query: Any, sql: Any, locale: Optional[str]
) -> str:
    if is_english_locale(locale):
        parts = []
        if natural_query:
            parts.append(f"NL={str(natural_query)[:80]}")
        elif query:
            parts.append(f"query={str(query)[:80]}")
        elif sql:
            parts.append(f"sql={str(sql)[:80]}")
        detail = ", ".join(parts)
        return f"About to run database_query ({detail})…" if detail else "About to run database_query…"
    parts = []
    if natural_query:
        parts.append(f"自然语言：{str(natural_query)[:80]}")
    elif query:
        parts.append(f"查询：{str(query)[:80]}")
    elif sql:
        parts.append(f"SQL：{str(sql)[:80]}")
    detail = "；".join(parts)
    return (
        f"即将执行 database_query（{detail}）…" if detail else "即将执行 database_query…"
    )


def incremental_running_summary_prompt(
    locale: Optional[str],
    prev_running_summary: str,
    step_index: int,
    tool: str,
    todo_text: str,
    nl_observation: str,
) -> str:
    """
    每步 observation 后合并生成「运行总览」Markdown；须含固定 ## 标题（与需求文档一致）。
    已确认段须概括本步客观结果，避免在无信息时滥用「- 无」。
    """
    prev = (prev_running_summary or "").strip()
    obs = (nl_observation or "").strip()
    todo = (todo_text or "").strip()[:2000]
    tool_s = str(tool or "").strip()
    step_n = int(step_index) + 1

    if is_english_locale(locale):
        prev_block = prev if prev else "(No prior summary)"
        body = f"""Merge new step into running summary. Output full Markdown.

Required format:
## Confirmed
## Next steps
## Risks and blockers
- Use "- " bullets for each section.
- **Confirmed** MUST list at least one bullet of **verifiable facts from this step**: tool name, success vs failure, and concrete highlights from the observation (e.g. grep hit counts/conclusion, modify preview target and field deltas, database row counts). If the observation text is non-empty or the tool clearly ran, do **not** leave Confirmed as only "- None".
- Use "- None" under Confirmed only when this step truly has nothing substantive to record.
- **Next steps**: pending actions (including "user must confirm/reject preview in UI"); may complement Confirmed but do not hide factual outcomes that belong under Confirmed.
- **Risks and blockers**: "- None" when there are none.
- Keep facts, no invention.
- **When the tool is `modify`**: any entity name (Bug / BadCase / test case / Card) in Confirmed must match the **fact line** `target` below; do **not** write BadCase just because the product name contains "BadCase"; IDs must match `target_id`.

Previous summary:
{prev_block}

New step (round {step_n}):
Tool: {tool_s}
Todo: {todo}
Observation:
{obs}

Output only the new summary."""
        return wrap_react_user_prompt(body, locale)

    prev_block = prev if prev else "（首次合并）"
    body = f"""合并本步观察到已有总览，输出完整 Markdown。

格式要求：
## 已确认
## 待办与建议下一步
## 风险与阻塞
- 每块用 "- " 列表。
- **已确认**：必须写出本步**可核对的客观结果**（至少一条）：工具名、成功/失败、观察摘要里的要点（如 grep 命中与结论、modify 预览涉及的记录与字段变化、查询返回规模等）。只要「观察」非空或本步工具已执行，就不得仅用「- 无」敷衍；仅在整步确实无任何实质信息时才写「- 无」。
- **待办与建议下一步**：写尚未完成的动作（含需在界面确认/拒绝的沙箱预览）；可与已确认互补，但不要把本应属于已确认的可核对事实只写在待办里。
- **风险与阻塞**：无则写「- 无」。
- 忠实合并，不编造。
- **modify 工具**：若观察摘要或待办中出现「Bug / BadCase / 测试用例」等实体名，**必须与下方「事实行」中的 target 一致**；**禁止**因产品名含「BadCase」就把 Bug 写成 BadCase；ID 须与 target_id 一致。

已有总览：
{prev_block}

本步（第 {step_n} 轮）：
工具：{tool_s}
待办：{todo}
观察：
{obs}

只输出新总览。"""
    return wrap_react_user_prompt(body, locale)


def enrich_grep_observation_nl_with_plan_names(
    base_nl: str,
    data: Dict[str, Any],
    locale: Optional[str],
) -> str:
    """
    增强 grep 观察结果的自然语言描述，添加计划名称信息。
    """
    if not base_nl:
        return ""
    
    result = base_nl
    
    plan_tree = data.get("plan_tree")
    if plan_tree:
        plan_names = []
        
        plans = plan_tree.get("plans")
        if isinstance(plans, list):
            for plan in plans:
                if isinstance(plan, dict):
                    plan_name = plan.get("plan_name") or plan.get("name")
                    if plan_name:
                        plan_names.append(str(plan_name))
        
        if plan_names:
            if is_english_locale(locale):
                result += f"\n\nRelated plans: {', '.join(plan_names[:5])}"
            else:
                result += f"\n\n相关计划：{', '.join(plan_names[:5])}"
    
    return result
