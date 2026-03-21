# agents/react_simplified.py
"""
极简 ReAct 引擎 - 结合 Claude Code 强约束 Prompt + 自我修正 + Skill动态加载 + Text2SQL
核心：单主循环 + Agent 自管理 Todo +强约束提示词 + 自动修正 +技能匹配 + 自然语言SQL

性能 / 体验（环境变量，可选）：
- REACT_THOUGHT_BRIEF_MS：低于该毫秒数则前端显示「Thought briefly」（默认 800）
- REACT_SKIP_THINK_HINT=1：跳过首轮用户向说明注入，略减首包延迟
- REACT_TOOL_DESC_MAX_CHARS：>0 时截断各工具 description，缩短首轮 THINK prompt（见 prompts.format_tools_for_prompt）
- GREP_PLAN_TREE_CACHE_TTL：grep 内计划树缓存秒数（默认 60，0 关闭），见 GrepTool._get_plan_tree
- PERF_LOG=1：打印各阶段耗时，便于对比模型与链路瓶颈

进一步提速方向（需产品/架构取舍，不单靠开关）：
- 合并多步 LLM（decide+observe 合一）、缩短 prompt、工具结果缓存
- 模型侧：更低延迟 endpoint、适当减小 max_tokens（本仓库不强制改模型）
- 工具侧：DB 索引、grep 范围缩小、异步 I/O
"""

import contextlib
import asyncio
import concurrent.futures
import json
import time
import os
import threading
import queue
import re
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional, AsyncIterator, Tuple

#原依赖
from .prompts import ReactPromptTemplates, format_tools_for_prompt
from .prompts import parse_xml_todos, parse_xml_decision, parse_xml_findings
from .self_correction import SelfCorrectionEngine
from .evidence_extractor import EvidenceExtractor

# Skill 动态加载
from .skill_loader import SkillLoader
from .skill_registry import skill_registry
from .skill import Skill
from .skill_integration import get_skill_integration  # Skill 集成管理器（懒加载）

# Text2SQL
try:
    from .tools.sqlcoder_agent import Text2SQLAgent, LLMBackend
    TEXT2SQL_AVAILABLE = True
except ImportError:
    TEXT2SQL_AVAILABLE = False
    print("[REACT]⚠  Text2SQLAgent 未安装，使用传统查询模式")


def get_text2sql_tool(db_path="instance/badcase_doctor.db"):
    """获取 Text2SQL 工具实例（进程级缓存 + 懒加载）。"""
    if not TEXT2SQL_AVAILABLE:
        return None
    try:
        from .tools.sqlcoder_agent import get_cached_text2sql_agent
        backend_env = (os.getenv("TEXT2SQL_LLM_BACKEND", "glm-4-flash") or "").strip().lower()
        backend = "glm-5" if backend_env in ("glm-5", "glm5") else "glm-4-flash"
        return get_cached_text2sql_agent(
            database_path=db_path,
            llm_backend=backend,
            debug=False,
            execution_mode="direct",
        )
    except Exception as e:
        print(f"[REACT] Text2SQL初始化失败: {e}")
        return None


def robust_parse_todos(raw: Any) -> List[str]:
    """
    健壮解析 LLM 返回的 todos：
    1）优先走现有的 XML 解析（parse_xml_todos）
    2）若失败或为空，再尝试：
       - 解析 <todo_list>...</todo_list> 里的 XML 结构
       - 从文本中用正则抽取 JSON 数组并 json.loads
       - 最后兜底：按行/项目符号提取
    返回：todo 文本列表（字符串列表）
    """
    # 已经是列表就直接兜底规范化
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]

    if raw is None:
        return []

    text = raw if isinstance(raw, str) else str(raw)
    if not text.strip():
        return []

    todos: List[str] = []

    # 1. 先走原有 XML 解析（保持兼容）
    try:
        base = parse_xml_todos(text)
        if base:
            # parse_xml_todos 目前可能返回列表 / dict，这里只关心列表
            if isinstance(base, list):
                todos = [str(x).strip() for x in base if str(x).strip()]
                if todos:
                    return todos
    except Exception as e:
        print(f"[REACT-TODO] parse_xml_todos 解析失败，继续尝试增强解析: {e}")

    # 2. 解析 <todo_list>...</todo_list> 里的简单 XML
    try:
        m = re.search(r'<todo_list[^>]*>([\s\S]*?)</todo_list>', text, re.IGNORECASE)
        if m:
            inner = m.group(1).strip()
            # 包一层根节点，容忍模型直接输出 <item> / <todo>
            xml_str = f"<root>{inner}</root>"
            root = ET.fromstring(xml_str)
            xml_todos: List[str] = []
            for node in root.iter():
                tag = (node.tag or "").lower()
                if tag in ("todo", "item", "step"):
                    content = (node.text or "").strip()
                    if content:
                        xml_todos.append(content)
            if xml_todos:
                print(f"[REACT-TODO] 从 XML 提取 {len(xml_todos)} 条 todos")
                return xml_todos
    except Exception as e:
        print(f"[REACT-TODO] XML todo_list 解析失败，将继续尝试 JSON/文本兜底: {e}")

    # 3. 从文本中抽取 JSON 数组（支持前后有其他文本/标签）
    try:
        # 尽量匹配第一段较“干净”的数组，避免把整个大长串都吃进去
        json_match = re.search(r'\[[\s\S]*?\]', text)
        if json_match:
            json_part = json_match.group(0)
            # 简单剪裁过长内容，防止极端情况
            if len(json_part) > 8000:
                json_part = json_part[:8000]
            arr = json.loads(json_part)
            if isinstance(arr, list):
                json_todos = [str(x).strip() for x in arr if str(x).strip()]
                if json_todos:
                    print(f"[REACT-TODO] 从 JSON 数组提取 {len(json_todos)} 条 todos")
                    return json_todos
    except Exception as e:
        print(f"[REACT-TODO] JSON 数组解析失败，将继续文本兜底: {e}")

    # 4. 文本兜底：从 <todo_list> 块里按行抽取
    try:
        block = ""
        m = re.search(r'<todo_list[^>]*>([\s\S]*?)</todo_list>', text, re.IGNORECASE)
        if m:
            block = m.group(1)
        else:
            block = text
        lines = [ln.strip() for ln in block.splitlines()]
        for ln in lines:
            if not ln:
                continue
            # 过滤 XML/HTML 标签行
            if ln.startswith("<") and ln.endswith(">"):
                continue
            # 项目符号 / 编号行
            if re.match(r'^[-*•\d]+\s*', ln):
                # 去掉前缀符号
                ln = re.sub(r'^[-*•\d\.\)]+\s*', '', ln).strip()
            if ln:
                todos.append(ln)
        if todos:
            print(f"[REACT-TODO] 文本兜底提取 {len(todos)} 条 todos")
            return todos
    except Exception as e:
        print(f"[REACT-TODO] 文本兜底解析失败: {e}")

    # 全部失败时，返回空列表，交由上层兜底
    return []


