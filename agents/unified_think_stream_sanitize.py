# -*- coding: utf-8 -*-
"""
统一流 LLM 输出 → 对前端 SSE 可见文本：不下发原始 XML 标签，改为本地化语义标记；
缓冲未完成标签，避免 <observation 被拆成 <o + bservation> 泄漏到用户正文。

注意：parse_unified_response 仍使用 run_stream 里单独累积的「原文」全文，与此处下发内容无关。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

MAX_TAIL = 96
# 闭合标签可能跨 chunk，保留后缀供匹配
CLOSE_TAIL = 32


def _lower_find(hay: str, needle: str, start: int = 0) -> int:
    return hay.lower().find(needle.lower(), start)


def _end_of_open_tag(work: str, pos: int, name_lower: str) -> int:
    if _lower_find(work, f"<{name_lower}", pos) != pos:
        return -1
    gt = work.find(">", pos)
    return gt


@dataclass
class UnifiedThinkStreamSanitizer:
    """块级状态机 + 语义标记（前端不再解析 XML，仅此后端实现）。"""

    markers: Dict[str, str]
    mode: str = "neutral"  # neutral | in_thinking | in_observation | in_decision | in_task_plan
    prev_mode: str = ""  # 进入 task_plan 前的模式
    tail: str = ""

    def feed(self, chunk: str) -> List[Tuple[str, Optional[str]]]:
        """
        返回 (text_piece, decision_phase_wait)：
        decision_phase_wait 为 'start' | 'end' 时由上层发 phase_wait（决策块内为隐藏 XML）。
        """
        out: List[Tuple[str, Optional[str]]] = []
        work = self.tail + (chunk or "")
        self.tail = ""
        m = self.markers

        guard = 0
        while work and guard < 200000:
            guard += 1
            if self.mode == "neutral":
                work = self._neutral(work, out, m)
                continue
            if self.mode == "in_thinking":
                work = self._in_thinking(work, out, m)
                continue
            if self.mode == "in_task_plan":
                work = self._in_task_plan(work, out, m)
                continue
            if self.mode == "in_observation":
                work = self._in_observation(work, out, m)
                continue
            if self.mode == "in_decision":
                work = self._in_decision(work, out, m)
                continue
            self.mode = "neutral"

        return out

    def end(self) -> List[Tuple[str, Optional[str]]]:
        """流结束：吐出尾部（非标签碎片）。"""
        if not self.tail:
            return []
        t = self.tail
        self.tail = ""
        if self.mode != "neutral":
            # 异常截断：尽量不丢字
            return [(t, None)]
        return [(t, None)]

    def _neutral(self, work: str, out: List[Tuple[str, Optional[str]]], m: Dict[str, str]) -> str:
        t_think = _lower_find(work, "<thinking", 0)
        t_dec = _lower_find(work, "<decision", 0)
        t_obs = _lower_find(work, "<observation", 0)
        first = min(
            t_think if t_think >= 0 else 2**30,
            t_dec if t_dec >= 0 else 2**30,
            t_obs if t_obs >= 0 else 2**30,
        )
        if first >= 2**30:
            lt = work.rfind("<")
            if lt >= 0 and len(work) - lt <= MAX_TAIL:
                out.append((work[:lt], None))
                self.tail = work[lt:]
            else:
                out.append((work, None))
            return ""

        if first > 0:
            out.append((work[:first], None))
            return work[first:]

        if _lower_find(work, "<thinking", 0) == 0:
            gt = _end_of_open_tag(work, 0, "thinking")
            if gt < 0:
                self._stash_incomplete_tag(work, out)
                return ""
            # 输出开始标记和阶段信息（用于前端阶段切换）
            out.append((m["thinking_start"], "thinking_start"))
            self.mode = "in_thinking"
            return work[gt + 1 :]

        if _lower_find(work, "<decision", 0) == 0:
            gt = _end_of_open_tag(work, 0, "decision")
            if gt < 0:
                self._stash_incomplete_tag(work, out)
                return ""
            # 输出开始标记和阶段信息
            out.append((m["decision_start"], "decision_start"))
            out.append(("", "start"))
            self.mode = "in_decision"
            return work[gt + 1 :]

        if _lower_find(work, "<observation", 0) == 0:
            gt = _end_of_open_tag(work, 0, "observation")
            if gt < 0:
                self._stash_incomplete_tag(work, out)
                return ""
            # 输出开始标记和阶段信息
            out.append((m["observation_start"], "observation_start"))
            self.mode = "in_observation"
            return work[gt + 1 :]

        out.append((work[0], None))
        return work[1:]

    def _stash_incomplete_tag(self, work: str, out: List[Tuple[str, Optional[str]]]) -> None:
        lt = work.rfind("<")
        if lt >= 0 and len(work) - lt <= MAX_TAIL:
            out.append((work[:lt], None))
            self.tail = work[lt:]
        elif len(work) > MAX_TAIL:
            out.append((work[: len(work) - MAX_TAIL], None))
            self.tail = work[-MAX_TAIL:]
        else:
            self.tail = work

    def _in_thinking(self, work: str, out: List[Tuple[str, Optional[str]]], m: Dict[str, str]) -> str:
        t_task = _lower_find(work, "<task_plan", 0)
        close = _lower_find(work, "</thinking>", 0)
        # 嵌套 <task_plan>：须在 </thinking> 之前处理；前文先出字
        if t_task >= 0 and (close < 0 or t_task < close):
            if t_task > 0:
                out.append((work[:t_task], None))
                return work[t_task:]
            gt = _end_of_open_tag(work, 0, "task_plan")
            if gt < 0:
                self._stash_thinking_tail(work, out)
                return ""
            out.append((m["task_plan_start"], "task_plan_start"))
            self.prev_mode = self.mode
            self.mode = "in_task_plan"
            return work[gt + 1 :]

        if close < 0:
            # 可能截断 </thinking>：保留后缀
            if len(work) > CLOSE_TAIL:
                safe = work[:-CLOSE_TAIL]
                self.tail = work[-CLOSE_TAIL:]
                if safe:
                    out.append((safe, None))
            else:
                self.tail = work
            return ""

        out.append((work[:close], None))
        out.append((m["thinking_end"], "thinking_end"))
        self.mode = "neutral"
        return work[close + len("</thinking>") :]

    def _stash_thinking_tail(self, work: str, out: List[Tuple[str, Optional[str]]]) -> None:
        lt = work.rfind("<")
        if lt >= 0 and len(work) - lt <= MAX_TAIL:
            if lt > 0:
                out.append((work[:lt], None))
            self.tail = work[lt:]
        elif len(work) > MAX_TAIL:
            out.append((work[: len(work) - MAX_TAIL], None))
            self.tail = work[-MAX_TAIL:]
        else:
            self.tail = work

    def _in_task_plan(self, work: str, out: List[Tuple[str, Optional[str]]], m: Dict[str, str]) -> str:
        close = _lower_find(work, "</task_plan>", 0)
        if close < 0:
            if len(work) > CLOSE_TAIL:
                self.tail = work[-CLOSE_TAIL:]
            else:
                self.tail = work
            return ""

        out.append((m["task_plan_end"], "task_plan_end"))
        self.mode = self.prev_mode or "in_thinking"
        return work[close + len("</task_plan>") :]

    def _in_observation(self, work: str, out: List[Tuple[str, Optional[str]]], m: Dict[str, str]) -> str:
        close = _lower_find(work, "</observation>", 0)
        if close < 0:
            if len(work) > CLOSE_TAIL:
                safe = work[:-CLOSE_TAIL]
                self.tail = work[-CLOSE_TAIL:]
                if safe:
                    out.append((safe, None))
            else:
                self.tail = work
            return ""

        out.append((work[:close], None))
        out.append((m["observation_end"], "observation_end"))
        self.mode = "neutral"
        return work[close + len("</observation>") :]

    def _in_decision(self, work: str, out: List[Tuple[str, Optional[str]]], m: Dict[str, str]) -> str:
        t_task = _lower_find(work, "<task_plan", 0)
        close = _lower_find(work, "</decision>", 0)
        # 嵌套 <task_plan>：须在 </decision> 之前处理；decision 内 XML 不向用户 SSE 推送
        if t_task >= 0 and (close < 0 or t_task < close):
            if t_task > 0:
                return work[t_task:]
            gt = _end_of_open_tag(work, 0, "task_plan")
            if gt < 0:
                self.tail = work
                return ""
            out.append((m["task_plan_start"], "task_plan_start"))
            self.prev_mode = self.mode
            self.mode = "in_task_plan"
            return work[gt + 1 :]

        if close < 0:
            if len(work) > CLOSE_TAIL:
                self.tail = work[-CLOSE_TAIL:]
            else:
                self.tail = work
            return ""

        out.append((m["decision_end"], "decision_end"))
        out.append(("", "end"))
        self.mode = "neutral"
        return work[close + len("</decision>") :]


def create_unified_think_sanitizer(locale: Optional[str]) -> UnifiedThinkStreamSanitizer:
    from .locale_prompts import react_unified_sse_xml_markers

    return UnifiedThinkStreamSanitizer(markers=react_unified_sse_xml_markers(locale))
