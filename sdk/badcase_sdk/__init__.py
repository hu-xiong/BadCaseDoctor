# badcase_sdk/__init__.py
"""
BadCase 指标采集 SDK - Python 版
采集对话相关五大因素，输出 Prometheus 指标，供 BadCase Doctor 分析
"""
from .config import init, get_config, SdkConfig
from .collector import BadCaseCollector
from .context import TraceContext, get_trace_context, set_trace_context, context_manager
from .decorators import llm_observe, llm_span, _LlMSpanContext
from .stream import observe_stream, observe_stream_sync
from .labels import (
    bucket_temperature,
    bucket_top_p,
    bucket_max_tokens,
    bucket_input_tokens,
    bucket_output_tokens,
    normalize_model,
    normalize_badcase_type,
)


def install(app, path: str = "/metrics", app_name=None, env_name=None) -> None:
    """
    一键安装：自动挂载 /metrics 到 Web 框架
    支持 FastAPI、Flask，根据 app 类型自动选择
    """
    from .config import init
    if app_name is not None or env_name is not None:
        init(app=app_name, env=env_name)

    app_type = type(app).__name__
    if "FastAPI" in app_type:
        try:
            from .fastapi_integration import install as _install
        except ImportError:
            raise ImportError("FastAPI support requires: pip install badcase-sdk[fastapi]")
        _install(app, path=path, app_name=app_name, env_name=env_name)
    elif "Flask" in app_type:
        try:
            from .flask_integration import install as _install
        except ImportError:
            raise ImportError("Flask support requires: pip install badcase-sdk[flask]")
        _install(app, path=path, app_name=app_name, env_name=env_name)
    else:
        raise ValueError(f"Unsupported app type: {app_type}. Use FastAPI or Flask.")


def set_badcase_label(request_key: str, badcase_type: str) -> None:
    """
    异步 BadCase 标注：当 badcase 在调用结束后才被判定时调用
    注意：Prometheus 不更新历史样本，此方法记录一条「标注计数」指标
    """
    from .collector import badcase_total
    from .labels import normalize_badcase_type
    from .config import get_config
    cfg = get_config()
    # 使用 badcase_marks 或复用 badcase_total，此处简化为 badcase_total
    badcase_total.labels(
        app=cfg.app,
        env=cfg.env,
        provider="unknown",
        endpoint="chat",
        model="unknown",
        streaming="false",
        badcase_type=normalize_badcase_type(badcase_type),
    ).inc()


__all__ = [
    "init",
    "get_config",
    "SdkConfig",
    "install",
    "BadCaseCollector",
    "llm_observe",
    "llm_span",
    "observe_stream",
    "observe_stream_sync",
    "TraceContext",
    "get_trace_context",
    "set_trace_context",
    "context_manager",
    "set_badcase_label",
]