class SimplifiedReActEngine:
    """增强版极简 ReAct 引擎 -集 Skill + Text2SQL"""
    
    def __init__(self, llm, tool_registry, skill_dir=".qoder/skills"):
        """初始化"""
        self.llm = llm
        self.tools = tool_registry
        self.correction_engine = SelfCorrectionEngine(llm)  # 自我修正引擎
        self.project_id = None  # 当前项目 ID
        
        # Skill动态加载
        self.skill_loader = SkillLoader(skill_dir)
        self.skill_registry = skill_registry
        print(f"[REACT]💡引擎已初始化，Skill目录: {skill_dir}")
        
        # Text2SQL
        # Text2SQL 懒加载：只在真正需要自然语言SQL时再初始化（避免每次请求前置 1s+）
        self.text2sql_tool = None
        if TEXT2SQL_AVAILABLE:
            print("[REACT] ✅ Text2SQL可用（懒加载）")
        else:
            print("[REACT] ⚠️  Text2SQL 不可用")
        # 线程池：modify 等工具内部有同步 DB（Flask/SQLAlchemy），在事件循环中会阻塞，导致流式“修改中...”卡住
        self._tool_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="react_tool")

    @contextlib.contextmanager
    def _llm_no_thinking(self):
        """与 run_stream 内 _NoThinking 一致：modify 决策/提取 modifications 时临时关闭思考模式。"""
        try:
            if hasattr(self.llm, "force_disable_thinking"):
                setattr(self.llm, "force_disable_thinking", True)
            yield
        finally:
            if hasattr(self.llm, "force_disable_thinking"):
                setattr(self.llm, "force_disable_thinking", False)

    def _resolve_chat_stream_iter(self, prompt: str, history: Optional[list] = None):
        """
        统一流式迭代：优先 chat_stream_with_reasoning，否则 chat_stream_fallback_chunks（直连 prompt，禁止 parse_intent 聚合）。
        """
        fn = getattr(self.llm, "chat_stream_with_reasoning", None)
        if callable(fn):
            return fn(prompt, history)
        fb = getattr(self.llm, "chat_stream_fallback_chunks", None)
        if callable(fb):
            return fb(prompt, history)
        raise RuntimeError(
            f"LLM {type(self.llm).__name__} 须实现 chat_stream_with_reasoning 或 chat_stream_fallback_chunks"
        )

    async def _collect_llm_text(self, prompt: str) -> str:
        """
        仅聚合正文（不向前端 yield），用于内部 JSON/参数提取等。
        与界面同源：只走 _resolve_chat_stream_iter（禁止 parse_intent）。
        """
        def _sync_collect():
            parts: List[str] = []
            try:
                for item in self._resolve_chat_stream_iter(prompt):
                    if not isinstance(item, dict):
                        continue
                    if item.get('type') == 'content_delta':
                        d = item.get('delta') or ''
                        if d:
                            parts.append(d)
            except Exception as e:
                return f'Error: {e}'
            return ''.join(parts).strip()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._tool_executor, _sync_collect)

    async def _stream_llm_prompt_collect(
        self,
        prompt: str,
        *,
        step_index: Optional[int] = None,
        stream_kind: str = 'think',
        full_text_sink: Optional[List[str]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        统一流式：复用 chat_stream_with_reasoning，边收边 yield。
        - think：reasoning + todos_stream（+ 可选 todos_partial）
        - decide/observe/summary 等：reasoning + llm_text_stream（带 index/kind）
        最终拼接正文：传入 full_text_sink（单元素 list），消费结束后 sink[0] 为全文（async generator 不能 return 值）。
        """
        try:
            _brief_ms_fb = max(0, int(os.getenv("REACT_THOUGHT_BRIEF_MS", "800")))
        except Exception:
            _brief_ms_fb = 800
        content_parts: List[str] = []
        q: 'queue.Queue[object]' = queue.Queue()
        DONE = object()
        _t_stream_start = time.time()
        _t_first_reasoning_fb = None
        _reasoning_buf_fb = ""
        _reasoning_timing_sent_fb = False
        _timing_kinds = frozenset({"think", "decide", "observe"})

        def _worker():
            try:
                for it in self._resolve_chat_stream_iter(prompt):
                    q.put(it)
            except Exception as e:
                q.put({'type': 'content_delta', 'delta': f'Error: {e}'})
            finally:
                q.put(DONE)

        threading.Thread(target=_worker, daemon=True).start()
        _todo_buf = ''
        _partial_parse_tick = 0
        _last_partial_n = 0

        while True:
            item = q.get()
            if item is DONE:
                break
            if not isinstance(item, dict):
                continue
            if item.get('type') == 'reasoning_delta':
                delta = item.get('delta')
                if delta is not None and isinstance(delta, str):
                    if stream_kind in _timing_kinds:
                        _reasoning_buf_fb += delta
                        if _t_first_reasoning_fb is None and _reasoning_buf_fb.strip():
                            _t_first_reasoning_fb = time.time()
                    if stream_kind in ('decide', 'observe') and step_index is not None:
                        yield {
                            'event': 'reasoning_step',
                            'content': delta,
                            'segment': stream_kind,
                            'index': step_index,
                        }
                    else:
                        yield {'event': 'reasoning', 'content': delta}
            elif item.get('type') == 'content_delta':
                delta = item.get('delta') or ''
                if not delta:
                    continue
                if stream_kind in _timing_kinds and not _reasoning_timing_sent_fb:
                    now = time.time()
                    if _t_first_reasoning_fb is not None:
                        duration_ms = int((now - _t_first_reasoning_fb) * 1000)
                        had_r = True
                    else:
                        duration_ms = int((now - _t_stream_start) * 1000)
                        had_r = False
                    _seg = stream_kind
                    _ev_rt: Dict[str, Any] = {
                        'event': 'reasoning_timing',
                        'segment': _seg,
                        'duration_ms': duration_ms,
                        'kind': 'brief' if duration_ms < _brief_ms_fb else 'normal',
                        'had_reasoning': had_r,
                        'brief_threshold_ms': _brief_ms_fb,
                    }
                    if step_index is not None:
                        _ev_rt['index'] = step_index
                    yield _ev_rt
                    _reasoning_timing_sent_fb = True
                content_parts.append(delta)
                if stream_kind == 'think':
                    yield {'event': 'todos_stream', 'delta': delta}
                    _todo_buf += delta
                    _partial_parse_tick += len(delta)
                    _should_try = (
                        _partial_parse_tick >= 96
                        or '</todo' in _todo_buf.lower()
                        or '</item>' in _todo_buf.lower()
                    )
                    if _should_try:
                        _partial_parse_tick = 0
                        try:
                            _pt = robust_parse_todos(_todo_buf)
                            if _pt and len(_pt) > _last_partial_n:
                                _last_partial_n = len(_pt)
                                yield {'event': 'todos_partial', 'data': _pt}
                        except Exception:
                            pass
                elif stream_kind == 'summary':
                    yield {'event': 'summary_stream', 'delta': delta}
                else:
                    ev: Dict[str, Any] = {
                        'event': 'llm_text_stream',
                        'delta': delta,
                        'kind': stream_kind,
                    }
                    if step_index is not None:
                        ev['index'] = step_index
                    yield ev
        if stream_kind in _timing_kinds and not _reasoning_timing_sent_fb and _reasoning_buf_fb.strip():
            if _t_first_reasoning_fb is not None:
                duration_ms = int((time.time() - _t_first_reasoning_fb) * 1000)
            else:
                duration_ms = int((time.time() - _t_stream_start) * 1000)
            _ev_edge: Dict[str, Any] = {
                'event': 'reasoning_timing',
                'segment': stream_kind,
                'duration_ms': duration_ms,
                'kind': 'brief' if duration_ms < _brief_ms_fb else 'normal',
                'had_reasoning': True,
                'brief_threshold_ms': _brief_ms_fb,
            }
            if step_index is not None:
                _ev_edge['index'] = step_index
            yield _ev_edge
        text = ''.join(content_parts).strip()
        if full_text_sink is not None:
            full_text_sink.clear()
            full_text_sink.append(text)

    async def run_stream(self, user_input: str, project_id: int = None, plan_id: int = None):
        """流式执行 ReAct 循环（使用 Skill 工具）。plan_id 为当前迭代计划 ID，传入则 grep 可只检索该计划下的记录（人类式先看本迭代）。"""
        print(f"\n[REACT] ReAct Stream Loop Start")
        perf = (os.getenv("PERF_LOG") == "1")
        t0 = time.perf_counter()
        self.project_id = project_id
        self.plan_id = plan_id  # 当前迭代计划，供 grep 按计划检索
        start_time = time.time()
            
        # 获取项目名称和计划名称（用于思考过程展示，必须在 Flask app_context 内查库）
        # 优化：与 tools_info 构造并行，减少 THINK 前置耗时
        async def _load_names():
            project_name = None
            plan_name = None
            try:
                from app import app, db, Project, Plan
                with app.app_context():
                    t_db0 = time.perf_counter()
                    if project_id:
                        project = db.session.query(Project).filter(Project.id == project_id).first()
                        if project:
                            project_name = project.name
                    if plan_id:
                        plan = db.session.query(Plan).filter(Plan.id == plan_id).first()
                        if plan:
                            plan_name = plan.name
                    if perf:
                        print(f"[PERF][react] project_plan_lookup_ms={(time.perf_counter()-t_db0)*1000:.1f}")
            except Exception as e:
                print(f"[REACT] 获取项目/计划名称失败：{e}")
            return project_name, plan_name

        result_context = {}
        # 并行：项目/计划名查询 与 工具说明格式化（省 THINK 前串行等待）
        (project_name, plan_name), tools_info = await asyncio.gather(
            _load_names(),
            asyncio.to_thread(format_tools_for_prompt, self.tools),
        )
        if perf:
            print(f"[PERF][react] gather_names_and_tools_parallel=1")
        if plan_id is not None:
            result_context['plan_id'] = plan_id  # 供 LLM 传给 grep，先检索本计划再阅读
            if plan_name:
                result_context['plan_name'] = plan_name

        # modify 流程要求不带思考：为支持的 LLM 提供一个临时开关
        def _set_force_disable_thinking(v: bool):
            try:
                if hasattr(self.llm, "force_disable_thinking"):
                    setattr(self.llm, "force_disable_thinking", bool(v))
            except Exception:
                pass

        class _NoThinking:
            def __enter__(self_nonlocal):
                _set_force_disable_thinking(True)
                return self_nonlocal
            def __exit__(self_nonlocal, exc_type, exc, tb):
                _set_force_disable_thinking(False)
                return False
        if project_id is not None:
            result_context['project_id'] = project_id
            if project_name:
                result_context['project_name'] = project_name
            
        findings = []
        steps = []
        thinking_start_time = time.time()  # 用于统计「思考了多少秒」
        
        try:
            # ===== STEP 1: THINK =====
            # 不再发送 thought 事件，直接让 LLM 生成 reasoning 内容
            # 关键体验优化：在 LLM 首 token 前先推一个不可见字符，让前端立刻出现「深度思考」块
            # （前端 v-if=reasoningContent；\u200b 为零宽空格，用户不可见但可触发渲染）
            yield {"event": "reasoning", "content": "\u200b"}
            # 可选：跳过首轮「说明」注入，略减首包延迟（REACT_SKIP_THINK_HINT=1）
            if (os.getenv("REACT_SKIP_THINK_HINT", "") or "").strip() not in ("1", "true", "yes"):
                try:
                    _hint = self._reasoning_summary_from_user_input(user_input)
                    if _hint and str(_hint).strip():
                        yield {'event': 'reasoning', 'content': str(_hint).strip() + '\n\n'}
                except Exception:
                    pass
            prompt = ReactPromptTemplates.think_prompt(
                user_input,
                tools_info,
                result_context,
                []
            )
            if perf:
                print(f"[PERF][react] think_prompt_build_ms={(time.perf_counter()-t0)*1000:.1f}")
            
            # 首轮思考：本处一律用 chat_stream_with_reasoning 边收边 yield（真流式）。
            # LLM 的 chat_with_reasoning 已改为「复用同一条流式迭代再汇总」，仅作无 stream 方法或上面流式失败时的回退，不再单独维护一套 DashScope 调用。
            response = None
            stream_attempted = False
            stream_ok = False
            print(
                f"[REACT-STREAM] LLM 流式：chat_stream_with_reasoning={hasattr(self.llm, 'chat_stream_with_reasoning')}, "
                f"chat_stream_fallback_chunks={hasattr(self.llm, 'chat_stream_fallback_chunks')}, "
                f"chat_with_reasoning={hasattr(self.llm, 'chat_with_reasoning')}"
            )
            stream_attempted = True
            try:
                content_parts = []
                # Cursor 式「Thought briefly / Thought for X.Xs」：从首段 reasoning 到首段正文（或首 token）
                try:
                    brief_ms = max(0, int(os.getenv("REACT_THOUGHT_BRIEF_MS", "800")))
                except Exception:
                    brief_ms = 800
                _t_stream_start = time.time()
                _t_first_reasoning = None
                _reasoning_timing_sent = False
                # 真正实时：在后台线程读取流式结果，通过队列逐段推送到 SSE（统一 _resolve_chat_stream_iter）
                q: "queue.Queue[object]" = queue.Queue()
                DONE = object()

                def _worker():
                    try:
                        for it in self._resolve_chat_stream_iter(prompt):
                            q.put(it)
                    except Exception as e:
                        q.put({"type": "content_delta", "delta": f"Error: {e}"})
                    finally:
                        q.put(DONE)

                t = threading.Thread(target=_worker, daemon=True)
                t.start()

                # 实时流式下发思考过程，不缓冲
                reasoning_buffer = ""
                first_reasoning_sent = False

                # 首轮「任务列表」正文流式：边收边推给前端，并择机解析出部分 Todo（无需等整段结束）
                _todo_buf = ""
                _partial_parse_tick = 0
                _last_partial_n = 0

                while True:
                    item = q.get()
                    if item is DONE:
                        break
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "reasoning_delta":
                        delta = item.get("delta")
                        if delta is not None and isinstance(delta, str):
                            reasoning_buffer += delta
                            if _t_first_reasoning is None and reasoning_buffer.strip():
                                _t_first_reasoning = time.time()
                            if perf and not first_reasoning_sent:
                                first_reasoning_sent = True
                                print(f"[PERF][react] first_reasoning_delta_ms={(time.perf_counter()-t0)*1000:.1f}")
                            yield {"event": "reasoning", "content": delta}
                    elif item.get("type") == "content_delta":
                        delta = item.get("delta") or ""
                        if delta:
                            if not _reasoning_timing_sent:
                                now = time.time()
                                if _t_first_reasoning is not None:
                                    duration_ms = int((now - _t_first_reasoning) * 1000)
                                    had_r = True
                                else:
                                    duration_ms = int((now - _t_stream_start) * 1000)
                                    had_r = False
                                kind = "brief" if duration_ms < brief_ms else "normal"
                                yield {
                                    "event": "reasoning_timing",
                                    "segment": "think",
                                    "duration_ms": duration_ms,
                                    "kind": kind,
                                    "had_reasoning": had_r,
                                    "brief_threshold_ms": brief_ms,
                                }
                                _reasoning_timing_sent = True
                            content_parts.append(delta)
                            _todo_buf += delta
                            yield {"event": "todos_stream", "delta": delta}
                            _partial_parse_tick += len(delta)
                            _should_try = (
                                _partial_parse_tick >= 96
                                or "</todo" in _todo_buf.lower()
                                or "</item>" in _todo_buf.lower()
                            )
                            if _should_try:
                                _partial_parse_tick = 0
                                try:
                                    _pt = robust_parse_todos(_todo_buf)
                                    if _pt and len(_pt) > _last_partial_n:
                                        _last_partial_n = len(_pt)
                                        yield {"event": "todos_partial", "data": _pt}
                                except Exception:
                                    pass

                # 仅产出 reasoning、无正文时补一条 timing（少见）
                if not _reasoning_timing_sent and reasoning_buffer.strip():
                    try:
                        bms = brief_ms
                    except Exception:
                        bms = 800
                    if _t_first_reasoning is not None:
                        duration_ms = int((time.time() - _t_first_reasoning) * 1000)
                    else:
                        duration_ms = int((time.time() - _t_stream_start) * 1000)
                    yield {
                        "event": "reasoning_timing",
                        "segment": "think",
                        "duration_ms": duration_ms,
                        "kind": "brief" if duration_ms < bms else "normal",
                        "had_reasoning": True,
                        "brief_threshold_ms": bms,
                    }

                # 用流式汇总的 content 作为 response
                response = "".join(content_parts).strip() if content_parts else None
                stream_ok = True
            except Exception as e:
                print(f"[REACT-STREAM] 统一流式迭代失败，将尝试 chat_with_reasoning / _stream_llm_prompt_collect 回退: {e}")
                import traceback
                traceback.print_exc()
            # 无流式方法、或流式抛错、或（极少数）未实现 stream 时：整段接口回退，仍走与前端一致的 reasoning / todos_stream 事件
            if (
                response is None
                and hasattr(self.llm, 'chat_with_reasoning')
                and (not stream_attempted or not stream_ok)
            ):
                try:
                    try:
                        _fb_brief_ms = max(0, int(os.getenv("REACT_THOUGHT_BRIEF_MS", "800")))
                    except Exception:
                        _fb_brief_ms = 800
                    _t_fb = time.time()
                    raw = await self.llm.chat_with_reasoning(prompt)
                    _dur_fb = int((time.time() - _t_fb) * 1000)
                    _had_r_fb = bool((raw.get('reasoning_content') or '').strip())
                    yield {
                        'event': 'reasoning_timing',
                        'segment': 'think',
                        'duration_ms': _dur_fb,
                        'kind': 'brief' if _dur_fb < _fb_brief_ms else 'normal',
                        'had_reasoning': _had_r_fb,
                        'brief_threshold_ms': _fb_brief_ms,
                    }
                    response = raw.get('content') or raw.get('result') or ''
                    reasoning = raw.get('reasoning_content')
                    if reasoning and isinstance(reasoning, str) and reasoning.strip():
                        yield {'event': 'reasoning', 'content': reasoning.strip()}
                    if response:
                        yield {'event': 'todos_stream', 'delta': response}
                        try:
                            _pt_fb = robust_parse_todos(response)
                            if _pt_fb:
                                yield {'event': 'todos_partial', 'data': _pt_fb}
                        except Exception:
                            pass
                except Exception as e:
                    print(f"[REACT-STREAM] chat_with_reasoning 失败，回退流式拉取: {e}")
            if response is None:
                _sink = []
                _ag = self._stream_llm_prompt_collect(prompt, stream_kind="think", full_text_sink=_sink)
                _ait = _ag.__aiter__()
                while True:
                    try:
                        _ev = await _ait.__anext__()
                        yield _ev
                    except StopAsyncIteration:
                        break
                response = _sink[0] if _sink else ""
            # 使用健壮版解析，优先 XML，其次 JSON/文本兜底
            todos = robust_parse_todos(response)
            thinking_time = time.time() - thinking_start_time  # 思考阶段耗时（不是总过程）
            
            print(f"[REACT-STREAM] 生成的Todos: {todos}")
            
            if not todos:
                yield {'event': 'error', 'message': '无法生成任务列表'}
                return
            
            if perf:
                print(f"[PERF][react] todos_ready_ms={(time.perf_counter()-t0)*1000:.1f} count={len(todos)}")
            yield {'event': 'todos', 'data': todos}
            
            # 提前拦截：用户要求修改「类型」时直接提示不可修改，不执行 grep/modify，避免长时间无意义执行
            if self._user_requested_type_modification(user_input) and any('modify' in (t or '').lower() or '修改' in (t or '') for t in todos):
                msg = '「类型」(type) 为系统固定字段，不可修改。可修改的字段包括：状态、期望结果、标题、优先级、复现步骤、负责人等。'
                yield {'event': 'immutable_field_rejection', 'message': msg}
                yield {'event': 'done', 'findings': [msg], 'steps_count': 0, 'duration': time.time() - start_time, 'thinking_time': thinking_time, 'summary': msg}
                return
            
            # ===== SKILL 匹配：检查是否有匹配的技能工作流 =====
            matched_skill, skill_score = get_skill_integration().match_skill(user_input, result_context)
            
            if matched_skill and skill_score >= 0.3:
                print(f"[REACT-STREAM] 🎯 匹配到技能: {matched_skill.name} (分数: {skill_score:.2f})")
                fallback_workflow_tools = []
                try:
                    wf = sorted(getattr(matched_skill, 'workflow', []) or [], key=lambda s: getattr(s, 'step', 0))
                    fallback_workflow_tools = [((getattr(s, 'tool', '') or '').strip()) for s in wf if (getattr(s, 'tool', '') or '').strip()]
                except Exception as e:
                    print(f"[REACT-STREAM] ⚠️ 读取技能 workflow 失败: {e}")

                # 技能捆绑了多步（如 grep + modify）时，若 LLM 只生成了少于步骤数的 todo（如 GLM5 只生成了 1 条），
                # 则用技能工作流生成的 todos 替换，保证会执行完整流程
                if len(fallback_workflow_tools) >= 2 and len(todos) < len(fallback_workflow_tools):
                    workflow_todos = self._generate_todos_from_skill_workflow(matched_skill, user_input)
                    if len(workflow_todos) >= len(fallback_workflow_tools):
                        todos = workflow_todos
                        yield {'event': 'todos', 'data': todos}
                        print(f"[REACT-STREAM] 📋 已按技能工作流补全 todos，共 {len(todos)} 个任务: {todos}")

                print(f"[REACT-STREAM] 📋 将按 todos 逐个执行，共 {len(todos)} 个任务")
                yield {'event': 'skill_matched', 'skill': matched_skill.name, 'score': skill_score}
                
                # 初始化 observation 变量
                observation = {}
                batch_results = []  # 收集所有批量修改结果
                
                # 按 todos 逐个执行，而不是按固定技能工作流
                for i, todo in enumerate(todos):
                    yield {'event': 'todo_start', 'index': i, 'todo': todo}
                    
                    # 从 todo 中提取关键词和状态
                    todo_params = await self._extract_todo_params(todo, user_input)
                    tool_name = todo_params['tool']

                    # 兜底：如果 todo 解析不出工具，用技能 workflow 的对应步骤工具补齐（不改 todo 文本，只改执行工具）
                    if tool_name == 'unknown' and fallback_workflow_tools:
                        mapped = fallback_workflow_tools[i] if i < len(fallback_workflow_tools) else fallback_workflow_tools[-1]
                        if mapped in ('grep', 'modify', 'create'):
                            tool_name = mapped
                            todo_params['tool'] = mapped
                            # 尽量补齐 grep/modify 的必要参数
                            params = todo_params.get('params') or {}
                            inferred_target = params.get('target')
                            if not inferred_target:
                                skill_name_lower = (matched_skill.name or '').lower()
                                if 'bug' in skill_name_lower:
                                    inferred_target = 'bug'
                                elif 'testcase' in skill_name_lower or 'test_case' in skill_name_lower:
                                    inferred_target = 'testcase'
                                elif user_input and ('测试用例' in user_input or 'test case' in user_input.lower()):
                                    inferred_target = 'testcase'
                                elif user_input and ('bug' in user_input or '缺陷' in user_input or 'Bug' in user_input):
                                    inferred_target = 'all'  # 兜底：在所有计划、不分类型查一遍
                                else:
                                    inferred_target = 'badcase'
                                params['target'] = inferred_target
                            if mapped == 'grep':
                                params.setdefault('mode', 'locate')
                                params.setdefault('keywords', self._extract_title_keywords_for_grep(user_input, todo) or '')
                            elif mapped == 'modify':
                                params.setdefault('confirm', False)
                                if 'modifications' not in params or not params.get('modifications'):
                                    params['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                            elif mapped == 'create':
                                params.setdefault('target', 'bug')
                                params.setdefault('fields', {})
                                params['confirm'] = False
                            todo_params['params'] = params
                            print(f"[REACT-STREAM] 🔧 todo 工具兜底映射: index={i}, unknown -> {mapped}")
                    
                    # secondary fallback: if parser still returns unknown, infer by todo text
                    if tool_name == 'unknown':
                        t = (todo or '').lower()
                        if 'create' in t:
                            tool_name = 'create'
                            todo_params['tool'] = 'create'
                            p = todo_params.get('params') or {}
                            p.setdefault('target', 'bug')
                            p.setdefault('fields', {})
                            p['confirm'] = False
                            todo_params['params'] = p
                        elif 'grep' in t or 'search' in t:
                            tool_name = 'grep'
                            todo_params['tool'] = 'grep'
                            p = todo_params.get('params') or {}
                            p.setdefault('mode', 'locate')
                            todo_params['params'] = p
                        elif 'modify' in t or 'update' in t:
                            tool_name = 'modify'
                            todo_params['tool'] = 'modify'
                            p = todo_params.get('params') or {}
                            p.setdefault('confirm', False)
                            p.setdefault('modifications', {})
                            todo_params['params'] = p

                    print(f"[REACT-STREAM] Todo[{i}] 提取参数: tool={tool_name}, params={todo_params}")
                    
                    # 确保必要参数
                    params = todo_params['params']
                    if 'project_id' not in params and project_id:
                        params['project_id'] = project_id
                    if 'userId' not in params:
                        params['userId'] = 'system_agent'
                    # 兜底：grep target=all 时在所有迭代计划查，不传 plan_id
                    if tool_name == 'grep' and params.get('target') == 'all':
                        params.pop('plan_id', None)
                    
                    # 如果是 modify 工具，需要从 grep 结果中获取 target_id（含 testcase）
                    # 用户说「修改bug」时必须用 target=bug 和 first_bug_id，不能默认 badcase 导致改错
                    if tool_name == 'modify':
                        grep_result = result_context.get('grep_result', {})
                        target_type = params.get('target') or self._infer_modify_target(user_input, todo)
                        params['target'] = target_type
                        if target_type == 'bug':
                            target_id = grep_result.get('first_bug_id')
                        elif target_type == 'testcase':
                            target_id = grep_result.get('first_testcase_id')
                        else:
                            target_id = grep_result.get('first_badcase_id')
                        if not target_id:
                            tid_m = self._try_target_id_from_merged_lists(
                                result_context, target_type, user_input, todo
                            )
                            if tid_m is not None:
                                target_id = tid_m
                                print(
                                    f"[REACT-STREAM] 从合并列表注入 target_id={target_id}, target={target_type}"
                                )
                        if target_id:
                            params['target_id'] = target_id
                            print(f"[REACT-STREAM] 从 grep 结果获取 target_id={target_id}, target={target_type}")
                        else:
                            print(f"[REACT-STREAM] ⚠️ 无法从 grep 结果获取 target_id (target={target_type})，尝试补救 grep…")
                            kw = self._extract_title_keywords_for_grep(user_input, todo) or ''
                            gparams: Dict[str, Any] = {
                                'project_id': project_id,
                                'keywords': kw,
                                'mode': 'locate',
                                'target': target_type if target_type in ('bug', 'badcase', 'testcase') else 'all',
                                'userId': 'system_agent',
                            }
                            if self.plan_id is not None and gparams.get('target') != 'all':
                                gparams['plan_id'] = self.plan_id
                            if gparams.get('target') == 'all':
                                gparams.pop('plan_id', None)
                            yield {
                                'event': 'executing',
                                'tool': 'grep',
                                'reason': f'Todo步骤 {i+1}',
                                'index': i,
                                'message': '正在补充定位记录（用于修改）…',
                            }
                            grep_obs = await self._execute_tool({'execute': True, 'tool': 'grep', 'params': gparams})
                            if grep_obs.get('success'):
                                self._merge_grep_observation_into_context(grep_obs, gparams, result_context)
                                grep_result = result_context.get('grep_result', {})
                                if target_type == 'bug':
                                    target_id = grep_result.get('first_bug_id')
                                elif target_type == 'testcase':
                                    target_id = grep_result.get('first_testcase_id')
                                else:
                                    target_id = grep_result.get('first_badcase_id')
                                if target_id:
                                    params['target_id'] = target_id
                                    print(f"[REACT-STREAM] 补救 grep 后 target_id={target_id}")
                                if not params.get('target_id'):
                                    tid_s = self._try_target_id_from_merged_lists(
                                        result_context, target_type, user_input, todo
                                    )
                                    if tid_s is not None:
                                        params['target_id'] = tid_s
                                        target_id = tid_s
                                        print(f"[REACT-STREAM] 技能分支补救 grep 后从列表注入 target_id={tid_s}")
                        
                        # 思考意图 + 探索记录（类似 Cursor 探索文件）：有 target_id 时先探索当前记录与用户列表，再让大模型基于探索结果确认 modifications
                        if target_id and (not params.get('modifications') or len(params.get('modifications', {})) == 0):
                            modify_tool = self.tools.get('modify')
                            if modify_tool and getattr(modify_tool, 'explore_record', None):
                                try:
                                    loop = asyncio.get_event_loop()
                                    exploration = await asyncio.wait_for(
                                        loop.run_in_executor(
                                            self._tool_executor,
                                            lambda: modify_tool.explore_record(target_type, target_id, params.get('project_id') or self.project_id),
                                        ),
                                        timeout=15,
                                    )
                                    if exploration and exploration.get('current_record'):
                                        yield {'event': 'exploring', 'message': '正在结合当前记录确认修改意图…'}
                                        # modify 步骤：所有模型都强制不带思考
                                        with _NoThinking():
                                            params['modifications'] = await self._extract_modifications_with_llm(todo, user_input, exploration=exploration)
                                        if not params.get('modifications') and user_input:
                                            params['modifications'] = self._extract_modifications_with_regex(user_input)
                                        print(f"[REACT-STREAM] 探索后提取的 modifications: {params.get('modifications')}")
                                except Exception as e:
                                    print(f"[REACT-STREAM] 探索记录失败，回退到仅 LLM 提取: {e}")
                                    if not params.get('modifications'):
                                        with _NoThinking():
                                            params['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                                        if not params.get('modifications'):
                                            params['modifications'] = self._extract_modifications_with_regex(user_input)
                            elif not params.get('modifications'):
                                with _NoThinking():
                                    params['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                                if not params.get('modifications'):
                                    params['modifications'] = self._extract_modifications_with_regex(user_input)

                    if tool_name == 'create':
                        grep_result = result_context.get('grep_result', {})
                        target_type = params.get('target') or self._infer_create_target(user_input, todo)
                        params['target'] = target_type
                        fields = params.get('fields') or {}
                        title_key = 'name' if target_type == 'plan' else 'title'
                        extracted_title = self._extract_create_title(user_input, todo)
                        if extracted_title and not fields.get(title_key):
                            fields[title_key] = extracted_title

                        wants_copy = any(token in (user_input or '') for token in ('复制', '一样', '相同')) or any(token in (todo or '') for token in ('复制', '一样', '相同'))
                        if wants_copy:
                            if target_type == 'bug':
                                source_id = grep_result.get('first_bug_id') or result_context.get('first_bug_id')
                                if source_id and not fields.get('copy_from_bug_id'):
                                    fields['copy_from_bug_id'] = source_id
                            elif target_type == 'badcase':
                                source_id = grep_result.get('first_badcase_id') or result_context.get('first_badcase_id')
                                if source_id and not fields.get('copy_from_badcase_id'):
                                    fields['copy_from_badcase_id'] = source_id
                            elif target_type == 'testcase':
                                source_id = grep_result.get('first_testcase_id') or result_context.get('first_testcase_id')
                                if source_id and not fields.get('copy_from_testcase_id'):
                                    fields['copy_from_testcase_id'] = source_id

                        params['fields'] = fields
                        params.setdefault('confirm', False)
                        params.setdefault('natural_query', user_input)
                        print(f"[REACT-STREAM] create 参数补齐: target={target_type}, fields={fields}")

                    # 技能分支：与主循环一致，执行 modify 前再 enrich + last_resort，避免仅有 modifications 却无 target_id 直接调工具报错
                    skill_skip_modify = False
                    if tool_name == 'modify':
                        decision_skill = {'execute': True, 'tool': 'modify', 'params': params}
                        decision_skill, _pre_ev = await self._enrich_modify_decision_for_main_loop(
                            decision_skill, todo, user_input, result_context, project_id, step_index=i
                        )
                        for _ev in _pre_ev:
                            yield _ev
                        if not self._modify_params_ready(decision_skill.get('params')):
                            decision_skill, _lr_ev = await self._last_resort_modify_fill(
                                decision_skill, todo, user_input, result_context, project_id, step_index=i
                            )
                            for _ev in _lr_ev:
                                yield _ev
                        params = decision_skill['params']
                        if not self._modify_params_ready(params):
                            nq = (user_input or todo or '').strip()
                            if nq:
                                params['natural_query'] = nq[:2000]
                        if not self._modify_params_ready(params):
                            skill_skip_modify = True
                            print(
                                "[REACT-STREAM] 技能分支 stability_gate: modify 仍缺 target_id/natural_query 或 modifications"
                            )

                    # 执行工具（skill_skip_modify 时跳过真实调用，避免 decision 未定义或重复调用）
                    if skill_skip_modify:
                        observation = {
                            'success': False,
                            'skipped': True,
                            'stability_gate': 'modify_params_incomplete',
                            'error': '缺少必要参数：modify 需要 target_id（或 natural_query）与非空 modifications，已尝试补全仍不足。',
                            'message': 'modify 未执行（参数未就绪）',
                        }
                        print(f"[REACT-STREAM] 技能分支跳过 modify 执行")
                        yield {'event': 'executing', 'tool': 'modify', 'reason': f'Todo步骤 {i+1}', 'index': i, 'message': '参数未就绪，已跳过修改'}
                    else:
                        decision = {'execute': True, 'tool': tool_name, 'params': params}
                        exec_payload = {'event': 'executing', 'tool': tool_name, 'reason': f'Todo步骤 {i+1}', 'index': i}
                        _pub = {}
                        for _k in ('keywords', 'target', 'mode', 'fields', 'modifications', 'target_id'):
                            if _k in params and params[_k] not in (None, '', {}):
                                _pub[_k] = params[_k]
                        if _pub:
                            exec_payload['params'] = _pub
                        if tool_name == 'modify':
                            exec_payload['message'] = '正在应用修改到数据库…'
                            print(f"[REACT-STREAM] modify 即将执行（探索/参数已就绪），进入线程池…")
                        yield exec_payload

                        # modify 可能执行较久：持续下发分步进度/心跳事件，避免前端“卡住没输出”
                        if tool_name == 'modify':
                            started = time.time()
                            task = asyncio.create_task(self._execute_tool(decision))
                            await asyncio.sleep(0.1)
                            while not task.done():
                                waited = time.time() - started
                                got_any = False
                                try:
                                    pq = (decision.get('params') or {}).get('progress_queue')
                                    if pq:
                                        while True:
                                            msg = pq.get_nowait()
                                            got_any = True
                                            yield {'event': 'executing', 'tool': 'modify', 'reason': f'Todo步骤 {i+1}', 'index': i, 'message': str(msg)}
                                            print(f"[REACT-STREAM] modify 进度: {msg}", flush=True)
                                except Exception:
                                    pass
                                if not got_any:
                                    yield {'event': 'executing', 'tool': 'modify', 'reason': f'Todo步骤 {i+1}', 'index': i, 'message': f'修改中…已等待 {waited:.0f}s'}
                                await asyncio.sleep(0.2 if got_any else 0.4)
                            observation = await task
                        else:
                            observation = await self._execute_tool(decision)
                    print(f"[REACT-STREAM] Todo[{i}] 工具 {tool_name} 结果: success={observation.get('success')}")
                    
                    # 更新上下文（供后续步骤使用，含 testcase；id 用 rerank 取分高的）
                    if tool_name == 'grep' and observation.get('success'):
                        self._merge_grep_observation_into_context(observation, params, result_context)
                    
                    # 如果是 modify，收集结果（含 testcase）；类型与 params.target 一致，避免误标为 badcase
                    if tool_name == 'modify':
                        pt = params.get('target') or self._infer_modify_target(user_input, todo)
                        if pt == 'bug' and result_context.get('bug_list'):
                            target_list, target_type = result_context['bug_list'], 'bug'
                        elif pt == 'testcase' and result_context.get('testcase_list'):
                            target_list, target_type = result_context['testcase_list'], 'testcase'
                        elif result_context.get('badcase_list'):
                            target_list, target_type = result_context['badcase_list'], 'badcase'
                        else:
                            target_list = (result_context.get('badcase_list') or result_context.get('bug_list') or result_context.get('testcase_list') or [])
                            target_type = 'badcase' if result_context.get('badcase_list') else ('bug' if result_context.get('bug_list') else 'testcase')
                        
                        if observation.get('success'):
                            # 优先用 modify 工具返回的 target，避免 params 被推断成 badcase 时误标
                            actual_target = observation.get('target') or target_type
                            _bef = observation.get('before') or {}
                            batch_results.append({
                                'target_id': params.get('target_id'),
                                'target': actual_target,
                                'plan_id': _bef.get('plan_id'),
                                'record_title': _bef.get('title') or _bef.get('name'),
                                'diff': observation.get('diff', []),
                                'modifications': params.get('modifications', {}),
                                'before': observation.get('before', {}),
                                'after': observation.get('after', {}),
                                'confirmation_required': observation.get('confirmation_required', True),
                                'success': True
                            })
                    
                    # 发送观察结果
                    yield {'event': 'observation', 'data': observation}
                    yield {'event': 'todo_end', 'index': i}
                
                # 技能工作流完成
                print(f"[REACT-STREAM] ✅ Todos 执行完成")
                
                # 汇总结果
                workflow_findings = []
                if batch_results:
                    # 批量修改结果（target 从结果中取，避免一律标为 badcase）
                    bt = batch_results[0].get('target', 'badcase') if batch_results else 'badcase'
                    target_name = 'Bug' if bt == 'bug' else ('测试用例' if bt == 'testcase' else 'BadCase')
                    mod_summaries = []
                    field_labels = {'status': '状态', 'expected_result': '期望结果', 'title': '标题', 'priority': '优先级', 'base_problem': '相似问题'}
                    for r in batch_results:
                        mods = r.get('modifications', {}) or {}
                        parts = []
                        for k, v in mods.items():
                            if v is None or v == '':
                                continue
                            label = field_labels.get(k, k)
                            val_str = str(v)[:30] + ('…' if len(str(v)) > 30 else '')
                            parts.append(f"{label}={val_str}")
                        if parts:
                            mod_summaries.append(f"ID={r['target_id']} " + "；".join(parts))
                    summary_text = "、".join(mod_summaries) if mod_summaries else f"已对 {len(batch_results)} 条记录生成修改预览"
                    observation = {
                        'success': all(r.get('success') for r in batch_results),
                        'message': f'已生成 {len(batch_results)} 条修改预览',
                        'summary': f'批量修改预览：{summary_text}',
                        'batch_modify': True,
                        'batch_results': batch_results,
                        'batch_count': len(batch_results),
                        'target': bt
                    }
                    workflow_findings.append(observation['summary'])
                    # 关键发现：再补一条简短说明，避免只有「批量修改预览：」时显得空
                    if not mod_summaries:
                        workflow_findings.append(f"已定位并生成 {len(batch_results)} 条{target_name}的修改预览，请在下方沙箱预览中查看详情。")
                    yield {'event': 'observation', 'data': observation}
                
                # 发送 done 事件（带统一总结；thinking_time 为上面 THINK 阶段已算好的）
                duration = time.time() - start_time
                summary = f"已生成 {len(batch_results)} 条修改预览，完成 {len(todos)} 步，耗时 {duration:.2f}s。请在下方沙箱预览中确认。"
                yield {
                    'event': 'done',
                    'findings': workflow_findings,
                    'steps_count': len(todos),
                    'duration': duration,
                    'thinking_time': thinking_time,
                    'summary': summary
                }
                return
            
            # ===== MAIN LOOP: ACT（正常流程，当没有匹配技能时）=====
            # modify 的 target_id / modifications 以服务端 _enrich_modify_decision_for_main_loop 补全为准，不依赖模型 XML 完整性。
            for i, todo in enumerate(todos):
                yield {'event': 'todo_start', 'index': i, 'todo': todo}
                
                # 决策：LLM决定使用哪个工具
                decision_prompt = ReactPromptTemplates.decide_prompt(
                    todo, user_input, tools_info, result_context
                )
                # 进入 modify 步骤：传递参数给所有的模型传递不开启思考
                if 'modify' in (todo or '').lower() or '修改' in (todo or ''):
                    with _NoThinking():
                        _sink_d = []
                        _dg = self._stream_llm_prompt_collect(
                            decision_prompt, step_index=i, stream_kind="decide", full_text_sink=_sink_d
                        )
                        _dit = _dg.__aiter__()
                        while True:
                            try:
                                _de = await _dit.__anext__()
                                yield _de
                            except StopAsyncIteration:
                                break
                        decision_response = _sink_d[0] if _sink_d else ""
                else:
                    _sink_d = []
                    _dg = self._stream_llm_prompt_collect(
                        decision_prompt, step_index=i, stream_kind="decide", full_text_sink=_sink_d
                    )
                    _dit = _dg.__aiter__()
                    while True:
                        try:
                            _de = await _dit.__anext__()
                            yield _de
                        except StopAsyncIteration:
                            break
                    decision_response = _sink_d[0] if _sink_d else ""
                print(f"[REACT-STREAM] LLM决策原始响应: {decision_response}")
                decision = parse_xml_decision(decision_response)
                
                print(f"[REACT-STREAM] 决策结果: {decision}")
                
                # 兜底逻辑：当 LLM 返回空响应但 Todo包含 modify 关键词时
                if not decision['execute'] and 'modify' in todo.lower():
                    print(f"[REACT-STREAM] 检测到 modify 任务但 LLM 返回空响应，尝试自动推断参数...")
                    decision = self._infer_modify_params(todo, result_context)
                    print(f"[REACT-STREAM] 自动推断的决策: {decision}")
                
                # Skill工具优化：智能任务处理
                if decision['execute']:
                    decision = await self._optimize_with_skill_tool(decision, user_input, result_context, project_id)
                
                if not decision['execute']:
                    print(f"[REACT-STREAM] 跳过任务（execute=False）")
                    yield {'event': 'skip', 'todo': todo, 'index': i}
                    yield {'event': 'todo_end', 'index': i}
                    continue
                
                # Text2SQL 优化：数据库查询优先使用自然语言
                if decision['execute'] and decision['tool'] == 'database_query':
                    natural_query = self._extract_natural_query(todo, user_input)
                    if natural_query and self.text2sql_tool is None:
                        self.text2sql_tool = get_text2sql_tool("instance/badcase_doctor.db")
                    if natural_query and self.text2sql_tool:
                        print(f"[REACT-STREAM] 优先使用 Text2SQL执行: {natural_query}")
                        decision['params']['natural_query'] = natural_query
                
                # Todo 文案与 LLM 决策对齐：避免「步骤标题是 create、executing 里却是 grep」导致前端展示矛盾
                if decision.get('execute') and decision.get('tool'):
                    todo_params_aligned = await self._extract_todo_params(todo, user_input)
                    t_from_todo = todo_params_aligned.get('tool')
                    if (
                        t_from_todo
                        and t_from_todo != 'unknown'
                        and t_from_todo != decision.get('tool')
                        and t_from_todo in ('create', 'grep', 'modify')
                        and decision.get('tool') in ('create', 'grep', 'modify')
                    ):
                        print(
                            f"[REACT-STREAM] Todo 与 LLM 工具不一致，按 Todo 纠正: "
                            f"{decision.get('tool')} -> {t_from_todo} | todo={todo!r}"
                        )
                        decision['tool'] = t_from_todo
                        new_params = dict(todo_params_aligned.get('params') or {})
                        old_p = decision.get('params') or {}
                        if isinstance(old_p, dict):
                            for k, v in old_p.items():
                                if v is None or v == '' or v == {}:
                                    continue
                                if k not in new_params or new_params.get(k) in (None, '', {}):
                                    new_params[k] = v
                        decision['params'] = new_params
                    if decision.get('tool') == 'create':
                        dp = decision.setdefault('params', {})
                        dp.setdefault('natural_query', user_input)

                skip_modify_exec = False
                # 主循环 modify：补全 target_id / modifications（与技能分支一致），并可选下发补救 grep 事件
                if decision.get('execute') and decision.get('tool') == 'modify':
                    decision, _pre_yield_modify = await self._enrich_modify_decision_for_main_loop(
                        decision, todo, user_input, result_context, project_id, step_index=i
                    )
                    for _ev in _pre_yield_modify:
                        yield _ev
                    if not self._modify_params_ready(decision.get('params')):
                        decision, _lr_ev = await self._last_resort_modify_fill(
                            decision, todo, user_input, result_context, project_id, step_index=i
                        )
                        for _ev in _lr_ev:
                            yield _ev
                    if not self._modify_params_ready(decision.get('params')):
                        nq = (user_input or todo or '').strip()
                        if nq:
                            decision.setdefault('params', {})['natural_query'] = nq[:2000]
                    if not self._modify_params_ready(decision.get('params')):
                        skip_modify_exec = True
                        print(
                            "[REACT-STREAM] stability_gate: modify 仍缺 target_id/natural_query 或 modifications，"
                            "跳过执行以避免无效调用"
                        )

                if skip_modify_exec:
                    observation = {
                        'success': False,
                        'skipped': True,
                        'stability_gate': 'modify_params_incomplete',
                        'error': '缺少必要参数：modify 需要 target_id（或 natural_query）与非空 modifications，已尝试 enrich/最后手段补全仍不足，请明确要改的记录与字段。',
                        'message': 'modify 未执行（参数未就绪）',
                    }
                    print(f"[REACT-STREAM] 执行工具: {decision['tool']} (stability_gate 跳过)")
                else:
                    print(f"[REACT-STREAM] 执行工具: {decision['tool']}")

                    # 如果是 modify，尝试从参数里提取要修改的字段，并带上首条进度文案，避免前端一直只显示“修改中...”
                    executing_payload = {
                        'event': 'executing',
                        'tool': decision['tool'],
                        'reason': decision.get('reason', '') or f'Todo步骤 {i + 1}',
                        'index': i,
                    }
                    if decision['tool'] == 'modify':
                        mods = (decision.get('params') or {}).get('modifications') or {}
                        if isinstance(mods, dict) and mods:
                            executing_payload['fields'] = list(mods.keys())
                        executing_payload['message'] = '正在启动修改（进入线程池）…'
                        _pp = decision.get('params') or {}
                        _pub = {}
                        for _k in ('keywords', 'target', 'mode', 'fields', 'modifications', 'target_id'):
                            if _k in _pp and _pp[_k] not in (None, '', {}):
                                _pub[_k] = _pp[_k]
                        if _pub:
                            executing_payload['params'] = _pub

                    yield executing_payload

                    # 批量修改逻辑：如果是 modify 工具，检查是否有候选列表（badcase/bug/testcase）
                    # 按用户意图选择类型：说「修改bug」用 bug_list，避免误用 badcase_list
                    if decision['tool'] == 'modify':
                        badcase_list = result_context.get('badcase_list', [])
                        bug_list = result_context.get('bug_list', [])
                        testcase_list = result_context.get('testcase_list', [])
                        mod_target = (decision.get('params') or {}).get('target') or self._infer_modify_target(user_input, (decision.get('reason') or ''))
                        if mod_target == 'bug' and bug_list:
                            target_list, target_type = bug_list, 'bug'
                        elif mod_target == 'testcase' and testcase_list:
                            target_list, target_type = testcase_list, 'testcase'
                        elif badcase_list:
                            target_list, target_type = badcase_list, 'badcase'
                        elif bug_list:
                            target_list, target_type = bug_list, 'bug'
                        elif testcase_list:
                            target_list, target_type = testcase_list, 'testcase'
                        else:
                            target_list, target_type = [], 'badcase'
    
                        # 仅一条候选时与 enrich 对齐：直接从列表写 target_id（grep_result.first_* 可能为空）
                        if (
                            decision.get('tool') == 'modify'
                            and target_list
                            and len(target_list) == 1
                            and not (decision.get('params') or {}).get('target_id')
                        ):
                            only = target_list[0]
                            oid = only.get('id') if isinstance(only, dict) else None
                            if oid is not None:
                                decision.setdefault('params', {})['target_id'] = oid
                                decision['params']['target'] = target_type
                                print(f"[REACT-STREAM] 主循环从单条候选注入 target_id={oid} ({target_type})")
                        
                        if target_list and len(target_list) > 1:
                            # 批量修改所有记录
                            all_results = []
                            for item in target_list:
                                item_id = item.get('id')
                                item_plan_id = item.get('plan_id')  # 获取 plan_id
                                if item_id:
                                    modify_decision = decision.copy()
                                    modify_decision['params']['target_id'] = item_id
                                    modify_decision['params']['target'] = target_type
                                    print(f"[REACT-STREAM] 批量修改 {target_type} ID={item_id}, plan_id={item_plan_id}")
                                    observation = await self._execute_tool(modify_decision)
                                    all_results.append({
                                        'id': item_id,
                                        'plan_id': item_plan_id,  # 添加 plan_id
                                        'result': observation
                                    })
                            
                            # 合并结果
                            target_name = 'Bug' if target_type == 'bug' else ('测试用例' if target_type == 'testcase' else 'BadCase')
                            modifications = decision.get('params', {}).get('modifications', {})
                            mod_summary = '、'.join([f'{k}:{v}' for k, v in modifications.items()])
                            observation = {
                                'success': all(r['result'].get('success') for r in all_results),
                                'message': f'已批量修改 {len(all_results)} 个 {target_type}',
                                'summary': f'批量修改{len(all_results)}条{target_name}：{mod_summary}',
                                'results': all_results,
                                'batch_modify': True,
                                'target': target_type
                            }
                        else:
                            # 单个修改：modify 可能执行较久，持续下发分步进度/心跳
                            if decision.get('tool') == 'modify':
                                started = time.time()
                                task = asyncio.create_task(self._execute_tool(decision))
                                await asyncio.sleep(0.1)
                                while not task.done():
                                    waited = time.time() - started
                                    got_any = False
                                    try:
                                        pq = (decision.get('params') or {}).get('progress_queue')
                                        if pq:
                                            while True:
                                                msg = pq.get_nowait()
                                                got_any = True
                                                yield {'event': 'executing', 'tool': 'modify', 'reason': '单个修改', 'index': i, 'message': str(msg)}
                                                print(f"[REACT-STREAM] modify 进度: {msg}", flush=True)
                                    except Exception:
                                        pass
                                    if not got_any:
                                        yield {'event': 'executing', 'tool': 'modify', 'reason': '单个修改', 'index': i, 'message': f'修改中…已等待 {waited:.0f}s'}
                                    await asyncio.sleep(0.2 if got_any else 0.4)
                                observation = await task
                            else:
                                observation = await self._execute_tool(decision)
                    else:
                        if decision.get('tool') == 'modify':
                            started = time.time()
                            task = asyncio.create_task(self._execute_tool(decision))
                            await asyncio.sleep(0.1)
                            while not task.done():
                                waited = time.time() - started
                                got_any = False
                                try:
                                    pq = (decision.get('params') or {}).get('progress_queue')
                                    if pq:
                                        while True:
                                            msg = pq.get_nowait()
                                            got_any = True
                                            yield {'event': 'executing', 'tool': 'modify', 'reason': decision.get('reason') or '执行中', 'index': i, 'message': str(msg)}
                                            print(f"[REACT-STREAM] modify 进度: {msg}", flush=True)
                                except Exception:
                                    pass
                                if not got_any:
                                    yield {'event': 'executing', 'tool': 'modify', 'reason': decision.get('reason') or '执行中', 'index': i, 'message': f'修改中…已等待 {waited:.0f}s'}
                                await asyncio.sleep(0.2 if got_any else 0.4)
                            observation = await task
                        else:
                            observation = await self._execute_tool(decision)
                
                print(f"[REACT-STREAM] 工具执行结果:")
                print(f"[REACT-STREAM]   成功: {observation.get('success', False)}")
                if 'results' in observation:
                    results = observation.get('results', [])
                    print(f"[REACT-STREAM]   结果条数: {len(results)}")
                    if results:
                        print(f"[REACT-STREAM] === 搜索结果详情 ===")
                        for idx, item in enumerate(results[:3], 1):
                            if isinstance(item, dict):
                                title = item.get('title') or item.get('text') or str(item)[:80]
                            else:
                                title = str(item)[:80]
                            print(f"[REACT-STREAM]   [{idx}] {title}")
                        if len(results) > 3:
                            print(f"[REACT-STREAM]   ... 还有 {len(results)-3} 条结果")
                if 'query' in observation:
                    print(f"[REACT-STREAM]   查询: {observation.get('query')}")
                if 'engine' in observation:
                    print(f"[REACT-STREAM]   引擎: {observation.get('engine')}")
                if 'error' in observation:
                    print(f"[REACT-STREAM]   错误: {observation.get('error')}")
                print(f"[REACT-STREAM]   完整结果: {observation}")
                
                # 智能重试：如果 modify 缺少 target_id，自动执行 grep 查询
                if (
                    not skip_modify_exec
                    and decision['tool'] == 'modify'
                    and observation.get('need_grep_first')
                ):
                    print(f"[REACT-STREAM] modify 缺少 target_id，自动执行 grep 查询...")
                    yield {'event': 'retry', 'message': '正在执行 grep 工具定位目标记录...'}
                    
                    suggested_params = observation.get('suggested_params', {})
                    # 从用户输入/ todo 中提取要查找的标题作为 keywords（拆分模糊匹配由 grep 内部处理）
                    keywords = self._extract_title_keywords_for_grep(user_input, todo)
                    # 兜底：在所有迭代计划、不分类型查一遍（target=all，不传 plan_id）
                    grep_params = {
                        'target': 'all',
                        'project_id': suggested_params.get('project_id', self.project_id),
                        'userId': 'system_agent'
                    }
                    if keywords:
                        grep_params['keywords'] = keywords
                        print(f"[REACT-STREAM] 从用户输入提取 grep keywords: '{keywords}'")
                    # 不传 plan_id，grep 查全项目所有计划
                    grep_decision = {
                        'execute': True,
                        'tool': 'grep',
                        'params': grep_params
                    }
                    grep_observation = await self._execute_tool(grep_decision)
                    print(f"[REACT-STREAM] grep 结果: success={grep_observation.get('success')}")
                    
                    # 从 grep 结果中提取 target_id（rerank 分高的选一条；支持 badcase/bug/testcase）
                    if grep_observation.get('success'):
                        grep_data = grep_observation.get('data', {})
                        badcase_list = grep_data.get('badcase_analysis', [])
                        bug_list = grep_data.get('bug_location', [])
                        testcase_list = grep_data.get('testcase_location', [])
                        
                        if badcase_list:
                            result_context['badcase_list'] = badcase_list
                            best = self._pick_best_match_from_list(badcase_list, keywords, key_title='title')
                            result_context['first_badcase_id'] = best.get('id')
                            print(f"[REACT-STREAM] BadCase rerank 选中 id={best.get('id')}")
                        if bug_list:
                            result_context['bug_list'] = bug_list
                            best = self._pick_best_match_from_list(bug_list, keywords, key_title='title')
                            result_context['first_bug_id'] = best.get('id')
                            print(f"[REACT-STREAM] Bug rerank 选中 id={best.get('id')}")
                        if testcase_list:
                            result_context['testcase_list'] = testcase_list
                            best = self._pick_best_match_from_list(testcase_list, keywords, key_title='title')
                            result_context['first_testcase_id'] = best.get('id')
                            print(f"[REACT-STREAM] 测试用例 rerank 选中 id={best.get('id')}")
                        
                        yield {'event': 'observation', 'data': grep_observation}
                        
                        # 按用户意图选类型：说「修改bug」用 bug_list
                        suggested = (decision.get('params') or {}).get('target') or suggested_params.get('target')
                        if not suggested:
                            suggested = self._infer_modify_target(user_input, '')
                        if suggested == 'bug' and result_context.get('bug_list'):
                            target_list, target_type = result_context['bug_list'], 'bug'
                        elif suggested == 'testcase' and result_context.get('testcase_list'):
                            target_list, target_type = result_context['testcase_list'], 'testcase'
                        elif result_context.get('badcase_list'):
                            target_list, target_type = result_context['badcase_list'], 'badcase'
                        elif result_context.get('bug_list'):
                            target_list, target_type = result_context['bug_list'], 'bug'
                        elif result_context.get('testcase_list'):
                            target_list, target_type = result_context['testcase_list'], 'testcase'
                        else:
                            target_list = []
                            target_type = 'badcase'
                        if target_list:
                            best_match = self._pick_best_match_from_list(target_list, keywords, key_title='title')
                            target_list = [best_match]
                            result_context['first_badcase_id' if target_type == 'badcase' else ('first_bug_id' if target_type == 'bug' else 'first_testcase_id')] = best_match.get('id')
                            # 单条修改（不再按“多条就批量”）
                            if len(target_list) >= 1:
                                print(f"[REACT-STREAM] 重试批量修改 {len(target_list)} 条 {target_type}")
                                all_results = []
                                for item in target_list:
                                    item_id = item.get('id')
                                    if item_id:
                                        retry_decision = decision.copy()
                                        retry_decision['params']['target_id'] = item_id
                                        retry_decision['params']['target'] = target_type
                                        if not retry_decision['params'].get('modifications'):
                                            retry_decision['params']['modifications'] = self._extract_modifications_with_regex(user_input)
                                        if not retry_decision['params'].get('modifications'):
                                            with self._llm_no_thinking():
                                                retry_decision['params']['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                                        retry_obs = await self._execute_tool(retry_decision)
                                        all_results.append({'id': item_id, 'plan_id': item.get('plan_id'), 'result': retry_obs})
                                
                                observation = {
                                    'success': all(r['result'].get('success') for r in all_results),
                                    'message': f'已批量修改 {len(all_results)} 个 {target_type}',
                                    'summary': f'批量修改{len(all_results)}条{"Bug" if target_type == "bug" else ("测试用例" if target_type == "testcase" else "BadCase")}',
                                    'results': all_results,
                                    'batch_modify': True,
                                    'target': target_type
                                }
                            else:
                                # 单个修改
                                retry_decision = decision.copy()
                                retry_decision['params']['target_id'] = target_list[0].get('id')
                                retry_decision['params']['target'] = target_type
                                if not retry_decision['params'].get('modifications'):
                                    retry_decision['params']['modifications'] = self._extract_modifications_with_regex(user_input)
                                if not retry_decision['params'].get('modifications'):
                                    with self._llm_no_thinking():
                                        retry_decision['params']['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                                print(f"[REACT-STREAM] 重试单个修改: target_id={retry_decision['params']['target_id']}")
                                observation = await self._execute_tool(retry_decision)

                # 结构化纠错：modify 失败后 grep+补参并重试（早于 LLM correct_and_retry）
                if (
                    decision.get('tool') == 'modify'
                    and not observation.get('success')
                    and not observation.get('skipped')
                ):
                    observation, _rec_ev = await self._recover_modify_after_failure(
                        decision,
                        observation,
                        todo,
                        user_input,
                        result_context,
                        project_id,
                    )
                    for _ev in _rec_ev:
                        yield _ev

                # 自动修正（最多1次）
                if (
                    not observation.get('success')
                    and not observation.get('corrected')
                    and not observation.get('skipped')
                ):
                    yield {'event': 'retry', 'message': '执行失败，正在尝试自动修正...'}
                    observation = await self.correction_engine.correct_and_retry(
                        todo=todo,
                        action=decision,
                        observation=observation,
                        context=result_context,
                        available_tools=tools_info,
                        execute_fn=self._execute_tool
                    )
                
                yield {'event': 'observation', 'data': observation}
                print(f"[REACT-DEBUG] Observation: {observation}")  # 调试日志
                
                # 提取执行证据并发送
                evidence = EvidenceExtractor.extract_from_observation(
                    decision['tool'],
                    decision.get('params', {}),
                    observation
                )
                # 直接发送 evidence 对象给前端
                yield {'event': 'evidence', 'data': evidence}
                
                # 将 evidence 转换为 findings 用于后续分析
                evidence_findings = EvidenceExtractor.format_as_findings(evidence)
                findings.extend(evidence_findings)
                
                # 分析
                analyze_prompt = ReactPromptTemplates.observe_prompt(
                    todo, decision, observation, result_context
                )
                _sink_o = []
                _og = self._stream_llm_prompt_collect(
                    analyze_prompt, step_index=i, stream_kind="observe", full_text_sink=_sink_o
                )
                _oit = _og.__aiter__()
                while True:
                    try:
                        _oe = await _oit.__anext__()
                        yield _oe
                    except StopAsyncIteration:
                        break
                analyze_response = _sink_o[0] if _sink_o else ""
                analysis = parse_xml_findings(analyze_response)
                
                # 更新状态
                result_context.update(analysis.get('context_update', {}))
                
                # 兜底逻辑：如果 context 中没有 bug_list/badcase_list 但 observation 中有，自动添加
                if decision['tool'] == 'grep' and isinstance(observation, dict):
                    # 多种可能的数据位置
                    obs_data = observation.get('data', observation)
                    if not isinstance(obs_data, dict):
                        obs_data = {}
                    
                    # Bug 列表 - 从多个可能的位置提取
                    if 'bug_list' not in result_context:
                        bug_location = obs_data.get('bug_location', []) or observation.get('bug_location', [])
                        if bug_location and isinstance(bug_location, list) and len(bug_location) > 0:
                            result_context['bug_list'] = bug_location
                            kw = result_context.get('_last_grep_keywords', '')
                            best = self._pick_best_match_from_list(bug_location, kw, 'title') if kw else (bug_location[0] if isinstance(bug_location[0], dict) else None)
                            result_context['first_bug_id'] = best.get('id') if isinstance(best, dict) else (bug_location[0].get('id') if isinstance(bug_location[0], dict) else None)
                            print(f"[REACT-STREAM] 自动将 bug_location 添加到 context: {len(bug_location)} 条")
                    
                    # BadCase 列表 - 从多个可能的位置提取
                    if 'badcase_list' not in result_context:
                        badcase_analysis = obs_data.get('badcase_analysis', []) or observation.get('badcase_analysis', [])
                        if badcase_analysis and isinstance(badcase_analysis, list) and len(badcase_analysis) > 0:
                            # 提取为简化列表格式
                            badcase_list = []
                            for bc in badcase_analysis:
                                if not isinstance(bc, dict):
                                    continue
                                bc_id = bc.get('id')
                                if bc_id is None:
                                    continue
                                badcase_list.append({
                                    'id': bc_id,
                                    'title': bc.get('title', ''),
                                    'status': bc.get('status'),
                                    'plan_id': bc.get('plan_id')
                                })
                            
                            if badcase_list:
                                result_context['badcase_list'] = badcase_list
                                result_context['badcase_analysis'] = badcase_analysis
                                kw = result_context.get('_last_grep_keywords', '')
                                best = self._pick_best_match_from_list(badcase_list, kw, 'title') if kw else badcase_list[0]
                                result_context['first_badcase_id'] = best.get('id')
                                print(f"[REACT-STREAM] 自动将 badcase_list 添加到 context: {len(badcase_list)} 条")
                    
                    if 'testcase_list' not in result_context:
                        testcase_location = obs_data.get('testcase_location', []) or observation.get('testcase_location', [])
                        if testcase_location and isinstance(testcase_location, list) and len(testcase_location) > 0:
                            testcase_list = [{'id': tc.get('id'), 'title': tc.get('title'), 'plan_id': tc.get('current_plan_id')} for tc in testcase_location if isinstance(tc, dict) and tc.get('id') is not None]
                            if testcase_list:
                                result_context['testcase_list'] = testcase_list
                                kw = result_context.get('_last_grep_keywords', '')
                                best = self._pick_best_match_from_list(testcase_list, kw, 'title') if kw else testcase_list[0]
                                result_context['first_testcase_id'] = best.get('id')
                                print(f"[REACT-STREAM] 自动将 testcase_list 添加到 context: {len(testcase_list)} 条")
                    
                    print(f"[REACT-STREAM] Context 更新后: bug_list={len(result_context.get('bug_list', []))}条, badcase_list={len(result_context.get('badcase_list', []))}条, testcase_list={len(result_context.get('testcase_list', []))}条")
                
                if analysis.get('findings'):
                    findings.extend(analysis['findings'])
                    for f in analysis['findings']:
                        print(f"[REACT-DEBUG] Finding: {f}")  # 调试日志
                        yield {'event': 'finding', 'data': f}
                
                steps.append({
                    'todo': todo,
                    'decision': decision,
                    'observation': observation,
                    'analysis': analysis
                })
                
                # 动态添加批量修改任务（仅当没有已有的modify任务时）
                if decision['tool'] == 'grep':
                    # 支持 BadCase 和 Bug 批量修改
                    target_list = result_context.get('badcase_list', []) or result_context.get('bug_list', [])
                    target_type = 'badcase' if result_context.get('badcase_list') else 'bug'
                    
                    # 检测用户是否有批量修改意图
                    modify_keywords = ['修改', '改成', '更新', '设为', '状态', '关闭', 'closed', 'resolved']
                    has_modify_intent = any(kw in user_input for kw in modify_keywords)
                    
                    # 检查是否已有 modify 任务（避免重复添加）
                    existing_modify_count = sum(1 for t in todos if 'modify' in t.lower())
                    
                    if has_modify_intent and target_list and len(target_list) > 1 and existing_modify_count == 0:
                        print(f"[REACT-STREAM] 检测到批量修改意图，{len(target_list)} 个 {target_type}，使用批量模式")
                        
                        # 只添加一个批量修改任务（后端会处理全部）
                        ids_str = ', '.join([str(item['id']) for item in target_list])
                        new_todo = f"使用 modify 工具批量修改 {len(target_list)} 个 {target_type} (ID: {ids_str}) 的状态"
                        todos.append(new_todo)
                        print(f"[REACT-STREAM] 添加批量修改任务: {new_todo}")
                        
                        # 通知前端任务列表已更新
                        yield {'event': 'todos', 'data': todos}
                
                yield {'event': 'todo_end', 'index': i}

            # 在结束前，让LLM总结关键发现（人类可读）
            summarized_findings = []
            if findings:
                print(f"[REACT] 开始总结 {len(findings)} 条原始发现...")
                try:
                    summary_prompt = f"""你是一个技术助手，需要将下面的技术执行结果总结为简洁、人类可读的关键发现。

原始结果：
{chr(10).join(f'{i+1}. {f}' for i, f in enumerate(findings))}

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
                    
                    _sink_s = []
                    _sg = self._stream_llm_prompt_collect(summary_prompt, stream_kind="summary", full_text_sink=_sink_s)
                    _sit = _sg.__aiter__()
                    while True:
                        try:
                            _se = await _sit.__anext__()
                            yield _se
                        except StopAsyncIteration:
                            break
                    summary_response = _sink_s[0] if _sink_s else ""
                    # 按行分割，过滤空行
                    summarized_findings = [line.strip() for line in summary_response.strip().split('\n') if line.strip()]
                    print(f"[REACT] LLM总结完成: {len(summarized_findings)} 条")
                    # 与下一段「统一总结」流式区分，避免前端同一段草稿串联两段模型输出
                    yield {'event': 'summary_stream_reset'}
                except Exception as e:
                    print(f"[REACT] LLM总结失败: {e}，使用原始数据")
                    summarized_findings = findings[:5]  # 降级：只显示前5条
            
            # 使用总结后的findings
            final_findings = summarized_findings if summarized_findings else findings
            # 兜底：若关键发现仍为空，从各步的 observation 中提取 summary，避免前端「关键发现」无内容
            if not final_findings and steps:
                for s in steps:
                    obs = s.get('observation') or {}
                    if not isinstance(obs, dict):
                        continue
                    summary = obs.get('summary')
                    if not summary and isinstance(obs.get('data'), dict):
                        summary = (obs['data'] or {}).get('summary')
                    if summary and isinstance(summary, str) and summary.strip():
                        summary = summary.strip()
                        if summary not in final_findings:
                            final_findings.append(summary)
            
            duration = time.time() - start_time
            # 大模型统一总结：一段话概括关键发现+执行统计（Cursor 式，供前端「耗时 Xs」下打字机展示）
            summary_text = ""
            try:
                summary_prompt = f"""将以下执行结果总结为一段话，2-4 句即可，像 Cursor 的 Thought 总结那样简洁自然。

关键发现/执行结果：
{chr(10).join(f"- {f}" for f in (final_findings[:8] or ["无"]))}

执行统计：完成 {len(steps)} 步，耗时 {duration:.2f}s。

要求：纯中文、无 emoji、无列表符号，直接一段话。"""
                _sink_u = []
                _ug = self._stream_llm_prompt_collect(summary_prompt, stream_kind="summary", full_text_sink=_sink_u)
                _uit = _ug.__aiter__()
                while True:
                    try:
                        _ue = await _uit.__anext__()
                        yield _ue
                    except StopAsyncIteration:
                        break
                summary_text = (_sink_u[0] if _sink_u else "").strip()
                if summary_text:
                    print(f"[REACT] 统一总结: {summary_text[:80]}...")
            except Exception as e:
                print(f"[REACT] 统一总结失败: {e}")
            
            yield {
                'event': 'done',
                'findings': final_findings,
                'steps_count': len(steps),
                'duration': duration,
                'thinking_time': thinking_time,
                'summary': summary_text
            }

        except Exception as e:
            yield {'event': 'error', 'message': str(e)}

    async def run(self, user_input: str, project_id: int = None) -> Dict[str, Any]:
        """
        极简主循环 - 三步：THINK / ACT-LOOP / RESULT
        """
        print(f"\n[REACT] ReAct Loop Start")
        print(f"[REACT] Input: {user_input[:60]}...\n")
        self.project_id = project_id  # 保存项目ID
        start_time = time.time()
        
        result = {
            'status': 'success',
            'steps': [],
            'context': {},
            'findings': [],
            'duration': 0,
            'error': None
        }
        
        try:
            # ===== STEP 1: THINK =====
            print(f"[REACT] STEP 1: THINK - Claude Prompt")
            
            tools_info = format_tools_for_prompt(self.tools)
            prompt = ReactPromptTemplates.think_prompt(
                user_input,
                tools_info,
                result['context'],
                []
            )
            
            response = await self._collect_llm_text(prompt)
            # 统一使用健壮版解析
            todos = robust_parse_todos(response)
            
            if not todos:
                result['error'] = 'LLM 无法生成 Todo'
                result['status'] = 'error'
                return result
            
            print(f"[REACT]   Generated {len(todos)} Todos\n")
            
            # ===== MAIN LOOP: ACT =====
            print(f"[REACT] MAIN LOOP: Executing Todos\n")
            
            for i, todo in enumerate(todos):
                print(f"[REACT] Todo {i+1}/{len(todos)}: {todo}")
                
                # 决策（ACT）
                decision_prompt = ReactPromptTemplates.decide_prompt(
                    todo,
                    user_input,
                    tools_info,
                    result['context']
                )
                
                decision_response = await self._collect_llm_text(decision_prompt)
                decision = parse_xml_decision(decision_response)
                
                if not decision['execute']:
                    print(f"[REACT]   Skip")
                    continue
                
                skip_modify_exec = False
                if decision.get('tool') == 'modify':
                    decision, _ = await self._enrich_modify_decision_for_main_loop(
                        decision, todo, user_input, result['context'], project_id, step_index=i
                    )
                    if not self._modify_params_ready(decision.get('params')):
                        decision, _ = await self._last_resort_modify_fill(
                            decision, todo, user_input, result['context'], project_id, step_index=i
                        )
                    if not self._modify_params_ready(decision.get('params')):
                        nq = (user_input or todo or '').strip()
                        if nq:
                            decision.setdefault('params', {})['natural_query'] = nq[:2000]
                    if not self._modify_params_ready(decision.get('params')):
                        skip_modify_exec = True
                        print("[REACT] stability_gate: modify 参数未就绪，跳过执行")

                # 执行工具
                print(f"[REACT]   Tool: {decision['tool']}")
                if skip_modify_exec:
                    observation = {
                        'success': False,
                        'skipped': True,
                        'stability_gate': 'modify_params_incomplete',
                        'error': '缺少必要参数：modify 需要 target_id（或 natural_query）与非空 modifications。',
                        'message': 'modify 未执行（参数未就绪）',
                    }
                else:
                    observation = await self._execute_tool(decision)

                if (
                    decision.get('tool') == 'modify'
                    and not observation.get('success')
                    and not observation.get('skipped')
                ):
                    observation, _ = await self._recover_modify_after_failure(
                        decision,
                        observation,
                        todo,
                        user_input,
                        result['context'],
                        project_id,
                    )

                # 自我修正：如果执行失败，尝试自动修正
                if not observation.get('success') and not observation.get('skipped'):
                    print(f"[REACT]   Execution failed, retrying with correction")
                    
                    tools_info = format_tools_for_prompt(self.tools)
                    observation = await self.correction_engine.correct_and_retry(
                        todo=todo,
                        action=decision,
                        observation=observation,
                        context=result['context'],
                        available_tools=tools_info,
                        execute_fn=self._execute_tool
                    )
                
                # 分析结果（OBSERVE） + 自我修正反馈
                analyze_prompt = ReactPromptTemplates.observe_prompt(
                    todo,
                    decision,
                    observation,
                    result['context']
                )
                
                analyze_response = await self._collect_llm_text(analyze_prompt)
                analysis = parse_xml_findings(analyze_response)
                
                # 记录
                result['steps'].append({
                    'todo': todo,
                    'decision': decision,
                    'observation': observation,
                    'analysis': analysis
                })
                
                # 更新上下文
                result['context'].update(analysis.get('context_update', {}))
                
                # 提取发现
                if analysis.get('findings'):
                    result['findings'].extend(analysis['findings'])
                    for f in analysis['findings']:
                        print(f"[REACT]   Found: {f}")
        
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            print(f"[REACT] Error: {str(e)}")
        
        result['duration'] = time.time() - start_time
        print(f"\n[REACT] Done | Steps: {len(result['steps'])} | Findings: {len(result['findings'])} | Duration: {result['duration']:.2f}s\n")
        return result
    
    async def _optimize_with_skill_tool(self, decision: Dict[str, Any], user_input: str, context: Dict[str, Any], project_id: int = None) -> Dict[str, Any]:
        """
        使用Skill工具优化决策
        当检测到复杂任务时，建议使用skill_executor工具
        """
        tool_name = decision['tool']
        
        # 识别需要Skill处理的复杂任务
        complex_task_keywords = [
            '修改缺陷', '创建缺陷', '查询缺陷',
            '修改badcase', '创建badcase', '查询badcase',
            '批量处理', '多步骤操作', '完整流程'
        ]
        
        #检查是否为复杂任务
        is_complex_task = any(keyword in user_input.lower() or keyword in decision.get('reason', '').lower() 
                            for keyword in complex_task_keywords)
        
        if is_complex_task and tool_name in ['grep', 'modify', 'create']:
            print(f"[REACT-STREAM] 🎯检测到复杂任务，建议使用Skill工具优化")
            
            # 重定向到skill_executor工具
            return {
                'execute': True,
                'tool': 'skill_executor',
                'params': {
                    'user_input': user_input,
                    'context': context,
                    'project_id': project_id
                },
                'reason': f'检测到复杂任务"{user_input}"，使用Skill工具进行智能处理'
            }
        
        # Text2SQL优化：数据库查询优先使用自然语言
        if tool_name == 'database_query':
            natural_query = self._extract_natural_query(user_input, user_input)
            if natural_query and self.text2sql_tool is None:
                self.text2sql_tool = get_text2sql_tool("instance/badcase_doctor.db")
            if natural_query and self.text2sql_tool:
                print(f"[REACT-STREAM]📊优先使用 Text2SQL执行: {natural_query}")
                decision['params']['natural_query'] = natural_query
        
        return decision
    
    def _generate_todos_from_skill_workflow(self, skill: Skill, user_input: str) -> List[str]:
        """根据技能工作流生成 Todo列表（按 step 排序，与 fallback_workflow_tools 一致）"""
        todos = []
        wf = sorted(getattr(skill, 'workflow', []) or [], key=lambda s: getattr(s, 'step', 0))
        for workflow_step in wf:
            # 生成人性化的 Todo描述
            if workflow_step.description and workflow_step.description != workflow_step.tool:
                todo_desc = workflow_step.description
            else:
                # 使用默认描述
                todo_desc = f"执行 {workflow_step.tool} 操作"
            
            todos.append(todo_desc)
        
        return todos
    
    async def _execute_tool_with_text2sql(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """使用 Text2SQL执行数据库工具"""
        if tool_name == 'database_query' and self.text2sql_tool is None:
            self.text2sql_tool = get_text2sql_tool("instance/badcase_doctor.db")
        if tool_name == 'database_query' and self.text2sql_tool:
            natural_query = params.get('natural_query')
            if natural_query:
                print(f"[REACT] Text2SQL执行: {natural_query}")
                return self.text2sql_tool.query(natural_query, params)
        
        #回到传统工具执行
        return await self._execute_tool(tool_name, params)
    
    def _extract_natural_query(self, todo: str, user_input: str) -> str:
        """从 Todo中提取自然语言查询"""
        # 关键词匹配
        query_keywords = ['查询', '搜索', '查找', '显示', '列出', '统计']
        
        for keyword in query_keywords:
            if keyword in todo or keyword in user_input:
                #构造自然语言查询
                if '登录' in todo or '登录' in user_input:
                    return "查询登录相关的缺陷"
                elif '未解决' in todo or '未解决' in user_input:
                    return "查询所有未解决的缺陷"
                elif '统计' in todo or '统计' in user_input:
                    return "统计缺陷数量"
                else:
                    return user_input  # 使用原始用户输入
        
        return ""

    def _rerank_score(self, item: Dict, keywords: str, key_title: str = 'title') -> float:
        """
        Rerank 打分：分高的优先。关键词命中数×10 + 整句命中加 50，便于选最相关的一条。
        """
        if not keywords or not keywords.strip():
            return 1.0
        import re
        title = (item.get(key_title) or '').strip()
        text = re.sub(r'[和与]', ' ', keywords.strip())
        parts = [p.strip() for p in text.split() if p.strip()]
        stop = {'的', '为', '与', '和', '或', '及'}
        terms = [p for p in parts if p not in stop and (len(p) > 1 or p not in stop)]
        if not terms:
            return 50.0 if keywords.strip() in title else 0.0
        score = sum(10 for t in terms if t in title)
        if keywords.strip() in title:
            score += 50
        return float(score)

    def _rerank_and_pick(self, items: List[Dict], keywords: str, key_title: str = 'title', top_k: int = 1) -> List[Dict]:
        """
        Rerank 后取分高的：按 _rerank_score 排序，返回 top_k 条（分高的就都可以，默认取 1 条）。
        """
        if not items:
            return []
        if not keywords or not keywords.strip():
            return items[:top_k]
        scored = [(item, self._rerank_score(item, keywords, key_title)) for item in items]
        scored.sort(key=lambda x: -x[1])
        # 同分都算「分高的」：取所有与最高分相同的项，再截 top_k
        if not scored:
            return []
        best_score = scored[0][1]
        top = [item for item, s in scored if s == best_score][:top_k]
        return top if top else [scored[0][0]]

    def _merge_grep_observation_into_context(
        self,
        observation: Dict[str, Any],
        params: Dict[str, Any],
        result_context: Dict[str, Any],
    ) -> None:
        """将 grep 成功的 observation 合并进 result_context，供后续 modify 使用。"""
        if not observation or not observation.get('success'):
            return
        grep_data = observation.get('data', {}) or {}
        badcase_list = grep_data.get('badcase_analysis', [])
        bug_list = grep_data.get('bug_location', [])
        testcase_list = grep_data.get('testcase_location', [])
        kw = (params.get('keywords') or result_context.get('_last_grep_keywords') or '')
        result_context['_last_grep_keywords'] = kw or params.get('keywords') or ''

        def first_id(lst, kws):
            if not lst:
                return None
            picked = self._rerank_and_pick(lst, kws, 'title', 1)
            return picked[0].get('id') if picked else lst[0].get('id')

        result_context['grep_result'] = {
            'first_badcase_id': first_id(badcase_list, kw),
            'first_bug_id': first_id(bug_list, kw),
            'first_testcase_id': first_id(testcase_list, kw),
            'badcase_list': badcase_list,
            'bug_list': bug_list,
            'testcase_list': testcase_list,
        }
        result_context['badcase_list'] = badcase_list
        result_context['bug_list'] = bug_list
        result_context['testcase_list'] = testcase_list
        print(
            f"[REACT-STREAM] grep 结果: {len(badcase_list)} badcase, {len(bug_list)} bug, {len(testcase_list)} testcase"
        )

    async def _enrich_modify_decision_for_main_loop(
        self,
        decision: Dict[str, Any],
        todo: str,
        user_input: str,
        result_context: Dict[str, Any],
        project_id: Optional[int],
        step_index: int,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        主循环（未走技能匹配分支）在解析 LLM 的 decide 结果后，补齐 modify 的 target_id / modifications。

        **可靠性口径**：真正执行 modify_tool 以前，以本函数补全/合并后的 params 为准；
        parse_xml_decision 仅提供 tool 选择与「有则更好」的初值，模型常省略参数，属预期行为。

        与技能分支内逻辑对齐：grep 上下文 → 必要时补救 grep → explore_record + LLM 提取 modifications
        → 正则兜底 → _infer_modify_params 合并。
        """
        events: List[Dict[str, Any]] = []
        params = decision.setdefault('params', {})
        if not isinstance(params, dict):
            params = {}
            decision['params'] = params
        if project_id is not None and 'project_id' not in params:
            params['project_id'] = project_id
        if 'userId' not in params:
            params['userId'] = 'system_agent'
        params.setdefault('confirm', False)

        grep_result = result_context.get('grep_result', {})
        target_type = params.get('target') or self._infer_modify_target(user_input, todo)
        params['target'] = target_type

        target_id = params.get('target_id')
        if target_id is not None:
            try:
                target_id = int(target_id)
                params['target_id'] = target_id
            except (TypeError, ValueError):
                params.pop('target_id', None)
                target_id = None

        if not target_id:
            if target_type == 'bug':
                target_id = grep_result.get('first_bug_id') or result_context.get('first_bug_id')
            elif target_type == 'testcase':
                target_id = grep_result.get('first_testcase_id') or result_context.get('first_testcase_id')
            else:
                target_id = grep_result.get('first_badcase_id') or result_context.get('first_badcase_id')
            if target_id is not None:
                try:
                    params['target_id'] = int(target_id)
                    target_id = params['target_id']
                except (TypeError, ValueError):
                    target_id = None

        if not params.get('target_id'):
            tid_m = self._try_target_id_from_merged_lists(
                result_context, target_type, user_input, todo
            )
            if tid_m is not None:
                params['target_id'] = tid_m
                print(f"[REACT-STREAM] enrich 从合并列表注入 target_id={tid_m} ({target_type})")

        if not params.get('target_id'):
            print(
                f"[REACT-STREAM] ⚠️ 主循环 modify：无法从上下文获取 target_id (target={target_type})，尝试补救 grep…"
            )
            kw = self._extract_title_keywords_for_grep(user_input, todo) or ''
            gparams: Dict[str, Any] = {
                'project_id': project_id,
                'keywords': kw,
                'mode': 'locate',
                'target': target_type if target_type in ('bug', 'badcase', 'testcase') else 'all',
                'userId': 'system_agent',
            }
            if self.plan_id is not None and gparams.get('target') != 'all':
                gparams['plan_id'] = self.plan_id
            if gparams.get('target') == 'all':
                gparams.pop('plan_id', None)
            events.append(
                {
                    'event': 'executing',
                    'tool': 'grep',
                    'reason': f'Todo步骤 {step_index + 1}',
                    'index': step_index,
                    'message': '正在补充定位记录（用于修改）…',
                }
            )
            grep_obs = await self._execute_tool({'execute': True, 'tool': 'grep', 'params': gparams})
            if grep_obs.get('success'):
                self._merge_grep_observation_into_context(grep_obs, gparams, result_context)
                grep_result = result_context.get('grep_result', {})
                if target_type == 'bug':
                    target_id = grep_result.get('first_bug_id')
                elif target_type == 'testcase':
                    target_id = grep_result.get('first_testcase_id')
                else:
                    target_id = grep_result.get('first_badcase_id')
                if target_id is not None:
                    try:
                        params['target_id'] = int(target_id)
                        print(f"[REACT-STREAM] 主循环补救 grep 后 target_id={params['target_id']}")
                    except (TypeError, ValueError):
                        pass
            if not params.get('target_id'):
                tid2 = self._try_target_id_from_merged_lists(
                    result_context, target_type, user_input, todo
                )
                if tid2 is not None:
                    params['target_id'] = tid2
                    print(f"[REACT-STREAM] enrich 补救 grep 后从列表注入 target_id={tid2}")

        tid = params.get('target_id')
        mods = params.get('modifications')
        _proj_for_explore = params.get('project_id') or self.project_id
        if tid and (not mods or (isinstance(mods, dict) and len(mods) == 0)):
            modify_tool = self.tools.get('modify')
            if modify_tool and getattr(modify_tool, 'explore_record', None) and _proj_for_explore is not None:
                try:
                    loop = asyncio.get_event_loop()
                    _eid = int(tid)
                    _epid = int(_proj_for_explore)
                    exploration = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._tool_executor,
                            lambda: modify_tool.explore_record(target_type, _eid, _epid),
                        ),
                        timeout=15,
                    )
                    if exploration and exploration.get('current_record'):
                        with self._llm_no_thinking():
                            params['modifications'] = await self._extract_modifications_with_llm(
                                todo, user_input, exploration=exploration
                            )
                        if not params.get('modifications') and user_input:
                            params['modifications'] = self._extract_modifications_with_regex(user_input)
                except Exception as e:
                    print(f"[REACT-STREAM] 主循环 explore_record 失败: {e}")
                    if not params.get('modifications'):
                        with self._llm_no_thinking():
                            params['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                        if not params.get('modifications'):
                            params['modifications'] = self._extract_modifications_with_regex(user_input)
            elif not params.get('modifications'):
                with self._llm_no_thinking():
                    params['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
                if not params.get('modifications'):
                    params['modifications'] = self._extract_modifications_with_regex(user_input)

        if (not params.get('target_id')) or (not params.get('modifications')):
            infer = self._infer_modify_params(todo, result_context)
            if infer.get('execute') and isinstance(infer.get('params'), dict):
                ip = infer['params']
                for k in ('target_id', 'target', 'modifications', 'project_id', 'confirm'):
                    if k not in params or params.get(k) in (None, '', {}):
                        v = ip.get(k)
                        if v is not None and v != '' and v != {}:
                            params[k] = v
                print(f"[REACT-STREAM] 主循环 modify 已合并 _infer_modify_params 兜底: keys={list(params.keys())}")

        return decision, events

    @staticmethod
    def _modify_params_ready(params: Optional[Dict[str, Any]]) -> bool:
        """
        modify 执行前需：非空 modifications，且满足其一：
        - 已有 target_id；或
        - 提供 natural_query（交给 modify_tool 用 Text2SQL/ORM 解析 id）
        """
        if not params or not isinstance(params, dict):
            return False
        m = params.get('modifications')
        if not m or not isinstance(m, dict) or len(m) == 0:
            return False
        if params.get('target_id') not in (None, ''):
            return True
        nq = (params.get('natural_query') or '').strip()
        return bool(nq)

    async def _last_resort_modify_fill(
        self,
        decision: Dict[str, Any],
        todo: str,
        user_input: str,
        result_context: Dict[str, Any],
        project_id: Optional[int],
        step_index: int,
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        最后手段：全库/宽关键词 grep → 合并列表 → 按 bug/testcase/badcase 顺序取 id → 正则+LLM 补 modifications。
        用于主循环 enrich 与单条注入后仍缺参的情况。
        """
        events: List[Dict[str, Any]] = []
        params = decision.setdefault('params', {})
        if not isinstance(params, dict):
            params = {}
            decision['params'] = params
        kw = (self._extract_title_keywords_for_grep(user_input, todo) or '').strip()
        if not kw and user_input:
            kw = (user_input[:200] or '').strip()
        if not kw and todo:
            kw = (todo[:200] or '').strip()
        if not kw:
            kw = ' '

        gparams: Dict[str, Any] = {
            'project_id': project_id,
            'keywords': kw,
            'mode': 'locate',
            'target': 'all',
            'userId': 'system_agent',
        }
        events.append(
            {
                'event': 'executing',
                'tool': 'grep',
                'reason': f'Todo步骤 {step_index + 1}',
                'index': step_index,
                'message': '最后手段：全库检索以定位修改目标…',
            }
        )
        grep_obs = await self._execute_tool({'execute': True, 'tool': 'grep', 'params': gparams})
        if grep_obs.get('success'):
            self._merge_grep_observation_into_context(grep_obs, gparams, result_context)
            for tt in ('bug', 'testcase', 'badcase'):
                tid = self._try_target_id_from_merged_lists(
                    result_context, tt, user_input, todo
                )
                if tid is not None:
                    params['target_id'] = tid
                    params['target'] = tt
                    print(f"[REACT-STREAM] last_resort 从列表选定 target_id={tid}, target={tt}")
                    break
        if not params.get('modifications') or (
            isinstance(params.get('modifications'), dict) and len(params.get('modifications')) == 0
        ):
            params['modifications'] = self._extract_modifications_with_regex(user_input or '')
            if not params.get('modifications'):
                with self._llm_no_thinking():
                    params['modifications'] = await self._extract_modifications_with_llm(todo, user_input)
            if not params.get('modifications'):
                params['modifications'] = self._extract_modifications_with_regex(todo or '')
        return decision, events

    async def _recover_modify_after_failure(
        self,
        decision: Dict[str, Any],
        observation: Dict[str, Any],
        todo: str,
        user_input: str,
        result_context: Dict[str, Any],
        project_id: Optional[int],
    ) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """
        modify 失败后的结构化纠错（在 LLM correct_and_retry 之前）：
        缺参 / need_grep_first 时：全库 grep + 列表 + 补 modifications → 再执行一次 modify。
        返回 (observation, 需在主循环中 yield 的事件列表)。
        """
        empty_ev: List[Dict[str, Any]] = []
        if observation.get('success'):
            return observation, empty_ev
        if decision.get('tool') != 'modify':
            return observation, empty_ev
        if observation.get('corrected'):
            return observation, empty_ev
        err = str(observation.get('error') or '')
        need = observation.get('need_grep_first') or '缺少必要参数' in err or 'target_id' in err.lower()
        if not need:
            return observation, empty_ev
        if self._modify_params_ready(decision.get('params')):
            # 参数已齐仍失败，交给上层修正
            return observation, empty_ev
        print(f"[REACT-STREAM] 🛠 结构化纠错：modify 失败后尝试 grep+补参并重试")
        try:
            decision2 = {
                'execute': True,
                'tool': 'modify',
                'params': dict(decision.get('params') or {}),
            }
            decision2, ev = await self._last_resort_modify_fill(
                decision2,
                todo,
                user_input,
                result_context,
                project_id,
                step_index=-1,
            )
            if not self._modify_params_ready(decision2.get('params')):
                nq = (user_input or todo or '').strip()
                if nq:
                    decision2.setdefault('params', {})['natural_query'] = nq[:2000]
            if not self._modify_params_ready(decision2.get('params')):
                return observation, ev
            retry_obs = await self._execute_tool(decision2)
            if retry_obs.get('success'):
                retry_obs['recovered'] = True
                retry_obs['recovery'] = 'structured_grep_after_failure'
            return retry_obs, ev
        except Exception as e:
            print(f"[REACT-STREAM] 结构化纠错异常: {e}")
            return observation, empty_ev

    def _try_target_id_from_merged_lists(
        self,
        result_context: Dict[str, Any],
        target_type: str,
        user_input: str,
        todo: str,
    ) -> Optional[int]:
        """
        grep_result.first_bug_id 等可能为空，但 _merge_grep_observation_into_context 已写入
        bug_list/badcase_list/testcase_list 时，从列表 rerank 取一条 id。
        """
        kw = self._extract_title_keywords_for_grep(user_input, todo) or ''
        if target_type == 'bug':
            lst = result_context.get('bug_list') or []
        elif target_type == 'testcase':
            lst = result_context.get('testcase_list') or []
        else:
            lst = result_context.get('badcase_list') or []
        if not lst:
            return None
        pick = self._pick_best_match_from_list(lst, kw, 'title') if kw else lst[0]
        if not isinstance(pick, dict):
            return None
        tid = pick.get('id')
        if tid is None:
            return None
        try:
            return int(tid)
        except (TypeError, ValueError):
            return None

    def _pick_best_match_from_list(self, items: List[Dict], keywords: str, key_title: str = 'title') -> Dict:
        """Rerank 后取分最高的那一条（兼容旧调用）。"""
        picked = self._rerank_and_pick(items, keywords, key_title, top_k=1)
        return picked[0] if picked else {}

    def _infer_modify_target(self, user_input: str, todo: str) -> str:
        """
        从用户输入/todo 推断 modify 的 target：用户说「修改bug」则用 bug，避免误改 BadCase。
        """
        text = ((user_input or '') + ' ' + (todo or '')).lower()
        if not text.strip():
            return 'badcase'
        if 'bug' in text and 'badcase' not in text and 'bad case' not in text:
            return 'bug'
        if '测试用例' in text or 'testcase' in text or 'test_case' in text:
            return 'testcase'
        if 'badcase' in text or 'bad case' in text:
            return 'badcase'
        return 'badcase'

    def _extract_title_keywords_for_grep(self, user_input: str, todo: str) -> str:
        """
        从用户输入或 todo 中提取要修改的 BadCase/Bug 标题，用于 grep 的 keywords 参数。
        例如：「修改雪碧和七喜的正确答案为理解正确」 -> 「雪碧和七喜」
        """
        import re
        text = (user_input or '') + ' ' + (todo or '')
        if not text.strip():
            return ''
        # 修改/把/将 XXX 的 … -> XXX（非贪婪，取到第一个「的」为止）
        for pattern in [
            r'修改\s*(.+?)\s*的',
            r'把\s*(.+?)\s*的',
            r'将\s*(.+?)\s*的',
            r'标题[是为]\s*([^，。\n]+)',
        ]:
            m = re.search(pattern, text)
            if m:
                kw = m.group(1).strip()
                if kw and len(kw) <= 50:  # 避免整句当关键词
                    return kw
        return ''

    def _infer_create_target(self, user_input: str, todo: str) -> str:
        text = f"{todo or ''} {user_input or ''}"
        text_lower = text.lower()
        if 'testcase' in text_lower or 'test_case' in text_lower or '测试用例' in text:
            return 'testcase'
        if 'plan' in text_lower or '计划' in text or '迭代' in text:
            return 'plan'
        if 'bug' in text_lower or '缺陷' in text:
            return 'bug'
        if 'badcase' in text_lower or 'bad case' in text_lower or 'BadCase' in text:
            return 'badcase'
        return 'bug'

    def _extract_create_title(self, user_input: str, todo: str) -> str:
        import re

        for text in (todo or '', user_input or ''):
            if not text:
                continue
            patterns = [
                r'标题\s*[=:：]\s*[\"“”‘’「]?([^，。,；;」\"“”‘’]+)',
                r'标题(?:叫|是|为)\s*[\"“”‘’「]?([^，。,；;」\"“”‘’]+)',
                r'叫做\s*[\"“”‘’「]?([^，。,；;」\"“”‘’]+)',
                r'叫\s*[\"“”‘’「]?([^，。,；;」\"“”‘’]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    title = (match.group(1) or '').strip()
                    if title:
                        return title
        return ''

    def _infer_modify_params(self, todo: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        从 Todo 和 Context 中推断 modify工具参数
        当 LLM 返回空响应时作为兜底逻辑
        优先使用技能匹配，回退到标准逻辑
        """
        import re
        
        result = {
            'execute': False,
            'tool': '',
            'params': {},
            'reason': ''
        }
        
        # 检查是否包含 modify 关键词
        if 'modify' not in todo.lower():
            return result
        
        #检查是否包含 modify 关键词
        if 'modify' not in todo.lower():
            return result
        
        #先尝匹配技能
        matched_skill, score = get_skill_integration().match_skill(todo, context)
        
        if matched_skill and score >= 0.3:
            #使用技能工作流参数
            for workflow_step in matched_skill.workflow:
                if workflow_step.tool == 'modify':
                    # 从技能配置中提取参数模板
                    tool_def = next((t for t in matched_skill.tools if t.name == 'modify'), None)
                    if tool_def:
                        params = tool_def.params.copy()
                        # 解析参数变量
                        for key, value in list(params.items()):  # 使用 list 避免迭代时修改
                            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                                var_name = value[2:-1]  #去除${}
                                
                                # 支持嵌套变量：grep_result.first_bug_id
                                resolved_value = None
                                
                                if '.' in var_name:
                                    # 嵌套变量解析
                                    parts = var_name.split('.')
                                    base_var = parts[0]  # grep_result
                                    field_path = parts[1:]  # ['first_bug_id']
                                    
                                    # 从 context 中获取基础变量
                                    base_value = context.get(base_var)
                                    if base_value and isinstance(base_value, dict):
                                        # 递归获取嵌套字段
                                        current = base_value
                                        for field in field_path:
                                            if isinstance(current, dict) and field in current:
                                                current = current[field]
                                            else:
                                                current = None
                                                break
                                        resolved_value = current
                                else:
                                    # 简单变量解析
                                    if var_name == 'user_modifications':
                                        resolved_value = self._extract_modifications_from_todo(todo)
                                    elif var_name == 'target_id':
                                        resolved_value = (context.get('first_bug_id') or context.get('first_badcase_id') or context.get('first_testcase_id'))
                                    elif var_name == 'project_id':
                                        resolved_value = context.get('project_id', '1')
                                    elif var_name in context:
                                        resolved_value = context[var_name]
                                
                                # 更新参数或删除无法解析的变量
                                if resolved_value is not None:
                                    params[key] = resolved_value
                                else:
                                    # 无法解析，删除该参数或跳过
                                    print(f"[REACT-STREAM] ⚠️ 无法解析变量: {var_name}")
                                    # 如果是 target_id，尝试从其他来源获取
                                    if key == 'target_id':
                                        target_id = (context.get('first_bug_id') or 
                                                    context.get('first_badcase_id') or 
                                                    context.get('first_testcase_id') or
                                                    context.get('target_id'))
                                        if target_id:
                                            params[key] = target_id
                                        else:
                                            # 没有有效的 target_id，不执行
                                            print(f"[REACT-STREAM] ❌ 缺少有效的 target_id，跳过执行")
                                            return result
                                    else:
                                        del params[key]  # 删除无法解析的参数
                        
                        # 检查必要参数是否完整
                        if 'target_id' not in params or params.get('target_id') is None:
                            print(f"[REACT-STREAM] ❌ 缺少 target_id，无法执行 modify")
                            return result
                        
                        result = {
                            'execute': True,
                            'tool': 'modify',
                            'params': params,
                            'reason': f'基于匹配技能 {matched_skill.name} 的工作流参数'
                        }
                        return result
        
        # 如果技能匹配失败，回到标准流程（含 testcase）
        bug_list = context.get('bug_list', [])
        badcase_list = context.get('badcase_list', [])
        testcase_list = context.get('testcase_list', [])
        if not bug_list and 'bug_location' in context:
            bug_list = context.get('bug_location', [])
        if not badcase_list and 'badcase_analysis' in context:
            badcase_analysis = context.get('badcase_analysis', [])
            if badcase_analysis and isinstance(badcase_analysis, list):
                badcase_list = badcase_analysis
        if not testcase_list and 'testcase_location' in context:
            testcase_list = context.get('testcase_location', [])
        target_list = bug_list or badcase_list or testcase_list
        target_type = 'bug' if bug_list else ('badcase' if badcase_list else ('testcase' if testcase_list else None))
        
        if not target_list or not isinstance(target_list, list) or len(target_list) == 0:
            print(f"[REACT-STREAM] 无法从 context 中获取有效的 bug_list 或 badcase_list")
            print(f"[REACT-STREAM] context keys: {list(context.keys())}")
            return result
        
        # 获取第一个目标的 ID
        first_item = target_list[0]
        if not isinstance(first_item, dict):
            print(f"[REACT-STREAM] target_list[0] 不是字典: {type(first_item)}")
            return result
        
        target_id = first_item.get('id')
        if target_id is None:
            print(f"[REACT-STREAM] 无法从 target_list 中提取 id")
            return result
        
        # 从 Todo 中提取要修改的字段
        # 例如：修改Bug的状态字段为'resolved' -> modifications: {status: 'resolved'}
        modifications = {}
        
        # 匹配状态修改
        status_match = re.search(r"状态.*?['\"](\w+)['\"]|status.*?['\"](\w+)['\"]|状态.*?(resolved|已解决|closed|关闭)", todo, re.IGNORECASE)
        if status_match:
            status_value = status_match.group(1) or status_match.group(2) or status_match.group(3)
            modifications['status'] = status_value
        
        # 匹配优先级修改
        priority_match = re.search(r"优先级.*?['\"](\w+)['\"]|priority.*?['\"](\w+)['\"]", todo, re.IGNORECASE)
        if priority_match:
            modifications['priority'] = priority_match.group(1)
        
        # 如果没有提取到修改内容，默认修改状态
        if not modifications:
            modifications['status'] = 'resolved'
        
        # 状态值标准化（确保使用英文）
        status_normalize = {
            '关闭': 'closed', '已关闭': 'closed', 'close': 'closed',
            '解决': 'resolved', '已解决': 'resolved',
            '重新打开': 'reopened', '重开': 'reopened', 'reopen': 'reopened',
            '新建': 'new', '新': 'new',
            '待处理': 'pending',
            '搁置': 'hold',
        }
        if 'status' in modifications:
            modifications['status'] = status_normalize.get(modifications['status'].lower(), modifications['status'])
        
        # 获取 project_id
        project_id = context.get('project_id') or self.project_id or '1'
        
        result = {
            'execute': True,
            'tool': 'modify',
            'params': {
                'target': target_type or 'badcase',  # 使用推断的目标类型
                'target_id': target_id,
                'modifications': modifications,
                'project_id': project_id,
                'confirm': False  # 默认使用沙箱预览模式，需要用户确认后才执行
            },
            'reason': f'基于 todo内容和 context推断的 modify 参数，target={target_type}, target_id={target_id}'
        }
        
        print(f"[REACT-STREAM] _infer_modify_params 返回: {result}")
        return result
    
    def _resolve_skill_params(self, param_template: Dict[str, Any], context: Dict[str, Any], user_input: str, project_id: int = None) -> Dict[str, Any]:
        """
        解析技能参数模板中的变量
        
        支持：
        - ${user_keywords}: 从用户输入提取关键词
        - ${user_modifications}: 从用户输入提取修改内容
        - ${grep_result.first_badcase_id}: 从上下文获取嵌套值
        - ${project_id}: 项目ID
        """
        import re
        params = {}
        
        for key, value in param_template.items():
            if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
                var_name = value[2:-1]  # 去除 ${}
                
                # 特殊变量处理
                if var_name == 'user_keywords':
                    # 从用户输入提取关键词
                    # 优先匹配“标题为XXX”或“标题是XXX”的模式
                    title_match = re.search(r'标题[是为]([^，。,]+)', user_input)
                    if title_match:
                        keywords = title_match.group(1).strip()
                        print(f"[REACT] 从用户输入提取标题关键词: '{keywords}'")
                    else:
                        # 回退：去除常见动词
                        keywords = re.sub(r'(修改|更新|调整|所有|状态|改成|设为|标题|为|是)', '', user_input).strip()
                    params[key] = keywords if keywords else ''
                
                elif var_name == 'user_modifications':
                    # 从用户输入提取修改内容
                    modifications = self._extract_modifications_from_todo(user_input)
                    params[key] = modifications if modifications else {}
                
                elif var_name == 'project_id':
                    params[key] = project_id or context.get('project_id', '1')
                
                elif '.' in var_name:
                    # 嵌套变量解析：grep_result.first_badcase_id
                    parts = var_name.split('.')
                    base_var = parts[0]
                    field_path = parts[1:]
                    
                    base_value = context.get(base_var)
                    if base_value:
                        current = base_value
                        for field in field_path:
                            if isinstance(current, dict) and field in current:
                                current = current[field]
                            else:
                                current = None
                                break
                        params[key] = current
                    else:
                        params[key] = None
                
                else:
                    # 简单变量
                    params[key] = context.get(var_name)
            
            else:
                # 非变量，直接使用
                params[key] = value
        
        return params
    
    def _extract_modifications_from_todo(self, todo: str) -> Dict[str, Any]:
        """
        从 todo描述中提取修改内容
        """
        import re
        modifications = {}
        
        # 中文状态映射
        status_map = {
            '重新打开': 'reopened', '重开': 'reopened', 'reopen': 'reopened',
            '已关闭': 'closed', '关闭': 'closed', 'close': 'closed',
            '新建': 'new', '新': 'new',
            '待处理': 'pending', '等待': 'pending',
            '已解决': 'resolved', '解决': 'resolved',
            '搁置': 'hold', '暂停': 'hold',
        }
        
        # 状态修改 - 支持中文
        status_value = None
        
        # 检查中文状态关键词
        for cn_status, en_status in status_map.items():
            if cn_status in todo:
                status_value = en_status
                print(f"[REACT] 从 todo 提取状态: '{cn_status}' -> '{en_status}'")
                break
        
        # 正则匹配英文状态
        if not status_value:
            status_match = re.search(r"status.*?['\"](\w+)['\"]|设为(\w+)", todo, re.IGNORECASE)
            if status_match:
                status_value = status_match.group(1) or status_match.group(2)
        
        if status_value:
            modifications['status'] = status_value
        
        # 优先级修改
        priority_match = re.search(r"优先级.*?(\w+)", todo, re.IGNORECASE)
        if priority_match:
            modifications['priority'] = priority_match.group(1)
        
        # 如果没有提取到任何内容，返回空
        if not modifications:
            print(f"[REACT] 无法从 todo 提取修改内容: {todo}")
            return {}
            
        return modifications
    
    async def _extract_modifications_with_llm(self, todo: str, user_input: str = '', exploration: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        使用大模型从 todo 中提取修改参数。可选传入 exploration（当前记录+用户列表），
        让模型先「探索」再思考意图（类似 Cursor 探索文件后再决定修改）。
        
        Args:
            todo: todo 描述文本
            user_input: 原始用户输入
            exploration: 可选，{ current_record, users }，来自 modify_tool.explore_record
            
        Returns:
            modifications: {字段名: 新值}
        """
        import re
        import json
        
        # 兜底：从用户输入直接解析「标题为/改成/改为 XXX」，避免 LLM 返回空
        text = (user_input or '').strip()
        if text:
            m = re.search(r'标题[为改成改为]+[：:\s]*([^\s，,。]+(?:\s+[^\s，,。]+)*)', text)
            if m:
                title_val = m.group(1).strip()
                if title_val and len(title_val) <= 200:
                    fallback = {'title': title_val}
                    print(f"[REACT-LLM] 从用户输入兜底解析标题: {fallback}")
                    return self._normalize_modifications_for_bug_expected_result(fallback, user_input)
        
        # 由大模型识别用户修改意图，归纳为工具参数。若有 exploration，先结合「当前记录+表可修改字段+用户列表」思考再输出。
        exploration_block = ""
        if exploration:
            cur = exploration.get('current_record') or {}
            users = exploration.get('users') or []
            fields = exploration.get('modifiable_fields') or []
            users_str = ", ".join([f"id={u.get('id')} name={u.get('name', '')}" for u in users[:30]])
            fields_str = "、".join([f"{f.get('field', '')}({f.get('label', '')})" for f in fields])
            exploration_block = f"""
【探索到的上下文】（类似 Cursor 探索文件：先看表记录与字段再决定改什么）
当前记录：{json.dumps(cur, ensure_ascii=False)}
本表可修改字段（仅可输出以下 field 名）：{fields_str}
可选用户（id/名称）：{users_str}
请结合上述记录、可修改字段与用户列表思考用户意图（例如负责人「33」对应用户列表中的谁）；只输出上述可修改字段中的 field 名作为 key，负责人用 assignee、值为用户名称，系统会按名称解析为 id。
"""
        
        prompt = f"""
原始用户请求：{user_input}
任务步骤描述：{todo}
{exploration_block}
请由你识别用户的具体修改意图，将意图归纳为「修改字段 → 值」的 JSON，作为 modify 工具的参数。

识别规则：用户表述方式多样（如「为」「改为」「改成」「设为」「调整为」等），只要语义是「把某字段改成某值」就输出对应字段与值。只返回与用户所述类型相符的字段（改 Bug 只出现 Bug 字段，改 BadCase 只出现 BadCase 字段，改测试用例只出现 TestCase 字段）。负责人：用户说的值一律视为对外属性（名称/展示名），输出 assignee 键即可，如「负责人为33」「的负责人为33」「负责人改成33」均输出 {{"assignee": "33"}}；系统会按名称解析为 id。不可修改字段勿返回：类型、id、project_id、plan_id、created_at、updated_at、creator_id；若用户仅要求改「类型」则返回 {{}}。

【Bug 字段映射】仅当用户明确在改 Bug 时使用：
- "标题" -> title
- "描述" -> description
- "状态" -> status（值：new/assigned/in_progress/resolved/closed/reopened）
- "优先级" -> priority（值：p1/p2/p3）
- "严重程度" -> severity
- "负责人" -> assignee（内部映射为 assignee_id）
- "复现步骤" -> steps_to_reproduce
- "期望结果"、"预期结果" -> expected_result
- "实际结果" -> actual_result

【BadCase 字段映射】仅当用户明确在改 BadCase 时使用：
- "标题" -> title
- "状态" -> status
- "优先级" -> priority
- "负责人" -> assignee
- "相似问题"、"具体问题"、"问题" -> base_problem
- "复现步骤" -> reproduction_steps
- "答案" -> answer（注意：不是"正确答案"）
- "正确答案" -> correct_answer
- "BadCase结果" -> badcase_result
- "解决方式" -> solution
- "问题原因" -> problem_reason

【TestCase 字段映射】仅当用户明确在改测试用例时使用：
- "标题" -> title
- "状态" -> status（值：draft/review/active/archived）
- "优先级" -> priority
- "负责人" -> assignee（内部映射为 assignee_id）
- "前置条件" -> preconditions
- "测试步骤" -> steps
- "备注" -> remark
- "基线" -> baseline
- "用例类型" -> case_type
- "测试类型" -> test_type
- "执行结果" -> execution_result
- "预估工时" -> estimated_time
- "实际工时" -> actual_time

示例（意图 → JSON）：
- "修改登录bug的期望结果为能正常登录" -> {{"expected_result": "能正常登录"}}
- "修改相似问题为XXX" -> {{"base_problem": "XXX"}}
- "状态改为已解决" -> {{"status": "resolved"}}
- "标题改成测试标题" -> {{"title": "测试标题"}}
- "修改创建测试用例7的负责人为33" / "的负责人为33" / "负责人改成33" -> {{"assignee": "33"}}

请直接返回 JSON，不要包含其他内容。"""
        
        try:
            response = await self._collect_llm_text(prompt)
            print(f"[REACT-LLM] 提取修改参数响应: {response}")
            
            # _collect_llm_text 一般为字符串；若以后改为结构化再处理 dict
            if isinstance(response, dict):
                print(f"[REACT-LLM] 提取的修改参数: {response}")
                return self._normalize_modifications_for_bug_expected_result(response, user_input)
            
            # 如果是字符串，提取 JSON 部分
            if isinstance(response, str):
                json_match = re.search(r'\{[^}]+\}', response, re.DOTALL)
                if json_match:
                    modifications = json.loads(json_match.group())
                    print(f"[REACT-LLM] 提取的修改参数: {modifications}")
                    return self._normalize_modifications_for_bug_expected_result(modifications, user_input)
        except Exception as e:
            print(f"[REACT-LLM] 提取修改参数失败: {e}")
        
        return {}
    
    def _user_facing_reasoning_summary(self, user_input: str, raw_reasoning: str) -> str:
        """将模型内部思考转为给用户看的说明。不截取深度思考文本，仅做 ID 转名称与内部词过滤。
        若包含工具名等内部词则回退为根据用户意图生成的简短说明。
        """
        if not raw_reasoning or not isinstance(raw_reasoning, str):
            return self._reasoning_summary_from_user_input(user_input)
        
        raw = raw_reasoning.strip()
        converted_reasoning = self._convert_ids_to_names(raw)
        
        internal_jargon = (
            'grep', 'modify', 'create', 'keywords', 'target', 'project_id', 'modifications',
            'Todo', 'todo', 'JSON', '必填', '可选', 'skill', '技能', 'workflow'
        )
        if any(j in converted_reasoning for j in internal_jargon):
            return self._reasoning_summary_from_user_input(user_input)
        cleaned = converted_reasoning.strip()
        return cleaned if cleaned else self._reasoning_summary_from_user_input(user_input)
    
    def _convert_ids_to_names(self, reasoning_text: str) -> str:
        """将 reasoning 中的内部 ID（project_id, plan_id, target_id）转换为用户可读的名称。
        
        转换规则：
        - project_id=1 → "A 计划项目"
        - plan_id=34 → "一个测试用例的计划"
        - target_id=6 → "创建测试用例"（从数据库中查找标题）
        """
        if not reasoning_text:
            return reasoning_text
        
        result = reasoning_text
        
        # 1. 转换 project_id（需在 app_context 内查库）
        # 2. 转换 plan_id
        import re
        try:
            from app import app, db, Project, Plan
            with app.app_context():
                if self.project_id:
                    project = db.session.query(Project).filter(Project.id == self.project_id).first()
                    if project:
                        result = re.sub(
                            rf'project_id[=：\s]*{self.project_id}',
                            f'"{project.name}"项目',
                            result
                        )
                        result = re.sub(
                            rf'项目 ID[=：\s]*{self.project_id}',
                            f'"{project.name}"项目',
                            result
                        )
                if self.plan_id:
                    plan = db.session.query(Plan).filter(Plan.id == self.plan_id).first()
                    if plan:
                        result = re.sub(
                            rf'plan_id[=：\s]*{self.plan_id}',
                            f'"{plan.name}"计划',
                            result
                        )
                        result = re.sub(
                            rf'迭代计划 ID[=：\s]*{self.plan_id}',
                            f'"{plan.name}"计划',
                            result
                        )
        except Exception as e:
            print(f"[REACT] 转换 project_id/plan_id 失败：{e}")
        
        # 3. 转换 target_id（需在 app_context 内查库）
        target_id_matches = re.findall(r'target_id[=：\s]*(\d+)', result)
        if target_id_matches:
            try:
                from app import app, db, Bug, BadCase, TestCase
                with app.app_context():
                    for match in target_id_matches:
                        target_id = int(match)
                        title = None
                        bug = db.session.query(Bug).filter(Bug.id == target_id).first()
                        if bug:
                            title = bug.title
                        else:
                            badcase = db.session.query(BadCase).filter(BadCase.id == target_id).first()
                            if badcase:
                                title = badcase.title
                            else:
                                testcase = db.session.query(TestCase).filter(TestCase.id == target_id).first()
                                if testcase:
                                    title = testcase.title
                        if title:
                            result = re.sub(
                                rf'target_id[=：\s]*{target_id}',
                                f'"{title}"记录',
                                result
                            )
            except Exception as e:
                print(f"[REACT] 转换 target_id 失败：{e}")
        
        return result
    
    def _user_requested_type_modification(self, user_input: str) -> bool:
        """检测用户是否在要求修改「类型」字段（类型不可修改，需提前拦截）。"""
        if not user_input or not isinstance(user_input, str):
            return False
        u = user_input.strip()
        # 修改...类型 / 类型改为 / 类型改成 / 把类型 / 将类型 / type 改为
        if '类型' in u and any(k in u for k in ('修改', '改', '改成', '改为', '设为', '更新')):
            return True
        if 'type' in u.lower() and any(k in u for k in ('修改', '改', '改成', '改为', '设为', '更新')):
            return True
        return False
    
    def _reasoning_summary_from_user_input(self, user_input: str) -> str:
        """根据用户输入生成一句给用户看的思考说明（不暴露内部参数）。"""
        if not user_input:
            return "正在分析您的请求并规划操作步骤。"
        u = user_input.strip()
        if any(k in u for k in ('修改', '改', '更新', '改成', '设为')):
            if any(k in u for k in ('期望结果', '预期结果')):
                return "先查找相关 Bug，再修改其期望结果。"
            if any(k in u for k in ('状态', '关闭', '解决', 'resolved', 'closed')):
                return "先定位相关记录，再修改状态。"
            if 'bug' in u.lower() or '缺陷' in u:
                return "先查找相关 Bug，再执行修改。"
            if 'badcase' in u.lower() or 'bad case' in u:
                return "先查找相关 BadCase，再执行修改。"
            return "先定位相关记录，再执行修改。"
        if any(k in u for k in ('查询', '搜索', '找', '列出', '显示')):
            return "正在查找相关记录。"
        if any(k in u for k in ('创建', '新建', '添加')):
            return "正在准备创建新记录。"
        return "正在分析您的请求并规划操作步骤。"
    
    def _normalize_modifications_for_bug_expected_result(self, modifications: Dict[str, Any], user_input: str) -> Dict[str, Any]:
        """兜底：用户说的是「期望结果」但 LLM 误提成 base_problem 时，改为 expected_result，避免沙箱预览显示为「相似问题」。"""
        if not modifications or not user_input:
            return modifications
        if 'expected_result' in modifications:
            return modifications
        if 'base_problem' not in modifications:
            return modifications
        if '期望结果' in user_input or '预期结果' in user_input:
            modifications = dict(modifications)
            modifications['expected_result'] = modifications.pop('base_problem')
            print(f"[REACT-LLM] 兜底：用户说期望结果，将 base_problem 改为 expected_result")
        return modifications
    
    def _extract_modifications_with_regex(self, user_input: str) -> Dict[str, Any]:
        """
        LLM 失败时的极简兜底（如解析异常、网络错误），仅做最宽松的匹配。
        主路径应由大模型识别意图并归纳为工具参数，不依赖写死的句式。
        """
        import re
        modifications = {}
        if not (user_input or '').strip():
            return modifications
        # 仅当明显包含「某字段 + 为/改为/改成 + 值」时，取最后一个这样的片段做极简推断，避免写死多种说法
        loose = re.search(r'(负责人|标题|状态)[为改成设为调整为]*\s*[：:\s]*([^\s，,。]+)', user_input)
        if loose:
            field_name = loose.group(1)
            value = loose.group(2).strip().rstrip('。，')
            key = 'assignee' if field_name == '负责人' else ('title' if field_name == '标题' else 'status')
            modifications[key] = value
            print(f"[REACT-REGEX] 兜底（极简）：{field_name} -> {key} = {value}")
        if not modifications and '负责人' in user_input:
            m2 = re.search(
                r'负责人\s*(?:修改|改|改为|设为|调整为|为)?\s*[：:\s]*([^\s，,。]+)',
                user_input,
            )
            if m2:
                modifications['assignee'] = m2.group(1).strip().rstrip('。，')
                print(f"[REACT-REGEX] 兜底（负责人句式）：assignee = {modifications['assignee']}")
        return modifications
    
    async def _extract_todo_params(self, todo: str, user_input: str) -> Dict[str, Any]:
        """
        从 todo 中提取工具名称和参数
        
        支持的 todo 格式:
        - "使用 grep 工具搜索标题为XXX的BadCase，keywords=XXX，target=badcase"
        - "使用 modify 工具将标题为XXX的BadCase状态修改为resolved"
        """
        import re
        result = {'tool': None, 'params': {}}
        
        # 1. 确定工具类型 - 优先匹配 modify，因为 modify 的 todo 中可能包含"搜索"关键词
        # 例如："使用 modify 工具将搜索到的 BadCase 状态修改为 resolved"
                
        # 先检查是否明确指定了 modify 工具或包含修改意图
        modify_keywords = ['modify', '修改', '改成', '改为', '更新', '设为', '调整']
        has_modify_intent = any(kw in todo.lower() for kw in modify_keywords)
                
        if has_modify_intent and 'grep' not in todo.lower():
            result['tool'] = 'modify'
                    
            # 使用大模型提取修改参数（更准确）
            modifications = await self._extract_modifications_with_llm(todo, user_input)
                    
            # 如果 LLM 调用失败，使用正则表达式兜底提取
            if not modifications and user_input:
                modifications = self._extract_modifications_with_regex(user_input)
                    
            # 提取目标类型：优先检查 testcase，再检查 bug，最后 badcase
            if 'testcase' in todo.lower() or 'test_case' in todo.lower() or '测试用例' in todo:
                target = 'testcase'
            elif 'bug' in todo.lower() or '缺陷' in todo or 'Bug' in todo:
                target = 'bug'
            elif 'badcase' in todo.lower() or 'bad case' in todo.lower() or 'bad 案例' in todo:
                target = 'badcase'
            else:
                target = 'badcase'  # 默认
                    
            result['params'] = {
                'target': target,
                'modifications': modifications,
                'confirm': False,
            }
            print(f"[REACT] 从 todo 提取 modify 参数：modifications={modifications}, target={target}")
        
        # 必须先于 create：todo 文案里常含标题「一个新增的 bug」，子串「新增」会误匹配 create
        elif 'grep' in todo.lower() or '搜索' in todo or '查找' in todo or '定位' in todo:
            result['tool'] = 'grep'
            
            # 提取关键词 - 优先匹配 keywords=XXX 格式
            keywords_match = re.search(r'keywords[=：]\s*([^，,]+)', todo, re.IGNORECASE)
            if keywords_match:
                keywords = keywords_match.group(1).strip()
            else:
                # 回退：匹配“标题为XXX”格式
                title_match = re.search(r'标题[是为]([^，。,]+)', todo)
                keywords = title_match.group(1).strip() if title_match else ''
            # 关键词兜底：从用户输入提取（如「修改登录bug的期望结果」->「登录」）
            if not keywords and user_input:
                keywords = self._extract_title_keywords_for_grep(user_input, todo)
            
            # 提取目标类型：todo 优先，否则结合用户输入（用户说「修改创建测试用例的前提条件」应查测试用例表）
            if 'bug' in todo.lower() or 'target=bug' in todo.lower():
                target = 'bug'
            elif 'testcase' in todo.lower() or 'test_case' in todo.lower() or 'target=testcase' in todo.lower():
                target = 'testcase'
            elif 'badcase' in todo.lower() or 'bad case' in todo.lower():
                target = 'badcase'
            elif user_input and ('测试用例' in user_input or 'test case' in user_input.lower()):
                # 兜底：用户提到测试用例但 todo 未写 target=testcase 时，按测试用例查
                target = 'testcase'
            elif user_input and ('bug' in user_input or '缺陷' in user_input or 'Bug' in user_input):
                # 兜底：用户提到 bug/缺陷但 todo 未写类型时，在所有迭代计划、不分类型查一遍（target=all，不限定 plan_id）
                target = 'all'
            else:
                target = 'badcase'  # 默认
            
            result['params'] = {
                'target': target,
                'mode': 'locate',
                'keywords': keywords or None,
            }
            # 兜底时查全部计划：target=all 时不传 plan_id，由 grep 查全项目
            if target == 'all':
                result['params'].pop('plan_id', None)
            print(f"[REACT] 从 todo 提取 grep 参数: keywords='{keywords}', target={target}")

        elif 'create' in todo.lower() or '创建' in todo or '新增' in todo or '新建' in todo:
            result['tool'] = 'create'
            target = self._infer_create_target(user_input, todo)
            title = self._extract_create_title(user_input, todo)
            fields = {}
            if title:
                fields['name' if target == 'plan' else 'title'] = title
            result['params'] = {
                'target': target,
                'fields': fields,
                'confirm': False,
            }
            print(f"[REACT] 从 todo 提取 create 参数: target={target}, fields={fields}")
        
        else:
            # 未知工具，返回空
            print(f"[REACT] 无法从 todo 识别工具: {todo}")
            result['tool'] = 'unknown'
        
        return result
    
    async def _execute_tool(self, decision: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具"""
        tool_name = decision['tool']
        original_tool_name = tool_name
        
        # 增加模糊匹配映射
        if 'bug' in tool_name.lower() and 'management' in tool_name.lower():
            tool_name = 'bug_management'
        elif 'browser' in tool_name.lower():
            tool_name = 'browser_test'
        elif 'search' in tool_name.lower():
            tool_name = 'search'
        
        print(f"[REACT] 正在执行工具: {original_tool_name} -> {tool_name}")
            
        tool = self.tools.get(tool_name)
        
        if not tool:
            print(f"[REACT] ❌ 工具不存在: {tool_name}")
            return {'success': False, 'error': f"工具不存在：{tool_name}"}
        
        try:
            # 确保传入 userId 和 project_id；并保证 params 与 decision['params'] 同引用，便于 run_stream 轮询 progress_queue
            params = decision.get('params') or {}
            if 'params' not in decision:
                decision['params'] = params
            if 'userId' not in params:
                params['userId'] = 'system_agent'
            if self.project_id and 'project_id' not in params:
                params['project_id'] = self.project_id
            
            print(f"[REACT] 工具参数: {params}")
            print(f"[REACT] 正在执行工具: {tool_name}")

            # modify 工具内部使用 Flask/SQLAlchemy 同步 DB，会阻塞 asyncio 事件循环，导致流式一直“修改中...”
            # 放到线程池中执行，在独立线程里跑新事件循环，避免阻塞主循环，并增加超时保护
            if tool_name == 'modify':
                print(f"[REACT] modify 进入线程池执行（target_id={params.get('target_id')}, target={params.get('target')}）…")
                loop = asyncio.get_event_loop()
                import queue as _queue
                progress_q: "_queue.Queue[str]" = _queue.Queue()
                # 暴露给上层 run_stream 轮询，向前端实时下发分步进度
                params['progress_queue'] = progress_q

                def _progress_cb(msg: str):
                    try:
                        progress_q.put(str(msg))
                    except Exception:
                        pass

                def _run_modify_in_thread():
                    thread_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(thread_loop)
                    try:
                        # 把进度回调传给 modify_tool（工具内分步上报）
                        params['progress_callback'] = _progress_cb
                        return thread_loop.run_until_complete(tool.execute(**params))
                    finally:
                        thread_loop.close()

                # 工具级超时时间（秒），可通过环境变量调整，默认 120s
                tool_timeout = int(os.getenv("AGENT_TOOL_TIMEOUT", "120"))
                try:
                    res = await asyncio.wait_for(
                        loop.run_in_executor(self._tool_executor, _run_modify_in_thread),
                        timeout=tool_timeout,
                    )
                except asyncio.TimeoutError:
                    print(f"[REACT] ❌ modify 工具执行超时（>{tool_timeout}s）")
                    return {
                        "success": False,
                        "error": f"modify 工具执行超时（>{tool_timeout}s），请检查后端数据库或网络状态后重试。",
                    }
            else:
                res = await tool.execute(**params)
            
            print(f"[REACT] ✅ 工具执行完成: {tool_name}")
            print(f"[REACT] 工具返回数据类型: {type(res).__name__}")
            if isinstance(res, dict) and 'results' in res:
                print(f"[REACT] 搜索结果数量: {len(res.get('results', []))}")
            if res is None:
                res = {'success': False, 'error': '工具返回空结果'}
            elif 'success' not in res:
                res['success'] = True # 默认成功
            return res
        except Exception as e:
            print(f"[REACT] ❌ 工具执行异常: {str(e)}")
            return {'success': False, 'error': str(e)}
