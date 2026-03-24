# badcase_sdk/labels.py
"""
Label 基数控制：将数值映射为有限 bucket，避免 Prometheus 高基数
"""
import re
from typing import Optional


def bucket_temperature(t: Optional[float]) -> str:
    """temperature 分桶"""
    if t is None:
        return "t_unknown"
    if t <= 0.0:
        return "t_0_0"
    if t <= 0.2:
        return "t_0_0_0_2"
    if t <= 0.7:
        return "t_0_2_0_7"
    if t < 1.0:
        return "t_0_7_1_0"
    return "t_1_0plus"


def bucket_top_p(p: Optional[float]) -> str:
    """top_p 分桶"""
    if p is None:
        return "p_unknown"
    if p <= 0.1:
        return "p_0_1"
    if p <= 0.9:
        return "p_0_1_0_9"
    if p < 1.0:
        return "p_0_9_1_0"
    return "p_1_0"


def bucket_max_tokens(n: Optional[int]) -> str:
    """max_tokens 分桶"""
    if n is None:
        return "mt_unknown"
    if n <= 256:
        return "mt_256"
    if n <= 512:
        return "mt_512"
    if n <= 1024:
        return "mt_1024"
    if n <= 4096:
        return "mt_4096"
    return "mt_4096plus"


def bucket_input_tokens(n: Optional[int]) -> str:
    """input_tokens 分桶"""
    if n is None:
        return "in_unknown"
    if n <= 512:
        return "in_0_512"
    if n <= 2048:
        return "in_512_2k"
    if n <= 8192:
        return "in_2k_8k"
    return "in_8kplus"


def bucket_output_tokens(n: Optional[int]) -> str:
    """output_tokens 分桶"""
    if n is None:
        return "out_unknown"
    if n <= 256:
        return "out_0_256"
    if n <= 1024:
        return "out_256_1k"
    return "out_1kplus"


def normalize_model(model: Optional[str]) -> str:
    """模型名归一化，去除日期/版本后缀"""
    if not model:
        return "unknown"
    s = str(model).strip()
    # 去除日期后缀如 -2026-02-15
    s = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", s)
    # 过长则截断
    if len(s) > 64:
        return s[:64]
    return s or "unknown"


def normalize_badcase_type(t: Optional[str]) -> str:
    """badcase_type 枚举化"""
    if not t:
        return "none"
    allowed = {"none", "hallucination", "format_error", "refuse", "tool_error", "timeout", "parse_error", "other"}
    v = str(t).strip().lower()
    if v in allowed:
        return v
    return "other"


def normalize_error_type(t: Optional[str]) -> str:
    """error_type 枚举化"""
    if not t:
        return "unknown"
    allowed = {"timeout", "http_429", "http_5xx", "http_4xx", "parse_error", "network_error", "other"}
    v = str(t).strip().lower()
    if v in allowed:
        return v
    return "other"


def normalize_stream_reason(r: Optional[str]) -> str:
    """stream interrupted reason"""
    if not r:
        return "unknown"
    allowed = {"client_cancel", "upstream_close", "timeout", "error", "unknown"}
    v = str(r).strip().lower()
    if v in allowed:
        return v
    return "unknown"


def normalize_finish_reason(r: Optional[str]) -> str:
    """finish_reason 枚举化"""
    if not r:
        return "unknown"
    allowed = {"stop", "length", "tool_calls", "content_filter", "error", "unknown"}
    v = str(r).strip().lower()
    if v in allowed:
        return v
    return "unknown"
