# agents/intelligent_devops_agent.py
"""
综合型 AI 运维 Agent
整合 ReAct 推理 + 多工具编排 + 上下文管理
"""

import time
import os
import threading
from typing import Any, Dict, Optional

from .react_simplified import SimplifiedReActEngine
from .tool_registry import ToolRegistry
from .tools.search_tool import SearchTool
from .tools.login_state_tool import LoginStateTool
from .tools.log_analyzer_tool import LogAnalyzerTool
from .tools.accuracy_tester_tool import AccuracyTesterTool
from .agent_engine_config import agent_engine_backend

class ConversationMemory:
    """对话记忆管理"""
    
    def __init__(self, max_history=10):
        self.history = []
        self.max_history = max_history
    
    async def add(self, user_input: str, result: Dict[str, Any]):
        """添加对话记录"""
        self.history.append({
            'user_input': user_input,
            'result': result,
            'timestamp': time.time()
        })
        
        # 保持历史记录大小
        if len(self.history) > self.max_history:
            self.history.pop(0)
    
    def get_context(self, limit: int = 3) -> str:
        """获取上下文"""
        if not self.history:
            return "无"
        
        context = []
        for item in self.history[-limit:]:
            context.append(f"Q: {item['user_input']}")
            findings = item['result'].get('findings', [])
            if findings:
                context.append(f"A: 发现 - {', '.join(findings[:2])}")
        
        return '\n'.join(context)


_SHARED_TOOL_REGISTRY: Optional["ToolRegistry"] = None
_SHARED_TOOL_REGISTRY_LOCK = threading.Lock()
_TOOL_BOOTSTRAP_DONE = False
_TOOL_BOOTSTRAP_LOCK = threading.Lock()


def register_core_builtin_tools(
    registry: "ToolRegistry",
    *,
    llm=None,
    db_session=None,
    react_engine=None,
    quiet: bool = False,
) -> int:
    """
    注册内置工具（不含 skill_executor，需 react_engine）。
    llm=None 时跳过依赖 LLM 实例化的业务工具，供应用启动快路径使用。
    """
    def _reg(tool):
        registry.register(tool, quiet=quiet)

    if llm is not None:
        _reg(LogAnalyzerTool(llm))
        _reg(AccuracyTesterTool(llm))
        _reg(SearchTool(llm))
    _reg(LoginStateTool())

    from agents.tools.grep_tool import GrepTool

    _reg(GrepTool())

    from agents.tools.client_local_bridge_tool import ClientLocalBridgeTool

    _reg(ClientLocalBridgeTool())

    from agents.tools.terminal_tool import TerminalTool

    _reg(TerminalTool())

    from agents.tools.client_browser_tool import ClientBrowserTool

    _reg(ClientBrowserTool())

    from agents.tools.modify_tool import ModifyTool

    _reg(ModifyTool(db_session))

    from agents.tools.create_tool import CreateTool

    _reg(CreateTool(db_session))
    from agents.tools.copy_tool import CopyTool

    _reg(CopyTool(db_session))
    from agents.tools.delete_tool import DeleteTool

    _reg(DeleteTool(db_session))

    try:
        from agents.tools.cdp_tool import CdpTool

        _reg(CdpTool())
    except Exception as e:
        if os.getenv("QUIET_LOG") != "1":
            print(f"[REGISTRY] CDP 工具未注册: {e}")

    if react_engine is not None:
        from agents.tools.skill_tool import SkillExecutorTool
        from agents.tools.get_tool_description_tool import GetToolDescriptionTool

        registry.tools["skill_executor"] = SkillExecutorTool(
            skill_loader=react_engine.skill_loader,
            skill_registry=react_engine.skill_registry,
            tool_registry=registry,
        )
        if not registry.has_tool("get_tool_description"):
            registry.register(GetToolDescriptionTool(registry), quiet=quiet)

    return len(registry)


def bootstrap_shared_tool_registry(db_session=None) -> "ToolRegistry":
    """应用启动时仅注册工具，不拉 LLM / 不建 ReAct 引擎（毫秒级）。"""
    global _SHARED_TOOL_REGISTRY, _TOOL_BOOTSTRAP_DONE
    with _TOOL_BOOTSTRAP_LOCK:
        if _TOOL_BOOTSTRAP_DONE and _SHARED_TOOL_REGISTRY is not None:
            _patch_db_on_registry(_SHARED_TOOL_REGISTRY, db_session)
            return _SHARED_TOOL_REGISTRY
        reg = ToolRegistry()
        register_core_builtin_tools(
            reg, llm=None, db_session=db_session, react_engine=None, quiet=True
        )
        with _SHARED_TOOL_REGISTRY_LOCK:
            _SHARED_TOOL_REGISTRY = reg
        _TOOL_BOOTSTRAP_DONE = True
        if os.getenv("QUIET_LOG") != "1":
            for _tn in sorted(reg.tools.keys()):
                print(f"[REGISTRY] ✅ 工具已注册: {_tn}", flush=True)
            print(
                f"[AGENT-BOOTSTRAP] 核心工具已注册 n={len(reg)}（未拉 LLM；首条对话再补 search 等）",
                flush=True,
            )
        return reg


