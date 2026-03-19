import json
import os
import statistics
import time
from typing import Dict, List, Optional, Tuple

import requests


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((len(s) - 1) * p))
    k = max(0, min(k, len(s) - 1))
    return s[k]


def run_once(base_url: str, payload: Dict, timeout_s: float = 60.0) -> Tuple[float, float, float]:
    """
    Returns: (ttfb_ms, first_step_ms, first_reasoning_ms)
    - ttfb_ms: 从发起请求到收到第一行SSE数据
    - first_step_ms: 到收到第一条 type=step
    - first_reasoning_ms: 到收到第一条 step.event=reasoning
    """
    t0 = time.perf_counter()
    ttfb_ms: Optional[float] = None
    first_step_ms: Optional[float] = None
    first_reasoning_ms: Optional[float] = None
    max_wait_reasoning_ms = float(os.getenv("MAX_WAIT_REASONING_MS", "8000"))
    max_wait_total_ms = float(os.getenv("MAX_WAIT_TOTAL_MS", "20000"))

    with requests.post(
        f"{base_url.rstrip('/')}/api/agent/react",
        json=payload,
        stream=True,
        timeout=timeout_s,
    ) as r:
        r.raise_for_status()
        for raw in r.iter_lines(decode_unicode=True):
            now_ms = (time.perf_counter() - t0) * 1000
            if now_ms > max_wait_total_ms:
                break
            if raw is None:
                continue
            line = raw.strip()
            if not line:
                continue
            if ttfb_ms is None:
                ttfb_ms = now_ms

            if line.startswith("data:"):
                try:
                    obj = json.loads(line[5:].strip())
                except Exception:
                    continue
                if isinstance(obj, dict) and obj.get("type") == "step":
                    if first_step_ms is None:
                        first_step_ms = now_ms
                    step = obj.get("data") or {}
                    if isinstance(step, dict) and step.get("event") == "reasoning":
                        if first_reasoning_ms is None:
                            first_reasoning_ms = now_ms
                            break
                    if isinstance(step, dict) and step.get("event") == "done":
                        break
            if first_step_ms is not None and first_reasoning_ms is None and now_ms > max_wait_reasoning_ms:
                break

    return float(ttfb_ms or 0.0), float(first_step_ms or 0.0), float(first_reasoning_ms or 0.0)


def main():
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:5000")
    runs = int(os.getenv("RUNS", "10"))
    model = os.getenv("MODEL", "glm-5")
    project_id = int(os.getenv("PROJECT_ID", "1"))
    plan_id_env = os.getenv("PLAN_ID", "")
    plan_id = int(plan_id_env) if plan_id_env.strip() else None

    payload = {
        "user_input": os.getenv("PROMPT", "新增一个测试用例，标题为：perf test case"),
        "stream": True,
        "model": model,
        "project_id": project_id,
    }
    if plan_id is not None:
        payload["plan_id"] = plan_id

    ttfb_list: List[float] = []
    step_list: List[float] = []
    reasoning_list: List[float] = []

    for i in range(runs):
        ttfb_ms, first_step_ms, first_reasoning_ms = run_once(base_url, payload)
        ttfb_list.append(ttfb_ms)
        step_list.append(first_step_ms)
        reasoning_list.append(first_reasoning_ms)
        print(f"run={i+1}/{runs} ttfb_ms={ttfb_ms:.1f} first_step_ms={first_step_ms:.1f} first_reasoning_ms={first_reasoning_ms:.1f}")

    def _summary(name: str, xs: List[float]):
        print(
            f"{name}: n={len(xs)} "
            f"mean={statistics.mean(xs):.1f} "
            f"p50={_percentile(xs, 0.50):.1f} "
            f"p95={_percentile(xs, 0.95):.1f} "
            f"max={max(xs):.1f}"
        )

    print("\n=== SUMMARY (ms) ===")
    _summary("ttfb", ttfb_list)
    _summary("first_step", step_list)
    _summary("first_reasoning", reasoning_list)


if __name__ == "__main__":
    main()

