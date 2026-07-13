# -*- coding: utf-8 -*-
"""多轮 Round1(cold) + Round2(hot) benchmark，分离 TTFT / decode / completion。"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Config
from llm.deepseek_llm import DeepSeekLLM
from scripts.benchmark_deepseek_prefix_cache import (
    BENCHMARK_SCENARIOS,
    _call_deepseek,
    _long_prefix_messages,
)
from memory.prompt_page_pipeline import get_session_state, prepare_llm_messages


def _stat(label: str, values: list[float]) -> str:
    if not values:
        return f"{label}: (empty)"
    if len(values) == 1:
        return f"{label}: {values[0]:.0f}"
    return (
        f"{label}: min={min(values):.0f}  p50={statistics.median(values):.0f}  "
        f"mean={statistics.mean(values):.0f}  max={max(values):.0f}  "
        f"stdev={statistics.stdev(values):.0f}"
    )


def _run_pair(
    llm: DeepSeekLLM,
    *,
    scenario_key: str,
    scenario: dict,
    session: str,
    long_mode: bool,
) -> tuple[dict, dict]:
    os.environ["DEEPSEEK_KV_USER_ID"] = session
    tails = list(scenario.get("tails") or [])[:2]
    rows = []
    for i, tail in enumerate(tails):
        raw = _long_prefix_messages(tail, long_mode=long_mode, scenario=scenario)
        prepared = prepare_llm_messages(
            raw,
            session_id=session,
            request_id=f"{session}_r{i + 1}",
            template="macro_compact",
            phase="benchmark",
            round_idx=i,
            locale="zh",
            tools_version=str(scenario.get("tools_version") or "default"),
            project_id="demo",
        )
        st = get_session_state(session)
        api = _call_deepseek(llm, prepared)
        rows.append(
            {
                "prefill": (st.last_stats or {}).get("prefill_tokens"),
                "drift": (st.last_stats or {}).get("prefix_drift_pages"),
                "eng_hit": (api.get("engine") or {}).get("engine_prefix_cache_hit_rate"),
                "ttft_ms": api.get("ttft_ms"),
                "decode_ms": api.get("decode_ms"),
                "completion_tokens": api.get("completion_tokens"),
                "elapsed_ms": api.get("elapsed_ms"),
            }
        )
        if i == 0:
            time.sleep(0.5)
    return rows[0], rows[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5, help="cold/hot 配对次数")
    parser.add_argument("--long", action="store_true")
    parser.add_argument("--prefix", default="multi_bench")
    parser.add_argument(
        "--scenario",
        default="modify",
        choices=list(BENCHMARK_SCENARIOS.keys()) + ["all"],
    )
    args = parser.parse_args()

    if not (Config.DEEPSEEK_API_KEY or "").strip():
        print("ERROR: DEEPSEEK_API_KEY 未配置")
        return 1

    os.environ.setdefault("PROMPT_PAGE_TABLE_ENABLED", "1")
    os.environ.setdefault("PROMPT_PAGE_CANONICAL_ASSEMBLE", "1")

    llm = DeepSeekLLM()
    scenario_keys = list(BENCHMARK_SCENARIOS.keys()) if args.scenario == "all" else [args.scenario]

    for sk in scenario_keys:
        scenario = BENCHMARK_SCENARIOS[sk]
        print(f"\nmodel={llm.model} runs={args.runs} long={args.long} scenario={sk}")
        print("=" * 100)

        metrics: dict[str, list[float]] = {
            "r1_ttft": [],
            "r2_ttft": [],
            "r1_decode": [],
            "r2_decode": [],
            "r1_completion": [],
            "r2_completion": [],
            "r1_total": [],
            "r2_total": [],
            "r2_prefill": [],
            "r2_drift": [],
            "ttft_speedup_pct": [],
        }

        for run in range(args.runs):
            session = f"{args.prefix}_{sk}_{run}"
            r1, r2 = _run_pair(
                llm, scenario_key=sk, scenario=scenario, session=session, long_mode=args.long
            )
            metrics["r1_ttft"].append(float(r1["ttft_ms"] or 0))
            metrics["r2_ttft"].append(float(r2["ttft_ms"] or 0))
            metrics["r1_decode"].append(float(r1["decode_ms"] or 0))
            metrics["r2_decode"].append(float(r2["decode_ms"] or 0))
            metrics["r1_completion"].append(float(r1["completion_tokens"] or 0))
            metrics["r2_completion"].append(float(r2["completion_tokens"] or 0))
            metrics["r1_total"].append(float(r1["elapsed_ms"] or 0))
            metrics["r2_total"].append(float(r2["elapsed_ms"] or 0))
            metrics["r2_prefill"].append(float(r2["prefill"] or 0))
            metrics["r2_drift"].append(float(r2["drift"] or 0))
            if r1["ttft_ms"]:
                metrics["ttft_speedup_pct"].append(
                    (float(r1["ttft_ms"]) - float(r2["ttft_ms"])) / float(r1["ttft_ms"]) * 100.0
                )
            print(
                f"Run {run + 1:>2} R1: TTFT={r1['ttft_ms']:>6.0f}ms decode={r1['decode_ms']:>6.0f}ms "
                f"completion={r1['completion_tokens']:>3} total={r1['elapsed_ms']:>6.0f}ms"
            )
            print(
                f"        R2: TTFT={r2['ttft_ms']:>6.0f}ms decode={r2['decode_ms']:>6.0f}ms "
                f"completion={r2['completion_tokens']:>3} prefill={r2['prefill']} "
                f"drift={r2['drift']} eng={r2['eng_hit']} total={r2['elapsed_ms']:>6.0f}ms"
            )

        print("=" * 100)
        print(f"场景: {scenario.get('label', sk)}")
        print("表1 · Prefill / Cache（Round2）")
        print(_stat("R2 app prefill_tokens", metrics["r2_prefill"]))
        print(_stat("R2 prefix_drift_pages", metrics["r2_drift"]))
        print()
        print("表2 · TTFT（前缀 cache 主要影响此项）")
        print(_stat("Round1 TTFT (ms)", metrics["r1_ttft"]))
        print(_stat("Round2 TTFT (ms)", metrics["r2_ttft"]))
        print(_stat("R2 vs R1 TTFT speedup (%)", metrics["ttft_speedup_pct"]))
        print()
        print("表3 · Decode / Completion")
        print(_stat("Round1 decode (ms)", metrics["r1_decode"]))
        print(_stat("Round2 decode (ms)", metrics["r2_decode"]))
        print(_stat("Round1 completion_tokens", metrics["r1_completion"]))
        print(_stat("Round2 completion_tokens", metrics["r2_completion"]))
        print()
        print("表4 · 端到端 total（= TTFT + decode，仅供参考）")
        print(_stat("Round1 total (ms)", metrics["r1_total"]))
        print(_stat("Round2 total (ms)", metrics["r2_total"]))
        print("=" * 100)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
