# -*- coding: utf-8 -*-
# agents/prompts.py
"""
ReAct Prompt 工程 - 公用强约束模板

提示词为公用：所有模型（GLM5、文心、Qwen、OpenAI 等）使用同一套 think/decide/observe 等模板，
仅底层调用的模型实例不同，不做按模型分支的差异化提示。

核心设计原则：
1. 长而精准 - 明确的系统上下文
2. XML 标签 - 固定输出格式
3. Good/Bad 示例 - 规范思考逻辑
4. Todo 锚定 - 保持任务焦点

架构：
- 静态提示词（SYSTEM_STATIC）：固定的系统规则、输出格式
- 动态提示词（build_dynamic_context）：项目名称、当前 todo list、原始 query
"""

import json
import os
import re
import threading
from typing import Any, List, Dict, Union, Optional, Tuple

_tools_format_cache_lock = threading.Lock()
_tools_format_cache_key: Optional[Tuple[Any, ...]] = None
_tools_format_cache_val: Optional[List[Dict[str, str]]] = None

from .locale_prompts import is_english_locale


def unified_round_grep_first_prompt_block(
    *,
    round_idx: int,
    prev_observation: Optional[dict],
    ui_locale: Optional[str] = None,
) -> str:
    """
    统一流：约束模型在推理/决策阶段就选 grep，而非首轮直驱 modify/delete。
    round_index=1 时强制；若上一轮因未 grep 被纠正，本轮仍须 grep。
    """
    if isinstance(prev_observation, dict) and prev_observation.get("reason") == "grep_required_before_modify":
        if is_english_locale(ui_locale):
            return """
**Corrective rule (this round):** You must call **grep** now to locate records. Do **not** call modify/delete until grep has run in this session. UI record_id does **not** replace grep.

"""
        return """
**纠正规则（本轮必读）：** 须在本轮调用 **grep** 定位记录；本会话内尚未完成过 grep 前**禁止** modify/delete。界面 record_id **不能**代替 grep。

"""
    if round_idx != 0:
        return ""
    if is_english_locale(ui_locale):
        return """
**Round 1 (modify/delete):** In `<thinking>`, plan **grep first**. Then **function call grep only** — do not call modify/delete yet. UI record_id does not replace grep.

<good_example><user>Change bug X status to hold</user>→ function call grep(keywords from title)</good_example>
<bad_example><user>Change status to hold</user>→ function call modify with UI record_id</bad_example>

"""
    return """
**首轮（改/删）：** `<thinking>` 里写先 **grep** 定位；随后 **function calling 只能调用 grep**，禁止首轮 modify/delete。界面 record_id 不能代替 grep。

<good_example><user>问登录问题答的不好 状态改为 hold</user>→ function call grep(keywords 含登录/标题)</good_example>
<bad_example><user>状态改为 hold</user>→ function call modify 且带 record_id</bad_example>

"""

_UNIFIED_CTX_SKIP_KEYS = frozenset(
    {"_tool_run_store", "frozen_macro", "grep_modify_raw_bug_list", "grep_modify_raw_badcase_list",
     "grep_modify_raw_card_list", "grep_modify_raw_plan_list", "grep_modify_raw_testcase_list",
     "_project_login_hint"}
)

_UNIFIED_DEFAULT_CORE_TOOLS: Tuple[str, ...] = (
    "grep",
    "modify",
    "create",
    "delete",
    "copy",
    "cdp",
    "get_tool_description",
    "terminal",
    "skill_executor",
)


def unified_core_tool_allowlist() -> Optional[Tuple[str, ...]]:
    """REACT_UNIFIED_CORE_TOOLS=0|all 时不裁剪；否则默认只暴露 CRUD 核心工具 + 元工具。"""
    raw = (os.getenv("REACT_UNIFIED_CORE_TOOLS", "1") or "1").strip().lower()
    if raw in ("0", "false", "no", "off", "all"):
        return None
    custom = (os.getenv("REACT_UNIFIED_TOOL_NAMES") or "").strip()
    if custom:
        parts = tuple(x.strip() for x in custom.split(",") if x.strip())
        return parts or _UNIFIED_DEFAULT_CORE_TOOLS
    return _UNIFIED_DEFAULT_CORE_TOOLS


def filter_tools_for_unified_prompt(
    tools_info: list,
    skill_tool_names: Optional[List[str]] = None,
) -> list:
    """统一流工具列表：核心 allowlist + 命中 skill 的工具；始终保留 get_tool_description。"""
    if not tools_info:
        return []
    allow = unified_core_tool_allowlist()
    names: set = {"get_tool_description"}
    if skill_tool_names:
        names.update(str(x) for x in skill_tool_names if x)
    if allow:
        names.update(allow)
    if allow or skill_tool_names:
        filtered = [t for t in tools_info if str((t or {}).get("name") or "") in names]
        if filtered:
            return filtered
    return list(tools_info)


def build_matched_skill_prompt_block(
    skill_name: str,
    skill_workflow_prompt: str,
    *,
    ui_locale: Optional[str] = None,
    include_footer: bool = True,
) -> str:
    body = (skill_workflow_prompt or "").strip()
    if not body:
        return ""
    block = f"""
<matched_skill name="{skill_name}">
{body}
</matched_skill>
"""
    if not include_footer:
        return block
    if is_english_locale(ui_locale):
        return block + """
**Follow the workflow above** (one tool per round). Call **get_tool_description** when parameter details are unclear.
"""
    return block + """
**须按上述技能工作流执行**（多步时一轮一个工具）。参数细节不确定时先调用 **get_tool_description**。
"""


def unified_minimal_decision_rules_block(
    *,
    fc_decide: bool,
    ui_locale: Optional[str] = None,
    has_matched_skill: bool = False,
) -> str:
    if is_english_locale(ui_locale):
        if has_matched_skill:
            return (
                "**Execution constraints (skill mode):**\n"
                "1. Follow `<matched_skill>` step order; **one tool per round**.\n"
                "2. Goal done or pure chat → **submit_unified_round**, execute=false.\n"
            )
        lines = [
            "**Decision rules (minimal):**",
            "1. One business tool per round when multiple steps remain; follow `<matched_skill>` if present.",
            "2. create/modify/delete: always `confirm:false` (preview only); never commit without user confirmation.",
            "3. Unclear tool params → call get_tool_description(tool_name) first.",
            "4. Goal fully met or pure chat → submit_unified_round with execute=false.",
        ]
        if not has_matched_skill:
            lines.insert(
                1,
                "1b. Multi-step data changes: prefer grep → modify/create/delete; server may correct wrong order.",
            )
        return "\n".join(lines) + "\n"
    if has_matched_skill:
        return (
            "**执行约束（技能模式）：**\n"
            "1. 严格按 `<matched_skill>` 顺序，**一轮一个工具**。\n"
            "2. 目标已完成或纯闲聊 → **submit_unified_round**，execute=false。\n"
        )
    lines = [
        "**决策规则（精简）：**",
        "1. 多步任务**一轮一个工具**；有 `<matched_skill>` 时严格按其工作流顺序执行。",
        "2. create/modify/delete 须 **confirm:false** 预览，禁止未经用户确认直接落库。",
        "2b. 新建**迭代计划**须 create(target=plan, confirm=false) 出沙箱 diff；禁止在对话里问「是否继续」代替工具预览。",
        "2c. 删除**迭代计划**须 delete(target=plan, plan_id=侧栏当前或 grep 的 first_plan_id, confirm=false) 预览 Plan 节点；"
        "侧栏已选中且用户说「这个/当前迭代计划」可直接 delete 预览，**不必**先 grep；"
        "**禁止**把删计划写成删卡片/bug/badcase，**禁止**在回复里罗列计划内卡片让用户确认。",
        "3. 参数/字段名不确定 → 先 **get_tool_description** 再调用业务工具。",
        "4. 用户目标已全部完成，或纯闲聊 → **submit_unified_round**，execute=false。",
    ]
    if not has_matched_skill:
        lines.insert(
            2,
            "1b. 改/删/复制类多步任务由技能或 task_plan 驱动；服务端会纠正未先检索就 modify 的错误。",
        )
    return "\n".join(lines) + "\n"


_PROMPT_MODIFY_DETAIL_BLOCK = """⭐ 人类式先检索再阅读（modify 前必读）：
- 流程：先 grep 检索出候选列表（badcase_analysis/bug_location/testcase_location/**card_location**），对候选做 rerank，**分高的**作为 target_id；支持 BadCase、Bug、测试用例、**统一卡片 Card**。
- **只读「查看详情」禁止误用 modify**：用户仅「查看/看看/展示/介绍下」某张**卡片**或某条 Bug/BadCase/用例的详情、**没有说要改字段或状态**时，**只用 grep 返回结果中的条目作答**（优先 **card_location** 及其中 title、plan、类型相关字段），整理成对话里的结构化说明即可。**禁止**为「展示详情」再调用 modify（modify 用于**修改**预览，不是只读查询接口）。信息不够时允许**再 grep** 缩小关键词或 target，仍不要用 modify 充当读详情。
- 若 context 中尚无列表，必须先 grep：grep(keywords="用户话里的标题或关键词", target="badcase"|"bug"|"testcase"|"card"|"all", project_id=当前项目)。**多词默认 OR**；**用户只要「查卡片/卡片列表」→ target 必须是 card**；**只要统一卡片层、不要 bug/源表并行结果时，必须用 target=card**（避免与 target=all 下历史 Bug 行重复）。**target=all** 时服务端会将同源「源表行 + Card」**合并为一条卡片导航**。**务必传 plan_id=当前侧栏选中的迭代**，否则命中面过大；导航列表会去重并限条数，仍以 plan 限定为准。
- 选 target_id 时：系统会对候选按与关键词的匹配度 rerank，分高的即可；modify 的 **target 必须与 modifications 字段所在源表一致**（改 Bug 状态 → target=bug + Bug.id）。grep 命中 **card_location** 时可用于定位，但若用户要改的是缺陷工作流字段，modify **仍用 bug/badcase/testcase**，可从同条 observation 的 bug_list 或合并项里的源表 id 取 target_id；**不要**用 target=card 写 status。**切勿**仅因标题含「testcase」就把 target 设为 testcase。
- 字段命名统一（避免混淆）：**答案用 answer**，**正确答案用 correct_answer**（由 modify 工具映射到数据库字段）。
- 不要在 params 里编造数字 id；若 context 中已有上一步 grep 结果，你可写出 target_id；**若不确定，params 可只含 target / 或留空，真实执行以服务端补参为准**（见下条）。

⭐ 服务端补参（真实可靠性口径，优先遵守）：
- 你只要 **execute=true 且 tool=modify** 即可完成任务绑定；**target_id、modifications 若写不全，不必硬编**，引擎会在调用 modify 工具前自动补全：合并上一步 grep 的候选 id、必要时自动再 grep、结合用户原话与探索记录生成 modifications。
- 你能写出完整 params（含 target、target_id、modifications）时，日志更清晰，但最终仍以 **服务端合并、校验后的参数** 为准。

⭐ modify 工具状态值规则（重要）：
修改 status 字段时，必须使用以下合法的状态值（英文），不能使用中文：
- Bug 的合法状态值：new（新建）、assigned（已分配）、in_progress（进行中）、resolved（已解决）、closed（已关闭）、reopened（重新打开）
- BadCase 的合法状态值：new（新建）、pending（待处理）、resolved（已解决）、hold（搁置）、reopened（重新打开）、closed（已关闭）
- 示例：用户说"关闭这个Bug"，应输出 "status": "closed"（Bug或BadCase都用closed）
- 示例：用户说"标记为已解决"，应输出 "status": "resolved"
- 示例：用户说"重新打开"，应输出 "status": "reopened"
"""

_PROMPT_SEARCH_ENGINE_DETAIL_BLOCK = """⭐ 搜索引擎智能选择规则（当使用 search 工具时）：
根据搜索关键词的语言、内容类型和用户意图智能选择最合适的搜索引擎：

【选择 "baidu"（百度）的情况】：
- 搜索关键词是中文（如："杨幂"、"C罗"、"Python教程"）
- 查询中国本土信息（如：中国企业、中国明星、国内新闻、中文网站）
- 涉及中国特色内容（如：淘宝、微信、支付宝、百度、腾讯、阿里巴巴）
- 查询中文资料、中文论坛、中文文档
- 混合中英文但以中文为主的查询

【选择 "google"（谷歌）的情况】：
- 搜索关键词是纯英文且涉及国际内容
- 查询国际技术资料（如：GitHub、Stack Overflow、官方英文文档）
- 搜索国际新闻、国际人物（如："Cristiano Ronaldo"、"Elon Musk"）
- 查询学术论文、英文教程
- 涉及国际平台和服务（如：AWS、Docker、Kubernetes）

【选择 "bing"（必应）的情况】：
- 用户明确要求使用必应
- 需要微软生态系统相关的搜索

⚠️ 重要原则：
- 中文关键词优先使用百度，即使包含英文技术词汇（如："Python 教程"、"React 入门"）
- 纯英文且明确国际化内容才使用 Google
- engine 参数值必须是小写："baidu" / "google" / "bing"（不是 "Baidu" / "Google" / "Bing"）
- 当不确定时，中文内容默认选择 "baidu"

示例：
- "杨幂" → engine: "baidu" （中文明星）
- "Cristiano Ronaldo" → engine: "google" （国际球星）
- "Python asyncio tutorial" → engine: "google" （英文技术文档）
- "Python 教程" → engine: "baidu" （中文教程，虽然包含 Python）
- "淘宝优惠券" → engine: "baidu" （中国本土电商）
- "github actions" → engine: "google" （国际技术平台）
"""

_MODIFY_INTENT_HINTS = (
    "modify",
    "修改",
    "改",
    "更新",
    "改成",
    "改为",
    "设为",
    "调整",
    "编辑",
    "变更",
    "复现步骤",
    "负责人",
    "优先级",
    "改状态",
    "改标题",
    "重命名",
)
_READ_ONLY_HINTS = ("查看", "看看", "展示", "介绍下", "介绍下", "有哪些", "列出")


def _prompt_text_blob(*, todo: str = "", user_input: str = "") -> str:
    return f"{todo or ''}\n{user_input or ''}"


