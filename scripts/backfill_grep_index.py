#!/usr/bin/env python3
"""全量回填 Bug/BadCase 到 ES work_item 索引（GREP_VECTOR_ENABLED=true 时使用）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill work items into ES work_item index")
    parser.add_argument("--project-id", type=int, default=None, help="仅回填指定项目")
    parser.add_argument(
        "--entity",
        choices=("bug", "badcase", "testcase", "card", "plan", "all"),
        default="all",
    )
    parser.add_argument("--sync", action="store_true", help="同步 embed+写入（默认走攒批队列）")
    parser.add_argument("--batch-log", type=int, default=50, help="进度日志间隔")
    args = parser.parse_args()

    from config import Config

    if not getattr(Config, "GREP_VECTOR_ENABLED", False):
        print("[backfill] GREP_VECTOR_ENABLED=false，请在 .env 中开启后再运行", flush=True)
        return 1

    from app import BadCase, Bug, Card, Plan, TestCase, app, db
    from memory.work_item_indexer import get_work_item_indexer

    indexer = get_work_item_indexer(Config)
    if not indexer:
        print("[backfill] indexer 初始化失败", flush=True)
        return 1

    with app.app_context():
        total_ok = 0
        total_fail = 0

        def _run_entity(et: str, q):
            nonlocal total_ok, total_fail
            n = 0
            for (rid,) in q.yield_per(200):
                ok = indexer.index_entity(et, int(rid), sync=args.sync)
                n += 1
                if ok:
                    total_ok += 1
                else:
                    total_fail += 1
                if n % max(1, args.batch_log) == 0:
                    print(f"[backfill] {et} progress={n} ok={total_ok} fail={total_fail}", flush=True)
            print(f"[backfill] {et} done count={n}", flush=True)

        if args.entity in ("bug", "all"):
            bq = db.session.query(Bug.id)
            if args.project_id:
                bq = bq.filter(Bug.project_id == int(args.project_id))
            _run_entity("bug", bq.order_by(Bug.id))

        if args.entity in ("badcase", "all"):
            cq = db.session.query(BadCase.id)
            if args.project_id:
                cq = cq.filter(BadCase.project_id == int(args.project_id))
            _run_entity("badcase", cq.order_by(BadCase.id))

        if args.entity in ("testcase", "all"):
            tq = db.session.query(TestCase.id)
            if args.project_id:
                tq = tq.filter(TestCase.project_id == int(args.project_id))
            _run_entity("testcase", tq.order_by(TestCase.id))

        if args.entity in ("card", "all"):
            card_q = db.session.query(Card.id)
            if args.project_id:
                card_q = card_q.filter(Card.project_id == int(args.project_id))
            _run_entity("card", card_q.order_by(Card.id))

        if args.entity in ("plan", "all"):
            pq = db.session.query(Plan.id)
            if args.project_id:
                pq = pq.filter(Plan.project_id == int(args.project_id))
            _run_entity("plan", pq.order_by(Plan.id))

        if not args.sync:
            flushed = indexer.flush()
            print(f"[backfill] embed queue flushed={flushed}", flush=True)

    print(f"[backfill] finished ok={total_ok} fail={total_fail}", flush=True)
    return 0 if total_fail == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
