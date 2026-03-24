# badcase_sdk/stream.py
"""
observe_stream: 包装 SSE 流式迭代器，自动记录 TTFT、chunk 数、stream_duration、interrupted
"""
import time
from typing import AsyncIterator, Iterator, Optional, Any

from .collector import BadCaseCollector
from .config import get_config


def observe_stream_sync(
    stream: Iterator[Any],
    provider: str = "unknown",
    endpoint: str = "chat",
    model: str = "unknown",
    app: Optional[str] = None,
    env: Optional[str] = None,
) -> Iterator[Any]:
    """
    同步流包装：迭代时累计 chunk、字节，首段记录 TTFT，结束记录 stream_duration
    """
    cfg = get_config()
    if not cfg.enabled:
        yield from stream
        return

    collector = BadCaseCollector(app=app or cfg.app, env=env or cfg.env)
    start = time.perf_counter()
    first_token_time: Optional[float] = None
    chunks = 0
    bytes_count = 0
    result = "success"
    finish_reason: Optional[str] = None

    try:
        for chunk in stream:
            if first_token_time is None:
                first_token_time = time.perf_counter() - start
                collector.record_time_to_first_token(
                    provider=provider,
                    endpoint=endpoint,
                    model=model,
                    result=result,
                    seconds=first_token_time,
                )
            chunks += 1
            if isinstance(chunk, (bytes, bytearray)):
                bytes_count += len(chunk)
            elif isinstance(chunk, str):
                bytes_count += len(chunk.encode("utf-8"))
            elif hasattr(chunk, "content") and chunk.content:
                s = str(chunk.content)
                bytes_count += len(s.encode("utf-8"))
            elif hasattr(chunk, "choices") and chunk.choices:
                c = chunk.choices[0]
                if hasattr(c, "delta") and getattr(c.delta, "content", None):
                    bytes_count += len(str(c.delta.content).encode("utf-8"))
            yield chunk
    except Exception:
        result = "fail"
        collector.record_stream_interrupted(
            provider=provider,
            endpoint=endpoint,
            model=model,
            reason="error",
        )
        raise
    finally:
        dur = time.perf_counter() - start
        collector.record_stream_duration(
            provider=provider,
            endpoint=endpoint,
            model=model,
            result=result,
            seconds=dur,
        )
        collector.record_stream_chunks(provider=provider, endpoint=endpoint, model=model, count=chunks)
        if bytes_count > 0:
            collector.record_stream_bytes(
                provider=provider,
                endpoint=endpoint,
                model=model,
                count=bytes_count,
            )
        if finish_reason:
            collector.record_finish_reason(
                provider=provider,
                endpoint=endpoint,
                model=model,
                reason=finish_reason,
            )


async def observe_stream(
    stream: AsyncIterator[Any],
    provider: str = "unknown",
    endpoint: str = "chat",
    model: str = "unknown",
    app: Optional[str] = None,
    env: Optional[str] = None,
) -> AsyncIterator[Any]:
    """
    异步流包装：与 observe_stream_sync 行为一致
    """
    cfg = get_config()
    if not cfg.enabled:
        async for chunk in stream:
            yield chunk
        return

    collector = BadCaseCollector(app=app or cfg.app, env=env or cfg.env)
    start = time.perf_counter()
    first_token_time: Optional[float] = None
    chunks = 0
    bytes_count = 0
    result = "success"
    finish_reason: Optional[str] = None

    try:
        async for chunk in stream:
            if first_token_time is None:
                first_token_time = time.perf_counter() - start
                collector.record_time_to_first_token(
                    provider=provider,
                    endpoint=endpoint,
                    model=model,
                    result=result,
                    seconds=first_token_time,
                )
            chunks += 1
            if isinstance(chunk, (bytes, bytearray)):
                bytes_count += len(chunk)
            elif isinstance(chunk, str):
                bytes_count += len(chunk.encode("utf-8"))
            elif hasattr(chunk, "content") and chunk.content:
                s = str(chunk.content)
                bytes_count += len(s.encode("utf-8"))
            elif hasattr(chunk, "choices") and chunk.choices:
                c = chunk.choices[0]
                if hasattr(c, "delta") and getattr(c.delta, "content", None):
                    bytes_count += len(str(c.delta.content).encode("utf-8"))
            yield chunk
    except Exception:
        result = "fail"
        collector.record_stream_interrupted(
            provider=provider,
            endpoint=endpoint,
            model=model,
            reason="error",
        )
        raise
    finally:
        dur = time.perf_counter() - start
        collector.record_stream_duration(
            provider=provider,
            endpoint=endpoint,
            model=model,
            result=result,
            seconds=dur,
        )
        collector.record_stream_chunks(provider=provider, endpoint=endpoint, model=model, count=chunks)
        if bytes_count > 0:
            collector.record_stream_bytes(
                provider=provider,
                endpoint=endpoint,
                model=model,
                count=bytes_count,
            )
        if finish_reason:
            collector.record_finish_reason(
                provider=provider,
                endpoint=endpoint,
                model=model,
                reason=finish_reason,
            )
