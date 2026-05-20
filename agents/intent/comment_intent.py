"""评论 vs 备注：意图识别与评论正文抽取（Bug / BadCase / TestCase 共用）。"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_COMMENT_INTENT_RE = re.compile(
    r"(?:添加|追加|发表|写|留|输入|新增).{0,10}?评论"
    r"|评论.{0,10}?(?:一下|内容|为|：|:)"
    r"|(?:append|add)\s*comment",
    re.I,
)
_REMARK_INTENT_RE = re.compile(
    r"(?:修改|更新|改|设置|填写|替换).{0,10}?备注"
    r"|备注.{0,10}?(?:为|成|改成|改为|更新)",
    re.I,
)
_COMMENT_BODY_RE = re.compile(
    r"(?:添加|追加|发表|写|留|输入|新增)(?:一条)?评论\s*[：:为]?\s*(.+)",
    re.I | re.DOTALL,
)


def intent_requests_append_comment(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    has_comment = bool(_COMMENT_INTENT_RE.search(t))
    has_remark = bool(_REMARK_INTENT_RE.search(t))
    if has_remark and not has_comment:
        return False
    return has_comment


def extract_append_comment_body(text: str) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None
    m = _COMMENT_BODY_RE.search(t)
    if m:
        body = m.group(1).strip().strip('"\'''「」')
        if body:
            return body
    # 「添加评论」后紧跟正文（无冒号）
    m2 = re.search(
        r"(?:添加|追加|发表|写|留|输入)(?:一条)?评论\s+(.+)",
        t,
        re.I | re.DOTALL,
    )
    if m2:
        body = m2.group(1).strip().strip('"\'''「」')
        if body:
            return body
    return None


def comment_body_exists_in_records(
    records: Optional[List[Dict[str, Any]]], body: str
) -> bool:
    want = (body or "").strip()
    if not want:
        return False
    for row in records or []:
        if not isinstance(row, dict):
            continue
        got = str(row.get("content") or "").strip()
        if got == want:
            return True
    return False


def apply_append_comment_intent_fallback(
    modifications: Optional[Dict[str, Any]],
    intent_text: str,
    comment_records: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    用户意图为追加评论时：若 LLM 返回空 / 误写 remark，补全 append_comment。
    仅当 comment_records 中尚无相同正文时才追加。
    """
    combined = (intent_text or "").strip()
    if not intent_requests_append_comment(combined):
        return dict(modifications or {})
    body = extract_append_comment_body(combined)
    if not body:
        return dict(modifications or {})
    if comment_body_exists_in_records(comment_records, body):
        out = dict(modifications or {})
        out.pop("remark", None)
        out.pop("append_comment", None)
        return out
    out = dict(modifications or {})
    if out.get("remark") is not None and out.get("append_comment") is None:
        out.pop("remark", None)
    out["append_comment"] = body
    return out
