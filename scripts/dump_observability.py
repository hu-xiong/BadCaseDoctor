#!/usr/bin/env python3
"""
一次性导出 Prometheus 指标文本 + 列出最近 agent trace 文件。

用法（项目根目录）：
  python scripts/dump_observability.py
  python scripts/dump_observability.py --request-id <react_request_id>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_SDK = _ROOT / "sdk"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump observability artifacts")
    parser.add_argument("--request-id", dest="request_id", default="")
    args = parser.parse_args()

    from utils.observability import flush_observability, trace_dir

    paths = flush_observability(prefix="manual")
    print("=== Prometheus text export ===")
    for k, v in paths.items():
        print(f"{k}: {v}")

    td = trace_dir()
    print("\n=== Agent trace files ===")
    print(f"dir: {td}")
    if not td.is_dir():
        print("(no trace dir yet — run an Agent task after restarting app.py)")
        return 0

    files = sorted(td.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in files[:15]:
        print(f"  {p.name}  ({p.stat().st_size} bytes)")

    rid = (args.request_id or "").strip()
    if rid:
        run_file = td / f"run_{rid}.jsonl"
        print(f"\n=== Trace for run {rid} ===")
        if not run_file.is_file():
            print(f"missing {run_file}")
            return 1
        for line in run_file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                print(line)
                continue
            print(json.dumps(ev, ensure_ascii=False, indent=2))
        return 0

    print("\nTip: python scripts/dump_observability.py --request-id <uuid-from-sse>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
