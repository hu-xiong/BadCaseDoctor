# -*- coding: utf-8 -*-
"""
DeepSeek 前缀缓存 Round1/2 实测：
- Round1：冷前缀（engine miss 为主）
- Round2：同 session、同 canonical 前缀 + 不同 user tail（期望 engine hit_rate 升高）

用法（项目根目录）：
  python scripts/benchmark_deepseek_prefix_cache.py
  python scripts/benchmark_deepseek_prefix_cache.py --long
  python scripts/benchmark_deepseek_prefix_cache.py --long --scenario create
  python scripts/benchmark_deepseek_prefix_cache.py --long --scenario all
  python scripts/multi_round_benchmark.py --long --scenario create --runs 5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config
from llm.deepseek_llm import DeepSeekLLM, _usage_prompt_cache_fields
from memory.prefix_cache_client import parse_engine_prefix_cache
from memory.prompt_page_pipeline import (
    get_session_state,
    prepare_llm_messages,
    use_prompt_page_table,
)

# grep→modify / grep→create / grep→delete 宏路径 benchmark 场景
BENCHMARK_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "modify": {
        "label": "grep→modify",
        "system_tools": "grep, modify, create, delete",
        "tools_version": "grep|modify|create|delete",
        "fact": "本步事实：grep 命中 3 条 Bug，id=111,222,333。",
        "tails": [
            "请 modify 把 Bug 111 状态改为 resolved。",
            "请 modify 把 Bug 222 优先级改为 P1。",
            "请 grep 登录相关 Bug。",
        ],
    },
    "create": {
        "label": "grep→create",
        "system_tools": "grep, modify, create, delete",
        "tools_version": "grep|modify|create|delete",
        "fact": "本步事实：grep 命中 1 条 badcase，id=555，card_id=12。",
        "tails": [
            "请 create 新建 Bug，标题「登录失败」，优先级 P2。",
            "请 create 新建 Bug，标题「支付超时」，优先级 P1。",
        ],
    },
    "delete": {
        "label": "grep→delete",
        "system_tools": "grep, modify, create, delete",
        "tools_version": "grep|modify|create|delete",
        "fact": "本步事实：grep 命中 1 条 badcase，id=777，delete.target=badcase。",
        "tails": [
            "请 delete 删除 id=777 的 badcase，confirm=false。",
            "请 delete 删除 id=888 的 badcase（若存在），confirm=false。",
        ],
    },
}


def _long_prefix_messages(
    user_tail: str,
    *,
    long_mode: bool = False,
    scenario: Dict[str, Any],
) -> list:
    rules = "宏规则与工具说明：grep/modify/create/delete 步骤。"
    if long_mode:
        rules = rules + (" 详细约束与示例。" * 200)
    system = (
        f"你是 BadCaseDoctor 测试助手。使用 grep/modify/create/delete 工具。\n"
        f"工具 schema：{scenario['system_tools']}。\n"
        f"{rules}\n"
        f"project_ctx: demo_project"
    )
    fact = str(scenario.get("fact") or "")
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{fact}\n\n{user_tail}"},
    ]


def _chunk_content_delta(chunk: Any) -> str:
    try:
        if chunk.choices:
            return getattr(chunk.choices[0].delta, "content", None) or ""
    except Exception:
        pass
    return ""


def _call_deepseek(llm: DeepSeekLLM, messages: list) -> dict:
    """流式调用：分离 TTFT / decode / completion_tokens，避免总延迟误导。"""
    from llm.chat_messages import normalize_chat_messages

    messages = normalize_chat_messages(messages)
    t0 = time.perf_counter()
    ttft_ms: Optional[float] = None
    content_parts: list[str] = []
    usage = None

    stream = llm._chat_create(messages, stream=True, enable_thinking=False)
    for chunk in stream:
        delta = _chunk_content_delta(chunk)
        if delta and ttft_ms is None:
            ttft_ms = (time.perf_counter() - t0) * 1000.0
        if delta:
            content_parts.append(delta)
        u = getattr(chunk, "usage", None)
        if u is not None:
            usage = u

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    if ttft_ms is None:
        ttft_ms = elapsed_ms
    decode_ms = max(0.0, elapsed_ms - ttft_ms)

    engine = parse_engine_prefix_cache(usage) or {}
    if usage is not None:
        from llm.deepseek_llm import _log_deepseek_prefix_cache_line

        _log_deepseek_prefix_cache_line(usage, model=llm.model, tag="completion_messages_stream")

    prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
    completion_tokens = getattr(usage, "completion_tokens", None) if usage else None

    return {
        "elapsed_ms": round(elapsed_ms, 1),
        "ttft_ms": round(ttft_ms, 1),
        "decode_ms": round(decode_ms, 1),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "content_len": len("".join(content_parts)),
        "engine": engine,
        "raw_usage": _usage_prompt_cache_fields(usage),
    }


def _format_round_line(row: dict, *, scenario_label: str = "") -> str:
    prefix = f"[{scenario_label}] " if scenario_label else ""
    return (
        f"{prefix}"
        f"Round {row['round']}: "
        f"prefill={row.get('app_prefill_tokens')} "
        f"eng_hit={row.get('engine_hit_rate')} "
        f"drift={row.get('app_prefix_drift_pages')} | "
        f"TTFT={row.get('ttft_ms')}ms "
        f"decode={row.get('decode_ms')}ms "
        f"completion_tok={row.get('completion_tokens')} "
        f"total={row.get('elapsed_ms')}ms"
    )


def run_scenario_benchmark(
    llm: DeepSeekLLM,
    *,
    scenario_key: str,
    scenario: Dict[str, Any],
    session: str,
    long_mode: bool,
    rounds: int,
) -> List[Dict[str, Any]]:
    os.environ["DEEPSEEK_KV_USER_ID"] = session
    tails: List[str] = list(scenario.get("tails") or [])
    if not tails:
        raise ValueError(f"scenario {scenario_key} 缺少 tails")

    print(f"\n>>> 场景 {scenario_key} ({scenario.get('label', scenario_key)}) session={session}")
    print("-" * 60)

    results: List[Dict[str, Any]] = []
    for i in range(max(2, rounds)):
        tail = tails[i % len(tails)]
        raw_msgs = _long_prefix_messages(tail, long_mode=long_mode, scenario=scenario)
        prepared = prepare_llm_messages(
            raw_msgs,
            session_id=session,
            request_id=f"{session}_r{i + 1}",
            template="macro_compact",
            phase="benchmark",
            round_idx=i,
            locale="zh",
            tools_version=str(scenario.get("tools_version") or "default"),
            project_id="demo_project",
        )
        st = get_session_state(session)
        app_stats = dict(st.last_stats or {})
        api_result = _call_deepseek(llm, prepared)
        row = {
            "scenario": scenario_key,
            "round": i + 1,
            "user_tail": tail[:40],
            "app_cache_hit_ratio": app_stats.get("cache_hit_ratio"),
            "app_prefill_tokens": app_stats.get("prefill_tokens"),
            "app_prefix_drift_pages": app_stats.get("prefix_drift_pages"),
            "engine_hit_rate": (api_result.get("engine") or {}).get(
                "engine_prefix_cache_hit_rate"
            ),
            "engine_hit_tokens": (api_result.get("engine") or {}).get(
                "engine_prefix_cache_hit_tokens"
            ),
            "engine_miss_tokens": (api_result.get("engine") or {}).get(
                "engine_prefix_cache_miss_tokens"
            ),
            "ttft_ms": api_result.get("ttft_ms"),
            "decode_ms": api_result.get("decode_ms"),
            "prompt_tokens": api_result.get("prompt_tokens"),
            "completion_tokens": api_result.get("completion_tokens"),
            "elapsed_ms": api_result["elapsed_ms"],
        }
        results.append(row)
        print(_format_round_line(row, scenario_label=str(scenario.get("label") or scenario_key)))
        if i == 0:
            time.sleep(0.5)
    return results


def _load_compare_helpers():
    try:
        from scripts.compare_prompt_cache_performance import (
            build_performance_comparison,
            calls_from_benchmark_results,
            print_performance_comparison,
        )
        return build_performance_comparison, calls_from_benchmark_results, print_performance_comparison
    except ImportError:
        import importlib.util

        cmp_path = ROOT / "scripts" / "compare_prompt_cache_performance.py"
        spec = importlib.util.spec_from_file_location("cmp_pcc", cmp_path)
        cmp_mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cmp_mod)
        return (
            cmp_mod.build_performance_comparison,
            cmp_mod.calls_from_benchmark_results,
            cmp_mod.print_performance_comparison,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--session", default="bench_prefix_cache_session")
    parser.add_argument("--long", action="store_true", help="使用 ~2k token 长前缀")
    parser.add_argument(
        "--scenario",
        default="modify",
        choices=list(BENCHMARK_SCENARIOS.keys()) + ["all"],
        help="benchmark 场景：modify/create/delete/all",
    )
    args = parser.parse_args()

    if not (Config.DEEPSEEK_API_KEY or "").strip():
        print("ERROR: DEEPSEEK_API_KEY 未配置，无法实测。")
        return 1

    os.environ.setdefault("PROMPT_PAGE_TABLE_ENABLED", "1")
    os.environ.setdefault("PROMPT_PAGE_CANONICAL_ASSEMBLE", "1")

    llm = DeepSeekLLM()
    print(f"model={llm.model} base={Config.DEEPSEEK_API_BASE_URL}")
    print(f"page_table={use_prompt_page_table()} scenario={args.scenario} long={args.long}")

    scenario_keys = list(BENCHMARK_SCENARIOS.keys()) if args.scenario == "all" else [args.scenario]
    all_results: List[Dict[str, Any]] = []

    build_performance_comparison, calls_from_benchmark_results, print_performance_comparison = (
        _load_compare_helpers()
    )

    for sk in scenario_keys:
        session = args.session if len(scenario_keys) == 1 else f"{args.session}_{sk}"
        scenario = BENCHMARK_SCENARIOS[sk]
        results = run_scenario_benchmark(
            llm,
            scenario_key=sk,
            scenario=scenario,
            session=session,
            long_mode=args.long,
            rounds=args.rounds,
        )
        all_results.extend(results)
        if len(results) >= 2:
            calls = calls_from_benchmark_results(results)
            report = build_performance_comparison(calls)
            print()
            print(f"=== 对比表 · {scenario.get('label', sk)} ===")
            print_performance_comparison(report)

    print(json.dumps(all_results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
