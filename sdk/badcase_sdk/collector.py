# badcase_sdk/collector.py
"""
BadCase 指标采集器 - 基于 prometheus_client 定义所有指标
"""
from typing import Optional, Dict, Any

from prometheus_client import Counter, Histogram, REGISTRY

from .labels import (
    bucket_temperature,
    bucket_top_p,
    bucket_max_tokens,
    bucket_input_tokens,
    bucket_output_tokens,
    normalize_model,
    normalize_badcase_type,
    normalize_error_type,
    normalize_stream_reason,
    normalize_finish_reason,
)

# 默认 buckets（秒）
_DURATION_BUCKETS = (0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0)


def _default_tags() -> Dict[str, str]:
    """从全局配置获取默认 app/env"""
    from .config import get_config
    cfg = get_config()
    return {"app": cfg.app, "env": cfg.env}


def _tags(**kw) -> Dict[str, str]:
    tags = _default_tags()
    tags.update(kw)
    return tags


# ==================== 基础指标 ====================

requests_total = Counter(
    "bdc_llm_requests_total",
    "LLM 请求总数",
    ["app", "env", "provider", "endpoint", "model", "streaming", "result"],
    registry=REGISTRY,
)

errors_total = Counter(
    "bdc_llm_errors_total",
    "LLM 错误总数",
    ["app", "env", "provider", "endpoint", "model", "error_type", "http_status"],
    registry=REGISTRY,
)

duration_seconds = Histogram(
    "bdc_llm_duration_seconds",
    "LLM 调用耗时",
    ["app", "env", "provider", "endpoint", "model", "streaming", "result"],
    buckets=_DURATION_BUCKETS,
    registry=REGISTRY,
)

tokens_total = Counter(
    "bdc_llm_tokens_total",
    "Token 用量",
    ["app", "env", "provider", "endpoint", "model", "kind"],
    registry=REGISTRY,
)

badcase_total = Counter(
    "bdc_llm_badcase_total",
    "BadCase 计数",
    ["app", "env", "provider", "endpoint", "model", "streaming", "badcase_type"],
    registry=REGISTRY,
)

# ==================== 流式指标 ====================

