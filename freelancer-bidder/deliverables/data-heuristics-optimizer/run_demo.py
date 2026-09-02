"""
Optimize Data Heuristics — demo runner

Usage:
  pip install -r requirements.txt
  python run_demo.py
  python run_demo.py --data data --out output

Replace files under data/ with the client's CSVs (same column names or adapt load.py).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from heuristics.pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run multi-CSV heuristics demo")
    parser.add_argument("--data", default="data", help="Directory with CSV sources")
    parser.add_argument("--out", default="output", help="Directory for result files")
    parser.add_argument("--horizon", type=int, default=14)
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    data_dir = (root / args.data).resolve() if not Path(args.data).is_absolute() else Path(args.data)
    out_dir = (root / args.out).resolve() if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    unified, decisions, metrics = run_pipeline(data_dir, horizon_days=args.horizon, validate=True)

    unified_path = out_dir / "unified_dataset.csv"
    decisions_path = out_dir / "decisions.csv"
    metrics_path = out_dir / "metrics.json"

    unified.to_csv(unified_path, index=False)
    decisions.to_csv(decisions_path, index=False)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    print("=== Heuristics demo OK ===")
    print(json.dumps(metrics, indent=2))
    print(f"\nUnified -> {unified_path}")
    print(f"Decisions -> {decisions_path}")
    print(f"Metrics -> {metrics_path}")
    print("\nTop actions:")
    print(decisions.head(12).to_string(index=False))


if __name__ == "__main__":
    main()