def prompt_likely_needs_modify(
    *,
    todo: str = "",
    user_input: str = "",
    context: Optional[dict] = None,
    prev_tool: Optional[str] = None,
) -> bool:
    blob = _prompt_text_blob(todo=todo, user_input=user_input)
    todo_l = (todo or "").lower()
    ctx = context or {}
    prev = str(prev_tool or "").lower()

    if "modify" in todo_l or "使用 modify" in (todo or "") or "modify 工具" in (todo or ""):
        return True

    grep_only_round = bool(todo) and "grep" in todo_l and "modify" not in todo_l
    if grep_only_round and not prev:
        return False

    skill_name = str(ctx.get("matched_skill") or "").lower()
    if skill_name.startswith("modify_") and prev == "grep":
        return True

    if prev == "grep":
        has_grep_ctx = bool(
            ctx.get("grep_result")
            or ctx.get("badcase_list")
            or ctx.get("bug_list")
            or ctx.get("grep_modify_raw_badcase_list")
            or ctx.get("grep_modify_raw_bug_list")
        )
        if has_grep_ctx and ("modify" in todo_l or "修改" in (todo or "")):
            return True

    if not any(h in blob for h in _MODIFY_INTENT_HINTS):
        return False
    if any(h in blob for h in _READ_ONLY_HINTS) and not any(
        h in blob for h in ("改", "modify", "更新", "设为", "改成", "改为")
    ):
        return False
    return not grep_only_round


def prompt_likely_needs_search(
    *,
    todo: str = "",
    user_input: str = "",
    context: Optional[dict] = None,
) -> bool:
    del context
    blob = _prompt_text_blob(todo=todo, user_input=user_input)
    blob_l = blob.lower()
    todo_l = (todo or "").lower()
    if "search" in todo_l or "使用 search" in (todo or "") or "使用搜索" in (todo or ""):
        return True
    if "search 工具" in (todo or "") or "搜索引擎" in blob:
        return True
    if any(k in blob_l for k in (" baidu", " google", " bing", "必应")) or blob_l.strip().startswith(
        ("baidu", "google", "bing")
    ):
        if "grep" not in todo_l and "badcase" not in blob_l and "bug" not in blob_l:
            return True
    return False


def build_prompt_conditional_tool_details(
    *,
    todo: str = "",
    user_input: str = "",
    context: Optional[dict] = None,
    prev_tool: Optional[str] = None,
    has_matched_skill: bool = False,
) -> str:
    """modify / search 长细则按需注入；未命中时不占 token。"""
    parts: List[str] = []
    if (
        not has_matched_skill
        and prompt_likely_needs_modify(
            todo=todo, user_input=user_input, context=context, prev_tool=prev_tool
        )
    ):
        parts.append(_PROMPT_MODIFY_DETAIL_BLOCK)
    if prompt_likely_needs_search(todo=todo, user_input=user_input, context=context):
        parts.append(_PROMPT_SEARCH_ENGINE_DETAIL_BLOCK)
    _cdp_detail = build_cdp_login_prompt_detail(
        todo=todo,
        user_input=user_input,
        context=context,
        prev_tool=prev_tool,
    )
    if _cdp_detail:
        parts.append(_cdp_detail)
    return "\n".join(parts)


_CREATE_INTENT_HINTS = ("create", "新建", "创建", "新增", "添加", "提bug", "提一个bug")
_COPY_INTENT_HINTS = ("复制", "拷贝", "clone", "copy_from", "参照", "基于", "和.*一样", "同样")
_BROWSER_CDP_HINTS = ("cdp", "自动化测试", "浏览器测试", "ui测试", "测登录", "端到端", "探测", "探索性")

_PROMPT_CDP_EXPLORE_BLOCK = """
**cdp 探测性测试（explore）：**
- 先 `action=explore phase=inventory` 列出当前页可点击元素（ref/role/name）。
- 再 `action=explore phase=dfs` 或 `phase=full` 深度优先点击探测（跳过删除/登出等危险按钮）。
- 发现明显问题（点击失败、错误文案、错误 URL）时，系统会按侧栏 **plan_id** 生成 Bug 预览；无有效迭代则先生成 **迭代计划** 预览再 Bug 预览（均需用户 confirm）。
- 推荐流程：`session create`+url → `login`（如需）→ `explore phase=inventory`（先列控件）→ `explore phase=full`（再点击探测）。
"""

_PROMPT_CDP_TEST_TASK_BLOCK = """
**cdp 测试任务（test task）：**
- 当用户**描述可执行测试步骤**（先…再…点击/打开）或要求**执行/跑某迭代计划的测试用例**时，系统自动开启 **cdp_test_run** 任务，逐步记录 CDP 操作与通过/失败。优先用 **cdp action=run_testcase**（testcase_id 或 steps）或 **run_step** 逐步驱动；纯「怎么测/如何测」问答不要开浏览器任务，先 grep 后给出步骤与预期说明。
- 用例模式：先 grep(target=testcase, plan_id=当前迭代) 定位用例，再 cdp 按用例 steps 逐步执行；任务结束会回写用例 execution_result（单用例时）。
- 手动模式：按用户描述的步骤依次 cdp snapshot/click/fill/assert。
- 观测结果中带 `cdp_test_run` 字段可查看本次任务汇总；SSE lane=cdp_test_task 推送 opened/step/done。
- 显式控制：params 可设 `test_task=true` 强制开启，`test_task=false` 关闭。
"""

_PROMPT_CDP_LOGIN_DETAIL_BLOCK = """
**cdp 与项目「网站登录配置」：**
{config_lines}
- 流程：`cdp session create`+url → `cdp action=login`（工具**自动**读取上表用户名与密码，**禁止**在 function params 明文传 password）。
- session create 会加载已保存的 login_state；登录成功后会写回 storage 供下次复用。
- 若上表显示缺密码或未配置，action=login 会暂停并请用户在对话提供账号密码。
"""


def build_cdp_login_prompt_detail(
    *,
    todo: str = "",
    user_input: str = "",
    context: Optional[dict] = None,
    prev_tool: Optional[str] = None,
) -> str:
    """浏览器/cdp 场景下注入项目登录配置摘要（按需，不占无关轮次 token）。"""
    if not (
        prompt_likely_needs_cdp(todo=todo, user_input=user_input)
        or str(prev_tool or "").lower() == "cdp"
    ):
        return ""
    hint = (context or {}).get("_project_login_hint")
    if isinstance(hint, dict) and hint.get("prompt_lines"):
        lines = "\n".join(str(x) for x in hint["prompt_lines"])
    elif isinstance(hint, dict) and hint.get("summary"):
        lines = str(hint["summary"])
    else:
        lines = "- （未能读取项目登录配置；执行 action=login 后若缺凭证会提示用户在对话补充）"
    explore_block = ""
    blob = _prompt_text_blob(todo=todo, user_input=user_input).lower()
    if any(k in blob for k in ("探测", "探索", "遍历", "explore", "dfs", "深度优先")):
        explore_block = _PROMPT_CDP_EXPLORE_BLOCK
    task_block = ""
    zh_blob = _prompt_text_blob(todo=todo, user_input=user_input)
    _advise_only = any(k in zh_blob for k in ("怎么测", "如何测", "怎样测", "怎么测试", "如何测试")) and not any(
        k in zh_blob for k in ("执行", "跑", "跑一下", "测一下", "验证一下", "跑用例", "执行用例")
    )
    if (not _advise_only) and any(k in zh_blob or k in blob for k in (
        "测试用例", "测试步骤", "执行用例", "跑用例", "按用例", "执行测试", "test case", "testcase",
        "先打开", "然后点击",
    )):
        task_block = _PROMPT_CDP_TEST_TASK_BLOCK
    return _PROMPT_CDP_LOGIN_DETAIL_BLOCK.format(config_lines=lines) + explore_block + task_block
_GREP_INTENT_HINTS = ("grep", "查询", "查找", "定位", "有哪些", "列表", "界面", "卡片", "搜索项目")


def prompt_likely_needs_read_only_query(
    *,
    todo: str = "",
    user_input: str = "",
) -> bool:
    blob = _prompt_text_blob(todo=todo, user_input=user_input)
    if not any(h in blob for h in _READ_ONLY_HINTS):
        return False
    return not any(h in blob for h in ("改", "modify", "更新", "设为", "改成", "改为"))


def prompt_likely_needs_copy(
    *,
    todo: str = "",
    user_input: str = "",
    context: Optional[dict] = None,
) -> bool:
    blob = _prompt_text_blob(todo=todo, user_input=user_input).lower()
    todo_l = (todo or "").lower()
    if "copy" in todo_l or "复制" in (todo or ""):
        return True
    if any(k in blob for k in ("复制", "拷贝", "copy_from", "参照", "clone")):
        return True
    if str((context or {}).get("matched_skill") or "").lower() == "copy_record":
        return True
    return False


def prompt_likely_needs_create(
    *,
    todo: str = "",
    user_input: str = "",
    context: Optional[dict] = None,
) -> bool:
    if prompt_likely_needs_copy(todo=todo, user_input=user_input, context=context):
        return False
    blob = _prompt_text_blob(todo=todo, user_input=user_input).lower()
    todo_l = (todo or "").lower()
    if "create" in todo_l or "使用 create" in (todo or ""):
        return True
    return any(k in blob for k in _CREATE_INTENT_HINTS)


def prompt_likely_needs_cdp(
    *,
    todo: str = "",
    user_input: str = "",
) -> bool:
    blob = _prompt_text_blob(todo=todo, user_input=user_input).lower()
    todo_l = (todo or "").lower()
    if "cdp" in todo_l or "browser_test" in todo_l or "browser test" in blob:
        return True
    return any(k in blob for k in _BROWSER_CDP_HINTS)


def prompt_likely_needs_browser_test(
    *,
    todo: str = "",
    user_input: str = "",
) -> bool:
    """兼容旧名，等同 prompt_likely_needs_cdp。"""
    return prompt_likely_needs_cdp(todo=todo, user_input=user_input)


def prompt_likely_needs_grep(
    *,
    todo: str = "",
    user_input: str = "",
    context: Optional[dict] = None,
    prev_tool: Optional[str] = None,
) -> bool:
    if prompt_likely_needs_search(todo=todo, user_input=user_input, context=context):
        return False
    todo_l = (todo or "").lower()
    blob = _prompt_text_blob(todo=todo, user_input=user_input)
    if "grep" in todo_l or "使用 grep" in (todo or ""):
        return True
    if prompt_likely_needs_read_only_query(todo=todo, user_input=user_input):
        return True
    prev = str(prev_tool or "").lower()
    if prompt_likely_needs_modify(
        todo=todo, user_input=user_input, context=context, prev_tool=prev_tool
    ):
        grep_only_round = bool(todo) and "grep" in todo_l and "modify" not in todo_l
        if grep_only_round or prev != "grep":
            return True
    if prompt_likely_needs_copy(todo=todo, user_input=user_input, context=context) and prev != "grep":
        return True
    ctx = context or {}
    if str(ctx.get("matched_skill") or "").lower().startswith(("modify_", "delete_")) and prev != "grep":
        return True
    return any(k in blob for k in _GREP_INTENT_HINTS)


# --- think：todo_list 规划示例（按场景拆分）---
_THINK_EXAMPLE_GREP = (
    '<good_example><request>界面</request><todo_list>'
    '<item>grep 界面相关 Bug，keywords=界面，target=bug</item></todo_list></good_example>'
)
_THINK_EXAMPLE_GREP_CARD = (
    '<good_example><request>查迭代里的卡片</request><todo_list>'
    '<item>grep keywords="" 或用户给出的关键词，target=card，plan_id=当前迭代</item>'
    '</todo_list></good_example>'
)
_THINK_EXAMPLE_READ_ONLY = (
    '<good_example><request>查看一下测试bug的卡片</request><todo_list>'
    '<item>grep keywords=测试bug，target=card，plan_id=当前迭代；根据 card_location 向用户说明详情，勿再调用 modify</item>'
    '</todo_list></good_example>'
)
_THINK_EXAMPLE_MODIFY = (
    '<good_example><request>改登录 Bug 关闭</request><todo_list>'
    '<item>grep keywords=登录，target=bug</item><item>modify 状态 closed</item></todo_list></good_example>\n'
    '<good_example><request>改创建测试用例7负责人33</request><todo_list>'
    '<item>grep keywords=创建测试用例7，target=testcase</item><item>modify 负责人=33</item></todo_list></good_example>'
)
_THINK_EXAMPLE_CREATE = (
    '<good_example><request>新建登录失败 Bug</request><todo_list>'
    '<item>create 标题登录失败</item></todo_list></good_example>'
)
_THINK_EXAMPLE_COPY = (
    '<good_example><request>复制登录bug1，标题改为登录bug2</request><todo_list>'
    '<item>grep keywords=登录bug1，target=bug</item>'
    '<item>create bug，fields 含 copy_from_bug_id 与新标题（或与复制新建技能一致：grep→copy→create）</item>'
    '</todo_list></good_example>'
)
_THINK_EXAMPLE_BROWSER = (
    '<good_example><request>测登录</request><todo_list>'
    '<item>cdp session create+url → cdp action=login（无凭证则暂停等用户填账号密码）</item></todo_list></good_example>'
)
_THINK_BAD_VAGUE = (
    '<bad_example><request>界面</request><todo_list><item>界面</item></todo_list>原因：应 grep</bad_example>'
)
_THINK_BAD_MODIFY_NO_GREP = (
    '<bad_example><request>改 Bug 状态</request><todo_list><item>仅 modify</item></todo_list>原因：缺 grep</bad_example>'
)
_THINK_BAD_READ_ONLY_MODIFY = (
    '<bad_example><request>看看某张卡片详情</request><todo_list>'
    '<item>grep …</item><item>modify 预览拉详情</item></todo_list>'
    '原因：只读查看应用 grep 返回字段作答，禁止用 modify 当查询</bad_example>'
)

# --- decide：tool/params 决策示例 ---
_DECIDE_EXAMPLE_GREP = """<good_example>
<todo>使用 grep 工具精准定位登录Bug，target=bug</todo>
<tool>grep</tool>
<params>
{{
  "keywords": "登录",
  "project_id": "1",
  "target": "bug"
}}
</params>
<reason>用户查询 Bug，target=bug 只分析 Bug</reason>
</good_example>"""

_DECIDE_EXAMPLE_MODIFY = """<good_example>
<todo>使用 modify 工具修改 Bug 的 priority 为「高」</todo>
<tool>modify</tool>
<params>
{{
  "target": "bug",
  "target_id": 1,
  "modifications": {{"priority": "高"}},
  "project_id": "1",
  "confirm": false
}}
</params>
<reason>先沙箱预览（confirm=false），用户确认后再落库</reason>
</good_example>

<good_example>
<todo>使用 modify 工具修改 BadCase 的 status 为「已关闭」</todo>
<current_context>
  "badcase_list": [{{"id": 3, "title": "测试badcase", "status": "closed"}}]
</current_context>
<tool>modify</tool>
<params>
{{
  "target": "badcase",
  "target_id": 3,
  "modifications": {{"status": "closed"}},
  "project_id": "1",
  "confirm": false
}}
</params>
<reason>从 context 的 badcase_list 取 id 作为 target_id</reason>
</good_example>"""

