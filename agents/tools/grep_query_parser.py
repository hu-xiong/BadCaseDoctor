"""Grep 查询解析：结构化 keywords（负责人:xx）与自然语言字段剥离。"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


_ASSIGNEE_KV_RE = re.compile(
    r"(?:负责人|assignee|owner)\s*[:：=]\s*([^\s,，;；]+)",
    re.IGNORECASE,
)
_STATUS_KV_RE = re.compile(
    r"(?:状态|status)\s*[:：=]\s*([^\s,，;；]+)",
    re.IGNORECASE,
)
_ASSIGNEE_NL_RE = re.compile(
    r"(?:负责人|assignee|owner)\s*"
    r"(?:为|是|[:：=])?\s*"
    r"([^\s,，;；的]+)"
    r"(?:\s*的|\s|$)",
    re.IGNORECASE,
)


@dataclass
class ParsedGrepQuery:
    keywords: Optional[str] = None
    assignee: Optional[str] = None
    status: Optional[str] = None
    record_id: Optional[int] = None
    entity_types: List[str] = field(default_factory=list)


def _strip_empty(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    t = str(s).strip()
    if not t or t in ("*", "全部", "所有"):
        return None
    return t


def parse_structured_grep_keywords(
    keywords: Optional[str],
    *,
    assignee: Optional[str] = None,
    status: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    从 keywords 剥离 负责人:hx / status:closed 等，合并到显式 assignee/status（显式优先）。
    返回 (keywords, assignee, status)。
    """
    kw = (keywords or "").strip() if keywords is not None else ""
    out_assignee = _strip_empty(assignee)
    out_status = _strip_empty(status)

    if kw:
        m = _ASSIGNEE_KV_RE.search(kw)
        if m and not out_assignee:
            out_assignee = m.group(1).strip()
            kw = _ASSIGNEE_KV_RE.sub(" ", kw).strip()
        m = _STATUS_KV_RE.search(kw)
        if m and not out_status:
            out_status = m.group(1).strip()
            kw = _STATUS_KV_RE.sub(" ", kw).strip()

    kw = _strip_empty(kw)
    return kw, out_assignee, out_status


def extract_assignee_from_natural_language(text: Optional[str]) -> Optional[str]:
    if not text or not str(text).strip():
        return None
    m = _ASSIGNEE_NL_RE.search(str(text))
    if m:
        return m.group(1).strip()
    m2 = re.search(
        r"(?:把|将|查|搜|检索|找|列出|获取)\s*(?:负责人|assignee)\s*"
        r"(?:为|是|[:：=])?\s*([^\s,，;；的]+)",
        str(text),
        re.IGNORECASE,
    )
    if m2:
        return m2.group(1).strip()
    return None


def enrich_grep_params(
    *,
    keywords: Optional[str] = None,
    assignee: Optional[str] = None,
    status: Optional[str] = None,
    user_input: Optional[str] = None,
    todo: Optional[str] = None,
    target: Optional[str] = None,
) -> ParsedGrepQuery:
    """合并 LLM params、结构化 keywords、用户原话中的负责人线索。"""
    kw, asn, st = parse_structured_grep_keywords(keywords, assignee=assignee, status=status)
    if not asn:
        combined = f"{user_input or ''} {todo or ''}"
        asn = extract_assignee_from_natural_language(combined)

    record_id: Optional[int] = None
    if kw and kw.isdigit():
        try:
            record_id = int(kw)
        except ValueError:
            record_id = None

    entity_types: List[str] = []
    t = (target or "all").strip().lower()
    if t in ("bug", "badcase", "testcase", "card"):
        entity_types = [t]
    elif t == "all":
        entity_types = ["bug", "badcase"]

    return ParsedGrepQuery(
        keywords=kw,
        assignee=asn,
        status=st,
        record_id=record_id,
        entity_types=entity_types,
    )
