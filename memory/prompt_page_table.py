# -*- coding: utf-8
"""提示词页表构建、KV 观测与 VPN 生命周期。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from memory.buddy_allocator import BuddyAllocator
from memory.canonical_messages import (
    assemble_messages_from_pages,
    canonical_message_dict,
    canonical_messages_bytes,
    content_hash_bytes,
    content_hash_text,
    get_static_prefix_cache,
    message_content_to_str,
)
from memory.page_compressor import PageCompressor
from memory.prompt_page_types import (
    COMPRESSION_RAW,
    PAGE_FLAG_COMPRESSED,
    VARIABLE_PAGE_TYPES,
    allowed_in_template,
    compression_max_for,
    default_flags_for,
)

__all__ = [
    "PromptPage",
    "PromptVPN",
    "PromptPageTableBuilder",
    "resolve_kv_observation",
    "vpn_trace_payload",
]


def _tokens_per_page() -> int:
    try:
        return max(200, int(os.getenv("PROMPT_TOKENS_PER_PAGE", "800")))
    except ValueError:
        return 800


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, (len(text) + 1) // 2)


def split_text_by_tokens(text: str, budget: int) -> List[str]:
    if not text:
        return [""]
    if estimate_tokens(text) <= budget:
        return [text]
    lines = text.splitlines(keepends=True)
    chunks: List[str] = []
    buf: List[str] = []
    buf_tokens = 0
    for ln in lines:
        lt = estimate_tokens(ln)
        if buf and buf_tokens + lt > budget:
            chunks.append("".join(buf))
            buf = [ln]
            buf_tokens = lt
        else:
            buf.append(ln)
            buf_tokens += lt
    if buf:
        chunks.append("".join(buf))
    if not chunks:
        return [text[: budget * 2]]
    return chunks


def infer_tool_fact_page_type(fact_body: str) -> str:
    """根据「本步事实」正文推断 tool_fact_* 页类型。"""
    text = fact_body or ""
    low = text.lower()
    if "delete.target" in low or "delete.target_id" in low:
        return "tool_fact_delete"
    if "delete" in low and ("删除" in text or "target_id" in low):
        return "tool_fact_delete"
    if "create.target" in low or "create preview" in low:
        return "tool_fact_create"
    if "create" in low and ("新建" in text or "创建" in text or "card_id" in low):
        return "tool_fact_create"
    if "modify.target" in low:
        if "before" in low or "after" in low or "diff" in low:
            return "tool_fact_modify"
        return "tool_fact_grep"
    if "grep" in low and ("命中" in text or "hit" in low):
        return "tool_fact_grep"
    return "tool_fact"


def infer_page_type(
    content: str,
    *,
    role: str,
    slot: int,
    msg_index: int,
    chunk_index: int,
) -> str:
    low = (content or "").lower()
    if role == "system":
        if msg_index == 0 and chunk_index == 0:
            return "system_core"
        if "tool" in low or "function" in low or "schema" in low or "参数" in content:
            return "tools_schema"
        if "project" in low or "计划" in content or "plan_id" in low:
            return "project_ctx"
        return "workflow_rules"
    if role == "user":
        if "本步事实" in content:
            fact_body = content.split("本步事实：", 1)[-1] if "本步事实：" in content else content
            if "\n\n" in fact_body:
                fact_body = fact_body.split("\n\n", 1)[0]
            return infer_tool_fact_page_type(fact_body)
        if "grep" in low and ("命中" in content or "hit" in low):
            return "tool_fact_grep"
        if "create.target" in low or ("create" in low and "新建" in content):
            return "tool_fact_create"
        if "delete.target" in low or ("delete" in low and "删除" in content):
            return "tool_fact_delete"
        if any(k in content for k in ("target=", "record_id", "ui_context", "view=")):
            if estimate_tokens(content) <= 400:
                return "ui_context_core"
        return "user_turn"
    if role == "assistant":
        if "本步事实" in content:
            fact_body = content.split("本步事实：", 1)[-1] if "本步事实：" in content else content
            if "\n\n" in fact_body:
                fact_body = fact_body.split("\n\n", 1)[0]
            pt = infer_tool_fact_page_type(fact_body)
            if pt != "tool_fact":
                return pt
        if "modify.target" in content:
            if "before" in low or "after" in low or "diff" in low:
                return "tool_fact_modify"
            return "tool_fact_grep"
        if "grep" in low and ("命中" in content or "hit" in low):
            return "tool_fact_grep"
        if "## 已确认" in content or "running_summary" in low:
            return "session_prefix"
        return "observe_nl"
    if role == "tool":
        if "modify" in low and ("diff" in low or "before" in low):
            return "tool_fact_modify"
        if "modify" in low:
            return "tool_fact_grep"
        if "create" in low:
            return "tool_fact_create"
        if "delete" in low:
            return "tool_fact_delete"
        return "tool_fact_grep"
    if "modifications" in low or ("modify" in low and "params" in low):
        return "tool_param"
    return "user_turn"


def split_message_into_segments(role: str, content: str) -> List[Tuple[str, str]]:
    """将单条 message 拆成 (page_type, text) 段；macro_compact 下工具事实与用户指令分页。"""
    if not content:
        return [("user_turn" if role == "user" else "", "")]

    if role == "user" and "本步事实：" in content:
        head, _, tail_block = content.partition("本步事实：")
        segments: List[Tuple[str, str]] = []
        if head.strip():
            segments.append(("user_turn", head))
        if "\n\n" in tail_block:
            fact_part, user_part = tail_block.split("\n\n", 1)
            fact_text = f"本步事实：{fact_part}"
            segments.append((infer_tool_fact_page_type(fact_part), fact_text))
            if user_part.strip():
                segments.append(("user_turn", user_part))
        else:
            fact_text = f"本步事实：{tail_block}"
            segments.append((infer_tool_fact_page_type(tail_block), fact_text))
        return segments

    return [("", content)]


@dataclass
class PromptPage:
    slot: int
    page_type: str
    content: str
    content_hash: str
    token_count: int
    flags: int
    compression_level: int
    compression_max: int
    role: str = "user"
    msg_index: int = 0
    kv_status: str = "NEW_PAGE"

    @classmethod
    def from_content(
        cls,
        *,
        slot: int,
        page_type: str,
        content: str,
        role: str,
        msg_index: int,
    ) -> "PromptPage":
        flags = default_flags_for(page_type)
        return cls(
            slot=slot,
            page_type=page_type,
            content=content,
            content_hash=content_hash_text(content),
            token_count=estimate_tokens(content),
            flags=flags,
            compression_level=COMPRESSION_RAW if compression_max_for(page_type) == COMPRESSION_RAW else 0,
            compression_max=compression_max_for(page_type),
            role=role,
            msg_index=msg_index,
        )


@dataclass
class PromptVPN:
    session_id: str
    request_id: str
    template: str
    phase: str
    pages: List[PromptPage] = field(default_factory=list)
    buddy_start: int = 0
    buddy_order: int = 0
    total_tokens: int = 0
    static_prefix_hash: str = ""
    messages: List[Dict[str, Any]] = field(default_factory=list)

    def page_hashes(self) -> List[str]:
        return [p.content_hash for p in self.pages]


@dataclass
class PromptPageTableBuilder:
    compressor: PageCompressor = field(default_factory=PageCompressor)
    buddy: BuddyAllocator = field(default_factory=BuddyAllocator)

    def build_vpn(
        self,
        messages: Sequence[Dict[str, Any]],
        *,
        session_id: str = "",
        request_id: str = "",
        template: str = "full",
        phase: str = "decide",
        locale: str = "",
        tools_version: str = "",
        project_id: str = "",
    ) -> PromptVPN:
        msgs = [canonical_message_dict(m) for m in messages]
        pages: List[PromptPage] = []
        slot = 0
        budget = _tokens_per_page()
        for mi, msg in enumerate(msgs):
            role = str(msg.get("role") or "user")
            content = message_content_to_str(msg.get("content"))
            for seg_type, seg_text in split_message_into_segments(role, content):
                for ci, chunk in enumerate(split_text_by_tokens(seg_text, budget)):
                    page_type = seg_type or infer_page_type(
                        chunk, role=role, slot=slot, msg_index=mi, chunk_index=ci
                    )
                    if not allowed_in_template(page_type, template):
                        continue
                    page = PromptPage.from_content(
                        slot=slot,
                        page_type=page_type,
                        content=chunk,
                        role=role,
                        msg_index=mi,
                    )
                    pages.append(page)
                    slot += 1

        vpn = PromptVPN(
            session_id=session_id or "",
            request_id=request_id or "",
            template=template,
            phase=phase,
            pages=pages,
            messages=list(msgs),
        )
        self._compress_pages(vpn)
        if pages:
            start, order = self.buddy.alloc(len(pages))
            vpn.buddy_start = start
            vpn.buddy_order = order
            for p in pages:
                self.buddy.register_hash(p.content_hash, start + p.slot)
                self.buddy.touch(start + p.slot)
        vpn.total_tokens = sum(p.token_count for p in pages)
        vpn.static_prefix_hash = self._cache_static_prefix(
            vpn,
            locale=locale,
            tools_version=tools_version,
            project_id=project_id,
        )
        return vpn

    def _compress_pages(self, vpn: PromptVPN) -> None:
        saved = 0
        for page in vpn.pages:
            before = page.token_count
            result = self.compressor.compress(
                page.content,
                page_type=page.page_type,
                level="auto",
                token_estimator=estimate_tokens,
            )
            page.content = result.content
            page.content_hash = content_hash_text(page.content)
            page.token_count = estimate_tokens(page.content)
            if result.blocked:
                page.kv_status = "COMPRESSION_BLOCKED"
            if result.level == COMPRESSION_RAW:
                page.compression_level = 0
            elif result.level >= 0:
                page.compression_level = result.level
                if result.level > 0:
                    page.flags |= PAGE_FLAG_COMPRESSED
            saved += max(0, before - page.token_count)
        vpn.total_tokens = sum(p.token_count for p in vpn.pages)
        self._compression_saved = saved

    def _cache_static_prefix(
        self,
        vpn: PromptVPN,
        *,
        locale: str,
        tools_version: str,
        project_id: str,
    ) -> str:
        static_types = {"system_core", "tools_schema", "workflow_rules", "project_ctx"}
        static_msgs: List[Dict[str, Any]] = []
        seen_msg_idx = set()
        for p in vpn.pages:
            if p.page_type not in static_types:
                continue
            if p.msg_index in seen_msg_idx:
                continue
            seen_msg_idx.add(p.msg_index)
            if p.msg_index < len(vpn.messages):
                static_msgs.append(vpn.messages[p.msg_index])
        if not static_msgs:
            return ""
        blob = canonical_messages_bytes(static_msgs)
        digest = content_hash_bytes(blob)
        cache = get_static_prefix_cache()
        key = cache.build_key(
            locale=locale,
            tools_version=tools_version,
            project_id=project_id,
            template=vpn.template,
        )
        cache.put(key, static_msgs, blob, digest)
        return digest

    def release_vpn(self, vpn: Optional[PromptVPN]) -> None:
        if not vpn:
            return
        seen = set()
        for p in vpn.pages:
            if p.content_hash in seen:
                continue
            seen.add(p.content_hash)
            self.buddy.release_hash(p.content_hash)
        try:
            max_cold = int(os.getenv("PROMPT_BUDDY_MAX_COLD_FRAMES", "256"))
        except ValueError:
            max_cold = 256
        self.buddy.maybe_evict(max_cold_frames=max_cold)

    def reassemble_messages(self, vpn: PromptVPN) -> List[Dict[str, Any]]:
        if not vpn.pages:
            return [canonical_message_dict(m) for m in vpn.messages]
        by_idx: Dict[int, List[PromptPage]] = {}
        for p in vpn.pages:
            by_idx.setdefault(p.msg_index, []).append(p)
        out: List[Dict[str, Any]] = []
        for mi in sorted(by_idx.keys()):
            if mi >= len(vpn.messages):
                continue
            base = vpn.messages[mi]
            pages = sorted(by_idx[mi], key=lambda x: x.slot)
            content = "".join(p.content for p in pages)
            msg: Dict[str, Any] = {"role": base.get("role", "user"), "content": content}
            for k in ("name", "tool_calls", "tool_call_id"):
                if base.get(k) is not None:
                    msg[k] = base[k]
            out.append(canonical_message_dict(msg))
        return out


def resolve_kv_observation(
    vpn: PromptVPN,
    prev: Optional[PromptVPN],
) -> Dict[str, Any]:
    prev_hashes = prev.page_hashes() if prev else []
    prev_pages = prev.pages if prev else []
    cache_hit = 0
    drift = 0
    new_pages = 0
    tail_changed = 0
    for i, page in enumerate(vpn.pages):
        if i < len(prev_hashes) and prev_hashes[i] == page.content_hash:
            page.kv_status = "CACHE_HIT"
            cache_hit += 1
        elif i < len(prev_hashes):
            prev_type = prev_pages[i].page_type if i < len(prev_pages) else ""
            if page.page_type in VARIABLE_PAGE_TYPES or prev_type in VARIABLE_PAGE_TYPES:
                page.kv_status = "TAIL_CHANGED"
                tail_changed += 1
            else:
                page.kv_status = "PREFIX_DRIFT"
                drift += 1
        else:
            page.kv_status = "NEW_PAGE"
            new_pages += 1
    total = len(vpn.pages) or 1
    prefix_pages = max(0, len(vpn.pages) - 1)
    prefix_hits = sum(
        1 for p in vpn.pages[:-1] if p.kv_status == "CACHE_HIT"
    ) if len(vpn.pages) > 1 else cache_hit
    prefix_total = max(1, prefix_pages)
    prefill_pages = sum(1 for p in vpn.pages if p.kv_status != "CACHE_HIT")
    prefill_tokens = sum(
        p.token_count for p in vpn.pages if p.kv_status != "CACHE_HIT"
    )
    return {
        "total_pages": len(vpn.pages),
        "prefill_pages": prefill_pages,
        "cache_hit_pages": cache_hit,
        "prefix_drift_pages": drift,
        "tail_changed_pages": tail_changed,
        "new_pages": new_pages,
        "cache_hit_ratio": round(cache_hit / total, 4),
        "prefix_cache_hit_ratio": round(prefix_hits / prefix_total, 4),
        "prefill_tokens": prefill_tokens,
        "buddy_order": vpn.buddy_order,
        "template": vpn.template,
        "phase": vpn.phase,
        "static_prefix_hash": vpn.static_prefix_hash,
    }


def vpn_trace_payload(
    vpn: PromptVPN,
    stats: Dict[str, Any],
    *,
    compression_saved_tokens: int = 0,
    ttft_ms: Optional[float] = None,
    early_execute_ms: Optional[float] = None,
    tool_start_ms: Optional[float] = None,
    fc_stream: Optional[bool] = None,
) -> Dict[str, Any]:
    data = dict(stats)
    data["compression_saved_tokens"] = compression_saved_tokens
    data["decode_tokens"] = data.get("decode_tokens", 0)
    if ttft_ms is not None:
        data["ttft_ms"] = round(ttft_ms, 2)
    if early_execute_ms is not None:
        data["early_execute_ms"] = round(early_execute_ms, 2)
    if tool_start_ms is not None:
        data["tool_start_ms"] = round(tool_start_ms, 2)
    if fc_stream is not None:
        data["fc_stream"] = bool(fc_stream)
    data["page_types"] = [p.page_type for p in vpn.pages]
    return data
