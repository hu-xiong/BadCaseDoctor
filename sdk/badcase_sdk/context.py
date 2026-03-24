# badcase_sdk/context.py
"""
Trace 上下文传递：使用 contextvars 在调用链中传递 conversation_id、request_id、span_id
"""
import contextvars
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TraceContext:
    """一次 LLM 调用或工作流步骤的 Trace 上下文"""
    conversation_id: Optional[str] = None
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    workflow_id: Optional[str] = None
    workflow_step: Optional[str] = None

    def child_span(self) -> "TraceContext":
        """创建子 span"""
        return TraceContext(
            conversation_id=self.conversation_id,
            request_id=str(uuid.uuid4())[:8],
            span_id=str(uuid.uuid4())[:8],
            parent_span_id=self.span_id or self.request_id,
            workflow_id=self.workflow_id,
            workflow_step=self.workflow_step,
        )


_trace_context: contextvars.ContextVar[Optional[TraceContext]] = contextvars.ContextVar(
    "badcase_trace_context", default=None
)


def get_trace_context() -> Optional[TraceContext]:
    """获取当前 trace 上下文"""
    return _trace_context.get()


def set_trace_context(ctx: Optional[TraceContext]) -> None:
    """设置 trace 上下文"""
    _trace_context.set(ctx)


@contextmanager
def run_with_context(ctx: TraceContext):
    """返回一个可复制的 context 以便在子协程/线程中传播"""
    token = _trace_context.set(ctx)
    try:
        yield ctx
    finally:
        _trace_context.reset(token)


@contextmanager
def context_manager(ctx: TraceContext):
    """用作 with 语句的上下文管理器"""
    token = _trace_context.set(ctx)
    try:
        yield ctx
    finally:
        _trace_context.reset(token)
