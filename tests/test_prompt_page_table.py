# -*- coding: utf-8 -*-
from memory.page_compressor import PageCompressor
from memory.prefix_cache_client import merge_engine_stats_into, parse_engine_prefix_cache
from memory.prompt_page_table import (
    PromptPageTableBuilder,
    infer_tool_fact_page_type,
    resolve_kv_observation,
)
from memory.prompt_page_pipeline import (
    LlmStreamTimer,
    prepare_llm_messages,
    preflight_agent_request,
    tools_version_from_names,
)
from memory.canonical_messages import messages_to_prompt


class _Usage:
    prompt_cache_hit_tokens = 900
    prompt_cache_miss_tokens = 100
    prompt_tokens = 1000
    completion_tokens = 50


def test_parse_engine_prefix_cache():
    fields = parse_engine_prefix_cache(_Usage())
    assert fields is not None
    assert fields["engine_prefix_cache_hit_rate"] == 0.9


def test_merge_engine_stats_delta():
    merged = merge_engine_stats_into(
        {"cache_hit_ratio": 0.85},
        {"engine_prefix_cache_hit_rate": 0.9},
    )
    assert merged["cache_hit_delta"] == -0.05


def test_compressor_l2_observe_nl():
    c = PageCompressor()
    text = "这是一段很长的 observe 自然语言观察结果。\n" * 20
    r = c.compress(text, page_type="observe_nl", level="auto")
    assert r.level == 2
    assert r.content.startswith("FACT:")


def test_reassemble_uses_page_content():
    b = PromptPageTableBuilder()
    msgs = [{"role": "user", "content": "  hello   world  "}]
    vpn = b.build_vpn(msgs)
    out = b.reassemble_messages(vpn)
    assert out[0]["content"] == vpn.pages[0].content


def test_build_vpn_and_cache_hit_second_round():
    msgs = [
        {"role": "system", "content": "你是测试助手。\n工具：grep, modify"},
        {"role": "user", "content": "请 grep 登录 bug"},
    ]
    b = PromptPageTableBuilder()
    v1 = b.build_vpn(msgs, session_id="s1", request_id="r1")
    s2 = resolve_kv_observation(
        b.build_vpn(msgs, session_id="s1", request_id="r2"), v1
    )
    assert s2["cache_hit_ratio"] >= 0.5


def test_macro_compact_grep_fact_user_tail_no_prefix_drift():
    """grep 事实与用户 tail 分页后，仅 tail 变化不应计为 prefix 漂移。"""
    b = PromptPageTableBuilder()
    sys_msg = {"role": "system", "content": "rules\n" + ("detail " * 50)}
    tail1 = "请 modify 把 Bug 111 状态改为 resolved。"
    tail2 = "请 modify 把 Bug 222 优先级改为 P1。"
    fact = "本步事实：grep 命中 3 条 Bug，id=111,222,333。"
    v1 = b.build_vpn(
        [sys_msg, {"role": "user", "content": f"{fact}\n\n{tail1}"}],
        template="macro_compact",
    )
    v2 = b.build_vpn(
        [sys_msg, {"role": "user", "content": f"{fact}\n\n{tail2}"}],
        template="macro_compact",
    )
    stats = resolve_kv_observation(v2, v1)
    assert stats["prefix_drift_pages"] == 0
    assert stats["tail_changed_pages"] == 1
    types = [p.page_type for p in v2.pages]
    assert "tool_fact_grep" in types
    assert types.count("user_turn") == 1
    grep_page = next(p for p in v2.pages if p.page_type == "tool_fact_grep")
    assert grep_page.kv_status == "CACHE_HIT"


def test_infer_tool_fact_page_type_create_delete():
    assert infer_tool_fact_page_type("grep 命中 1 条，id=1") == "tool_fact_grep"
    assert infer_tool_fact_page_type("create.target=badcase，card_id=12") == "tool_fact_create"
    assert infer_tool_fact_page_type("delete.target=badcase，delete.target_id=7") == "tool_fact_delete"


