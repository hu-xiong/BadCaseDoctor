# -*- coding: utf-8
"""
从 agent trace 或 benchmark 结果对比 Round1 vs Round2 前缀缓存性能。

用法（项目根目录）：
  python scripts/compare_prompt_cache_performance.py --request-id <react_request_id>
  python scripts/compare_prompt_cache_performance.py --latest
  python scripts/compare_prompt_cache_performance.py --run-benchmark --long
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass
class LlmCallPerf:
    index: int
    round_idx: Optional[int] = None
    phase: str = ""
    ts: str = ""
    app_cache_hit_ratio: Optional[float] = None
    app_prefill_tokens: Optional[int] = None
    prefix_drift_pages: Optional[int] = None
    total_pages: Optional[int] = None
    engine_hit_rate: Optional[float] = None
    engine_hit_tokens: Optional[int] = None
    engine_miss_tokens: Optional[int] = None
    ttft_ms: Optional[float] = None
    decode_ms: Optional[float] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    early_execute_ms: Optional[float] = None
    tool_start_ms: Optional[float] = None
    elapsed_ms: Optional[float] = None
    fc_stream: Optional[bool] = None

    def as_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


def _pct_delta(before: Optional[float], after: Optional[float]) -> Optional[float]:
    if before is None or after is None:
        return None
    if before == 0:
        return None
    return round((after - before) / before * 100.0, 1)


def _abs_delta(before: Optional[float], after: Optional[float]) -> Optional[float]:
    if before is None or after is None:
        return None
    return round(after - before, 2)


def build_performance_comparison(
    calls: List[LlmCallPerf],
    *,
    baseline_index: int = 0,
    compare_index: int = 1,
) -> Dict[str, Any]:
    """Round1 vs Round2（或任意两轮）性能对比摘要。"""
    if len(calls) <= compare_index:
        return {"error": "需要至少 2 次 LLM 调用记录", "calls": len(calls)}

    r1 = calls[baseline_index]
    r2 = calls[compare_index]
    out: Dict[str, Any] = {
        "baseline": {"label": f"Call#{baseline_index + 1}", **r1.as_dict()},
        "compare": {"label": f"Call#{compare_index + 1}", **r2.as_dict()},
        "delta": {},
        "verdict": "",
    }

    delta = out["delta"]
    delta["app_cache_hit_ratio"] = _abs_delta(r1.app_cache_hit_ratio, r2.app_cache_hit_ratio)
    delta["app_prefill_tokens"] = _abs_delta(
        float(r1.app_prefill_tokens) if r1.app_prefill_tokens is not None else None,
        float(r2.app_prefill_tokens) if r2.app_prefill_tokens is not None else None,
    )
    delta["app_prefill_tokens_pct"] = _pct_delta(
        float(r1.app_prefill_tokens) if r1.app_prefill_tokens is not None else None,
        float(r2.app_prefill_tokens) if r2.app_prefill_tokens is not None else None,
    )
    delta["engine_hit_rate"] = _abs_delta(r1.engine_hit_rate, r2.engine_hit_rate)
    delta["engine_hit_tokens"] = _abs_delta(
        float(r1.engine_hit_tokens) if r1.engine_hit_tokens is not None else None,
        float(r2.engine_hit_tokens) if r2.engine_hit_tokens is not None else None,
    )
    delta["ttft_ms"] = _abs_delta(r1.ttft_ms, r2.ttft_ms)
    delta["ttft_ms_pct"] = _pct_delta(r1.ttft_ms, r2.ttft_ms)
    delta["decode_ms"] = _abs_delta(r1.decode_ms, r2.decode_ms)
    delta["decode_ms_pct"] = _pct_delta(r1.decode_ms, r2.decode_ms)
    delta["completion_tokens"] = _abs_delta(
        float(r1.completion_tokens) if r1.completion_tokens is not None else None,
        float(r2.completion_tokens) if r2.completion_tokens is not None else None,
    )
    delta["elapsed_ms"] = _abs_delta(r1.elapsed_ms, r2.elapsed_ms)
    delta["elapsed_ms_pct"] = _pct_delta(r1.elapsed_ms, r2.elapsed_ms)
    delta["early_execute_ms"] = _abs_delta(r1.early_execute_ms, r2.early_execute_ms)
    delta["tool_start_ms"] = _abs_delta(r1.tool_start_ms, r2.tool_start_ms)

    eng2 = r2.engine_hit_rate
    prefill_drop = delta.get("app_prefill_tokens_pct")
    ttft_drop = delta.get("ttft_ms_pct")
    decode_drop = delta.get("decode_ms_pct")
    elapsed_drop = delta.get("elapsed_ms_pct")

    if eng2 is not None and float(eng2) >= 0.5 and ttft_drop is not None and ttft_drop <= -10:
        out["verdict"] = "PASS：引擎前缀命中 >= 50% 且 TTFT 明显下降"
    elif eng2 is not None and float(eng2) >= 0.5:
        out["verdict"] = "PASS：DeepSeek 前缀命中率 >= 50%，prefill 优化生效"
    elif eng2 is not None and float(eng2) - float(r1.engine_hit_rate or 0) >= 0.1:
        out["verdict"] = "PARTIAL：命中率明显提升，但未达 50%"
    elif prefill_drop is not None and prefill_drop <= -20:
        out["verdict"] = "PARTIAL：应用侧 prefill_tokens 明显下降（引擎 stats 可能缺失）"
    elif ttft_drop is not None and ttft_drop <= -15:
        out["verdict"] = "PARTIAL：TTFT 明显下降"
    else:
        out["verdict"] = "WARN：未观察到明显前缀缓存收益（前缀太短/漂移/首轮）"

    return out


def _print_table(title: str, rows: List[tuple], delta: Dict[str, Any]) -> None:
    print("=" * 72)
    print(title)
    print("=" * 72)
    print(f"{'指标':<28} {'Round1':>12} {'Round2':>12} {'变化':>14}")
    print("-" * 72)
    for label, v1, v2, d, pct_key in rows:
        if v1 is None and v2 is None:
            continue
        d_str = ""
        if d is not None:
            d_str = f"{d:+.2f}"
            pct = delta.get(pct_key) if pct_key else None
            if pct is not None:
                d_str += f" ({pct:+.1f}%)"
        print(f"{label:<28} {str(v1 if v1 is not None else '-'):>12} {str(v2 if v2 is not None else '-'):>12} {d_str:>14}")
    print("-" * 72)


def print_performance_comparison(report: Dict[str, Any]) -> None:
    if report.get("error"):
        print(f"ERROR: {report['error']} (calls={report.get('calls', 0)})")
        return

    base = report["baseline"]
    cmp = report["compare"]
    delta = report["delta"]

    cache_rows = [
        ("应用 cache_hit_ratio", base.get("app_cache_hit_ratio"), cmp.get("app_cache_hit_ratio"), delta.get("app_cache_hit_ratio"), None),
        ("应用 prefill_tokens", base.get("app_prefill_tokens"), cmp.get("app_prefill_tokens"), delta.get("app_prefill_tokens"), "app_prefill_tokens_pct"),
        ("前缀漂移页数", base.get("prefix_drift_pages"), cmp.get("prefix_drift_pages"), None, None),
        ("DeepSeek hit_rate", base.get("engine_hit_rate"), cmp.get("engine_hit_rate"), delta.get("engine_hit_rate"), None),
        ("DeepSeek hit_tokens", base.get("engine_hit_tokens"), cmp.get("engine_hit_tokens"), delta.get("engine_hit_tokens"), None),
        ("DeepSeek miss_tokens", base.get("engine_miss_tokens"), cmp.get("engine_miss_tokens"), None, None),
    ]
    _print_table("表1 · 前缀缓存 / Prefill", cache_rows, delta)

    latency_rows = [
        ("TTFT (ms)", base.get("ttft_ms"), cmp.get("ttft_ms"), delta.get("ttft_ms"), "ttft_ms_pct"),
        ("Decode 阶段 (ms)", base.get("decode_ms"), cmp.get("decode_ms"), delta.get("decode_ms"), "decode_ms_pct"),
        ("completion_tokens", base.get("completion_tokens"), cmp.get("completion_tokens"), delta.get("completion_tokens"), None),
        ("prompt_tokens", base.get("prompt_tokens"), cmp.get("prompt_tokens"), None, None),
        ("端到端 total (ms)", base.get("elapsed_ms"), cmp.get("elapsed_ms"), delta.get("elapsed_ms"), "elapsed_ms_pct"),
        ("early_execute (ms)", base.get("early_execute_ms"), cmp.get("early_execute_ms"), delta.get("early_execute_ms"), None),
        ("tool_start (ms)", base.get("tool_start_ms"), cmp.get("tool_start_ms"), delta.get("tool_start_ms"), None),
    ]
    _print_table("表2 · 延迟分解（看 TTFT，别看 total）", latency_rows, delta)

    print(f"结论: {report.get('verdict', '')}")
    print("提示: total ≈ TTFT + decode；decode 随 completion_tokens 波动，不宜单独评判 cache。")
    print("=" * 72)


def parse_trace_file(path: Path) -> List[LlmCallPerf]:
    events: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    calls: List[LlmCallPerf] = []
    pending: Dict[int, LlmCallPerf] = {}

    for ev in events:
        span = ev.get("span") or ""
        data = ev.get("data") or {}
        rnd = ev.get("round")
        if rnd is None and isinstance(data.get("round"), int):
            rnd = data.get("round")

        if span == "prompt.pages":
            idx = len(calls)
            call = LlmCallPerf(
                index=idx,
                round_idx=rnd if isinstance(rnd, int) else idx,
                phase=str(data.get("phase") or ""),
                ts=str(ev.get("ts") or ""),
                app_cache_hit_ratio=data.get("cache_hit_ratio"),
                app_prefill_tokens=data.get("prefill_tokens"),
                prefix_drift_pages=data.get("prefix_drift_pages"),
                total_pages=data.get("total_pages"),
                fc_stream=data.get("fc_stream"),
            )
            calls.append(call)
            key = call.round_idx if call.round_idx is not None else idx
            pending[key] = call
            continue

        key = rnd if isinstance(rnd, int) else (len(calls) - 1 if calls else 0)
        target = pending.get(key) or (calls[-1] if calls else None)
        if target is None:
            continue

        if span == "prompt.pages.timing":
            target.ttft_ms = data.get("ttft_ms")
            target.decode_ms = data.get("decode_ms")
            target.completion_tokens = data.get("completion_tokens")
            target.prompt_tokens = data.get("prompt_tokens")
            target.early_execute_ms = data.get("early_execute_ms")
            target.tool_start_ms = data.get("tool_start_ms")
            if data.get("fc_stream") is not None:
                target.fc_stream = data.get("fc_stream")
        elif span == "kv.engine_prefix_cache":
            target.engine_hit_rate = data.get("engine_prefix_cache_hit_rate")
            target.engine_hit_tokens = data.get("engine_prefix_cache_hit_tokens")
            target.engine_miss_tokens = data.get("engine_prefix_cache_miss_tokens")

    return calls


def load_trace_calls(*, request_id: str = "", latest: bool = False) -> List[LlmCallPerf]:
    from utils.observability import trace_dir

    td = trace_dir()
    if request_id:
        path = td / f"run_{request_id}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"未找到 trace: {path}")
        return parse_trace_file(path)

    if latest:
        files = sorted(td.glob("run_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files:
            calls = parse_trace_file(p)
            if len(calls) >= 1:
                print(f"使用 trace: {p.name} ({len(calls)} 次 prompt.pages)")
                return calls
        raise FileNotFoundError(f"{td} 下无含 prompt.pages 的 run_*.jsonl")

    raise ValueError("请指定 --request-id 或 --latest")


def calls_from_benchmark_results(results: List[Dict[str, Any]]) -> List[LlmCallPerf]:
    out: List[LlmCallPerf] = []
    for i, row in enumerate(results):
        out.append(
            LlmCallPerf(
                index=i,
                round_idx=row.get("round", i + 1),
                app_cache_hit_ratio=row.get("app_cache_hit_ratio"),
                app_prefill_tokens=row.get("app_prefill_tokens"),
                prefix_drift_pages=row.get("app_prefix_drift_pages"),
                engine_hit_rate=row.get("engine_hit_rate"),
                engine_hit_tokens=row.get("engine_hit_tokens"),
                engine_miss_tokens=row.get("engine_miss_tokens"),
                ttft_ms=row.get("ttft_ms"),
                decode_ms=row.get("decode_ms"),
                prompt_tokens=row.get("prompt_tokens"),
                completion_tokens=row.get("completion_tokens"),
                elapsed_ms=row.get("elapsed_ms"),
            )
        )
    return out


def run_benchmark_and_compare(
    *,
    long_mode: bool,
    session: str,
    json_output: bool = False,
    scenario: str = "modify",
) -> int:
    from config import Config
    from llm.deepseek_llm import DeepSeekLLM
    from scripts.benchmark_deepseek_prefix_cache import BENCHMARK_SCENARIOS, run_scenario_benchmark

    os.environ.setdefault("PROMPT_PAGE_TABLE_ENABLED", "1")
    os.environ.setdefault("PROMPT_PAGE_CANONICAL_ASSEMBLE", "1")

    if not (Config.DEEPSEEK_API_KEY or "").strip():
        print("ERROR: DEEPSEEK_API_KEY 未配置")
        return 1

    llm = DeepSeekLLM()
    scenario_keys = list(BENCHMARK_SCENARIOS.keys()) if scenario == "all" else [scenario]
    print(f"benchmark model={llm.model} long={long_mode} scenario={scenario}\n")

    for sk in scenario_keys:
        sc = BENCHMARK_SCENARIOS[sk]
        sess = session if len(scenario_keys) == 1 else f"{session}_{sk}"
        results = run_scenario_benchmark(
            llm,
            scenario_key=sk,
            scenario=sc,
            session=sess,
            long_mode=long_mode,
            rounds=2,
        )
        if len(results) < 2:
            continue
        calls = calls_from_benchmark_results(results)
        report = build_performance_comparison(calls)
        print(f"\n=== 对比表 · {sc.get('label', sk)} ===")
        print_performance_comparison(report)
        if json_output:
            print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Round1 vs Round2 前缀缓存性能对比")
    parser.add_argument("--request-id", default="", help="react_request_id / SSE request_id")
    parser.add_argument("--latest", action="store_true", help="使用最新含 prompt.pages 的 run trace")
    parser.add_argument("--run-benchmark", action="store_true", help="现场跑 DeepSeek Round1/2 并对比")
    parser.add_argument("--long", action="store_true", help="benchmark 使用长前缀")
    parser.add_argument(
        "--scenario",
        default="modify",
        choices=["modify", "create", "delete", "all"],
        help="benchmark 场景",
    )
    parser.add_argument("--session", default="bench_perf_compare")
    parser.add_argument("--json", action="store_true", help="额外输出 JSON")
    args = parser.parse_args()

    if args.run_benchmark:
        return run_benchmark_and_compare(
            long_mode=args.long,
            session=args.session,
            json_output=args.json,
            scenario=args.scenario,
        )

    try:
        calls = load_trace_calls(request_id=args.request_id.strip(), latest=args.latest)
    except (FileNotFoundError, ValueError) as ex:
        print(f"ERROR: {ex}")
        return 1

    if len(calls) < 2:
        print(f"WARN: 仅 {len(calls)} 次 prompt.pages，无法做 Round1/2 对比")
        for c in calls:
            print(json.dumps(c.as_dict(), ensure_ascii=False))
        return 1

    report = build_performance_comparison(calls)
    print_performance_comparison(report)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