def _patch_db_on_registry(registry: "ToolRegistry", db_session) -> None:
    if registry is None or db_session is None:
        return
    try:
        for tool_name in ("modify", "create", "copy", "delete"):
            tool = registry.get(tool_name)
            if tool is not None and hasattr(tool, "db"):
                setattr(tool, "db", db_session)
    except Exception:
        pass


class IntelligentDevOpsAgent:
    """
    综合型 AI 运维 Agent
    
    功能：
    1. 执行自动化测试 -> 生成 Bug 列表
    2. 分析日志 -> 定位问题根因
    3. 测试准确率 -> 生成 BadCase 列表
    4. 多工具协调 -> 复杂问题诊断
    """
    
    def __init__(self, llm, db_session=None, engine_backend: str | None = None):
        """
        初始化 Agent
        
        Args:
            llm: 语言模型（千帆）
            db_session: 数据库会话
            engine_backend: 可选，覆盖 AGENT_ENGINE（``react`` / ``langgraph``）
        """
        perf = (os.getenv("PERF_LOG") == "1")
        t0 = time.perf_counter()
        self.llm = llm
        self.db = db_session
        
        global _SHARED_TOOL_REGISTRY
        with _SHARED_TOOL_REGISTRY_LOCK:
            if _SHARED_TOOL_REGISTRY is not None and len(_SHARED_TOOL_REGISTRY) > 0:
                self.tool_registry = _SHARED_TOOL_REGISTRY
                _patch_db_on_registry(self.tool_registry, db_session)
                if perf:
                    print(
                        f"[PERF][agent] reuse_shared_tool_registry tools={len(self.tool_registry)}",
                        flush=True,
                    )
            else:
                self.tool_registry = ToolRegistry()

        # 初始化执行引擎（必须在 _register_tools 之前；skill 工具依赖 engine）
        t_engine0 = time.perf_counter()
        _backend = (engine_backend or "").strip().lower() or agent_engine_backend()
        if _backend in ("langgraph", "lg", "graph"):
            _backend = "langgraph"
        else:
            _backend = "react"
        self.engine_backend = _backend
        if _backend == "langgraph":
            from .langgraph_engine import LangGraphReactEngine

            self.react_engine = LangGraphReactEngine(
                llm=llm,
                tool_registry=self.tool_registry,
            )
            print("[AGENT] 使用 LangGraph 引擎 (AGENT_ENGINE=langgraph)", flush=True)
        else:
            self.react_engine = SimplifiedReActEngine(
                llm=llm,
                tool_registry=self.tool_registry,
            )
        self.react_engine.db = db_session
        if perf:
            print(
                f"[PERF][agent] react_engine_init_ms={(time.perf_counter()-t_engine0)*1000:.1f} "
                f"backend={_backend}"
            )

        # 注册工具（在 react_engine 之后，因为 skill_tool 需要 react_engine）
        t_reg0 = time.perf_counter()
        self._register_tools()
        with _SHARED_TOOL_REGISTRY_LOCK:
            if _SHARED_TOOL_REGISTRY is None and len(self.tool_registry) > 0:
                _SHARED_TOOL_REGISTRY = self.tool_registry
        if perf:
            print(f"[PERF][agent] register_tools_ms={(time.perf_counter()-t_reg0)*1000:.1f} tools={len(self.tool_registry)}")
        
        # 记忆系统
        self.memory = ConversationMemory()
        if perf:
            print(f"[PERF][agent] agent_init_total_ms={(time.perf_counter()-t0)*1000:.1f}")
    
    def _ensure_llm_tools_if_missing(self) -> None:
        """启动快路径未拉 LLM 时，首条对话补注册 search 等工具。"""
        if self.llm is None:
            return
        if self.tool_registry.has_tool("search"):
            return
        self.tool_registry.register(LogAnalyzerTool(self.llm))
        self.tool_registry.register(AccuracyTesterTool(self.llm))
        self.tool_registry.register(SearchTool(self.llm))

    def _register_tools(self):
        """注册所有工具 - 包含分层工具和Skill工具"""
        if len(self.tool_registry) > 0 and self.tool_registry.has_tool("grep"):
            _patch_db_on_registry(self.tool_registry, self.db)
            self._ensure_llm_tools_if_missing()
            self._register_skill_tools_only()
            if os.getenv("QUIET_LOG") != "1":
                print(
                    f"[AGENT] 复用启动已注册工具 n={len(self.tool_registry)}"
                    f"（跳过重复 [REGISTRY]）",
                    flush=True,
                )
            return

        register_core_builtin_tools(
            self.tool_registry,
            llm=self.llm,
            db_session=self.db,
            react_engine=self.react_engine,
        )

        if os.getenv("QUIET_LOG") != "1":
            print(f"[AGENT]工具注册完成，共 {len(self.tool_registry)} 个工具")

    def _register_skill_tools_only(self):
        """Skill / get_tool_description 依赖 react_engine，每实例刷新 skill_executor。"""
        from agents.tools.skill_tool import SkillExecutorTool
        from agents.tools.get_tool_description_tool import GetToolDescriptionTool

        self.tool_registry.tools["skill_executor"] = SkillExecutorTool(
            skill_loader=self.react_engine.skill_loader,
            skill_registry=self.react_engine.skill_registry,
            tool_registry=self.tool_registry,
        )
        if not self.tool_registry.has_tool("get_tool_description"):
            self.tool_registry.register(GetToolDescriptionTool(self.tool_registry))

    def set_db_session(self, db_session):
        """允许复用 Agent 实例时更新 db session 引用。"""
        self.db = db_session
        if getattr(self, "react_engine", None) is not None:
            self.react_engine.db = db_session
        try:
            for tool_name in ("modify", "create", "copy"):
                tool = self.tool_registry.get(tool_name)
                if tool is not None and hasattr(tool, "db"):
                    setattr(tool, "db", db_session)
        except Exception:
            pass
    
    async def handle_user_request_stream(
        self,
        user_input: str,
        project_id: int = None,
        plan_id: int = None,
        card_id: int = None,
        card_type: str = None,
        locale: str = None,
        pending_diff_context: list = None,
        agent_session_id: str = None,
        chat_session_id: int = None,
        long_memory_context: dict = None,
        conversation_history: list = None,
        hint_project_name: str = None,
        hint_plan_name: str = None,
        client_shell: dict = None,
        images: list = None,
        ui_context: dict = None,
    ):
        """流式处理用户请求。plan_id 为当前迭代计划ID时，grep 会只检索该计划下的记录（人类式先看本迭代）。"""
        _llm = self.llm
        print(
            f"[AGENT-LLM] 本请求绑定 LLM: class={type(_llm).__name__} "
            f"model_attr={getattr(_llm, 'model', None)!r} instance_id={id(_llm)}"
        )
        print(f"\n[AGENT] User Request (Stream): {user_input}")
        if project_id:
            print(f"[AGENT] Project ID: {project_id}")
        if plan_id is not None:
            print(f"[AGENT] Plan ID (当前迭代): {plan_id}")
        if card_id is not None:
            print(f"[AGENT] Card ID (当前卡片): {card_id} card_type={card_type!r}")
        
        # 0. 协议 v1：连接就绪（不再使用 type=status / 双写 step）
        yield {'type': 'hello', 'payload': {}}

        # 不推假的 reasoning 占位：深度思考区块仅在有实质思考内容时由前端展示（见 SimpleChatPanel substantiveReasoning）。

        # ReAct：run_stream 已在引擎出口转为 v1（type/payload），此处只透传
        # 卡片层适配：将卡片上下文注入 user_input，避免改动引擎签名的同时让模型“以卡片为主”决策工具参数
        from agents.conversation_history import (
            build_recent_url_hint,
            normalize_conversation_history,
        )
        from agents.locale_prompts import format_ui_context_for_prompt

        _hist = normalize_conversation_history(conversation_history)
        if _hist:
            print(f"[AGENT] conversation_history messages={len(_hist)}", flush=True)

        _effective_input = user_input
        _ui_block = format_ui_context_for_prompt(
            ui_context if isinstance(ui_context, dict) else None,
            locale=locale,
        )
        if _ui_block:
            _effective_input = f"{_ui_block}{user_input}"
        _url_hint = build_recent_url_hint(_hist, locale=locale)
        if _url_hint and "http://" not in (user_input or "") and "https://" not in (user_input or ""):
            _effective_input = f"{_url_hint}\n{_effective_input}"
        if card_id is not None and str(card_id).strip():
            try:
                _ct = str(card_type).strip() if card_type is not None else ""
            except Exception:
                _ct = ""
            _hint = f"[上下文] 当前卡片(card) id={card_id}" + (f", type={_ct}" if _ct else "")
            _effective_input = f"{_hint}\n{_effective_input}"

        async for pkt in self.react_engine.run_stream(
            _effective_input,
            project_id=project_id,
            plan_id=plan_id,
            locale=locale,
            pending_diff_context=pending_diff_context,
            agent_session_id=agent_session_id,
            chat_session_id=chat_session_id,
            long_memory_prefetch=long_memory_context,
            conversation_history=_hist,
            hint_project_name=hint_project_name,
            hint_plan_name=hint_plan_name,
            client_shell=client_shell if isinstance(client_shell, dict) else None,
            images=images if isinstance(images, list) else None,
            raw_user_input=user_input,
            ui_context=ui_context if isinstance(ui_context, dict) else None,
        ):
            yield pkt

        # 获取最终结果并格式化
        # 这里从 react_engine 的状态中获取最终结果可能更好，但目前 SimplifiedReActEngine 是无状态的
        # 我们让 run_stream 最后 yield 一个 summary
        
    async def handle_user_request(
        self, user_input: str, project_id: int = None, locale: str = None
    ) -> Dict[str, Any]:
        """
        处理用户请求
        
        Args:
            user_input: 用户输入
            project_id: 项目ID，用于获取登录配置
            
        Returns:
            执行结果
        """
        print(f"\n[AGENT] User Request: {user_input}")
        if project_id:
            print(f"[AGENT] Project ID: {project_id}")
        
        # 1. 分类意图
        intent = await self._classify_intent(user_input)
        print(f"[AGENT] Intent Classification: {intent}")
        
        # 2. 启动 ReAct 循环 - 传入 project_id
        result = await self.react_engine.run(user_input, project_id=project_id, locale=locale)
        
        # 3. 后处理结果
        final_output = await self._format_output(result, intent)
        
        # 4. 保存到记忆
        await self.memory.add(user_input, result)
        
        print(f"\n[AGENT] Request Processed\n")
        
        return final_output
    
    def _classify_intent_rule_fallback(self, user_input: str) -> str:
        """
        纯关键词意图标签（不调 LLM）。
        仅影响非流式 handle_user_request 的 _format_output 推荐文案；与 ReAct 工具选择无关。
        """
        text = (user_input or "").strip()
        modify_keywords = (
            "修改",
            "编辑",
            "改为",
            "改成",
            "更新",
            "把",
            "的答案",
            "复现步骤",
            "标题",
            "期望结果",
            "预期结果",
        )
        if any(kw in text for kw in modify_keywords):
            return "diagnose"
        if any(k in text for k in ("自动化测试", "执行测试", "跑测试", "运行测试")):
            return "run_test"
        if any(k in text for k in ("准确率", "准确率低", "对话准确率")):
            return "test_accuracy"
        if any(k in text for k in ("失败用例", "生成 badcase", "生成 BadCase")):
            return "generate_badcase"
        if any(k in text for k in ("日志", "根因", "定位原因", "定位问题")):
            return "locate_bug"
        query_markers = (
            "查询",
            "列出",
            "有哪些",
            "搜索",
            "查找",
            "检索",
            "看一下",
            "迭代计划",
            "计划列表",
            "当前计划",
        )
        if any(m in text for m in query_markers):
            return "find_bugs"
        return "diagnose"

    async def _classify_intent(self, user_input: str) -> str:
        """
        意图标签（无 LLM）：供非流式 _format_output 使用。
        流式对话的决策完全由 ReAct 统一流完成，不再并行浪费一次 parse_intent。
        """
        return self._classify_intent_rule_fallback(user_input)
    
    async def _format_output(self, result: Dict[str, Any], intent: str) -> Dict[str, Any]:
        """
        格式化输出
        
        根据意图类型组织结果
        """
        formatted = {
            'intent': intent,
            'status': result['status'],
            'findings': result['findings'],
            'context': await self._get_execution_context(result),
            'recommendations': []
        }
        
        # 根据意图类型提供建议
        if intent == 'run_test':
            bugs_count = len(result['context'].get('bugs', []))
            formatted['recommendations'] = [
                f"已生成 {bugs_count} 个 Bug",
                "建议优先处理 high 和 critical 级别的 Bug",
                "点击『保存 Bug』按钮可将其导入数据库"
            ]
        
        elif intent == 'test_accuracy':
            accuracy = result['context'].get('accuracy', 0)
            formatted['recommendations'] = [
                f"准确率: {accuracy:.2%}",
                f"已识别 {len(result['context'].get('badcases', []))} 个 BadCase",
                "建议分析失败用例，优化对应功能"
            ]
        
        elif intent == 'locate_bug':
            root_cause = result['context'].get('root_cause', '')
            formatted['recommendations'] = [
                f"根因分析: {root_cause}",
                "建议立即修复或上报",
                "已提取相关日志片段供参考"
            ]
        
        return formatted
    
    async def _get_execution_context(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """获取执行上下文 - 兼容ReAct新格式"""
        return {
            'step_count': len(result.get('steps', [])),
            'duration': result.get('duration', 0),
            'previous_context': self.memory.get_context(limit=2)
        }
