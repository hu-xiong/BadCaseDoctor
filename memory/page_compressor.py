# -*- coding: utf-8 -*-
"""页内容压缩（L0/L1/L2）与 compression_max 硬限制。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from memory.prompt_page_types import (
    COMPRESSION_L0,
    COMPRESSION_L1,
    COMPRESSION_L2,
    COMPRESSION_RAW,
    compression_max_for,
)

__all__ = ["PageCompressor", "CompressionResult"]


@dataclass
class CompressionResult:
    content: str
    level: int
    blocked: bool = False
    saved_tokens: int = 0


class PageCompressor:
    def compress(
        self,
        content: str,
        *,
        page_type: str,
        level: str | int = "auto",
        token_estimator=None,
    ) -> CompressionResult:
        raw = content if isinstance(content, str) else str(content or "")
        max_level = compression_max_for(page_type)
        if max_level == COMPRESSION_RAW:
            est = self._estimate(raw, token_estimator)
            return CompressionResult(content=raw, level=COMPRESSION_RAW, saved_tokens=0)

        target = self._resolve_level(level, page_type, max_level)
        if target > max_level:
            est = self._estimate(raw, token_estimator)
            return CompressionResult(
                content=raw,
                level=COMPRESSION_L0 if max_level == COMPRESSION_L0 else max_level,
                blocked=True,
                saved_tokens=0,
            )

        before = self._estimate(raw, token_estimator)
        if target <= COMPRESSION_L0:
            out = self._l0(raw)
            after = self._estimate(out, token_estimator)
            return CompressionResult(
                content=out,
                level=COMPRESSION_L0,
                saved_tokens=max(0, before - after),
            )
        if target == COMPRESSION_L1:
            out = self._l1(raw, page_type)
            after = self._estimate(out, token_estimator)
            return CompressionResult(
                content=out,
                level=COMPRESSION_L1,
                saved_tokens=max(0, before - after),
            )
        if target == COMPRESSION_L2:
            out = self._l2(raw, page_type)
            after = self._estimate(out, token_estimator)
            return CompressionResult(
                content=out,
                level=COMPRESSION_L2,
                saved_tokens=max(0, before - after),
            )
        return CompressionResult(content=raw, level=COMPRESSION_L0, saved_tokens=0)

    def _resolve_level(self, level: str | int, page_type: str, max_level: int) -> int:
        if isinstance(level, int):
            return min(level, max_level)
        if level == "auto":
            if max_level >= COMPRESSION_L2 and page_type in ("observe_nl", "session_prefix"):
                return COMPRESSION_L2
            if max_level >= COMPRESSION_L1 and page_type in (
                "tool_fact_grep",
                "tool_fact_create",
                "tool_fact_delete",
                "tool_fact",
            ):
                return COMPRESSION_L1
            return COMPRESSION_L0
        if level in ("raw", "RAW"):
            return COMPRESSION_RAW
        if level in ("l0", "L0", 0):
            return COMPRESSION_L0
        if level in ("l1", "L1", 1):
            return COMPRESSION_L1
        if level in ("l2", "L2", 2):
            return COMPRESSION_L2
        return COMPRESSION_L0

    def _l0(self, text: str) -> str:
        t = text.strip()
        t = re.sub(r"[ \t]+\n", "\n", t)
        t = re.sub(r"\n{3,}", "\n\n", t)
        t = self._try_json_minify(t)
        return t

    def _l1(self, text: str, page_type: str) -> str:
        base = self._l0(text)
        if page_type not in (
            "tool_fact_grep",
            "tool_fact_create",
            "tool_fact_delete",
            "tool_fact",
        ):
            return base
        lines = [ln.strip() for ln in base.splitlines() if ln.strip()]
        rows = []
        for ln in lines:
            if ln.startswith("|") and ln.endswith("|"):
                rows.append(ln)
                continue
            if re.match(r"^[-*]\s+", ln) or re.match(r"^\d+[.)]\s+", ln):
                rows.append(ln)
                continue
            if len(ln) > 120:
                rows.append(ln[:117] + "...")
            else:
                rows.append(ln)
        return "\n".join(rows[:40])

    def _l2(self, text: str, page_type: str) -> str:
        base = self._l1(text, page_type) if page_type in (
            "tool_fact_grep",
            "tool_fact_create",
            "tool_fact_delete",
            "tool_fact",
        ) else self._l0(text)
        lines = [ln.strip() for ln in base.splitlines() if ln.strip()]
        if page_type == "session_prefix":
            keep = [ln for ln in lines if ln.startswith("##") or ln.startswith("-")]
            return "\n".join(keep[:24]) if keep else base[:600]
        if page_type == "observe_nl":
            one = " ".join(lines)
            if len(one) > 400:
                one = one[:397] + "..."
            return f"FACT:{one}"
        return base[:800]

    def _try_json_minify(self, text: str) -> str:
        s = text.strip()
        if not s or s[0] not in "{[":
            return text
        try:
            obj = json.loads(s)
            return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        except Exception:
            return text

    def _estimate(self, text: str, token_estimator=None) -> int:
        if token_estimator is not None:
            return int(token_estimator(text))
        if not text:
            return 0
        return max(1, (len(text) + 1) // 2)