def test_macro_compact_create_fact_user_tail_no_prefix_drift():
    b = PromptPageTableBuilder()
    sys_msg = {"role": "system", "content": "rules\n" + ("detail " * 50)}
    fact = "本步事实：grep 命中 1 条 badcase，id=555，card_id=12。"
    tail1 = "请 create 新建 Bug，标题「登录失败」。"
    tail2 = "请 create 新建 Bug，标题「支付超时」。"
    v1 = b.build_vpn(
        [sys_msg, {"role": "user", "content": f"{fact}\n\n{tail1}"}],
        template="macro_compact",
    )
    v2 = b.build_vpn(
        [sys_msg, {"role": "user", "content": f"{fact}\n\n{tail2}"}],
        template="macro_compact",
    )
    stats = resolve_kv_observation(v2, v1)
    assert stats["prefix_drift_pages"] == 0
    assert stats["tail_changed_pages"] == 1
    fact_page = next(p for p in v2.pages if p.page_type == "tool_fact_grep")
    assert fact_page.kv_status == "CACHE_HIT"


def test_macro_compact_delete_fact_user_tail_no_prefix_drift():
    b = PromptPageTableBuilder()
    sys_msg = {"role": "system", "content": "rules\n" + ("detail " * 50)}
    fact = "本步事实：grep 命中 1 条 badcase，id=777，delete.target=badcase。"
    tail1 = "请 delete 删除 id=777。"
    tail2 = "请 delete 删除 id=888。"
    v1 = b.build_vpn(
        [sys_msg, {"role": "user", "content": f"{fact}\n\n{tail1}"}],
        template="macro_compact",
    )
    v2 = b.build_vpn(
        [sys_msg, {"role": "user", "content": f"{fact}\n\n{tail2}"}],
        template="macro_compact",
    )
    stats = resolve_kv_observation(v2, v1)
    assert stats["prefix_drift_pages"] == 0
    assert stats["tail_changed_pages"] == 1
    fact_page = next(p for p in v2.pages if p.page_type == "tool_fact_delete")
    assert fact_page.kv_status == "CACHE_HIT"


def test_macro_compact_skips_session_prefix():
    msgs = [
        {"role": "system", "content": "rules"},
        {"role": "assistant", "content": "## 已确认\n- 第1步 grep"},
        {"role": "user", "content": "target=bug record_id=999"},
    ]
    b = PromptPageTableBuilder()
    full = b.build_vpn(msgs, template="full")
    compact = b.build_vpn(msgs, template="macro_compact")
    assert "session_prefix" in {p.page_type for p in full.pages}
    assert "session_prefix" not in {p.page_type for p in compact.pages}


def test_prepare_canonical_assemble(monkeypatch):
    monkeypatch.setenv("PROMPT_PAGE_TABLE_ENABLED", "1")
    monkeypatch.setenv("PROMPT_PAGE_CANONICAL_ASSEMBLE", "1")
    msgs = [{"role": "user", "content": "  hello   world  "}]
    out = prepare_llm_messages(msgs, session_id="t2", request_id="t2")
    assert out[0]["content"] == "hello   world"


def test_messages_to_prompt_roundtrip():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "usr"},
    ]
    p = messages_to_prompt(msgs)
    assert "<system>" in p
    assert "usr" in p


def test_preflight_agent_request():
    stats = preflight_agent_request(session_id="sess1", user_id="u1")
    assert stats.get("allowed") is True


def test_tools_version_from_names():
    v1 = tools_version_from_names(["modify", "grep"])
    v2 = tools_version_from_names(["grep", "modify"])
    assert v1 == v2


def test_llm_stream_timer_first_chunk():
    class _Chunk:
        class _Choice:
            delta = type("D", (), {"content": "hi"})()

        choices = [_Choice()]

    timer = LlmStreamTimer("sid", request_id="sid", fc_stream=True)
    timer.on_fc_chunk(_Chunk())
    st = __import__("memory.prompt_page_pipeline", fromlist=["get_session_state"]).get_session_state("sid")
    assert st.pending_timing.get("ttft_ms") is not None
