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
from typing import Literal, Optional

IntentBucket = Literal["modify", "create", "unclear"]

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
    """
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


def infer_modify_target_from_user(user_input: Optional[str]) -> str:
    """从用户话里猜 grep/modify 的 target：testcase / bug / badcase / all。"""
    if not user_input:
        return "all"
    u = user_input.lower()
    zh = user_input
    if "测试用例" in zh or "testcase" in u or "test case" in u:
        return "testcase"
    if "badcase" in u or "坏例" in zh:
        return "badcase"
    if "bug" in u or "缺陷" in zh:
        return "bug"
    return "all"
