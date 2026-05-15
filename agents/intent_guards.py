# agents/intent_guards.py
"""
意图门控：区分「改已有」与「新建」。
- 启发式明确 → 直接用 bucket（modify / create）
- 模糊（两者都像或都不明显）→ 可选调用更强模型仲裁（见 arbitrate_modify_or_create）
"""
from __future__ import annotations

import json
import os
import re
from typing import Literal, Optional, Tuple

IntentBucket = Literal["modify", "create", "unclear"]


def agent_testing_mode() -> bool:
    """
    AI 测试助手模式：减少「改已有 vs 新建」前置澄清，把分流交给 THINK 内 [GATE]（见 AGENT_TESTING_MODE）。
    开启：AGENT_TESTING_MODE=1
    """
    return (os.getenv("AGENT_TESTING_MODE", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


# 明显在改已有数据 / 状态 / 负责人（中英）
_MODIFY_HINTS_ZH = (
    "修改",
    "改",
    "更新",
    "变更",
    "改为",
    "改成",
    "变成",
    "变为",
    "设为",
    "调整",
    "更正",
    "草稿",
    "生效",
    "评审",
    "归档",
    "关闭",
    "解决",
    "指派",
    "负责人",
    "状态",
    "置为",
    "切换为",
)
_MODIFY_HINTS_EN = (
    "assignee",
    "status",
    "draft",
    "active",
    "review",
    "archived",
    "resolved",
    "closed",
    "reopen",
)

# 强「新建一条」表述（避免标题里「新增的」误触）
_STRONG_CREATE_RES = (
    re.compile(r"创建\s*(?:一个|一条)?\s*测试用例"),
    re.compile(r"新建\s*(?:一个|一条)?\s*测试用例"),
    re.compile(r"添加\s*(?:一个|一条)?\s*测试用例"),
    re.compile(r"新增\s*(?:一个|一条)\s*测试用例"),
    re.compile(r"创建\s*(?:一个|一条)?\s*(?:bug|缺陷)"),
    re.compile(r"新建\s*(?:一个|一条)?\s*(?:bug|缺陷)"),
    re.compile(r"添加\s*(?:一个|一条)?\s*(?:bug|缺陷)"),
    re.compile(r"新增\s*(?:一个|一条)\s*(?:bug|缺陷)"),
    re.compile(r"创建\s*(?:一个|一条)?\s*bad\s*case", re.I),
    re.compile(r"新建\s*(?:一个|一条)?\s*bad\s*case", re.I),
    re.compile(r"添加\s*(?:一个|一条)?\s*bad\s*case", re.I),
    re.compile(r"create\s+new\s+(?:test\s*case|bug|badcase)", re.I),
)


def user_modify_intent(user_input: Optional[str]) -> bool:
    if not user_input or not isinstance(user_input, str):
        return False
    u = user_input.strip()
    if not u:
        return False
    low = u.lower()
    if any(h in u for h in _MODIFY_HINTS_ZH):
        return True
    if any(h in low for h in _MODIFY_HINTS_EN):
        return True
    return False


def user_strong_create_intent(user_input: Optional[str]) -> bool:
    """明确的「新建一条」类请求；标题里「一个新增的xxx」不应命中。"""
    if not user_input or not isinstance(user_input, str):
        return False
    u = user_input.strip()
    if not u:
        return False
    for rx in _STRONG_CREATE_RES:
        if rx.search(u):
            return True
    return False


def intent_bucket(user_input: Optional[str]) -> IntentBucket:
    """明确修改 / 明确新建 / 需仲裁。"""
    m = user_modify_intent(user_input)
    c = user_strong_create_intent(user_input)
    if m and not c:
        return "modify"
    if c and not m:
        return "create"
    return "unclear"


def _looks_like_readonly_query(user_input: Optional[str]) -> bool:
    """偏查询/列举，不应因「意图模糊」打断让用户澄清改 vs 新建。"""
    if not user_input or not isinstance(user_input, str):
        return True
    u = user_input.strip()
    if not u:
        return True
    low = u.lower()
    zh_markers = (
        "列出",
        "查看",
        "看一下",
        "看下",
        "看看",
        "阅读",
        "显示",
        "有哪些",
        "什么",
        "统计",
        "导出",
        "介绍一下",
        "说明一下",
        "讲讲",
        "搜一下",
        "搜索",
        "查找",
        "找一下",
        "帮我找",
    )
    en_markers = ("list all", "list the", "show me", "what are", "how many", "search for", "find all")
    if any(m in u for m in zh_markers):
        return True
    if any(m in low for m in en_markers):
        return True
    return False


def mentions_case_or_bug_context(user_input: Optional[str]) -> bool:
    """与 Bug/用例/BadCase 等业务对象相关，才有「改已有 vs 新建」的歧义风险。"""
    if not user_input or not isinstance(user_input, str):
        return False
    u = user_input
    low = u.lower()
    if any(x in u for x in ("测试用例", "用例", "缺陷", "坏例", "BadCase", "bad case")):
        return True
    if "bug" in low or "badcase" in low or "testcase" in low or "test case" in low:
        return True
    if any(x in u for x in ("那条", "这条", "该条", "这个单", "那个单", "工单", "记录")):
        return True
    return False


def needs_modify_vs_create_clarification(user_input: Optional[str]) -> bool:
    """
    是否应在执行 ReAct 前请用户澄清「改已有」还是「新建」。
    - 同时命中修改意图与强新建：直接冲突
    - 意图桶为 unclear 且涉及用例/Bug 等、且不像纯查询：避免静默猜错
    环境变量 INTENT_CLARIFY_ENABLED=0 可关闭。
    AGENT_TESTING_MODE=1 时跳过本澄清（避免与「测试任务分流」重复门控）。
    """
    if agent_testing_mode():
        return False
    if (os.getenv("INTENT_CLARIFY_ENABLED", "1") or "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    if not user_input or not isinstance(user_input, str):
        return False
    u = user_input.strip()
    if not u:
        return False
    # 1) 明确冲突：又要改又要新建一条
    if user_modify_intent(u) and user_strong_create_intent(u):
        return True
    # 2) 模糊 + 业务相关 + 非纯查询 → 请用户说清楚，不浪费 THINK/工具
    if intent_bucket(u) == "unclear" and mentions_case_or_bug_context(u) and not _looks_like_readonly_query(u):
        return True
    return False


def intent_clarification_message(user_input: Optional[str], locale: Optional[str] = None) -> str:
    """与 needs_modify_vs_create_clarification 配套的提示文案。"""
    from .locale_prompts import is_english_locale

    u = (user_input or "").strip()
    if is_english_locale(locale):
        if u and user_modify_intent(u) and user_strong_create_intent(u):
            return (
                "Your message sounds like both **editing an existing item** and **creating a new one**. "
                "Please choose one: edit an existing Bug / test case / BadCase (title, keyword, or ID), "
                "or **create a new** record?"
            )
        return (
            "Your request is ambiguous: it may mean updating an existing record or creating a new one.\n"
            "Please clarify: **which existing record** (title, keyword, or ID), or **create new**?"
        )
    if u and user_modify_intent(u) and user_strong_create_intent(u):
        return (
            "您这句话里同时有「修改已有内容」和「新建一条」的意思，系统无法自动取舍。\n"
            "请直接说明二选一：是要**改某一条已有**的 Bug / 测试用例 / BadCase（可带标题、关键词或 ID），"
            "还是要**新建一条**？"
        )
    return (
        "当前描述不太明确，可能是在说「改已有记录」或「新建记录」。\n"
        "请补充说明：要操作的是**已有的一条**（请描述标题、关键词或 ID），还是要**新建一条**？"
    )


def needs_low_signal_clarification(user_input: Optional[str]) -> bool:
    """
    输入信息量过低，无法判断用户目标（应先澄清再执行 THINK/工具，避免 grep 出无意义关键词如「1」）。
    环境变量 INTENT_LOW_SIGNAL_CLARIFY_ENABLED=0 可关闭。
    """
    if (os.getenv("INTENT_LOW_SIGNAL_CLARIFY_ENABLED", "1") or "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    u = (user_input or "").strip()
    if not u:
        return True
    # 单字符数字 / 单个 ASCII 字母或符号：多为误触
    if len(u) == 1:
        if u.isdigit():
            return True
        if u.isascii() and (u.isalnum() or u in "+-_"):
            return True
    # 极短且仅重复同一无意义字符
    if len(u) <= 3 and len(set(u)) == 1 and u[0] in "0123456789?.。！!":
        return True
    return False


def low_signal_clarification_message(locale: Optional[str] = None) -> str:
    from .locale_prompts import is_english_locale

    if is_english_locale(locale):
        return (
            "Not enough information to tell whether you want to **search**, **edit**, or **create**.\n"
            "Please state your goal in one sentence, e.g. list test cases whose title contains “login”, "
            "change a case’s status to draft, or create a new case about payments."
        )
    return (
        "当前输入信息不足，无法判断您要**查什么、改什么还是新建什么**。\n"
        "请用一句话说明具体目标，例如：「列出标题包含登录的测试用例」「把某某用例状态改为草稿」「新建一条与支付相关的用例」。"
    )


def should_veto_create_named_skill(user_input: Optional[str], skill_name: Optional[str]) -> bool:
    """仅「明确修改、非强新建」时否决 create_*（供同步路径软降权参考，不再用于硬删列表）。"""
    sn = (skill_name or "").strip().lower()
    if not sn.startswith("create_"):
        return False
    return intent_bucket(user_input) == "modify"


def _extract_json_object(text: str) -> Optional[dict]:
    """从模型输出中取出第一个完整 JSON 对象（容忍 Markdown 围栏）。"""
    if not text or not isinstance(text, str):
        return None
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        s = "\n".join(lines).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    i = s.find("{")
    if i < 0:
        return None
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[i : j + 1])
                except Exception:
                    return None
    return None


def _parse_need_plan_ui(obj: dict) -> Optional[bool]:
    """意图 JSON 中的 need_plan_ui；缺省或非法 → None（与旧版一致，仅步数阈值）。"""
    if (os.getenv("REACT_INTENT_PLAN_UI_ENABLED", "1") or "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return None
    v = obj.get("need_plan_ui")
    if v is True or (isinstance(v, str) and v.lower() in ("true", "yes", "1")):
        return True
    if v is False or (isinstance(v, str) and v.lower() in ("false", "no", "0")):
        return False
    return None


def _parse_need_todo_list(obj: dict) -> Optional[bool]:
    """[GATE] JSON 中的 need_todo_list：是否要在 THINK 中生成可见 Todo/XML 计划；缺省或非法 → None（走启发式）。"""
    v = obj.get("need_todo_list")
    if v is True or (isinstance(v, str) and str(v).strip().lower() in ("true", "yes", "1")):
        return True
    if v is False or (isinstance(v, str) and str(v).strip().lower() in ("false", "no", "0")):
        return False
    return None


def react_need_todo_list_heuristic_fallback(user_input: Optional[str]) -> bool:
    """
    模型未在 [GATE] 中给出 need_todo_list 时的降级：偏「多步/多工具」则 True（生成计划），否则 False（直驱无 Todo 列表）。
    REACT_NEED_TODO_LIST_HEURISTIC=0 时恒为 True（保守：始终期望可解析计划）。
    """
    if (os.getenv("REACT_NEED_TODO_LIST_HEURISTIC", "1") or "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return True
    u = (user_input or "").strip()
    if not u:
        return True
    # 多步、批量、多工具线索 → 生成 Todo 清单
    if re.search(r"(先|首先|第[一二三四五六七八九十\d]+步).{0,48}(再|然后|接着|最后|其次)", u):
        return True
    if re.search(r"(批量|多个|分别|以及|同时|还有|另外|再)", u) and len(u) > 6:
        return True
    if len(re.findall(r"\b(?:grep|modify|create|delete|browser_test)\b", u, re.I)) >= 2:
        return True
    if re.search(r"(复制|拷贝).{0,40}(并|再|然后|接着)", u):
        return True
    return False


def resolve_need_todo_list_effective(
    intent: Optional[dict], user_input: Optional[str]
) -> bool:
    """以 [GATE] 为准；缺省或无时用启发式。返回 True=应生成/解析 Todo 列表。"""
    if intent and isinstance(intent, dict):
        ntl = _parse_need_todo_list(intent)
        if ntl is not None:
            return bool(ntl)
    return react_need_todo_list_heuristic_fallback(user_input)


THINK_EMBEDDED_GATE_OPEN = "[GATE]"
THINK_EMBEDDED_GATE_CLOSE = "[/GATE]"


def try_parse_completed_think_embedded_gate(accumulated: str) -> Optional[Tuple[dict, str]]:
    """
    流式缓冲中一旦出现完整的 THINK_EMBEDDED_GATE_CLOSE，解析首个嵌入式门控块。
    返回 (intent, suffix)，suffix 为关闭标签之后的正文（供后续 todo 解析）。
    intent: need_tools(bool), message(str), need_plan_ui(Optional[bool]), need_todo_list(Optional[bool])。
    JSON 无法解析或缺字段时保守 need_tools=True（与独立门控一致）。
    """
    if not accumulated or THINK_EMBEDDED_GATE_CLOSE not in accumulated:
        return None
    close_idx = accumulated.find(THINK_EMBEDDED_GATE_CLOSE)
    suffix = accumulated[close_idx + len(THINK_EMBEDDED_GATE_CLOSE) :]
    head = accumulated[: close_idx + len(THINK_EMBEDDED_GATE_CLOSE)]
    open_idx = head.find(THINK_EMBEDDED_GATE_OPEN)
    if open_idx < 0:
        print("[REACT-THINK-GATE] 缺少 [GATE] 起始，保守 need_tools=true")
        return ({"need_tools": True, "message": "", "need_plan_ui": None, "need_todo_list": None}, suffix)
    inner = head[open_idx + len(THINK_EMBEDDED_GATE_OPEN) : close_idx].strip()
    obj = _extract_json_object(inner)
    if not isinstance(obj, dict):
        print(f"[REACT-THINK-GATE] JSON 解析失败，保守 need_tools=true: {inner[:120]!r}")
        return ({"need_tools": True, "message": "", "need_plan_ui": None, "need_todo_list": None}, suffix)
    nt = obj.get("need_tools")
    if nt is True or (isinstance(nt, str) and nt.lower() in ("true", "yes", "1")):
        npu = _parse_need_plan_ui(obj)
        ntl = _parse_need_todo_list(obj)
        return ({"need_tools": True, "message": "", "need_plan_ui": npu, "need_todo_list": ntl}, suffix)
    if nt is False or (isinstance(nt, str) and nt.lower() in ("false", "no", "0")):
        msg = obj.get("message") or obj.get("reply") or ""
        return ({"need_tools": False, "message": str(msg).strip(), "need_plan_ui": None, "need_todo_list": None}, suffix)
    print(f"[REACT-THINK-GATE] need_tools 缺省，保守 true: {obj!r}")
    return ({"need_tools": True, "message": "", "need_plan_ui": None, "need_todo_list": None}, suffix)


def strip_leading_think_embedded_gate(full_text: str) -> Tuple[Optional[dict], str]:
    """从完整 THINK 输出去掉首个 [GATE]…[/GATE]，供回退路径解析 todo。无闭合块则 (None, 原文)。"""
    if not full_text or THINK_EMBEDDED_GATE_CLOSE not in full_text:
        return None, full_text
    got = try_parse_completed_think_embedded_gate(full_text)
    if got is None:
        return None, full_text
    intent, rest = got
    return intent, rest.lstrip()


# 工具意图启发式：典型「要改数据 / 要跑工具」句式（子串少误伤释义句）
_REACT_TOOLS_STRONG_ACTION = re.compile(
    r"(?:"
    r"把[^，。；;\n]{0,40}?(?:改为|改成|设为|更新为|指派给)|"
    r"将[^，。；;\n]{0,40}?(?:改为|改成|设为|更新为)|"
    r"(?:负责人|assignee)\s*[:：]?\s*(?:改为|改成|设为|更新)|"
    r"(?:状态|status)\s*[:：]?\s*(?:改为|改成|设为)|"
    r"(?:修改为|更新为|变更为|调整为)|"
    r"\bgrep\b|\bmodify\b|\bcreate\b|\bdelete\b"
    r")",
    re.I,
)


def react_tools_intent_likely_need_tools_heuristic(user_input: Optional[str]) -> bool:
    """
    明显需要走工具链时跳过门控 LLM，省一次 DashScope 往返（常为数秒～数十秒）。
    策略：强操作句式优先；再排除「纯释义/列举型问句」；最后用较窄关键词命中（已去掉「用例/迭代/草稿」等过宽子串）。
    REACT_TOOLS_INTENT_HEURISTIC=0 关闭。
    """
    if (os.getenv("REACT_TOOLS_INTENT_HEURISTIC", "1") or "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    u = (user_input or "").strip()
    if len(u) < 4:
        return False

    head = u[:220]
    # 偏概念/列举/元问题：无明确操作词则不走启发式 True，交给门控 LLM
    _concept = re.search(
        r"(是什么|什么意思|怎么用|如何理解|介绍一下|说明一下|请问|有何区别|有什么区别|"
        r"指的是|含义是|定义|区别在哪|为何要|为什么|怎么理解|"
        r"列举|汇总一下|统计一下|导出|有哪些类型|分哪几种)",
        head,
    )
    _action_guard = re.search(
        r"(修改|改为|改成|新建|创建|删除|grep|负责人|状态|设为|添加|批量|把|将|指派|更新|变更|定位|搜索|查找)",
        u,
    )
    if _concept and not _action_guard:
        return False
    # 「搜索/查找 是什么」类元问题，仍走门控，避免命中下方「搜索」子串（若将来加回）
    if re.search(
        r"(?:搜索|查找|定位|grep).{0,10}是\s*什|什么是.{0,10}(?:搜索|查找|定位|grep)",
        u,
    ):
        return False

    if _REACT_TOOLS_STRONG_ACTION.search(u):
        return True

    ul = u.lower()
    # 较窄关键词：避免「用例/草稿/迭代」等单点误命中；「搜索/查找」配合上文释义排除
    needles = (
        "grep",
        "modify",
        "badcase",
        "sandbox",
        "负责人",
        "修改为",
        "改为",
        "改成",
        "指派",
        "改状态",
        "新建",
        "创建",
        "添加",
        "删除",
        "测试用例",
        "缺陷",
        "批量",
        "搜索",
        "查找",
        "定位",
        "test case",
        "bad case",
        "database_query",
        "database query",
    )
    for n in needles:
        if n.isascii():
            if n in ul:
                return True
        else:
            if n in u:
                return True
    # 英文缺陷常用词（\b 在「中文+bug」粘连时失效，改用前后非 ASCII 字母约束）
    if re.search(r"(?<![a-z])bugs?(?![a-z])", ul):
        return True
    return False


def react_tools_intent_classify_sync(
    user_input: Optional[str], locale: Optional[str] = None
) -> tuple[bool, str, Optional[bool]]:
    """
    用大模型判断本轮是否需要走工具链（THINK / grep / modify 等）。
    返回 (need_tools, direct_reply, need_plan_ui)。
    - need_tools=False 时 direct_reply 为可直接展示给用户的短回复（寒暄等）；need_plan_ui 为 None。
    - need_tools=True 时可选 need_plan_ui：false=不展示顶部「规划备忘」类 UI（单步/原子动作）；true=希望展示；
      未返回则 None，仅沿用 REACT_PLAN_SSE_MIN_STEPS。
    - 未启用、无 Key、调用失败：保守 (True, "", None)，避免误伤真实任务。

    环境变量：
    - REACT_TOOLS_INTENT_ENABLED=0：跳过，返回 (True, "", None)
    - REACT_TOOLS_INTENT_MODEL：默认 qwen-turbo（偏快）
    - REACT_INTENT_PLAN_UI_ENABLED=0：不解析 need_plan_ui，恒为 None
    """
    if (os.getenv("REACT_TOOLS_INTENT_ENABLED", "1") or "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return True, "", None
    u = (user_input or "").strip()
    if not u:
        return True, "", None
    if react_tools_intent_likely_need_tools_heuristic(u):
        print("[REACT-TOOLS-INTENT] 启发式判定需工具，跳过门控 LLM")
        return True, "", None

    from .locale_prompts import is_english_locale

    model = (os.getenv("REACT_TOOLS_INTENT_MODEL") or "qwen-turbo").strip()
    try:
        from llm.dashscope_compat import get_dashscope_compat_client
        from config import Config
    except Exception:
        return True, "", None

    key = getattr(Config, "DASHSCOPE_API_KEY", None) or getattr(Config, "QWEN_API_KEY", None)
    if not key:
        print("[REACT-TOOLS-INTENT] 无 DashScope Key，跳过门控")
        return True, "", None

    if is_english_locale(locale):
        prompt = (
            "You gate a testing/defect workflow assistant. Decide if the user's message requires "
            "calling system tools (e.g. grep, modify, create, database_query, search, browser_test) "
            "to fulfill the request.\n"
            "need_tools=true: user wants to query/list/search/edit/create/run tests or work with Bugs, "
            "test cases, BadCases in the project, or similar actionable ops.\n"
            "need_tools=false: pure greetings/thanks/small talk/meta chat with no data action. "
            "Then write `message`: 2–4 sentences, warm and helpful—briefly introduce what you can do "
            "(bugs, test cases, BadCases, search/edit/create), invite them to state a goal. "
            "Do not only mirror their greeting; no Markdown.\n"
            "When need_tools=true, also set need_plan_ui:\n"
            "- need_plan_ui=true: multi-step, unclear scope, user asked for a plan, or several tools likely.\n"
            "- need_plan_ui=false: one clear atomic action (single grep, one lookup, one field change) where "
            "the top planning strip adds little value.\n"
            "Omit need_plan_ui if unsure (server falls back to step-count rule).\n"
            "Output exactly one JSON object, no other text:\n"
            '{"need_tools": true}\n'
            '{"need_tools": true, "need_plan_ui": false}\n'
            '{"need_tools": true, "need_plan_ui": true}\n'
            'or {"need_tools": false, "message": "..."}\n\n'
            f"User message:\n{u[:4000]}"
        )
    else:
        prompt = (
            "你是测试/缺陷工作流助手的意图门控。判断用户这句话是否需要调用系统工具"
            "（如 grep、modify、create、database_query、search、browser_test 等）才能完成。\n"
            "need_tools=true：要查询/列出/搜索/修改/创建/测试项目内 Bug、测试用例、BadCase，"
            "或跑自动化、查日志、执行数据操作等明确任务。\n"
            "need_tools=false：纯寒暄、致谢、闲聊或与具体数据操作无关的泛泛而谈。"
            "此时 `message` 要写 2～4 句自然中文：先友好回应，再简要说明你能协助处理 Bug/测试用例/BadCase 的"
            "查询、修改与新建，并邀请用户用一句话说清目标；不要只回一个「你好」式镜像句。"
            "不要用 Markdown；不要用英文双引号，需要引号请用「」。\n"
            "当 need_tools=true 时，请增加 need_plan_ui：\n"
            "- need_plan_ui=true：多步、范围不清、用户明确要求规划、或明显会调用多个工具。\n"
            "- need_plan_ui=false：单步即可完成、原子动作（如一次 grep 定位、一次查询、改一个字段），"
            "顶部「规划备忘」对体验帮助不大时可标 false。\n"
            "不确定时可省略 need_plan_ui，由服务端按步数阈值决定。\n"
            "只输出一个 JSON 对象，不要其它文字，例如：\n"
            '{"need_tools": true}\n'
            '{"need_tools": true, "need_plan_ui": false}\n'
            '{"need_tools": true, "need_plan_ui": true}\n'
            '或 {"need_tools": false, "message": "..."}\n\n'
            f"用户输入：\n{u[:4000]}"
        )

    try:
        client = get_dashscope_compat_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=384,
            temperature=0.45,
        )
        text = (resp.choices[0].message.content or "").strip()
        obj = _extract_json_object(text)
        if not isinstance(obj, dict):
            print(f"[REACT-TOOLS-INTENT] 无法解析 JSON，保守 need_tools=true: {text[:120]!r}")
            return True, "", None
        nt = obj.get("need_tools")
        if nt is True or (isinstance(nt, str) and nt.lower() in ("true", "yes", "1")):
            npu = _parse_need_plan_ui(obj)
            print(f"[REACT-TOOLS-INTENT] need_tools=true need_plan_ui={npu!r}")
            return True, "", npu
        if nt is False or (isinstance(nt, str) and nt.lower() in ("false", "no", "0")):
            msg = obj.get("message") or obj.get("reply") or ""
            return False, str(msg).strip(), None
        print(f"[REACT-TOOLS-INTENT] need_tools 缺省，保守 true: {obj!r}")
        return True, "", None
    except Exception as e:
        print(f"[REACT-TOOLS-INTENT] 调用/解析失败，保守 need_tools=true: {e}")
        return True, "", None


def arbitrate_modify_or_create(user_input: Optional[str]) -> str:
    """
    在意图 unclear 时调用。返回 'modify' 或 'create'。
    环境变量：
    - INTENT_ARBITER_MODEL：默认 qwen-max（DashScope）
    - INTENT_ARBITER_ENABLED=0：跳过调用，返回 modify（保守）
    """
    if (os.getenv("INTENT_ARBITER_ENABLED", "1") or "1").strip().lower() in ("0", "false", "no", "off"):
        return "modify"
    u = (user_input or "").strip()
    if not u:
        return "modify"
    model = (os.getenv("INTENT_ARBITER_MODEL") or "qwen-max").strip()
    try:
        from llm.dashscope_compat import get_dashscope_compat_client
        from config import Config
    except Exception:
        return "modify"

    key = getattr(Config, "DASHSCOPE_API_KEY", None) or getattr(Config, "QWEN_API_KEY", None)
    if not key:
        print("[INTENT-ARB] 无 DashScope Key，默认 modify")
        return "modify"

    prompt = (
        "你是意图分类器，只做二选一。系统里有 Bug、测试用例、BadCase 等「已存在」的记录。\n"
        "modify = 用户要改已有记录（状态、负责人、标题、草稿变生效、评审等）。\n"
        "create = 用户要新做一条记录（创建/新建/添加一条全新的用例或 Bug 等）。\n"
        "若一句话里既有「新建」又有「改某条已有」，以是否以「改已有」为主目标为准。\n"
        "只输出一行 JSON，不要 Markdown、不要解释："
        '{"intent":"modify"} 或 {"intent":"create"}\n\n'
        f"用户原话：{u[:2000]}"
    )
    try:
        client = get_dashscope_compat_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        text = (resp.choices[0].message.content or "").strip()
        m = re.search(r"\{[^{}]*\"intent\"[^{}]*\}", text)
        if not m:
            m = re.search(r"\{[^}]+\}", text)
        if m:
            obj = json.loads(m.group())
            intent = str(obj.get("intent", "")).lower().strip()
            if intent == "create":
                return "create"
        return "modify"
    except Exception as e:
        print(f"[INTENT-ARB] 解析/调用失败，默认 modify: {e}")
        return "modify"


def is_vague_generic_todo(todo: Optional[str]) -> bool:
    """THINK 只吐出泛化句、无法解析工具时的特征。"""
    if not todo or not isinstance(todo, str):
        return True
    t = todo.strip()
    if not t:
        return True
    low = t.lower()
    vague_markers = (
        "分析用户请求",
        "生成解决方案",
        "分析需求",
        "理解用户",
        "制定方案",
        "规划步骤",
        "思考如何",
    )
    if any(m in t for m in vague_markers):
        return True
    # 没有任何可识别工具关键词
    tool_hints = ("grep", "modify", "create", "search", "database", "查询", "搜索", "修改", "创建", "定位")
    if not any(h in low or h in t for h in tool_hints):
        return True
    return False


_BUG_ENTITY_WORD_RE = re.compile(r"\bbugs?\b", re.IGNORECASE)


def user_text_implies_bug_entity_type(text: Optional[str]) -> bool:
    """
    用户是否在谈「Bug 缺陷」实体类型（而非标题里的 bug 前缀如 bug1.2、debug 等）。
    - 中文「缺陷」视为明确缺陷意图
    - 常见「修改bug / bug的标题」：中英之间无空格，re \\b 不可靠，单独用子串/短模式匹配
    - 英文仍匹配整词 bug / bugs（\\b），避免 debug 等误伤
    """
    if not text:
        return False
    zh = text
    if "缺陷" in zh:
        return True
    # 「登录bug的标题」「修改bug xxx」等
    if re.search(r"(?i)bug的标题|bug的名称|bug的\s*标题", zh):
        return True
    if re.search(r"(?i)(修改|更改|变更|改|更新|编辑)\s*bug(?=\s|[\u4e00-\u9fff]|$)", zh):
        return True
    return bool(_BUG_ENTITY_WORD_RE.search(text))


def user_text_implies_card_entity_type(text: Optional[str]) -> bool:
    """用户明确在操作统一卡片层（Card）：改卡片标题/描述、card_id 等。"""
    if not text:
        return False
    zh = text
    u = text.lower()
    # 看板/迭代列表上展示名常对应 Card.title，与 Bug.title 可不同步
    if "看板" in zh and any(k in zh for k in ("标题", "名称", "重命名")):
        return True
    has_card = ("卡片" in zh) or ("card" in u)
    if not has_card:
        return False
    if any(k in zh for k in ("标题", "描述", "名称", "重命名")):
        return True
    if "card_id" in u or re.search(r"\bcard\s*id\b", u):
        return True
    if re.search(r"(修改|编辑|更新|改).{0,10}卡片", zh):
        return True
    return False


def user_text_implies_plan_entity_type(text: Optional[str]) -> bool:
    """用户明确在搜/改迭代计划节点（粗粒度；具体检索仍可能走 plan_id + grep）。"""
    if not text:
        return False
    zh = text
    markers = (
        "迭代计划",
        "计划树",
        "计划节点",
        "搜计划",
        "查计划",
        "查找计划",
        "搜索计划",
        "计划名称",
    )
    return any(m in zh for m in markers)


def infer_modify_target_from_user(user_input: Optional[str]) -> str:
    """从用户话里猜 grep/modify 的 target：testcase / bug / badcase / card / plan / all。"""
    if not user_input:
        return "all"
    u = user_input.lower()
    zh = user_input
    if "测试用例" in zh or "testcase" in u or "test case" in u:
        return "testcase"
    if "badcase" in u or "坏例" in zh:
        return "badcase"
    if user_text_implies_card_entity_type(user_input):
        return "card"
    if user_text_implies_plan_entity_type(user_input):
        return "plan"
    if user_text_implies_bug_entity_type(user_input):
        return "bug"
    return "all"
