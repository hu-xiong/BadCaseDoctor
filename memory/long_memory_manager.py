"""长期记忆门面：基于开源 mem0（本地 Qdrant + 项目 Embedding）。"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from config import Config
from memory.mem0_client import get_mem0_memory


_SENSITIVE_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"mysql\+pymysql://[^ \n]+", re.IGNORECASE),
    re.compile(r"\bpassword\s*=\s*[^ \n]+", re.IGNORECASE),
    re.compile(r"\bsecret\s*=\s*[^ \n]+", re.IGNORECASE),
    re.compile(r"\btoken\s*=\s*[^ \n]+", re.IGNORECASE),
]


def _looks_sensitive(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return any(p.search(t) for p in _SENSITIVE_PATTERNS)


@dataclass
class RetrievedMemory:
    id: str
    type: str
    text: str
    score: float


def _meta_get(row: Dict[str, Any], key: str, default=None):
    md = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    if key in md:
        return md.get(key)
    return row.get(key, default)


def _is_enabled(row: Dict[str, Any]) -> bool:
    v = _meta_get(row, "enabled", True)
    if v is False or str(v).strip().lower() in ("0", "false", "no", "off"):
        return False
    return True


def _row_to_item(row: Dict[str, Any], *, score: Optional[float] = None) -> Optional[RetrievedMemory]:
    mid = str(row.get("id") or "")
    txt = str(row.get("memory") or row.get("memory_text") or row.get("text") or "").strip()
    if not mid or not txt or _looks_sensitive(txt):
        return None
    if not _is_enabled(row):
        return None
    mtype = str(_meta_get(row, "type") or _meta_get(row, "memory_type") or "fact")
    sc = float(score if score is not None else (row.get("score") if row.get("score") is not None else 1.0))
    return RetrievedMemory(id=mid, type=mtype, text=txt[:800], score=sc)


def _items_to_ctx(items: List[RetrievedMemory]) -> Dict[str, Any]:
    merged_lines = [f"{i}. [{it.type}] {it.text}" for i, it in enumerate(items, start=1)]
    return {
        "long_memory_items": [it.__dict__ for it in items],
        "long_memory_text": "\n".join(merged_lines),
    }


def _match_scope(
    row: Dict[str, Any],
    *,
    project_id: Optional[str],
    plan_id: Optional[str],
    types: Optional[List[str]],
) -> bool:
    if project_id is not None and str(project_id).strip():
        pid = _meta_get(row, "project_id")
        if pid is None or str(pid) != str(project_id):
            return False
    if plan_id is not None and str(plan_id).strip():
        pl = _meta_get(row, "plan_id")
        if pl is None or str(pl) != str(plan_id):
            return False
    if types:
        type_set = {str(t) for t in types}
        mtype = str(_meta_get(row, "type") or _meta_get(row, "memory_type") or "fact")
        if mtype not in type_set:
            return False
    return True


class _Mem0StoreFacade:
    """兼容旧 routers：mgr.store.list_items / set_enabled / set_feedback / delete。"""

    def __init__(self, mgr: "LongMemoryManager"):
        self._mgr = mgr

    def list_items(
        self,
        *,
        user_id: str,
        project_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        size: int = 50,
        offset: int = 0,
        types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self._mgr.list_items(
            user_id=user_id,
            project_id=project_id,
            plan_id=plan_id,
            size=size,
            offset=offset,
            types=types,
        )

    def set_enabled(self, *, memory_id: str, enabled: bool) -> None:
        self._mgr.set_enabled(memory_id=memory_id, enabled=enabled)

    def set_feedback(self, *, memory_id: str, feedback: str) -> None:
        self._mgr.set_feedback(memory_id=memory_id, feedback=feedback)

    def delete(self, *, memory_id: str) -> None:
        self._mgr.delete(memory_id=memory_id)


class LongMemoryManager:
    def __init__(self):
        self.enabled = bool(getattr(Config, "LONG_MEMORY_ENABLED", False))
        self.top_k = int(getattr(Config, "LONG_MEMORY_TOP_K", 10) or 10)
        self.use_n = int(getattr(Config, "LONG_MEMORY_USE_N", 4) or 4)
        self.min_score = float(getattr(Config, "LONG_MEMORY_MIN_SCORE", 0.0) or 0.0)
        self.store = _Mem0StoreFacade(self)

    def _memory(self):
        return get_mem0_memory()

    def retrieve_context(
        self,
        *,
        user_id: str,
        query: str,
        project_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"long_memory_items": [], "long_memory_text": ""}
        q = (query or "").strip()
        if not q:
            return {"long_memory_items": [], "long_memory_text": ""}

        filters: Dict[str, Any] = {"user_id": str(user_id)}
        if project_id is not None and str(project_id).strip():
            filters["project_id"] = str(project_id)
        if plan_id is not None and str(plan_id).strip():
            filters["plan_id"] = str(plan_id)

        try:
            raw = self._memory().search(
                q[:4000],
                top_k=max(self.top_k, self.use_n),
                filters=filters,
                threshold=float(self.min_score) if self.min_score > 0 else 0.0,
            )
        except Exception:
            return {"long_memory_items": [], "long_memory_text": ""}

        results = raw.get("results") if isinstance(raw, dict) else None
        if not isinstance(results, list):
            results = []

        items: List[RetrievedMemory] = []
        for row in results:
            if not isinstance(row, dict):
                continue
            if not _match_scope(row, project_id=project_id, plan_id=plan_id, types=types):
                continue
            it = _row_to_item(row, score=row.get("score"))
            if it is None:
                continue
            if it.score < self.min_score:
                continue
            items.append(it)
            if len(items) >= self.use_n:
                break
        return _items_to_ctx(items)

    def retrieve_recent_for_project(
        self,
        *,
        user_id: str,
        project_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not self.enabled or not (project_id or "").strip():
            return {"long_memory_items": [], "long_memory_text": ""}
        listed = self.list_items(
            user_id=str(user_id),
            project_id=str(project_id),
            plan_id=str(plan_id) if plan_id else None,
            size=max(self.use_n, 8),
            offset=0,
            types=types,
        )
        items: List[RetrievedMemory] = []
        for row in listed.get("items") or []:
            if len(items) >= self.use_n:
                break
            if row.get("enabled") is False:
                continue
            mid = str(row.get("id") or "")
            txt = str(row.get("memory_text") or "").strip()
            if not mid or not txt or _looks_sensitive(txt):
                continue
            mtype = str(row.get("type") or "fact")
            items.append(RetrievedMemory(id=mid, type=mtype, text=txt[:800], score=1.0))
        return _items_to_ctx(items)

    def write_simple(
        self,
        *,
        user_id: str,
        project_id: Optional[str],
        plan_id: Optional[str],
        agent_session_id: Optional[str],
        memory_type: str,
        memory_text: str,
        source: str = "user_explicit",
        confidence: float = 0.7,
        infer: bool = False,
    ) -> Dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("长期记忆未开启（LONG_MEMORY_ENABLED=false）。")
        txt = (memory_text or "").strip()
        if not txt:
            raise RuntimeError("memory_text 不能为空。")
        if _looks_sensitive(txt):
            raise RuntimeError("检测到敏感信息，拒绝写入长期记忆。")

        metadata: Dict[str, Any] = {
            "type": str(memory_type or "fact"),
            "source": str(source or "user_explicit"),
            "confidence": float(confidence),
            "enabled": True,
            "feedback": "none",
        }
        if project_id is not None:
            metadata["project_id"] = str(project_id)
        if plan_id is not None:
            metadata["plan_id"] = str(plan_id)
        if agent_session_id is not None:
            metadata["agent_session_id"] = str(agent_session_id)

        res = self._memory().add(
            txt[:4000],
            user_id=str(user_id),
            metadata=metadata,
            infer=bool(infer),
        )
        results = res.get("results") if isinstance(res, dict) else None
        mid = ""
        if isinstance(results, list) and results:
            mid = str((results[0] or {}).get("id") or "")
        return {
            "id": mid,
            "memory_text": txt[:800],
            "type": metadata["type"],
            "source": metadata["source"],
            "raw": res,
        }

    def capture_conversation(
        self,
        *,
        user_id: str,
        user_input: str,
        assistant_text: str,
        project_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        agent_session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """对话结束后让 mem0 LLM 抽取事实（infer=True）。"""
        if not self.enabled:
            return {"skipped": True, "reason": "disabled"}
        if not getattr(Config, "MEM0_AUTO_CAPTURE", False):
            return {"skipped": True, "reason": "auto_capture_off"}
        u = (user_input or "").strip()
        a = (assistant_text or "").strip()
        if not u or not a:
            return {"skipped": True, "reason": "empty"}
        if _looks_sensitive(u) or _looks_sensitive(a):
            return {"skipped": True, "reason": "sensitive"}

        metadata: Dict[str, Any] = {
            "type": "fact",
            "source": "react_auto",
            "enabled": True,
            "feedback": "none",
        }
        if project_id is not None:
            metadata["project_id"] = str(project_id)
        if plan_id is not None:
            metadata["plan_id"] = str(plan_id)
        if agent_session_id is not None:
            metadata["agent_session_id"] = str(agent_session_id)

        messages = [
            {"role": "user", "content": u[:4000]},
            {"role": "assistant", "content": a[:4000]},
        ]
        res = self._memory().add(
            messages,
            user_id=str(user_id),
            metadata=metadata,
            infer=True,
        )
        return {"ok": True, "raw": res}

    def schedule_capture_conversation(self, **kwargs) -> None:
        """后台线程沉淀，不阻塞 SSE。"""

        def _run():
            try:
                self.capture_conversation(**kwargs)
            except Exception as e:
                print(f"[LONG-MEMORY] auto capture failed: {e}", flush=True)

        threading.Thread(target=_run, name="mem0-auto-capture", daemon=True).start()

    def list_items(
        self,
        *,
        user_id: str,
        project_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        size: int = 50,
        offset: int = 0,
        types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"total": 0, "items": []}
        filters: Dict[str, Any] = {"user_id": str(user_id)}
        if project_id is not None and str(project_id).strip():
            filters["project_id"] = str(project_id)
        if plan_id is not None and str(plan_id).strip():
            filters["plan_id"] = str(plan_id)
        try:
            raw = self._memory().get_all(
                filters=filters,
                top_k=max(int(size) + int(offset), int(size), 20),
            )
        except Exception:
            return {"total": 0, "items": []}
        results = raw.get("results") if isinstance(raw, dict) else None
        if not isinstance(results, list):
            results = []

        def _sort_key(row: Dict[str, Any]):
            return str(row.get("updated_at") or row.get("created_at") or "")

        results = sorted(
            [r for r in results if isinstance(r, dict)],
            key=_sort_key,
            reverse=True,
        )
        items: List[Dict[str, Any]] = []
        for row in results:
            if not _match_scope(row, project_id=project_id, plan_id=plan_id, types=types):
                continue
            txt = str(row.get("memory") or "").strip()
            if not txt:
                continue
            items.append(
                {
                    "id": str(row.get("id") or ""),
                    "memory_text": txt[:2000],
                    "type": str(_meta_get(row, "type") or "fact"),
                    "enabled": _is_enabled(row),
                    "feedback": str(_meta_get(row, "feedback") or "none"),
                    "source": str(_meta_get(row, "source") or ""),
                    "project_id": _meta_get(row, "project_id"),
                    "plan_id": _meta_get(row, "plan_id"),
                    "created_at": row.get("created_at"),
                    "updated_at": row.get("updated_at"),
                    "score": row.get("score"),
                }
            )
        total = len(items)
        sliced = items[int(offset) : int(offset) + int(size)]
        return {"total": total, "items": sliced}

    def set_enabled(self, *, memory_id: str, enabled: bool) -> None:
        mid = str(memory_id or "")
        if not mid:
            raise RuntimeError("缺少 memory_id")
        mem = self._memory()
        existing = mem.get(mid) or {}
        md = dict(existing.get("metadata") or {}) if isinstance(existing, dict) else {}
        md["enabled"] = bool(enabled)
        mem.update(mid, metadata=md)

    def set_feedback(self, *, memory_id: str, feedback: str) -> None:
        mid = str(memory_id or "")
        if not mid:
            raise RuntimeError("缺少 memory_id")
        mem = self._memory()
        existing = mem.get(mid) or {}
        md = dict(existing.get("metadata") or {}) if isinstance(existing, dict) else {}
        md["feedback"] = str(feedback or "none")
        mem.update(mid, metadata=md)

    def delete(self, *, memory_id: str) -> None:
        mid = str(memory_id or "")
        if not mid:
            raise RuntimeError("缺少 memory_id")
        self._memory().delete(mid)