_DECIDE_EXAMPLE_CREATE = """<good_example>
<todo>使用 create 工具创建 Bug，标题=登录失败</todo>
<tool>create</tool>
<params>
{{
  "target": "bug",
  "fields": {{"title": "登录失败", "priority": "高"}},
  "project_id": "1",
  "confirm": false
}}
</params>
<reason>创建前先预览（confirm=false）</reason>
</good_example>"""

_DECIDE_EXAMPLE_SEARCH = """<good_example>
<todo>搜索 Python asyncio tutorial</todo>
<tool>search</tool>
<params>
{{
  "query": "Python asyncio tutorial",
  "engine": "google",
  "limit": 10
}}
</params>
<reason>英文技术资料优先 google</reason>
</good_example>"""

_DECIDE_BAD_VAGUE = """<bad_example>
<todo>思考应该测试什么</todo>
<tool>unknown</tool>
<reason>Todo 太模糊，没有明确工具</reason>
</bad_example>"""

_DECIDE_BAD_MODIFY_NO_GREP = """<bad_example>
<todo>改 Bug 状态</todo>
<tool>modify</tool>
<reason>缺 grep 定位，不应直接 modify</reason>
</bad_example>"""


def build_prompt_conditional_examples(
    *,
    style: str = "decide",
    todo: str = "",
    user_input: str = "",
    context: Optional[dict] = None,
    prev_tool: Optional[str] = None,
    has_matched_skill: bool = False,
) -> str:
    """按任务类型按需注入 examples；未命中时返回空字符串。"""
    if has_matched_skill:
        return ""
    ctx = context or {}
    prev = str(prev_tool or "").lower() or None
    parts: List[str] = []
    _skip_modify_examples = has_matched_skill and str(
        ctx.get("matched_skill") or ""
    ).lower().startswith("modify_")

    if style == "think":
        if prompt_likely_needs_grep(
            todo=todo, user_input=user_input, context=ctx, prev_tool=prev
        ):
            parts.append(_THINK_EXAMPLE_GREP)
            blob = _prompt_text_blob(todo=todo, user_input=user_input)
            if "卡片" in blob or "card" in blob.lower():
                parts.append(_THINK_EXAMPLE_GREP_CARD)
            if prompt_likely_needs_read_only_query(todo=todo, user_input=user_input):
                parts.append(_THINK_EXAMPLE_READ_ONLY)
                parts.append(_THINK_BAD_READ_ONLY_MODIFY)
        if (
            not _skip_modify_examples
            and prompt_likely_needs_modify(
                todo=todo, user_input=user_input, context=ctx, prev_tool=prev
            )
        ):
            parts.append(_THINK_EXAMPLE_MODIFY)
            parts.append(_THINK_BAD_MODIFY_NO_GREP)
        if prompt_likely_needs_create(todo=todo, user_input=user_input, context=ctx):
            parts.append(_THINK_EXAMPLE_CREATE)
        if prompt_likely_needs_copy(todo=todo, user_input=user_input, context=ctx):
            parts.append(_THINK_EXAMPLE_COPY)
        if prompt_likely_needs_browser_test(todo=todo, user_input=user_input):
            parts.append(_THINK_EXAMPLE_BROWSER)
        if prompt_likely_needs_grep(
            todo=todo, user_input=user_input, context=ctx, prev_tool=prev
        ):
            parts.append(_THINK_BAD_VAGUE)
    else:
        todo_l = (todo or "").lower()
        grep_step = "grep" in todo_l and "modify" not in todo_l
        modify_step = prompt_likely_needs_modify(
            todo=todo, user_input=user_input, context=ctx, prev_tool=prev
        )
        if grep_step or (
            prompt_likely_needs_grep(
                todo=todo, user_input=user_input, context=ctx, prev_tool=prev
            )
            and not modify_step
        ):
            parts.append(_DECIDE_EXAMPLE_GREP)
        if modify_step and not _skip_modify_examples:
            parts.append(_DECIDE_EXAMPLE_MODIFY)
            if prev != "grep" and "grep" not in todo_l:
                parts.append(_DECIDE_BAD_MODIFY_NO_GREP)
        if prompt_likely_needs_create(todo=todo, user_input=user_input, context=ctx):
            parts.append(_DECIDE_EXAMPLE_CREATE)
        if prompt_likely_needs_search(todo=todo, user_input=user_input, context=ctx):
            parts.append(_DECIDE_EXAMPLE_SEARCH)
        if not parts:
            parts.append(_DECIDE_BAD_VAGUE)

    if not parts:
        return ""

    seen: set = set()
    unique: List[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    if style == "think":
        body = "\n".join(unique)
        return f"<examples>\n{body}\n</examples>\n"

    header = (
        "好的决策（示例仅展示 tool/params/reason；**勿**包在 `<decision>` XML 内，"
        "用 function calling 提交）：\n\n"
    )
    bad_parts = [p for p in unique if p.startswith("<bad_example>")]
    good_parts = [p for p in unique if not p.startswith("<bad_example>")]
    body = "\n\n".join(good_parts)
    if bad_parts:
        body += "\n\n不好的决策（避免）：\n" + "\n\n".join(bad_parts)
    return f"<examples>\n{header}{body}\n</examples>\n"


from .evidence_extractor import deep_sse_json_safe
try:
    import xml.etree.ElementTree as ET
except ImportError:
    ET = None


# ============================================================
# 静态系统提示词 - 固定的规则、格式、行为约束
# <system> 块由 llm.chat_messages 在请求前拆为 API role=system（非 user 正文标签）
# ============================================================

REACT_SYSTEM_STATIC = """<system>
你是 ReAct 任务执行引擎，负责分析用户请求并调用工具完成任务。

**输出格式（两段，顺序固定）：**
1) 行动前说明：约 3～10 句，说明目标与执行路径；**不要**写泛泛的「风险点/备选方案」（除非可能造成严重误操作）；**禁止** XML/JSON/思维链标签
2) **仅**一个 <decision>...</decision>，结构如下

**决策规则：**
- 修改类任务须先 grep 后 modify；删除 Bug/BadCase/用例/卡片须先 grep 后 delete（观察里已有列表时从 context 取 id）
- **删除迭代计划**：delete(target=plan, plan_id=…, confirm=false)；侧栏 plan_id 已明确时可直删预览；**禁止**列举计划内卡片当作待删对象
- **仅查看**卡片/Bug/用例详情、用户未要求改字段时：用 grep（或已有 observation 里的列表）直接回答，**不要**调用 modify 当「读详情」
- create/modify/delete 预览用 confirm=false，禁止直接落库
- 目标已达成则 execute=false，tool 留空
- 纯聊天/问候场景：execute=false，不调用工具
- 涉及搜索、查询、测试、修改时 execute 必须为 true
- 不确定参数时可简写，服务端会补全

**modify 工具参数格式（重要）：**
- target: "bug" 或 "badcase" 或 "testcase"（须与 **modifications 字段所属源实体** 一致；**禁止**因上一步 grep 用了 target=card 定位就把 modify 设成改 Card 去写 status/复现等 Bug 字段）
- **禁止从卡片标题推断 target**：标题里出现「testcase」「Bug」「badcase」等字样**不等于**类型；须以 grep 结果中的 **Card.source_type / bug_list·testcase_list** 等为准。**grep target=card 只用于检索 Card 行**；若要改 Bug 状态/复现/严重程度等，modify 的 **target 仍为 bug**，**target_id 为 Bug.id**（从 bug_list / bug_location 取）；可选额外传 **card_id** 辅助关联，**不要**把 modify 写成 target=card + status。
- target_id: 单条记录的 ID（整数）
- target_ids: 多条同一修改时传 ID 数组，如 [9,8]，**一次调用**批量预览（与「各调一次 modify」等价但 UI 稳定为一张卡片多条 diff）
- modifications: {"字段名": "新值"}  # 必须嵌套在 modifications 里！
- **禁止误写 title**：用户用语义里的 Bug/卡片名称（如「一个测试的bug」）**只做定位**，除非用户明确说「改标题/重命名/标题改为」等，否则 **modifications 不要包含 title**。改状态/优先级/负责人时只传对应字段；否则会把 Bug 记录标题写脏（迭代卡片标题已与 Bug 标题解耦，但仍会污染 Bug 列表详情）。
- confirm: false  # 预览模式
</system>

<format>
<decision>
<execute>true 或 false</execute>
<tool>工具名（execute=false 时可为空）</tool>
<params>{"key": "value"}</params>
<reason>一句决策理由</reason>
</decision>
</format>
"""


def build_dynamic_context(
    *,
    project_name: str = "",
    current_todo: str = "",
    user_query: str = "",
    round_idx: int = 0,
    context: dict = None,
    last_observation: dict = None,
    available_tools: list = None,
) -> str:
    """
    构建动态提示词 - 当前对话的具体信息
    
    参数：
    - project_name: 当前项目名称（没有则不显示）
    - current_todo: 当前步骤的待办任务（没有则不显示）
    - user_query: 用户原始请求
    - round_idx: 当前轮次
    - context: 当前上下文信息
    - last_observation: 上一轮观察结果
    - available_tools: 可用工具列表
    """
    parts = []
    
    # 项目信息（有则显示）
    if project_name:
        parts.append(f"<project>{project_name}</project>")
    
    # 用户原始请求
    if user_query:
        parts.append(f"<user_request>{user_query}</user_request>")
    
    # 当前轮次
    parts.append(f"<round_index>{round_idx + 1}</round_index>")
    
    # 当前待办任务（有则显示，没有则提示自主决策）
    if current_todo:
        parts.append(f"<current_todo>{current_todo}</current_todo>")
    else:
        parts.append("<current_todo>（无特定待办，根据上下文自主决策）</current_todo>")
    
    # 当前上下文
    if context:
        context_str = "\n".join([
            f"  - {k}: {str(v)[:500]}"
            for k, v in list(context.items())[:15]
        ])
        parts.append(f"<current_context>\n{context_str}\n</current_context>")
    
    # 上一轮观察（有则显示）
    if last_observation:
        try:
            obs_str = json.dumps(last_observation, ensure_ascii=False, indent=2)[:8000]
        except Exception:
            obs_str = str(last_observation)[:6000]
        parts.append(f"<last_observation>\n{obs_str}\n</last_observation>")
    
    # 可用工具
    if available_tools:
        tools_info = "\n".join([
            f"  <tool id=\"{t['name']}\" description=\"{t['description'][:150]}\"/>"
            for t in available_tools[:20]
        ])
        parts.append(f"<available_tools>\n{tools_info}\n</available_tools>")
    
    return "\n".join(parts)


def _react_think_fc_enabled() -> bool:
    return (os.getenv("REACT_THINK_FC", "1") or "1").strip().lower() in ("1", "true", "yes", "on")


def _react_observe_fc_enabled() -> bool:
    return (os.getenv("REACT_OBSERVE_FC", "1") or "1").strip().lower() in ("1", "true", "yes", "on")


def _react_decide_xml_fallback() -> bool:
    return (os.getenv("REACT_DECIDE_XML_FALLBACK", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def parse_opening_decision(text: str) -> Dict[str, Any]:
    """
    解析首轮 LLM 输出，支持两种格式：
    1. 纯文本（闲聊）→ {"type": "chat", "message": "..."}
    2. {"tool": "...", "params": {...}} → {"type": "single", "tool": "...", "params": {...}}
    
    不再支持 {"plan": [...]} 格式，复杂任务通过多轮对话完成。
    
    返回结构：
    - type: "chat" | "single" | "unknown"
    - message: 闲聊消息（仅 chat 类型）
    - tool/params: 单步任务（仅 single 类型）
    """
    if not text or not isinstance(text, str):
        return {"type": "unknown"}
    
    t = text.strip()
    if not t:
        return {"type": "unknown"}
    
    # 尝试提取 JSON（支持代码块包裹）
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', t)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        # 尝试直接匹配 JSON 对象
        json_match = re.search(r'\{[\s\S]*\}', t)
        json_str = json_match.group(0) if json_match else None
    
    if json_str:
        try:
            obj = json.loads(json_str)
            if isinstance(obj, dict):
                # 格式 2: 单步任务 {"tool": "...", "params": {...}}
                if "tool" in obj:
                    return {
                        "type": "single",
                        "tool": str(obj.get("tool", "")).strip(),
                        "params": obj.get("params") or {},
                        "raw": t,
                    }
                # 不再支持 {"plan": [...]} 格式，忽略 plan 字段
        except json.JSONDecodeError:
            pass
    
    # 格式 1: 纯文本（闲聊）
    # 如果没有匹配到 JSON，且文本不包含工具调用相关关键词，视为闲聊
    tool_keywords = [
        "grep",
        "modify",
        "create",
        "delete",
        "terminal",
        "search",
        "database",
        "cdp",
        "get_tool_description",
    ]
    if not any(kw in t.lower() for kw in tool_keywords):
        return {"type": "chat", "message": t}
    
    # 尝试从文本中提取工具调用
    tool_match = re.search(r'"tool"\s*:\s*"([^"]+)"', t)
    if tool_match:
        tool_name = tool_match.group(1)
        params_match = re.search(r'"params"\s*:\s*(\{[^}]*\})', t)
        params = {}
        if params_match:
            try:
                params = json.loads(params_match.group(1))
            except:
                pass
        return {"type": "single", "tool": tool_name, "params": params, "raw": t}
    
    
    return {"type": "unknown", "raw": t}


def _triple_inference_narrative_zh() -> str:
    """首轮 THINK / 每轮 decide 正文：前两段必写；（3）仅重大问题时可选。"""
    return (
        "【推断结构（正文）】用纯文本组织，**力求简短**（常见任务总篇幅优先控制在约 3～8 句）：\n"
        "（1）**目标与约束**：用户要什么、范围与边界（1～2 句）。\n"
        "（2）**路径与步骤**：本步与整体计划；若有多步 Todo（如先 grep 再 modify），"
        "**逐步**点名每步目的与顺序，**禁止只写当前步而忽略后续步骤**。\n"
        "（3）**风险与备选（默认省略）**：**不要**写套路化的「若未找到/若命中过多/关键词不准」等泛泛风险与备选方案。"
        "仅当存在**重大**不确定性（例如可能误改大批量数据、权限不明、用户意图严重歧义无法安全执行）时，才用 **1～2 句**写清风险与应对；否则本段不写。\n\n"
    )


def _triple_inference_narrative_en() -> str:
    return (
        "[Inference (prose)] Keep it **short** (often ~3–8 sentences total). "
        "(1) **Goals & constraints** (1–2 sentences). "
        "(2) **Path & steps**—if multi-step (e.g. grep then modify), name **each** step in order; do not only describe the first. "
        "(3) **Risks & fallbacks (omit by default)**—do **not** write boilerplate about empty results, too many hits, or keyword tuning. "
        "Only if there is a **major** risk (bulk wrong edits, unclear permission, dangerously ambiguous intent), add **1–2 sentences**; otherwise skip this part.\n\n"
    )


class ReactPromptTemplates:
    """ReAct Prompt 模板库"""
    
    @staticmethod
    def think_prompt(
        user_input: str,
        available_tools: list,
        context: dict,
        todo_list: list,
        ui_locale: Optional[str] = None,
        require_json_plan: Optional[bool] = None,
        force_legacy_xml: bool = False,
    ) -> str:
        """
        THINK 阶段 Prompt - 生成结构化 Todo 列表
        
        强约束：
        - 必须返回 XML 标签包装的 JSON 数组
        - 每项 Todo 对应一个明确的工具或分析步骤
        - 最多 3-5 项，避免过度拆分
        
        require_json_plan：是否要求输出一次性 JSON 计划；None 时读环境变量 REACT_THINK_JSON_PLAN（默认开启）。
        force_legacy_xml：为 True 时强制使用原 XML 模板（供 THINK FC 失败回退）。
        """
        from .intent_guards import agent_testing_mode

        if not force_legacy_xml and _react_think_fc_enabled():
            return ReactPromptTemplates.think_prompt_fc(
                user_input,
                available_tools,
                context,
                todo_list,
                ui_locale=ui_locale,
                require_json_plan=require_json_plan,
            )

        if require_json_plan is None:
            require_json_plan = (os.getenv("REACT_THINK_JSON_PLAN", "1") or "1").strip().lower() not in (
                "0",
                "false",
                "no",
                "off",
            )
        _json_zh = (
            "【一次性完整计划 JSON】在简短规划说明之后，必须再输出**一个**合法 JSON 对象（推荐用 ```json 代码块包裹），"
            "格式严格为：{\"plan\":[{\"id\":1,\"description\":\"……\",\"status\":\"pending\"}, …]}。"
            "id 为递增整数；description 为可执行步骤（与后续工具调用一致）；首轮全部 status 均为 pending，**禁止**分多轮追加步骤。"
            "可同时保留 <todo_list> 与 description 对齐（可选）。\n\n"
        )
        _json_en = (
            "【One-shot plan JSON】After a brief plan narrative, emit **one** valid JSON object (```json fenced), "
            "exactly: {\"plan\":[{\"id\":1,\"description\":\"...\",\"status\":\"pending\"}, ...]}."
            " All steps in the first turn; every status starts as pending; do not append steps across turns."
            " Optional <todo_list> may mirror descriptions.\n\n"
        )
        _json_block = (_json_en if is_english_locale(ui_locale) else _json_zh) if require_json_plan else ""

        _testing_extra_zh = (
            "【测试助手分流】仅当用户明确要求：代码测试、缺陷定位、用例生成/补全、覆盖率或工程质检、或项目内 Bug/用例/BadCase 的查询与修改时，"
            "才输出 <todo_list>。"
            "寒暄、情绪表达、泛泛日常聊天、与上述无关的元问题：简短友好回复（2～4 句），且不要输出 <todo_list>。\n"
            "无明确数据操作目标时，请用户一句话说清目标。\n"
            "Todo 步骤尽量原子化；若两步互不依赖、可同时进行，可写 <item parallel=\"true\">…</item>（与下一无依赖步骤同批并行，由引擎按层调度）。\n"
            "涉及代码结构分析、根因推断时，优先规划可结构化解析的路径（AST/符号/调用关系），避免只做浅层全文关键词猜测。\n\n"
        )
        _testing_extra_en = (
            "[Testing-assistant routing] Output <todo_list> only when the user clearly asks for: code testing, defect triage, "
            "test-case authoring/coverage/quality checks, or in-project Bug/test case/BadCase CRUD/search. "
            "Greetings, venting, small talk, or unrelated meta questions → short warm reply (2–4 sentences); "
            "do not emit <todo_list>. When unsure and no data action is implied, ask user to clarify goal.\n"
            "Keep todo steps atomic; independent steps may use <item parallel=\"true\">…</item> to batch with the next independent step.\n"
            "For code-structure or root-cause work, prefer AST/symbol/call-graph style reasoning over shallow string matching.\n\n"
        )
        _testing_block = (
            (_testing_extra_en if is_english_locale(ui_locale) else _testing_extra_zh)
            if agent_testing_mode()
            else ""
        )

        _gate_block = _testing_block + _json_block

        compact = (os.getenv("REACT_THINK_PROMPT_COMPACT", "1") or "1").strip().lower()
        if compact not in ("0", "false", "no", "off"):
            tools_description = "\n".join([
                f"- {t['name']}: {t['description'][:120]}"
                for t in available_tools[:12]
            ])
            _index_note = ""
            if (os.getenv("REACT_TOOLS_PROMPT_INDEX", "0") or "0").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            ):
                _index_note = (
                    "\n\n【工具索引模式】上表为短描述。不确定参数或用法时，先调用 get_tool_description（tool_name=工具名）"
                    " 获取完整说明，再执行目标工具。"
                )
            context_brief = "\n".join([
                f"- {k}: {str(v)[:120]}"
                for k, v in list((context or {}).items())[:12]
            ]) or "无"
            return f"""{_gate_block}为用户请求生成最短可执行 Todo（优先 1-2 步，最多 3 步）。

<user_request>{user_input}</user_request>
<available_tools>
{tools_description}{_index_note}
</available_tools>
<context>
{context_brief}
</context>
<rules>
1) 查询优先 grep；修改优先 grep 再 modify；创建用 create；**仅在需要用户本机 Shell（git/构建/本地文件）时用 terminal**（command 必填；cwd/timeout 可选；多条本机命令且希望前序失败则不再跑后续时设 stop_on_error=true）。**禁止**用 client_local_bridge 执行或代替 terminal（client_local_bridge 仅用于首次下载安装 go-local-proxy，与「跑一条 Shell」无关）。
2) 禁止空泛步骤（如“分析问题”）；每步必须可执行；**规划说明**须写清「目标与约束 → 路径与步骤（逐步对应每个 &lt;item&gt;）」；**不要**写常规风险与备选；禁止只写 grep 而忽略后续 modify 等步骤。
3) 只输出：
<todo_list><item>...</item></todo_list>
</rules>
"""

        tools_description = "\n".join([
            f"  - <tool name=\"{t['name']}\">{t['description']}</tool>"
            for t in available_tools
        ])
        
        context_str = "\n".join([
            f"  - {k}: {v}"
            for k, v in context.items()
        ])

        _examples = build_prompt_conditional_examples(
            style="think",
            user_input=user_input,
            context=context,
        )
        _examples_intro = (
            "请先掌握上文 <system> 与 <examples>；再结合文末本轮输入生成 Todo。先规划说明再 <todo_list>："
            if _examples
            else "请先掌握上文 <system>；再结合文末本轮输入生成 Todo。先规划说明再 <todo_list>："
        )
        
        # 顺序：固定规则与 examples 置于前半段，便于 LLM 前缀缓存命中；用户请求/工具/上下文置尾（每轮变化）
        return f"""{_gate_block}任务规划：据用户请求生成 Todo（≤3 条），每项对应一个工具。

<system>
两段（顺序固定）1) 规划说明 **简短** 中文（目标与约束 + 路径与步骤，**逐步对应每个 item，含后续 modify 等**；**不写**泛泛风险与备选，除非重大不确定性），无 XML。2) 仅 <todo_list>…</todo_list>，每步 <item>。

规则：有 project_name/plan_name 用自然语言，勿写 project_id=；勿编造名称。技能匹配则跟技能流（阈值约 0.3）。
查询→一步 grep。仅**查看**详情（未要求修改）→一步 grep 或基于已有 grep 结果直接回答，**禁止**为展示而调用 modify。修改→两步 grep 再 modify（禁止只 modify）。**零起新建**→一步 create。**按已有记录复制新建**（copy_record 技能）→三步 **grep → copy（属性合并/不落库）→ create（预览与落库）**；若合并链稳定也可一步 **create**，fields 含 **copy_from_bug_id / copy_from_badcase_id / copy_from_testcase_id / copy_from_card_id**（与 copy→create **等价**，并非只能用卡片）。**copy 工具支持 bug、badcase、testcase、card**。浏览器/UI 测试→多步 **cdp**（描述测试步骤或用迭代计划**测试用例**时自动开启 **cdp_test_run** 任务；session create+url → login → 按步骤/用例 cdp 操作或 explore phase=full；失败可自动 create Bug/计划预览）。本机命令→一步 terminal（command 必填）。
grep：keywords 在 Bug/BadCase/TestCase/Card 的**主要文本字段**中模糊匹配（标题、描述、步骤、状态、优先级、类型、环境、负责人等；纯数字可匹配 id）；**多词默认 OR**；须全部词命中时 GREP_KEYWORDS_MATCH_MODE=and。按负责人筛可传 assignee=姓名。**主界面迭代列表即 Card 表**；泛查用 target=all；用户明确「查卡片/卡片列表」时用 target=card。target∈bug/badcase/testcase/card/all；查全用 "" 或 *。「测试用例/用例」→ testcase。
modify：按 **要改的字段** 选 bug/badcase/testcase（**grep 用 card 与 modify 用 card 无必然关系**；改状态/复现等缺陷字段时 target 必须是 bug 等源表，勿 target=card）。不可改 type/id/project_id/plan_id。批量：一条 grep 全量 + 一条 modify。复制用例：fields 可含 copy_from_testcase_id。
</system>

{_examples}
<format>第二段仅 <todo_list><item>…</item></todo_list></format>
{_examples_intro}

---
本轮输入（以下内容每轮变化）

<user_request>
{user_input}
</user_request>

<available_tools>
{tools_description}
</available_tools>

<context>
已知信息：
{context_str if context_str else "无"}
</context>

现在请生成 Todo 列表：
"""

    @staticmethod
    def think_prompt_fc(
        user_input: str,
        available_tools: list,
        context: dict,
        todo_list: list,
        ui_locale: Optional[str] = None,
        require_json_plan: Optional[bool] = None,
    ) -> str:
        """
        THINK：仅用 function calling（submit_react_think），不要求正文中的 <todo_list> / JSON 计划块。
        """
        from .intent_guards import agent_testing_mode

        _testing_extra_zh = (
            "【测试助手分流】仅当用户明确要求代码测试、缺陷、用例、覆盖率或项目内数据操作时 need_tools=true 并给出 todo_items；"
            "寒暄与无关闲聊 need_tools=false，message 简短友好，不要 todo_items。\n\n"
        )
        _testing_extra_en = (
            "[Testing routing] need_tools=true only for testing/defect/coverage/in-project data work; "
            "small talk → need_tools=false with a short message; omit todo_items.\n\n"
        )
        _testing_block = (
            (_testing_extra_en if is_english_locale(ui_locale) else _testing_extra_zh)
            if agent_testing_mode()
            else ""
        )
        _branch_zh = (
            "【三分支】据本轮推断**只选其一**，勿折中：\n"
            "· **直驱工具**：已明确单步、单工具即可（如仅一次 grep）；**修改/删除须先 grep**，禁止首轮直驱 modify/delete。"
            "need_tools=true，need_todo_list=false，todo_items 必须为空 []；系统不展示 Todo 列表，直接进入工具决策与执行。\n"
            "· **推断需 Todo**：多步、跨工具、或需要向用户展示执行计划，need_tools=true，need_todo_list=true，"
            "todo_items 每步一条可执行描述；主循环中每步为观察/决策 → 再思考 → 再调工具。\n"
            "· **闲聊/寒暄/纯文字**：不涉及项目内 Bug/BadCase/测试用例等的查改，need_tools=false，"
            "message 写 2～4 句友好回复；不要 todo_items。\n\n"
        )
        _branch_en = (
            "[Three branches] Choose **exactly one** from inference:\n"
            "· **Direct tool**: one clear atomic step (e.g. single grep only); "
            "**modify/delete must follow grep**—never skip grep on the first tool call. "
            "need_tools=true, need_todo_list=false, todo_items MUST be [].\n"
            "· **Todo plan**: multi-step / cross-tool / user should see the plan → need_tools=true, need_todo_list=true, "
            "todo_items one string per step; main loop per step: observe/decide → think → tool.\n"
            "· **Chat only**: small talk / no in-project record work → need_tools=false, message only; omit todo_items.\n\n"
        )
        _fc_gate_zh = (
            "【输出方式】正文可先写简短分析（纯文本，不要用 XML）。"
            "**必须**调用函数 **submit_react_think** 一次，填写：need_tools、need_todo_list、可选 need_plan_ui、"
            "need_tools=false 时的 message、need_todo_list=true 时的 todo_items（每步一条）。"
            "禁止输出 <todo_list> 或 ```json 计划块。\n\n"
        )
        _fc_gate_en = (
            "[Output] You may write a brief analysis in plain text (no XML). "
            "You **must** call **submit_react_think** once with need_tools, need_todo_list, optional need_plan_ui, "
            "message when need_tools=false, and todo_items when need_todo_list=true. "
            "Do not emit <todo_list> or fenced JSON plans.\n\n"
        )
        _triple_narr = (
            _triple_inference_narrative_en()
            if is_english_locale(ui_locale)
            else _triple_inference_narrative_zh()
        )
        _fc_block = (
            _testing_block
            + (_branch_en if is_english_locale(ui_locale) else _branch_zh)
            + _triple_narr
            + (_fc_gate_en if is_english_locale(ui_locale) else _fc_gate_zh)
        )

        compact = (os.getenv("REACT_THINK_PROMPT_COMPACT", "1") or "1").strip().lower()
        if compact not in ("0", "false", "no", "off"):
            tools_description = "\n".join([
                f"- {t['name']}: {t['description'][:120]}"
                for t in available_tools[:12]
            ])
            _index_note = ""
            if (os.getenv("REACT_TOOLS_PROMPT_INDEX", "0") or "0").strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            ):
                _index_note = (
                    "\n\n【工具索引】上表为短描述。不确定参数时可先调用 get_tool_description（tool_name=工具名）。"
                )
            context_brief = "\n".join([
                f"- {k}: {str(v)[:120]}"
                for k, v in list((context or {}).items())[:12]
            ]) or "无"
            return f"""{_fc_block}为用户请求生成最短可执行路径（优先 1～2 步，最多 3 步）。

<user_request>{user_input}</user_request>
<available_tools>
{tools_description}{_index_note}
</available_tools>
<context>
{context_brief}
</context>
<rules>
1) 查询优先 grep；修改优先 grep 再 modify；创建用 create；本机 Shell 用 terminal（command 必填）。
2) need_todo_list=true 时 todo_items 中禁止空泛步骤；每步必须可执行；上文「路径与步骤」须**逐项**覆盖 todo_items，禁止只写第一步。
3) need_todo_list=false 时 todo_items 必须为空；禁止闲聊却 need_tools=true。
4) 有 project_name/plan_name 用自然语言，勿写 project_id=；勿编造名称。
</rules>
"""

        tools_description = "\n".join([
            f"  - <tool name=\"{t['name']}\">{t['description']}</tool>"
            for t in available_tools
        ])
        context_str = "\n".join([f"  - {k}: {v}" for k, v in context.items()])
        return f"""{_fc_block}任务规划（仅通过 submit_react_think 提交）。

<system>
单步直驱：need_todo_list=false 且 todo_items=[]。多步计划：need_todo_list=true 且 todo_items 逐项列出。
need_tools=false 时不要 todo_items（闲聊分支）。
规则：查询→grep。修改→grep 再 modify。创建→create。浏览器测试→多步 cdp。本机命令→terminal（command）。
多步时：上文「路径与步骤」必须与 todo_items **逐步一一对应**（含后续 modify），不得只描述 grep。
</system>

<user_request>
{user_input}
</user_request>

<available_tools>
{tools_description}
</available_tools>

<context>
{context_str if context_str else "无"}
</context>
现在请调用 submit_react_think 完成本轮规划：
"""

    @staticmethod
    def merged_opening_decide_prompt_fc(
        user_input: str,
        available_tools: list,
        context: dict,
        *,
        ui_locale: Optional[str] = None,
    ) -> str:
        """
        合并首轮：根据任务复杂度选择输出模式。
        - 闲聊：直接回复文本
        - 简单单步：输出 {"tool": "...", "params": {...}}
        - 复杂多步：输出 {"plan": [...], "first_tool": "...", "first_params": {...}}
        """
        tools_info = "\n".join([
            f"  - {t['name']}: {t['description'][:150]}"
            for t in available_tools[:10]
        ])
        context_str = "\n".join([
            f"  - {k}: {str(v)[:100]}"
            for k, v in list((context or {}).items())[:10]
        ]) if context else "无"

        _head_zh = """【行为模式·最高优先级】
你必须直接给出“决定”，不要输出任何元认知语句（例如“我需要分析一下”“让我想想”）。

【三选一输出模式】
1. **闲聊**：用户只是打招呼或聊天 → 直接回复友好文本
2. **简单单步**：一次查询或单个操作即可完成 → 输出 JSON：`{"tool": "工具名", "params": {...}}`
3. **复杂多步**：需要先查询再修改、或涉及多个工具 → 输出 JSON：`{"plan": ["步骤1", "步骤2", ...], "first_tool": "首个工具", "first_params": {...}}`

**判断标准**：
- 仅查询（grep/search）→ 简单单步
- 仅创建单条记录（create）→ 简单单步
- 仅本机 Shell（git/构建/本地文件）→ 简单单步（工具 terminal，params.command；多步且前序失败要停后续可加 stop_on_error=true）；勿用 client_local_bridge（仅下载安装代理）
- 先查再改（grep + modify）→ 复杂多步
- 批量操作或多表关联 → 复杂多步

**禁止事项**：
- 不要输出 <decision> XML 标签
- 不要在 JSON 前后写长篇分析
- 不要输出元认知语句
"""
        _head_en = """【Behavior Pattern·Highest Priority】
You MUST give a "decision" directly. Do NOT output any meta-cognitive statements (e.g., "Let me analyze", "I need to think").

【Choose ONE output mode】
1. **Chat**: User just says hi or chats → Reply with friendly text directly
2. **Simple single step**: One query or single operation → Output JSON: `{"tool": "tool_name", "params": {...}}`
3. **Complex multi-step**: Query then modify, or multiple tools → Output JSON: `{"plan": ["step1", "step2", ...], "first_tool": "first_tool", "first_params": {...}}`

**Decision criteria**:
- Query only (grep/search) → Simple single step
- Create single record (create) → Simple single step
- Local shell only (git/build/files) → Simple single step (tool `terminal`, params.command; optional `stop_on_error=true` to skip later queued commands after a failure)
- Query then modify (grep + modify) → Complex multi-step
- Batch operations or multi-table → Complex multi-step

**Prohibitions**:
- Do NOT output <decision> XML tags
- Do NOT write lengthy analysis before/after JSON
- Do NOT output meta-cognitive statements
"""
        head = _head_en if is_english_locale(ui_locale) else _head_zh

        return f"""{head}

<user_request>
{user_input}
</user_request>

<available_tools>
{tools_info}
</available_tools>

<context>
{context_str}
</context>

<rules>
1. 查询优先 grep；修改优先 grep 再 modify；创建用 create；本机 Shell（git/构建等）用 terminal（command）。
2. 单步任务直接调用工具；多步任务先输出 plan 再调用首个工具。
3. plan 中的步骤必须具体可执行，不要空泛描述。
</rules>
"""

    @staticmethod
    def decide_prompt_fc(todo: str, user_input: str, available_tools: list, context: dict) -> str:
        """ACT：仅用 function calling 选择工具；不要求 <decision> XML。"""
        tools_info = "\n".join([
            f"  - {t['name']}: {t['description'][:200]}"
            for t in available_tools
        ])
        context_str = "\n".join([
            f"  - {k}: {str(v)[:100]}"
            for k, v in (context or {}).items()
        ]) if context else "无"

        _tool_details = build_prompt_conditional_tool_details(
            todo=todo,
            user_input=user_input,
            context=context,
        )
        _examples = build_prompt_conditional_examples(
            style="decide",
            todo=todo,
            user_input=user_input,
            context=context,
        )

        return f"""<system>
你是任务执行决策专家。{_triple_inference_narrative_zh()}请先写 **简短** 中文「行动前说明」（纯文本，不要用 XML），
优先 **4～10 句**：须覆盖（1）目标与约束（2）路径与步骤；**（3）风险与备选仅在有重大不确定性时写 1～2 句，否则省略**。
若整体计划含多步（如先 grep 再 modify），在「路径与步骤」中说明本步与后续未执行步骤的关系。
然后**必须**通过 **function calling** 调用**一条**工具函数，参数为 JSON 对象（与原先 <decision> 内 params 一致）。
不要输出 <decision> 标签。

绑定规则（最高优先级）：
- Todo 明确写「使用 grep 工具」→ 只能调用 grep。
- Todo 明确写「使用 modify 工具」→ 只能调用 modify。
- 同理 create / cdp（浏览器测试）。

原则：涉及搜索/查询/测试/修改项目数据时 execute 对应为 true（通过实际调用工具体现）。
modify 前若上下文无列表，应先 grep；params 可不全，服务端会合并补参。modify/create 的 confirm 须为 false。
细则不确定时先 **get_tool_description**(modify|search|grep)。

{_tool_details}
{_examples}
</system>
<current_todo>
{todo}
</current_todo>
<user_request>
{user_input}
</user_request>
<available_tools>
{tools_info}
</available_tools>
<current_context>
{context_str}
</current_context>
请说明后调用工具函数完成决策：
"""
    
    @staticmethod
    def decide_prompt(todo: str, user_input: str, available_tools: list, context: dict) -> str:
        """
        ACT 阶段 Prompt - 决定是否执行并选择工具
        
        强约束：
        - 必须返回 XML 包装的 JSON 对象
        - 包含 execute / tool / params 三个关键字段
        - 提供详细的决策理由
        - 智能选择搜索引擎
        - modify：params 可不全；引擎会按服务端补参逻辑在执行前合并（见 prompt 内「服务端补参」）
        """
        if not _react_decide_xml_fallback():
            return ReactPromptTemplates.decide_prompt_fc(todo, user_input, available_tools, context)
        tools_info = "\n".join([
            f"  <tool id=\"{t['name']}\" description=\"{t['description']}\"/>"
            for t in available_tools
        ])
        
        context_str = "\n".join([
            f"  - {k}: {str(v)[:100]}"
            for k, v in context.items()
        ]) if context else "无"

        _tool_details = build_prompt_conditional_tool_details(
            todo=todo,
            user_input=user_input,
            context=context,
        )
        _examples = build_prompt_conditional_examples(
            style="decide",
            todo=todo,
            user_input=user_input,
            context=context,
        )

        return f"""你是一个任务执行决策专家。分析当前 Todo，决定是否执行以及使用哪个工具。

<system>
你必须分两段输出（顺序固定）：
1) **行动前说明**：用 **3～10 句**中文说明怎么做、为什么；**不要**堆砌泛泛「风险点/备选方案」（除非可能造成严重误操作）。可在首行使用「💭」（可选）。这一段**禁止使用 XML 标签**（包含 <decision>/<thinking> 等）。
2) **机器可读决策**：在说明之后，**单独**输出且仅输出一个 <decision>...</decision> 块。

你的角色：根据 Todo 和当前上下文，做出执行决策
涉及代码阅读、缺陷根因、结构理解时：优先采用可结构化分析的方式（AST/符号表/调用关系、精确文件与行号），避免仅凭模糊关键词臆测；若工具有模式参数，优先选结构化/精准模式。
决策原则（严格按以下规则）：
1. 强制绑定规则（优先级最高，绝不能违反）：
   - 如果 Todo 文本中明确包含「使用 grep 工具」或 \"use grep tool\"，则 tool 字段必须为 \"grep\"。
   - 如果 Todo 文本中明确包含「使用 modify 工具」或 \"use modify tool\"，则 tool 字段必须为 \"modify\"。
   - 如果 Todo 文本中明确包含「使用 create 工具」或 \"use create tool\"，则 tool 字段必须为 \"create\"。
   - 如果 Todo 文本中明确包含「使用 cdp 工具」或 \"use cdp tool\"，则 tool 字段必须为 \"cdp\"。
   - 当存在上述绑定时，绝对禁止选择其他工具（例如：Todo 里写了「使用 modify 工具」，决策结果却给出 cdp，这是错误的）。
2. 在没有明确「使用 XXX 工具」字样时，再根据 Todo 内容选择最合适的工具。
3. 如果 Todo 包含工具操作词汇（search、搜索、查询、测试、browser、数据库等），必须执行（execute: true）
4. 如果 Todo 涉及外部信息获取或用户请求验证，必须执行（execute: true）
5. 仅当 Todo 是纯分析/整理且完全不涉及工具调用时，才考虑跳过（execute: false）
6. 优先执行而非跳过 - 当有疑问时，必须 execute: true
7. 提供清晰的决策理由
8. 工具参数应该具体且可执行
9. create 工具：**params 中 confirm 必须为 false**（仅生成预览与 diff）；禁止在对话首轮直接落库，采纳由用户在左侧列表完成。
10. **新建迭代计划（target=plan）**：用户说「创建/新建迭代计划」时**必须立刻**调用 create(target=plan, fields 含 name 等, confirm=false) 生成沙箱 diff；**禁止**在对话里口头问「是否继续/要不要创建」代替工具预览；用户回复「是/否」时不得当作已创建或已取消，须以侧栏沙箱预览的 ✓/✗ 为准。fields.name 必填；缺 start_date/end_date 时服务端会补默认日期。
11. **删除迭代计划（target=plan）**：用户说「删除/删掉迭代计划」时调用 delete(target=plan, plan_id=当前侧栏或 grep 的 first_plan_id, confirm=false) 预览 **Plan 节点**；用户确认后再 confirm=true。**禁止** target=card/bug/badcase；**禁止**在 natural language 回复中罗列计划内 Bug/卡片清单代替 plan 预览摘要。

{_tool_details}
</system>

<current_todo>
{todo}
</current_todo>

<user_request>
{user_input}
</user_request>

<available_tools>
{tools_info}
</available_tools>

<current_context>
{context_str}
</current_context>

{_examples}
<format>
第二段必须是且仅包含：
<decision>
<execute>true/false</execute>
<tool>工具名（execute=true 时必填，选择最符合 Todo 的工具）</tool>
<params>
{{
  "param_name": "param_value",
  "engine": "baidu/google/bing (仅当工具是search时需要根据规则智能选择)"
}}
</params>
<reason>决策理由（简洁，1-2 句话，说明为什么选择该工具和参数）</reason>
</decision>

⚠️ 重要：
- 当 Todo 涉及搜索、查询、测试时，execute 必须是 true
- 不要因为担心错误而跳过任务，工具失败比跳过任务更好
- 使用 search 工具时，必须根据关键词特征智能选择合适的搜索引擎
</format>

请先写「行动前说明」，再输出 <decision>：

现在请做出决策：
"""

    @staticmethod
    def decide_prompt_react_dynamic(
        user_input: str,
        available_tools: list,
        context: dict,
        *,
        round_idx: int,
        last_observation: Optional[dict],
        last_analysis: Optional[dict],
        current_todo: str = "",
        project_name: str = "",
    ) -> str:
        """
        动态 ReAct：每一步根据「当前上下文 + 上一步观察」再决策。
        
        结构：静态系统提示词 + 动态上下文信息
        """
        # 构建动态上下文
        dynamic_context = build_dynamic_context(
            project_name=project_name,
            current_todo=current_todo,
            user_query=user_input,
            round_idx=round_idx,
            context=context,
            last_observation=last_observation,
            available_tools=available_tools,
        )
        
        # 返回：静态系统提示 + 动态上下文
        return f"""{REACT_SYSTEM_STATIC}

{dynamic_context}

请先写行动前说明，再输出 <decision>：
"""

    @staticmethod
    def react_unified_prompt(
        user_input: str,
        available_tools: list,
        context: dict,
        *,
        round_idx: int = 0,
        prev_observation: Optional[dict] = None,
        prev_action: Optional[dict] = None,
        plan_hints: List[str] = None,
        todo: str = "",
        scheduled_plan: Optional[List[str]] = None,
        first_round_task_plan: bool = False,
        ui_locale: Optional[str] = None,
        fc_decide: bool = False,
        matched_skill_name: Optional[str] = None,
        skill_workflow_prompt: Optional[str] = None,
        skill_tool_names: Optional[List[str]] = None,
    ) -> str:
        """统一流：observation/thinking XML + function calling 决策（无 `<decision>` XML）。"""
        _has_skill = bool((matched_skill_name or "").strip() and (skill_workflow_prompt or "").strip())
        try:
            _max_tools = int((os.getenv("REACT_UNIFIED_MAX_TOOLS") or "16").strip() or "16")
        except Exception:
            _max_tools = 16
        _max_tools = max(4, min(_max_tools, 32))
        _tools_for_prompt = sorted(
            filter_tools_for_unified_prompt(available_tools or [], skill_tool_names)[:_max_tools],
            key=lambda t: str((t or {}).get("name") or ""),
        )
        try:
            _tool_desc_cap = int(os.getenv("REACT_TOOL_INDEX_DESC_CHARS", "120") or "120")
        except ValueError:
            _tool_desc_cap = 120
        _tool_desc_cap = max(40, _tool_desc_cap)

        def _tool_desc_for_prompt(t: dict) -> str:
            name = str((t or {}).get("name") or "")
            desc = str((t or {}).get("description") or "")
            if name == "get_tool_description":
                return desc
            if _has_skill and len(desc) > 80:
                return desc[:80].rstrip() + "…"
            if len(desc) > _tool_desc_cap:
                return desc[:_tool_desc_cap].rstrip() + "…"
            return desc

        tools_info = "\n".join([
            f"  <tool id=\"{t['name']}\" description=\"{_tool_desc_for_prompt(t)}\"/>"
            for t in _tools_for_prompt
        ])
        _tools_hint = (
            "Tool list is a short index; call **get_tool_description** for full params."
            if is_english_locale(ui_locale)
            else "工具列表为短索引；完整参数与用法请调用 **get_tool_description**。"
        )
        # context 键按名字排序，避免 dict 插入顺序变化导致每轮字符串漂移
        _ctx_items = sorted(
            ((k, v) for k, v in (context or {}).items() if k not in _UNIFIED_CTX_SKIP_KEYS),
            key=lambda kv: str(kv[0]),
        )[:15]
        context_str = "\n".join([
            f"  - {k}: {str(v)[:300]}"
            for k, v in _ctx_items
        ]) if _ctx_items else "无"

        if scheduled_plan:
            n = len(scheduled_plan)
            if round_idx < n:
                cur = scheduled_plan[round_idx]
                if _has_skill:
                    current_todo_body = f"【技能当前步】{cur}"
                else:
                    tail = [scheduled_plan[i] for i in range(round_idx + 1, n)]
                    tail_join = "；".join(tail[:8])
                    if len(tail) > 8:
                        tail_join += " …"
                    current_todo_body = f"【第 {round_idx + 1}/{n} 步（本轮须推进）】{cur}"
                    if tail_join:
                        current_todo_body += f"\n【后续步骤】{tail_join}"
            else:
                current_todo_body = (
                    f"计划内共列出 {n} 步；若所需工具已全部执行完毕则 execute=false；"
                    "否则继续下一工具 execute=true，直至无遗漏。"
                )
        else:
            current_todo_body = todo or "（无特定待办）"

        first_round_plan_block = ""
        if (
            first_round_task_plan
            and round_idx == 0
            and not scheduled_plan
            and not _has_skill
        ):
            first_round_plan_block = """
**首轮任务计划（可选）：** 复杂多步可在 `<thinking>` 内写 `<task_plan>`（2～12 步）；简单单步不写。多步时本回合 function 须与第 1 步一致。
"""

        obs_str = "（这是首轮，还没有上一轮观察）"
        if prev_observation is not None:
            _obs_for_json = (
                deep_sse_json_safe(prev_observation)
                if isinstance(prev_observation, dict)
                else prev_observation
            )
            try:
                raw = json.dumps(
                    _obs_for_json,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                    sort_keys=True,
                )
                obs_str = raw[:8000] + ("…" if len(raw) > 8000 else "")
            except Exception:
                obs_str = str(prev_observation)[:6000]

        action_str = "无"
        if prev_action:
            try:
                _params_safe = deep_sse_json_safe(prev_action.get("params", {}))
                if not isinstance(_params_safe, dict):
                    _params_safe = {}
                _ap = json.dumps(
                    _params_safe,
                    ensure_ascii=False,
                    default=str,
                    sort_keys=True,
                )
            except Exception:
                _ap = str(prev_action.get("params", {}))
            action_str = f"工具: {prev_action.get('tool')}，参数: {_ap}"

        _prev_tool = (
            str((prev_action or {}).get("tool") or "").strip().lower() or None
            if isinstance(prev_action, dict)
            else None
        )
        _tool_details = build_prompt_conditional_tool_details(
            todo=current_todo_body,
            user_input=user_input,
            context=context,
            prev_tool=_prev_tool,
            has_matched_skill=_has_skill,
        )
        _examples = build_prompt_conditional_examples(
            style="decide",
            todo=current_todo_body,
            user_input=user_input,
            context=context,
            prev_tool=_prev_tool,
            has_matched_skill=_has_skill,
        )

        if is_english_locale(ui_locale):
            _unified_lang_block = """**UI language (strict):** The user is on the **English** UI. All human-readable prose inside `<observation>`, `<thinking>`, `<reason>`, and any `<task_plan>` step lines must be **clear English**. Keep tool names, XML tag names, JSON keys, code, and direct quotes of non-English user text as needed; do not add English-only scaffolding if the user wrote in another language unless you are explaining that quote.

"""
        else:
            _unified_lang_block = """**界面语言（须严格遵守）：** 当前为**简体中文**界面。`<observation>`、`<thinking>`、`<reason>` 以及 `<task_plan>` 内步骤说明等**所有面向人的自然语言**须使用**简体中文**；勿用「Thinking Process」「Analyze the Request」等英文小节标题或英文模板化推理（工具名、XML 标签名、JSON 字段名、代码、用户原文引用除外）。

"""

        _grep_first_block = ""
        if not _has_skill:
            if isinstance(prev_observation, dict) and prev_observation.get("reason") == "grep_required_before_modify":
                _grep_first_block = unified_round_grep_first_prompt_block(
                    round_idx=round_idx,
                    prev_observation=prev_observation,
                    ui_locale=ui_locale,
                )
            elif round_idx == 0:
                _grep_first_block = unified_round_grep_first_prompt_block(
                    round_idx=round_idx,
                    prev_observation=prev_observation,
                    ui_locale=ui_locale,
                )

        _skill_block = ""
        if _has_skill:
            _skill_block = build_matched_skill_prompt_block(
                str(matched_skill_name),
                str(skill_workflow_prompt or ""),
                ui_locale=ui_locale,
                include_footer=False,
            )

        _decision_rules = unified_minimal_decision_rules_block(
            fc_decide=True,
            ui_locale=ui_locale,
            has_matched_skill=_has_skill,
        )

        _output_format_block = """
**输出格式（两段 XML + function calling；禁止 `<decision>` / `<execute>` / `<params>` XML）：**

1. `<observation>...</observation>` — 首轮留空；后续轮最多2句
2. `<thinking>...</thinking>` — 先写目标与推理（3句以内）；**末行**（`</thinking>` 前）写 `<think_summary>…</think_summary>`（一句≤40字，归纳上文思考结论，供界面折叠展示）；复杂多步且无 `<matched_skill>` 时可写 `<task_plan>`
3. 上述 XML 闭合后 → **function calling** 调用恰好一个函数（业务工具，或收尾时 submit_unified_round）
"""
        _format_tail = ""
        _closing_instruction = "请输出 observation → thinking → 一个 function call："

        _segment_title = "观察分析 → 思考规划 → function calling"
        _self_check = "<observation>、<thinking> 写全并闭合后，再发起 function calling。"
        return f"""你是 ReAct 任务执行引擎。一次输出：{_segment_title}。

<system>
{_unified_lang_block}**输出前自检（在心里完成即可）：** {_self_check}

{_output_format_block}
{_grep_first_block}{_skill_block}{_decision_rules}{_tool_details}{_examples}{first_round_plan_block}
{_tools_hint}
</system>

<user_request>
{user_input}
</user_request>

<available_tools>
{tools_info}
</available_tools>
{_format_tail}

以下为本轮动态上下文（轮次、待办、项目上下文、上一轮动作与观察；每轮都会变，须结合决策）：

<round_index>{round_idx + 1}</round_index>

<current_todo>
{current_todo_body}
</current_todo>

<current_context>
{context_str}
</current_context>

<prev_action>
{action_str}
</prev_action>

<prev_observation>
{obs_str}
</prev_observation>

{_closing_instruction}
"""

    @staticmethod
    def observe_prompt(
        todo: str,
        action: dict,
        observation: dict,
        context: dict,
        *,
        force_legacy_xml: bool = False,
    ) -> str:
        """
        OBSERVE 阶段 Prompt - 分析工具结果并提取关键信息
        
        强约束：
        - 必须返回 XML 包装的结构化结果
        - 提取 key_findings / context_updates / next_step
        - 为下一个 Todo 准备上下文
        force_legacy_xml：为 True 时强制 <result> XML 模板（供 observe FC 失败回退）。
        """
        if not force_legacy_xml and _react_observe_fc_enabled():
            return ReactPromptTemplates.observe_prompt_fc(todo, action, observation, context)
        observation_str = json.dumps(observation, ensure_ascii=False, indent=2)
        
        return f"""分析工具结果，供下一步决策使用。

<system>
两段（顺序固定）：
1) 分析说明：2～8 句中文；**禁止**在说明里写 <result>/<finding>。
2) **仅**一个 <result>...</result>，结构见 <format>。
要点：提炼成败与关键数据；grep 时把 bug_list/badcase_list/testcase 等写入 context_update 供 modify；搜索类总结结论勿堆砌原文。
</system>
<todo>{todo}</todo>
<action_taken>工具：{action.get('tool')} 参数：{json.dumps(action.get('params', {}), ensure_ascii=False)}</action_taken>
<tool_result>
{observation_str}
</tool_result>
<current_context>
{json.dumps(context, ensure_ascii=False, indent=2) if context else "{{}}"}
</current_context>
<format>
<result>
<key_findings>
  <finding type="bug|info|success">…</finding>
</key_findings>
<context_update>{{ "key": "value" }}</context_update>
<next_step>…</next_step>
</result>
</format>
先说明再 <result>：
"""

    @staticmethod
    def observe_prompt_fc(todo: str, action: dict, observation: dict, context: dict) -> str:
        """OBSERVE：仅用 function calling（submit_observe_analysis），不要求 <result> XML。"""
        observation_str = json.dumps(observation, ensure_ascii=False, indent=2)
        return f"""分析工具执行结果，供下一步决策。

<system>
两段：1) 先用 2～8 句中文说明分析（纯文本，不要写 XML）。2) **必须**调用函数 **submit_observe_analysis**，传入 findings（字符串数组）、context_update（对象）、next_step（字符串）。
禁止输出 <result>。
要点：提炼成败与关键数据；grep 时把列表类结果写入 context_update 供后续 modify。
</system>
<todo>{todo}</todo>
<action_taken>工具：{action.get('tool')} 参数：{json.dumps(action.get('params', {}), ensure_ascii=False)}</action_taken>
<tool_result>
{observation_str}
</tool_result>
<current_context>
{json.dumps(context, ensure_ascii=False, indent=2) if context else "{{}}"}
</current_context>
先说明再调用 submit_observe_analysis：
"""

    @staticmethod
    def ui_params_summary_prompt(
        todo: str,
        tool: str,
        params: Optional[dict],
        reason: str = "",
        todos_overview: str = "",
    ) -> str:
        """面向聊天面板：把结构化入参改写成用户可读说明（不展示原始 JSON）。"""
        pj = json.dumps(params or {}, ensure_ascii=False, indent=2)
        r = (reason or "").strip()
        rline = f"\n模型简述：{r[:900]}" if r else ""
        tv = (todos_overview or "").strip() or "（仅本步，未提供完整列表）"
        return f"""用 2～5 句中文说明本步将执行什么（工具、关键词、target、关键 id）。勿 JSON/XML/代码块。

待办全貌：
{tv}
本步 Todo：{todo}
工具：{tool}
参数要点：{pj}{rline}
"""

    @staticmethod
    def ui_decision_summary_prompt(todo: str, decision: dict, todos_overview: str = "") -> str:
        """面向聊天面板：总结决策结论（替代原始 XML）。"""
        tool = str(decision.get("tool") or "")
        ex = "是" if decision.get("execute") else "否"
        pj = json.dumps(decision.get("params") or {}, ensure_ascii=False, indent=2)
        r = (decision.get("reason") or "").strip()
        rline = f"\n模型决策理由：{r[:1200]}" if r else ""
        tv = (todos_overview or "").strip() or "（仅本步，未提供完整列表）"
        return f"""2～5 句中文：是否执行、工具、意图。勿 XML/JSON/代码块。

待办：{tv}
Todo：{todo} | 执行：{ex} | 工具：{tool}
参数：{pj}{rline}
"""

    @staticmethod
    def ui_observe_summary_prompt(
        todo: str, tool: str, observation: Any, todos_overview: str = ""
    ) -> str:
        """面向聊天面板：总结工具执行结果（替代原始 observe XML）。"""
        try:
            if isinstance(observation, dict):
                obs_s = json.dumps(observation, ensure_ascii=False)
            else:
                obs_s = str(observation)
        except Exception:
            obs_s = str(observation)
        max_len = 8000
        if len(obs_s) > max_len:
            obs_s = obs_s[:max_len] + "\n…（已截断）"
        tv = (todos_overview or "").strip() or "（仅本步，未提供完整列表）"
        return f"""2～6 句中文：本步结果、关键数据、对后续含义。勿 XML/JSON/代码块。

待办：{tv}
Todo：{todo} | 工具：{tool}
返回节选：
{obs_s}
"""


def format_tools_for_prompt(
    tool_registry,
    exclude_tool_names: Optional[Tuple[str, ...]] = None,
) -> list:
    """格式化工具信息。REACT_TOOL_DESC_MAX_CHARS>0 时截断描述，缩短首轮 THINK prompt（不改模型，仅减 token）。

    REACT_TOOLS_PROMPT_INDEX=1：除 get_tool_description 外，各工具描述截断为短索引（REACT_TOOL_INDEX_DESC_CHARS，默认 120），
    与元工具 get_tool_description 配合渐进式披露。

    默认对「同一套工具定义 + 同一截断配置」做进程内缓存，避免每轮对话重复遍历/截断；``REACT_TOOLS_FORMAT_CACHE=0`` 关闭。
    """
    try:
        max_chars = int(os.getenv("REACT_TOOL_DESC_MAX_CHARS", "0") or "0")
    except Exception:
        max_chars = 0
    index_mode = (os.getenv("REACT_TOOLS_PROMPT_INDEX", "1") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    try:
        index_short = int(os.getenv("REACT_TOOL_INDEX_DESC_CHARS", "120") or "120")
    except Exception:
        index_short = 120
    index_short = max(40, index_short)
    cache_on = (os.getenv("REACT_TOOLS_FORMAT_CACHE", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    tools = getattr(tool_registry, "tools", None) or {}
    if exclude_tool_names:
        _ex = set(exclude_tool_names)
        tools = {k: v for k, v in tools.items() if str(k) not in _ex}
    ex_key: Tuple[str, ...] = tuple(sorted(exclude_tool_names)) if exclude_tool_names else ()
    fp: Tuple[Any, ...] = tuple(
        (str(name), str(getattr(t, "description", None) or ""))
        for name, t in sorted(tools.items(), key=lambda kv: str(kv[0]))
    )
    key = (max_chars, index_mode, index_short, fp, ex_key)
    global _tools_format_cache_key, _tools_format_cache_val
    if cache_on:
        with _tools_format_cache_lock:
            if _tools_format_cache_key == key and _tools_format_cache_val is not None:
                return [dict(x) for x in _tools_format_cache_val]
    out: List[Dict[str, str]] = []
    for _name, tool in sorted(tools.items(), key=lambda kv: str(kv[0])):
        desc = (getattr(tool, "description", None) or "") or ""
        if index_mode and str(tool.name) != "get_tool_description" and len(desc) > index_short:
            desc = desc[:index_short].rstrip() + "…"
        if max_chars > 0 and len(desc) > max_chars:
            desc = desc[:max_chars].rstrip() + "…"
        out.append({"name": tool.name, "description": desc})
    if cache_on:
        with _tools_format_cache_lock:
            _tools_format_cache_key = key
            _tools_format_cache_val = out
    return [dict(x) for x in out]


def extract_xml_field(text: Any, tag: str) -> str:
    """从 XML 中提取字段值，增加鲁棒性检查"""
    if not isinstance(text, str):
        return ''
    pattern = f'<{tag}>(.*?)</{tag}>'
    import re
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ''


def _parse_decision_loose_subtags(text: str) -> Optional[Dict[str, Any]]:
    """
    无标准 <decision>...</decision> 包裹时，从全文正则抽取 execute / tool / params / reason。
    供 parse_xml_decision 与统一流兜底共用（定义在 parse_xml_decision 之前以便引用）。
    """
    if not text or not isinstance(text, str):
        return None
    out: Dict[str, Any] = {
        "execute": False,
        "tool": "",
        "params": {},
        "reason": "",
    }
    exec_match = re.search(
        r"<execute>\s*(true|false|是|否|1|0)\s*</execute>",
        text,
        re.IGNORECASE,
    )
    if exec_match:
        out["execute"] = exec_match.group(1).lower() in ("true", "是", "1")
    tool_match = re.search(r"<tool>\s*([^<]*)\s*</tool>", text, re.IGNORECASE)
    if tool_match:
        out["tool"] = (tool_match.group(1) or "").strip()
    params_match = re.search(r"<params>\s*([\s\S]*?)\s*</params>", text, re.IGNORECASE)
    if params_match:
        ps = (params_match.group(1) or "").strip()
        try:
            out["params"] = json.loads(ps) if ps else {}
        except json.JSONDecodeError:
            if ps:
                out["params"] = {"raw": ps}
    reason_match = re.search(r"<reason>\s*([\s\S]*?)\s*</reason>", text, re.IGNORECASE)
    if reason_match:
        out["reason"] = (reason_match.group(1) or "").strip()
    if out.get("tool") or out.get("execute") or (out.get("reason") or "").strip():
        return out
    return None


def parse_xml_decision(text: Any) -> dict:
    """解析决策 XML 结果 - 兼容各种 JSON 响应和 Qwen 默认格式，增加搜索引擎智能选择"""
    result = {
        'execute': False,
        'tool': '',
        'params': {},
        'reason': ''
    }
    
    # 方案 -1: 如果是 list，取第一项
    if isinstance(text, list) and len(text) > 0:
        text = text[0]

    # 方案 0: 如果已经是 dict，直接处理
    if isinstance(text, dict):
        # 新增：智能推断工具参数（LLM 直接返回参数的情况）
        if 'engine' in text and 'query' in text:
            # 这是 search 工具的参数
            result['execute'] = True
            result['tool'] = 'search'
            result['params'] = text
            # 智能选择搜索引擎（如果没有指定）
            result['params'] = _smart_select_search_engine(result['params'])
            result['reason'] = '检测到搜索参数，自动执行 search 工具'
            return result
        
        # test_case / 浏览器脚本 → cdp
        if "test_case" in text:
            result["execute"] = True
            result["tool"] = "cdp"
            result["params"] = text.get('info') if isinstance(text.get('info'), dict) else {"action": "session", **(text if isinstance(text, dict) else {})}
            result["reason"] = "检测到浏览器测试参数，使用 cdp 工具"
            return result
        
        if 'sql' in text or 'query_type' in text:
            # 这是 database_query 工具的参数
            result['execute'] = True
            result['tool'] = 'database_query'
            result['params'] = text
            result['reason'] = '检测到数据库参数，自动执行 database_query 工具'
            return result
        
        if 'keywords' in text and 'project_id' in text and 'query_type' not in text:
            # 这是 grep 工具的参数（keywords + project_id，但没有query_type）
            result['execute'] = True
            result['tool'] = 'grep'
            result['params'] = text
            result['reason'] = '检测到grep参数，自动执行grep工具'
            return result
        
        # grep 工具参数识别（放宽条件：有 target 和 project_id 也识别为 grep）
        if 'target' in text and 'project_id' in text and 'query_type' not in text and 'modifications' not in text and 'fields' not in text:
            result['execute'] = True
            result['tool'] = 'grep'
            result['params'] = text
            result['reason'] = '检测到grep参数（target+project_id），自动执行grep工具'
            return result
        
        if 'modifications' in text and ('target_id' in text or 'target' in text):
            # 这是 modify 工具的参数
            result['execute'] = True
            result['tool'] = 'modify'
            result['params'] = text
            # 确保 confirm 默认为 False（沙箱预览模式），需要用户确认后才执行
            if 'confirm' not in result['params']:
                result['params']['confirm'] = False
            result['reason'] = '检测到修改参数，自动执行modify工具（沙箱预览模式）'
            return result
        
        if 'fields' in text and 'target' in text and text.get('target') in ['bug', 'badcase', 'plan', 'testcase']:
            # 这是 create 工具的参数
            result['execute'] = True
            result['tool'] = 'create'
            result['params'] = text
            # 与 modify 一致：对话中 create 一律沙箱预览，禁止直接落库
            result['params']['confirm'] = False
            result['reason'] = '检测到创建参数，自动执行 create 工具（沙箱预览模式）'
            return result
        
        # 兼容 Qwen 默认格式 (agent/action/script)
        if 'agent' in text or 'action' in text:
            result['execute'] = True
            
            # 智能映射 Qwen 的 Agent 名称到实际工具名
            qwen_agent = text.get('agent', '')
            qwen_action = text.get('action', '')
            qwen_script = str(text.get('script', '')).lower()
            
            # 默认映射
            actual_tool = qwen_agent or qwen_action
            
            # 规则匹配
            if qwen_agent == 'scriptAgent':
                if 'browser' in qwen_script:
                    actual_tool = 'cdp'
                elif 'log' in qwen_script:
                    actual_tool = 'log_analyzer'
                elif 'accuracy' in qwen_script:
                    actual_tool = 'accuracy_tester'
                else:
                    actual_tool = 'cdp'
            elif qwen_agent in ['bug_management_agent', 'mysql_agent']:
                actual_tool = 'database_query'
            
            # 已废弃的 L1 browser_* 名称 → cdp（在 params 赋值后合并 action）
            _legacy_browser_to_cdp = {
                "click": "click",
                "input": "fill",
                "wait": "wait",
                "assert": "wait",
                "browser_click": "click",
                "browser_input": "fill",
                "browser_wait": "wait",
                "browser_assert": "wait",
            }
            _cdp_action = _legacy_browser_to_cdp.get(actual_tool)
            if _cdp_action:
                actual_tool = "cdp"

            result['tool'] = actual_tool
            result['params'] = text.get('info') or {}
            if _cdp_action and isinstance(result['params'], dict):
                result['params'].setdefault('action', _cdp_action)
            
            # 关键修复：将 top-level 的 action 合并到 params 中，作为 query_type 或 action
            qwen_action = text.get('action', '')
            if qwen_action and 'query_type' not in result['params'] and 'action' not in result['params']:
                result['params']['query_type'] = qwen_action
                result['params']['action'] = qwen_action
                
            # 如果 params 是空的，把 script 塞进去
            if not result['params'] and text.get('script'):
                result['params'] = {'script': text.get('script')}
            
            # 补充必要的默认参数
            if actual_tool == 'cdp' and isinstance(result.get('params'), dict):
                result['params'].setdefault('action', 'session')
            
            # 智能选择搜索引擎（如果是 search 工具）
            if actual_tool == 'search':
                result['params'] = _smart_select_search_engine(result['params'])
                
            result['reason'] = text.get('planActions') or 'LLM 自动分发任务'
            return result
            
        result['execute'] = text.get('execute', False) in [True, 'true', 'yes']
        result['tool'] = text.get('tool', '')
        result['params'] = text.get('params', {})
        result['reason'] = text.get('reason', '')
        
        # 智能选择搜索引擎（如果是 search 工具）
        if result['tool'] == 'search':
            result['params'] = _smart_select_search_engine(result['params'])
        
        return result

    # 方案 1: XML 格式
    decision_xml = extract_xml_field(text, 'decision')
    if decision_xml:
        # 提取 execute
        execute_str = extract_xml_field(decision_xml, 'execute')
        result['execute'] = execute_str.lower() in ['true', 'yes']
        
        # 提取 tool
        result['tool'] = extract_xml_field(decision_xml, 'tool')
        
        # 提取 reason
        result['reason'] = extract_xml_field(decision_xml, 'reason')
        
        # 提取 params（JSON 格式）
        params_str = extract_xml_field(decision_xml, 'params')
        try:
            result['params'] = json.loads(params_str) if params_str else {}
        except:
            result['params'] = {}
        
        # 智能选择搜索引擎（如果是 search 工具）
        if result['tool'] == 'search':
            result['params'] = _smart_select_search_engine(result['params'])
        
        if result['execute'] or result['tool']:
            return result

    # 方案 1b：无完整 <decision> 块或嵌套错误时，从全文松散子标签提取
    if isinstance(text, str):
        loose = _parse_decision_loose_subtags(text)
        if loose:
            result["execute"] = bool(loose.get("execute"))
            result["tool"] = loose.get("tool") or ""
            result["params"] = loose.get("params") if isinstance(loose.get("params"), dict) else {}
            result["reason"] = loose.get("reason") or ""
            if result["tool"] == "search":
                result["params"] = _smart_select_search_engine(result["params"])
            return result
    
    # 方案 2: 字符串但包含 JSON 格式
    if isinstance(text, str):
        # 先尝试提取 markdown 代码块中的 JSON
        text_to_parse = text.strip()
        
        # 提取 ```json ... ``` 或 ``` ... ``` 代码块
        code_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text_to_parse)
        if code_block_match:
            text_to_parse = code_block_match.group(1).strip()
        
        try:
            parsed = json.loads(text_to_parse)
            # 处理 JSON 数组（千帆 FC 可能返回 [{"name": "grep", "parameters": {...}}]）
            if isinstance(parsed, list) and len(parsed) > 0:
                first_item = parsed[0]
                if isinstance(first_item, dict):
                    # 提取 name 作为 tool，parameters/arguments 作为 params
                    tool_name = first_item.get('name', '') or first_item.get('tool', '')
                    # 兼容多种参数字段名：parameters、arguments、params
                    params = first_item.get('parameters', {}) or first_item.get('arguments', {}) or first_item.get('params', {})
                    if tool_name:
                        result['execute'] = True
                        result['tool'] = tool_name
                        result['params'] = params
                        result['reason'] = f'从 JSON 数组解析出工具调用: {tool_name}'
                        # 智能选择搜索引擎
                        if result['tool'] == 'search':
                            result['params'] = _smart_select_search_engine(result['params'])
                        return result
            if isinstance(parsed, dict):
                # JSON 对象，提取相关字段
                result['execute'] = parsed.get('execute', False) in [True, 'true', 'yes']
                result['tool'] = parsed.get('tool', '')
                result['params'] = parsed.get('params', {})
                result['reason'] = parsed.get('reason', '')
                
                # 智能选择搜索引擎（如果是 search 工具）
                if result['tool'] == 'search':
                    result['params'] = _smart_select_search_engine(result['params'])
                
                return result
        except:
            pass
    
    # 方案 3: 默认
    result['execute'] = False
    return result


def _extract_unified_task_plan_steps(text: str) -> List[str]:
    """从统一流整段回复中提取 <task_plan><step>…</step></task_plan>（可位于 thinking 或 decision 内）。"""
    if not text or not isinstance(text, str):
        return []
    m = re.search(r"<task_plan>([\s\S]*?)</task_plan>", text, re.IGNORECASE)
    if not m:
        return []
    inner = m.group(1) or ""
    steps = re.findall(r"<step>([\s\S]*?)</step>", inner, re.IGNORECASE)
    out: List[str] = []
    for s in steps:
        t = re.sub(r"\s+", " ", (s or "").strip())
        if t:
            out.append(t)
    return out


def _first_tag_open_end(text: str, tag: str) -> int:
    """第一个 <tag ...> 的 '>' 下标；无则 -1。"""
    m = re.search(rf"<{re.escape(tag)}\b[^>]*>", text, re.IGNORECASE)
    return m.end() - 1 if m else -1


def _strip_xml_block(text: str, tag: str) -> str:
    """移除首个 <tag>…</tag> 块（含标签），用于从 thinking 正文去掉 think_summary（约定在末行，通常仅一块）。"""
    if not text:
        return ""
    m = re.search(
        rf"<{re.escape(tag)}\b[^>]*>[\s\S]*?</{re.escape(tag)}\s*>",
        text,
        re.IGNORECASE,
    )
    if not m:
        return text.strip()
    return (text[:m.start()] + text[m.end():]).strip()


def _extract_xml_block_robust(
    text: str,
    tag: str,
    aliases: Tuple[str, ...] = (),
) -> Tuple[str, List[str]]:
    """
    多级提取 <tag>...</tag> 内正文。
    1) 非贪婪匹配；2) 同名首开到末闭（缓解嵌套/截断导致的错配）；3) 别名标签。
    """
    notes: List[str] = []
    candidates = (tag,) + aliases

    for name in candidates:
        m = re.search(rf"<{re.escape(name)}>([\s\S]*?)</{re.escape(name)}>", text, re.IGNORECASE)
        if m:
            inner = (m.group(1) or "").strip()
            notes.append(f"{name}:non_greedy")
            return inner, notes

    for name in candidates:
        gt = _first_tag_open_end(text, name)
        if gt < 0:
            continue
        closes = list(re.finditer(rf"</{re.escape(name)}\s*>", text, re.IGNORECASE))
        if not closes:
            continue
        last = closes[-1]
        if last.start() <= gt:
            continue
        inner = text[gt + 1 : last.start()].strip()
        notes.append(f"{name}:first_open_to_last_close")
        return inner, notes

    return "", notes


def _parse_unified_decision_inner(decision_text: str) -> Dict[str, Any]:
    """从 decision 块内文本解析 execute / tool / params / reason / goal_done。"""
    loose = _parse_decision_loose_subtags(decision_text)
    out: Dict[str, Any] = (
        dict(loose)
        if loose
        else {"execute": False, "tool": "", "params": {}, "reason": ""}
    )
    goal_done = False
    gd_match = re.search(
        r"<goal_done>\s*(true|false|是|否|1|0)\s*</goal_done>",
        decision_text,
        re.IGNORECASE,
    )
    if gd_match:
        _gv = gd_match.group(1).lower()
        goal_done = _gv in ("true", "是", "1")

    return {"decision": out, "goal_done": goal_done}


def _fallback_decision_loose_tags(text: str) -> Tuple[Dict[str, Any], bool, List[str]]:
    """
    无完整 <decision> 包裹时，在全文用正则抽取 decision 子标签（最后一层容错）。
    返回 (decision_dict, goal_done, notes)。
    """
    notes: List[str] = []
    parsed = _parse_unified_decision_inner(text)
    inner = parsed["decision"]
    gd = parsed["goal_done"]
    if inner.get("tool") or inner.get("execute") or inner.get("reason"):
        notes.append("loose_tags:full_scan")
    return inner, gd, notes


def parse_unified_fc_content(text: str) -> Dict[str, Any]:
    """方案 C：从 content 解析 observation/thinking/plan；决策由 FC 提供，不含 decision XML。"""
    if not text or not isinstance(text, str):
        return {
            "observation": "",
            "thinking": "",
            "plan_steps": [],
            "goal_done": False,
            "raw": "",
        }
    plan_steps = _extract_unified_task_plan_steps(text)
    obs, _on = _extract_xml_block_robust(text, "observation", ("observe",))
    think, _tn = _extract_xml_block_robust(text, "thinking", ("think",))
    think_summary, _tsn = _extract_xml_block_robust(think or "", "think_summary", ())
    if think_summary and think:
        think = _strip_xml_block(think, "think_summary")
    goal_done = False
    _loose, gd_loose, _ln = _fallback_decision_loose_tags(text)
    if gd_loose:
        goal_done = True
    return {
        "observation": obs or "",
        "thinking": think or "",
        "think_summary": (think_summary or "").strip(),
        "plan_steps": plan_steps,
        "goal_done": goal_done,
        "raw": text,
    }


def parse_unified_response(text: str) -> Dict[str, Any]:
    """解析三段式 XML：observation + thinking + decision；含多级 fallback 与 parse_meta。"""
    if not text or not isinstance(text, str):
        return {
            "observation": "",
            "thinking": "",
            "think_summary": "",
            "decision": {"execute": False, "tool": "", "params": {}, "reason": ""},
            "plan_steps": [],
            "goal_done": False,
            "raw": "",
            "parse_meta": {
                "fallbacks": [],
                "decision_envelope_ok": False,
                "retry_recommended": False,
            },
        }

    parse_notes: List[str] = []
    tl = text.lower()
    decision_envelope_ok = ("</decision>" in tl) or ("</decide>" in tl)

    result: Dict[str, Any] = {
        "observation": "",
        "thinking": "",
        "think_summary": "",
        "decision": {"execute": False, "tool": "", "params": {}, "reason": ""},
        "plan_steps": _extract_unified_task_plan_steps(text),
        "goal_done": False,
        "raw": text,
        "parse_meta": {
            "fallbacks": parse_notes,
            "decision_envelope_ok": decision_envelope_ok,
            "retry_recommended": False,
        },
    }

    obs, on = _extract_xml_block_robust(text, "observation", ("observe",))
    if obs:
        result["observation"] = obs
        parse_notes.extend([f"observation:{x}" for x in on])

    think, tn = _extract_xml_block_robust(text, "thinking", ("think",))
    think_summary = ""
    if think:
        think_summary, _tsn = _extract_xml_block_robust(think, "think_summary", ())
        if think_summary:
            think = _strip_xml_block(think, "think_summary")
            parse_notes.extend([f"think_summary:{x}" for x in _tsn])
        result["thinking"] = think
        parse_notes.extend([f"thinking:{x}" for x in tn])
    result["think_summary"] = (think_summary or "").strip()

    decision_text = ""
    dn: List[str] = []
    for tag, als in (("decision", ("decide",)), ("decide", ())):
        decision_text, dn = _extract_xml_block_robust(text, tag, als)
        if decision_text or dn:
            parse_notes.extend([f"decision_block:{x}" for x in dn])
            break

    if decision_text:
        inner = _parse_unified_decision_inner(decision_text)
        result["decision"] = inner["decision"]
        result["goal_done"] = inner["goal_done"]
        if not (
            (result["decision"].get("tool") or "").strip()
            or result["decision"].get("execute")
            or (result["decision"].get("reason") or "").strip()
        ):
            fb = parse_xml_decision(text)
            if fb.get("tool") or fb.get("execute"):
                result["decision"] = {
                    "execute": bool(fb.get("execute")),
                    "tool": fb.get("tool") or "",
                    "params": fb.get("params") if isinstance(fb.get("params"), dict) else {},
                    "reason": fb.get("reason") or "",
                }
                parse_notes.append("parse_xml_decision:fallback")
    else:
        loose, gd_loose, ln = _fallback_decision_loose_tags(text)
        if loose.get("tool") or loose.get("execute") or loose.get("reason"):
            result["decision"] = loose
            result["goal_done"] = gd_loose
            parse_notes.extend(ln)
        else:
            fb = parse_xml_decision(text)
            if fb.get("tool") or fb.get("execute"):
                result["decision"] = {
                    "execute": bool(fb.get("execute")),
                    "tool": fb.get("tool") or "",
                    "params": fb.get("params") if isinstance(fb.get("params"), dict) else {},
                    "reason": fb.get("reason") or "",
                }
                parse_notes.append("parse_xml_decision:fallback")

    if not result["decision"].get("tool") and not result["decision"].get("execute"):
        fallback = parse_xml_decision(text)
        if fallback.get("tool") or fallback.get("execute"):
            result["decision"] = {
                "execute": bool(fallback.get("execute")),
                "tool": fallback.get("tool") or "",
                "params": fallback.get("params") if isinstance(fallback.get("params"), dict) else {},
                "reason": fallback.get("reason") or "",
            }
            if "parse_xml_decision:fallback" not in parse_notes:
                parse_notes.append("parse_xml_decision:fallback")

    _has_dec = bool(
        (result["decision"].get("tool") or "").strip()
        or result["decision"].get("execute")
        or (result["decision"].get("reason") or "").strip()
    )
    result["parse_meta"]["fallbacks"] = parse_notes
    result["parse_meta"]["decision_envelope_ok"] = decision_envelope_ok
    result["parse_meta"]["retry_recommended"] = (
        (not decision_envelope_ok) and len(text.strip()) >= 40 and not _has_dec
    )

    return result


def _smart_select_search_engine(params: dict, llm=None) -> dict:
    """
    智能选择搜索引擎
    优先使用 LLM 智能推断，如果没有 LLM 则使用规则匹配
    
    规则（作为 LLM 失败后的退路）：
    - 中文关键词或中国本土信息 -> baidu
    - 英文关键词或国际信息 -> google
    - 混合或不确定 -> baidu (默认)
    - 中文优先级高于国际关键词
    """
    if not isinstance(params, dict):
        return params
    
    # 如果已经指定了 engine，直接返回
    if 'engine' in params and params['engine']:
        # 将 engine 转换为小写
        params['engine'] = params['engine'].lower()
        return params
    
    # 获取搜索关键词
    query = params.get('query') or params.get('keyword') or params.get('keywords') or params.get('search_query') or params.get('q') or ''
    
    if not query:
        # 没有 query，使用默认百度
        params['engine'] = 'baidu'
        return params
    
    # 如果有 LLM，使用 LLM 智能推断
    if llm:
        try:
            import asyncio
            # 如果是在异步上下文中，直接 await
            # 否则跳过 LLM 推断，使用规则
            if asyncio.get_event_loop().is_running():
                # 异步环境，但我们不能在同步函数中 await
                # 跳过 LLM，使用规则
                pass
            else:
                # 同步环境，也跳过
                pass
        except:
            pass
    
    # 使用基于规则的快速判断
    return _rule_based_engine_selection(params, query)


def _rule_based_engine_selection(params: dict, query: str) -> dict:
    """
    基于规则的搜索引擎选择
    作为 LLM 推断的退路方案
    """
    # 判断是否包含中文
    import re
    has_chinese = bool(re.search(r'[\u4e00-\u9fff]', query))
    has_english = bool(re.search(r'[a-zA-Z]', query))
    
    # 中国本土关键词
    china_keywords = ['百度', '阿里', '腾讯', '淘宝', '京东', '微信', '支付宝', '中国', '国内', '中文']
    has_china_keyword = any(kw in query for kw in china_keywords)
    
    # 国际关键词
    international_keywords = ['github', 'stackoverflow', 'python', 'javascript', 'react', 'vue', 'docker', 'kubernetes', 'aws', 'google', 'facebook', 'twitter', 'tutorial', 'documentation', 'api']
    has_international_keyword = any(kw in query.lower() for kw in international_keywords)
    
    # 决策逻辑（中文优先级高）
    if has_china_keyword:
        # 有中国本土关键词，使用百度
        params['engine'] = 'baidu'
    elif has_chinese and not has_english:
        # 纯中文关键词，使用百度
        params['engine'] = 'baidu'
    elif has_chinese and has_english:
        # 混合中英文，中文优先，使用百度
        params['engine'] = 'baidu'
    elif has_international_keyword and not has_chinese:
        # 有国际关键词且没有中文，使用 Google
        params['engine'] = 'google'
    elif has_english and not has_chinese:
        # 纯英文关键词，使用 Google
        params['engine'] = 'google'
    else:
        # 其他情况，默认百度
        params['engine'] = 'baidu'
    
    return params


def parse_xml_findings(text: Any) -> dict:
    """解析发现 XML 结果 - 增加对对象格式的兼容"""
    result = {
        'findings': [],
        'context_update': {},
        'next_step': ''
    }
    
    # 方案 -1: 如果是 list
    if isinstance(text, list) and len(text) > 0:
        text = text[0]

    # 方案 0: 如果已经是 dict
    if isinstance(text, dict):
        # 兼容 Qwen 默认格式
        if 'planActions' in text or 'action' in text:
            result['findings'] = [text.get('planActions') or text.get('action')]
            result['context_update'] = text.get('info') or {}
            result['next_step'] = text.get('script') or ''
            return result
            
        result['findings'] = text.get('findings', [])
        result['context_update'] = text.get('context_update', {})
        result['next_step'] = text.get('next_step', '')
        return result

    # 方案 1: XML 格式
    findings_xml = extract_xml_field(text, 'key_findings')
    if findings_xml:
        import re
        findings = re.findall(r'<finding[^>]*>(.*?)</finding>', findings_xml)
        result['findings'] = findings
        
        # 提取 context_update
        context_str = extract_xml_field(text, 'context_update')
        try:
            result['context_update'] = json.loads(context_str) if context_str else {}
        except:
            result['context_update'] = {}
        
        # 提取 next_step
        result['next_step'] = extract_xml_field(text, 'next_step')
        return result
    
    # 方案 2: JSON 格式
    if isinstance(text, str):
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict):
                result['findings'] = parsed.get('findings', [])
                result['context_update'] = parsed.get('context_update', {})
                result['next_step'] = parsed.get('next_step', '')
                return result
        except:
            pass
            
    return result


def _normalize_plan_item(obj: Dict[str, Any], idx: int) -> Optional[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return None
    desc = obj.get("description") or obj.get("name") or obj.get("title")
    if not desc or not str(desc).strip():
        return None
    try:
        sid = int(obj.get("id", idx + 1))
    except Exception:
        sid = idx + 1
    st = obj.get("status") or "pending"
    if isinstance(st, str):
        st = st.strip().lower()
    else:
        st = "pending"
    return {"id": sid, "description": str(desc).strip(), "status": st}


def parse_react_json_plan(text: Any) -> Optional[List[Dict[str, Any]]]:
    """
    从 THINK 输出中提取一次性完整计划：{"plan":[{"id":1,"description":"...","status":"pending"}, ...]}
    支持 ```json 代码块或文中裸 JSON 对象。
    """
    if not text or not isinstance(text, str):
        return None
    raw = text.strip()
    if not raw:
        return None

    candidates: List[str] = []
    for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I):
        chunk = (m.group(1) or "").strip()
        if chunk.startswith("{") or chunk.startswith("["):
            candidates.append(chunk)
    lb, rb = raw.find("{"), raw.rfind("}")
    if lb >= 0 and rb > lb:
        candidates.append(raw[lb : rb + 1])

    seen: set = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        try:
            obj = json.loads(cand)
        except Exception:
            continue
        plan = obj.get("plan") if isinstance(obj, dict) else None
        if not isinstance(plan, list) or not plan:
            continue
        out: List[Dict[str, Any]] = []
        for i, item in enumerate(plan):
            norm = _normalize_plan_item(item if isinstance(item, dict) else {}, i)
            if norm:
                out.append(norm)
        if out:
            return out
    return None


def parse_xml_todos(text: Any) -> list:
    """解析 Todo 列表 XML 结果 - 增加对列表对象的直接支持"""
    # 方案 0: 如果已经是 list
    if isinstance(text, list):
        todos = []
        for item in text:
            if isinstance(item, dict):
                todo_text = item.get('planActions') or item.get('action') or str(item)
                if todo_text and todo_text not in todos:
                    todos.append(todo_text)
            elif isinstance(item, str):
                todos.append(item)
        return todos if todos else ['分析用户请求并生成解决方案']

    # 方案 1: <todo_list> 内按 XML 解析（<item>/<todo>/<step>），不再优先 json.loads
    todo_str = extract_xml_field(text, 'todo_list')
    if todo_str and todo_str.strip():
        s = todo_str.strip()
        # 先按 XML 解析
        if ET is not None:
            try:
                root = ET.fromstring(f"<root>{s}</root>")
                items = []
                for node in root.iter():
                    tag = (node.tag or "").lower()
                    if tag in ("todo", "item", "step"):
                        content = (node.text or "").strip()
                        if content:
                            items.append(content)
                if items:
                    return items
            except Exception:
                pass
        # 无标签时按行兜底
        lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
        if lines:
            cleaned = [re.sub(r'^[-*•\d\.\)]+\s*', '', ln).strip() for ln in lines if re.sub(r'^[-*•\d\.\)]+\s*', '', ln).strip()]
            if cleaned:
                return cleaned
        # 兼容旧版：内容恰为 JSON 数组字符串时再试
        try:
            out = json.loads(s)
            if isinstance(out, list) and out:
                return [str(x).strip() for x in out if str(x).strip()]
        except Exception:
            pass
    
    # 方案 2: 字符串包含 JSON 格式
    if isinstance(text, str):
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, list):
                todos = []
                for item in parsed:
                    if isinstance(item, dict):
                        todo_text = item.get('planActions') or item.get('action') or str(item)
                        if todo_text and todo_text not in todos:
                            todos.append(todo_text)
                    elif isinstance(item, str):
                        todos.append(item)
                return todos if todos else ['分析用户请求并生成解决方案']
        except:
            pass
    
    # 方案 3: 默认
    return ['分析用户请求并生成解决方案']
