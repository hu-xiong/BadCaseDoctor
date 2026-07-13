# -*- coding: utf-8 -*-
from agents.unified_think_stream_sanitize import create_unified_think_sanitizer


def _collect_chunks(text: str):
    san = create_unified_think_sanitizer("zh-CN")
    chunks = []
    for piece, pw in san.feed(text):
        chunks.append((piece, pw))
    for piece, pw in san.end():
        chunks.append((piece, pw))
    return chunks


def test_think_summary_streamed_after_thinking_end():
    """末行 summary：正文先流式，thinking 闭合后再出摘要。"""
    chunks = _collect_chunks(
        "<thinking>详细分析…<think_summary>准备 cdp 登录</think_summary></thinking>"
    )

    summary_parts = [p for p, w in chunks if w == "think_summary_piece"]
    body_parts = [p for p, w in chunks if w is None and p]
    assert "准备 cdp 登录" in "".join(summary_parts)
    assert "详细分析" in "".join(body_parts)
    assert "准备 cdp 登录" not in "".join(body_parts)

    thinking_end_idx = next(i for i, c in enumerate(chunks) if c[1] == "thinking_end")
    summary_idx = next(i for i, c in enumerate(chunks) if c[1] == "think_summary_piece")
    assert thinking_end_idx < summary_idx


def test_think_summary_buffered_if_model_puts_summary_first():
    """模型误把 summary 放首行时，仍等 </thinking> 后再下发。"""
    chunks = _collect_chunks(
        "<thinking><think_summary>早写结论</think_summary>详细分析…</thinking>"
    )
    thinking_end_idx = next(i for i, c in enumerate(chunks) if c[1] == "thinking_end")
    summary_idx = next(i for i, c in enumerate(chunks) if c[1] == "think_summary_piece")
    assert thinking_end_idx < summary_idx
    assert "早写结论" in "".join(p for p, w in chunks if w == "think_summary_piece")


def test_strip_think_summary_from_thinking_parse():
    from agents.prompts import _strip_xml_block

    raw = "后面正文\n<think_summary>一句结论</think_summary>"
    stripped = _strip_xml_block(raw, "think_summary")
    assert stripped == "后面正文"
    assert "一句结论" not in stripped
