# badcase_sdk/decorators.py
"""
llm_observe 装饰器、llm_span 上下文管理器
"""
import functools
import time
from contextlib import contextmanager
from typing import Callable, Optional, Any, Dict

from .collector import BadCaseCollector
from .context import TraceContext, set_trace_context, get_trace_context, context_manager
from .config import get_config


def llm_observe(
    app: Optional[str] = None,
    env: Optional[str] = None,
    provider: str = "unknown",
    endpoint: str = "chat",
    model: str = "unknown",
    streaming: bool = False,
    prompt_template_id: Optional[str] = None,
    prompt_version: Optional[str] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    max_tokens: Optional[int] = None,
    tools_enabled: bool = False,
):
    """
    装饰器：包裹单次 LLM 调用，自动记录请求、耗时、token、badcase
    被装饰函数可返回 (result, meta) 或仅 result；meta 可含 input_tokens, output_tokens, badcase_type, error_type
    """

    def decorator(fn: Callable):
        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            cfg = get_config()
            if not cfg.enabled:
                return fn(*args, **kwargs)

            collector = BadCaseCollector(app=app or cfg.app, env=env or cfg.env)
            ctx = TraceContext()
            set_trace_context(ctx)

            start = time.perf_counter()
            result = "success"
            meta: Dict[str, Any] = {}

            try:
                out = fn(*args, **kwargs)
                if isinstance(out, tuple) and len(out) >= 2:
                    out, meta = out[0], (out[1] if isinstance(out[1], dict) else {})
                return out
            except Exception as e:
                result = "fail"
                meta["error_type"] = getattr(e, "error_type", "other")
                meta["http_status"] = getattr(e, "http_status", "")
                collector.record_error(
                    provider=provider,
                    endpoint=endpoint,
                    model=model,
                    error_type=meta.get("error_type", "other"),
                    http_status=str(meta.get("http_status", "")),
                )
                raise
            finally:
                dur = time.perf_counter() - start
                collector.record_request(
                    provider=provider,
                    endpoint=endpoint,
                    model=model,
                    streaming=streaming,
                    result=result,
                )
                collector.record_duration(
                    provider=provider,
                    endpoint=endpoint,
                    model=model,
                    streaming=streaming,
                    result=result,
                    seconds=dur,
                )
                itok = meta.get("input_tokens")
                otok = meta.get("output_tokens")
                if itok is not None:
                    collector.record_tokens(provider, endpoint, model, "input", int(itok))
                if otok is not None:
                    collector.record_tokens(provider, endpoint, model, "output", int(otok))
                if itok is not None and otok is not None:
                    collector.record_tokens(provider, endpoint, model, "total", int(itok) + int(otok))
                bt = meta.get("badcase_type", "none")
                collector.record_badcase(
                    provider=provider,
                    endpoint=endpoint,
                    model=model,
                    streaming=streaming,
                    badcase_type=bt,
                )

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            cfg = get_config()
            if not cfg.enabled:
                return await fn(*args, **kwargs)

            collector = BadCaseCollector(app=app or cfg.app, env=env or cfg.env)
            ctx = TraceContext()
            set_trace_context(ctx)

            start = time.perf_counter()
            result = "success"
            meta: Dict[str, Any] = {}

            try:
                out = await fn(*args, **kwargs)
                if isinstance(out, tuple) and len(out) >= 2:
                    out, meta = out[0], (out[1] if isinstance(out[1], dict) else {})
                return out
            except Exception as e:
                result = "fail"
                meta["error_type"] = getattr(e, "error_type", "other")
                meta["http_status"] = getattr(e, "http_status", "")
                collector.record_error(
                    provider=provider,
                    endpoint=endpoint,
                    model=model,
                    error_type=meta.get("error_type", "other"),
                    http_status=str(meta.get("http_status", "")),
                )
                raise
            finally:
                dur = time.perf_counter() - start
                collector.record_request(
                    provider=provider,
                    endpoint=endpoint,
                    model=model,
                    streaming=streaming,
                    result=result,
                )
                collector.record_duration(
                    provider=provider,
                    endpoint=endpoint,
                    model=model,
                    streaming=streaming,
                    result=result,
                    seconds=dur,
                )
                itok = meta.get("input_tokens")
                otok = meta.get("output_tokens")
                if itok is not None:
                    collector.record_tokens(provider, endpoint, model, "input", int(itok))
                if otok is not None:
                    collector.record_tokens(provider, endpoint, model, "output", int(otok))
                if itok is not None and otok is not None:
                    collector.record_tokens(provider, endpoint, model, "total", int(itok) + int(otok))
                bt = meta.get("badcase_type", "none")
                collector.record_badcase(
                    provider=provider,
                    endpoint=endpoint,
                    model=model,
                    streaming=streaming,
                    badcase_type=bt,
                )

        import asyncio
        if asyncio.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    return decorator


@contextmanager
def llm_span(
    app: Optional[str] = None,
    env: Optional[str] = None,
    conversation_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
    workflow_step: Optional[str] = None,
):
    """
    上下文管理器：多段（检索 + 工具 + 模型）记录
    通过 ctx.record_retrieval / record_tool_call 等记录子指标
    """
    cfg = get_config()
    ctx = TraceContext(
        conversation_id=conversation_id,
        workflow_id=workflow_id,
        workflow_step=workflow_step,
    )

    with context_manager(ctx):
        span_ctx = _LlMSpanContext(
            app=app or cfg.app,
            env=env or cfg.env,
            conversation_id=conversation_id,
            workflow_id=workflow_id,
            workflow_step=workflow_step,
        )
        yield span_ctx


class _LlMSpanContext:
    """llm_span 内部上下文，提供 record_* 方法"""

    def __init__(
        self,
        app: str,
        env: str,
        conversation_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        workflow_step: Optional[str] = None,
    ):
        self.collector = BadCaseCollector(app=app, env=env)
        self.conversation_id = conversation_id
        self.workflow_id = workflow_id
        self.workflow_step = workflow_step

    def record_retrieval(
        self,
        provider: str = "unknown",
        model: str = "unknown",
        count: int = 0,
        duration: float = 0.0,
        result: str = "success",
    ) -> None:
        self.collector.record_retrieval(
            provider=provider,
            model=model,
            result=result,
            seconds=duration,
            docs_count=count,
        )

    def record_tool_call(
        self,
        tool_name: str,
        provider: str = "unknown",
        endpoint: str = "chat",
        model: str = "unknown",
        duration: float = 0.0,
        result: str = "success",
    ) -> None:
        self.collector.record_tool_call(
            provider=provider,
            endpoint=endpoint,
            model=model,
            tool_name=tool_name,
            result=result,
            duration_sec=duration,
        )

    def record_workflow_step(
        self,
        workflow_id: str,
        workflow_step: str,
        step_type: str,
        duration: float,
        result: str = "success",
    ) -> None:
        self.collector.record_workflow_step(
            workflow_id=workflow_id,
            workflow_step=workflow_step,
            step_type=step_type,
            result=result,
            seconds=duration,
        )