time_to_first_token_seconds = Histogram(
    "bdc_llm_time_to_first_token_seconds",
    "首 token 延迟",
    ["app", "env", "provider", "endpoint", "model", "result"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
    registry=REGISTRY,
)

stream_duration_seconds = Histogram(
    "bdc_llm_stream_duration_seconds",
    "流式总耗时",
    ["app", "env", "provider", "endpoint", "model", "result"],
    buckets=_DURATION_BUCKETS,
    registry=REGISTRY,
)

stream_chunks_total = Counter(
    "bdc_llm_stream_chunks_total",
    "流式 chunk 数",
    ["app", "env", "provider", "endpoint", "model"],
    registry=REGISTRY,
)

stream_bytes_total = Counter(
    "bdc_llm_stream_bytes_total",
    "流式累计字节数",
    ["app", "env", "provider", "endpoint", "model"],
    registry=REGISTRY,
)

stream_interrupted_total = Counter(
    "bdc_llm_stream_interrupted_total",
    "流中断次数",
    ["app", "env", "provider", "endpoint", "model", "reason"],
    registry=REGISTRY,
)

finish_reason_total = Counter(
    "bdc_llm_finish_reason_total",
    "停止原因计数",
    ["app", "env", "provider", "endpoint", "model", "reason"],
    registry=REGISTRY,
)

# ==================== 工具调用 ====================

tool_calls_total = Counter(
    "bdc_llm_tool_calls_total",
    "工具调用次数",
    ["app", "env", "provider", "endpoint", "model", "tool_name", "result"],
    registry=REGISTRY,
)

tool_call_duration_seconds = Histogram(
    "bdc_llm_tool_call_duration_seconds",
    "工具调用耗时",
    ["app", "env", "provider", "endpoint", "model", "tool_name", "result"],
    buckets=_DURATION_BUCKETS,
    registry=REGISTRY,
)

# ==================== 检索 ====================

retrieval_duration_seconds = Histogram(
    "bdc_llm_retrieval_duration_seconds",
    "检索耗时",
    ["app", "env", "provider", "model", "result"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0),
    registry=REGISTRY,
)

retrieval_docs_total = Counter(
    "bdc_llm_retrieval_docs_total",
    "召回文档数",
    ["app", "env", "provider", "model"],
    registry=REGISTRY,
)

# ==================== 工作流 ====================

workflow_steps_total = Counter(
    "bdc_llm_workflow_steps_total",
    "工作流步骤计数",
    ["app", "env", "workflow_id", "workflow_step", "step_type", "result"],
    registry=REGISTRY,
)

workflow_duration_seconds = Histogram(
    "bdc_llm_workflow_duration_seconds",
    "工作流单步耗时",
    ["app", "env", "workflow_id", "workflow_step", "step_type"],
    buckets=_DURATION_BUCKETS,
    registry=REGISTRY,
)


class BadCaseCollector:
    """指标记录门面，封装 bucket 化与默认标签"""

    def __init__(self, app: Optional[str] = None, env: Optional[str] = None):
        from .config import get_config
        cfg = get_config()
        self._app = app or cfg.app
        self._env = env or cfg.env

    def _t(self, **kw) -> Dict[str, str]:
        return {"app": self._app, "env": self._env, **kw}

    def record_request(
        self,
        provider: str,
        endpoint: str,
        model: str,
        streaming: bool,
        result: str = "success",
    ) -> None:
        model = normalize_model(model)
        requests_total.labels(
            **self._t(
                provider=provider,
                endpoint=endpoint,
                model=model,
                streaming="true" if streaming else "false",
                result=result,
            )
        ).inc()

    def record_error(
        self,
        provider: str,
        endpoint: str,
        model: str,
        error_type: str,
        http_status: str = "",
    ) -> None:
        model = normalize_model(model)
        errors_total.labels(
            **self._t(
                provider=provider,
                endpoint=endpoint,
                model=model,
                error_type=normalize_error_type(error_type),
                http_status=str(http_status) or "0",
            )
        ).inc()

    def record_duration(
        self,
        provider: str,
        endpoint: str,
        model: str,
        streaming: bool,
        result: str,
        seconds: float,
    ) -> None:
        model = normalize_model(model)
        duration_seconds.labels(
            **self._t(
                provider=provider,
                endpoint=endpoint,
                model=model,
                streaming="true" if streaming else "false",
                result=result,
            )
        ).observe(seconds)

    def record_tokens(
        self,
        provider: str,
        endpoint: str,
        model: str,
        kind: str,
        count: int,
    ) -> None:
        model = normalize_model(model)
        tokens_total.labels(
            **self._t(provider=provider, endpoint=endpoint, model=model, kind=kind)
        ).inc(count)

    def record_badcase(
        self,
        provider: str,
        endpoint: str,
        model: str,
        streaming: bool,
        badcase_type: str,
    ) -> None:
        model = normalize_model(model)
        badcase_total.labels(
            **self._t(
                provider=provider,
                endpoint=endpoint,
                model=model,
                streaming="true" if streaming else "false",
                badcase_type=normalize_badcase_type(badcase_type),
            )
        ).inc()

    def record_time_to_first_token(
        self,
        provider: str,
        endpoint: str,
        model: str,
        result: str,
        seconds: float,
    ) -> None:
        model = normalize_model(model)
        time_to_first_token_seconds.labels(
            **self._t(provider=provider, endpoint=endpoint, model=model, result=result)
        ).observe(seconds)

    def record_stream_duration(
        self,
        provider: str,
        endpoint: str,
        model: str,
        result: str,
        seconds: float,
    ) -> None:
        model = normalize_model(model)
        stream_duration_seconds.labels(
            **self._t(provider=provider, endpoint=endpoint, model=model, result=result)
        ).observe(seconds)

    def record_stream_chunks(
        self,
        provider: str,
        endpoint: str,
        model: str,
        count: int = 1,
    ) -> None:
        model = normalize_model(model)
        stream_chunks_total.labels(
            **self._t(provider=provider, endpoint=endpoint, model=model)
        ).inc(count)

    def record_stream_bytes(
        self,
        provider: str,
        endpoint: str,
        model: str,
        count: int,
    ) -> None:
        model = normalize_model(model)
        stream_bytes_total.labels(
            **self._t(provider=provider, endpoint=endpoint, model=model)
        ).inc(count)

    def record_stream_interrupted(
        self,
        provider: str,
        endpoint: str,
        model: str,
        reason: str,
    ) -> None:
        model = normalize_model(model)
        stream_interrupted_total.labels(
            **self._t(
                provider=provider,
                endpoint=endpoint,
                model=model,
                reason=normalize_stream_reason(reason),
            )
        ).inc()

    def record_finish_reason(
        self,
        provider: str,
        endpoint: str,
        model: str,
        reason: str,
    ) -> None:
        model = normalize_model(model)
        finish_reason_total.labels(
            **self._t(
                provider=provider,
                endpoint=endpoint,
                model=model,
                reason=normalize_finish_reason(reason),
            )
        ).inc()

    def record_tool_call(
        self,
        provider: str,
        endpoint: str,
        model: str,
        tool_name: str,
        result: str = "success",
        duration_sec: Optional[float] = None,
    ) -> None:
        model = normalize_model(model)
        tool_name = str(tool_name)[:32]  # 限制长度
        tool_calls_total.labels(
            **self._t(
                provider=provider,
                endpoint=endpoint,
                model=model,
                tool_name=tool_name,
                result=result,
            )
        ).inc()
        if duration_sec is not None and duration_sec >= 0:
            tool_call_duration_seconds.labels(
                **self._t(
                    provider=provider,
                    endpoint=endpoint,
                    model=model,
                    tool_name=tool_name,
                    result=result,
                )
            ).observe(float(duration_sec))

    def record_retrieval(
        self,
        provider: str,
        model: str,
        result: str,
        seconds: float,
        docs_count: Optional[int] = None,
    ) -> None:
        model = normalize_model(model)
        retrieval_duration_seconds.labels(
            **self._t(provider=provider, model=model, result=result)
        ).observe(seconds)
        if docs_count is not None:
            retrieval_docs_total.labels(
                **self._t(provider=provider, model=model)
            ).inc(docs_count)

    def record_workflow_step(
        self,
        workflow_id: str,
        workflow_step: str,
        step_type: str,
        result: str,
        seconds: Optional[float] = None,
    ) -> None:
        workflow_steps_total.labels(
            **self._t(
                workflow_id=str(workflow_id)[:32],
                workflow_step=str(workflow_step)[:32],
                step_type=str(step_type)[:32],
                result=result,
            )
        ).inc()
        if seconds is not None:
            workflow_duration_seconds.labels(
                **self._t(
                    workflow_id=str(workflow_id)[:32],
                    workflow_step=str(workflow_step)[:32],
                    step_type=str(step_type)[:32],
                )
            ).observe(seconds)
