# -*- coding: utf-8 -*-
"""
LangSmith 金路径离线评测。

用法：
  # 本地 dry-run（不需要 API Key，适合 CI / 定时任务先自检）
  python -m evals.langsmith.run_eval --dry-run

  # 上传到 LangSmith（需 LANGSMITH_API_KEY）
  set LANGSMITH_API_KEY=lsv2_...
  set LANGSMITH_TRACING=1
  python -m evals.langsmith.run_eval --upload

  # 指定实验前缀
  python -m evals.langsmith.run_eval --upload --prefix nightly-golden
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

# 保证项目根在 path
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("LANGGRAPH_CHECKPOINTER", "memory")
os.environ.setdefault("LANGGRAPH_OBSERVE", "0")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="BadCaseDoctor LangSmith golden-path eval")
    p.add_argument("--dry-run", action="store_true", help="本地打分，不上传 LangSmith")
    p.add_argument("--upload", action="store_true", help="创建/更新 dataset 并 evaluate 上传")
    p.add_argument("--prefix", default="", help="experiment_prefix")
    p.add_argument(
        "--out",
        default="",
        help="结果 JSON 路径（默认 evals/langsmith/results/latest.json）",
    )
    return p.parse_args()


def _results_path(explicit: str) -> Path:
    if explicit:
        return Path(explicit)
    d = Path(__file__).resolve().parent / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d / "latest.json"


def run_dry() -> Dict[str, Any]:
    # 禁止 dry-run 误连 LangSmith 云端
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    try:
        import agents.langsmith_tracing as _lt

        _lt._setup_done = False
    except Exception:
        pass

    from evals.langsmith.evaluators import local_score
    from evals.langsmith.harness import load_dataset, run_example

    ds = load_dataset()
    rows: List[Dict[str, Any]] = []
    means: List[float] = []
    for ex in ds.get("examples") or []:
        inputs = ex.get("inputs") or {}
        ref = ex.get("outputs") or {}
        outs = run_example(inputs)
        scores = local_score(outs, ref)
        means.append(float(scores.get("_mean") or 0.0))
        rows.append(
            {
                "id": ex.get("id"),
                "inputs": inputs,
                "outputs": outs,
                "scores": scores,
            }
        )
    overall = sum(means) / len(means) if means else 0.0
    return {
        "mode": "dry-run",
        "dataset": ds.get("dataset_name"),
        "overall_mean": overall,
        "n": len(rows),
        "examples": rows,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def run_upload(prefix: str) -> Dict[str, Any]:
    os.environ["LANGSMITH_EVAL_ALLOW_TRACE"] = "1"
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"

    from agents.langsmith_tracing import langsmith_project, setup_langsmith_tracing
    from evals.langsmith.evaluators import all_evaluators
    from evals.langsmith.harness import load_dataset, run_example
    from langsmith import Client, evaluate

    # 强制重读 tracing 开关
    import agents.langsmith_tracing as _lt

    _lt._setup_done = False
    if not setup_langsmith_tracing(force=True):
        raise SystemExit(
            "需要 LANGSMITH_API_KEY 且 LANGSMITH_TRACING=1（或仅设 API Key）才能 --upload"
        )

    ds = load_dataset()
    name = str(ds.get("dataset_name") or "badcase-golden-path")
    client = Client()

    # 幂等：已有则复用，否则创建
    existing = None
    try:
        existing = client.read_dataset(dataset_name=name)
    except Exception:
        existing = None
    if existing is None:
        existing = client.create_dataset(
            dataset_name=name,
            description=str(ds.get("description") or "BadCaseDoctor golden path"),
        )
        for ex in ds.get("examples") or []:
            client.create_example(
                inputs=ex.get("inputs") or {},
                outputs=ex.get("outputs") or {},
                dataset_id=existing.id,
                metadata={"example_id": ex.get("id")},
            )
        print(f"[LANGSMITH] created dataset={name} id={existing.id}", flush=True)
    else:
        print(f"[LANGSMITH] reuse dataset={name} id={existing.id}", flush=True)

    exp_prefix = (prefix or "").strip() or f"golden-{datetime.now().strftime('%Y%m%d-%H%M')}"
    results = evaluate(
        run_example,
        data=name,
        evaluators=all_evaluators(),
        experiment_prefix=exp_prefix,
        metadata={
            "app": "badcase_doctor",
            "suite": "golden_path",
            "project": langsmith_project(),
        },
        max_concurrency=1,
        client=client,
        upload_results=True,
    )

    # ExperimentResults 可迭代；尽量提取摘要
    summary: Dict[str, Any] = {
        "mode": "upload",
        "dataset": name,
        "experiment_prefix": exp_prefix,
        "project": langsmith_project(),
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    try:
        summary["experiment_name"] = getattr(results, "experiment_name", None) or str(results)
    except Exception:
        summary["experiment_name"] = str(results)
    return summary


def main() -> int:
    args = _parse_args()
    if not args.dry_run and not args.upload:
        args.dry_run = True  # 默认本地

    if args.upload:
        report = run_upload(args.prefix)
    else:
        report = run_dry()

    out = _results_path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in report if k != "examples"}, ensure_ascii=False, indent=2))
    print(f"[LANGSMITH-EVAL] wrote {out}", flush=True)

    if report.get("mode") == "dry-run":
        mean = float(report.get("overall_mean") or 0.0)
        if mean < 0.99:
            print(f"[LANGSMITH-EVAL] FAIL overall_mean={mean}", flush=True)
            return 1
        print(f"[LANGSMITH-EVAL] PASS overall_mean={mean}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
