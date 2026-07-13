# -*- coding: utf-8 -*-
"""
远端 Elasticsearch 压测（与 Grep hybrid 路径一致的操作）。

用法（项目根目录）:
  python scripts/benchmark_remote_es.py
  python scripts/benchmark_remote_es.py --repeats 50 --project-id 1
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _stats_ms(samples: List[float]) -> Dict[str, float]:
    if not samples:
        return {}
    s = sorted(samples)
    n = len(s)

    def pct(p: float) -> float:
        if n == 1:
            return s[0]
        idx = int(round((n - 1) * p))
        return s[max(0, min(n - 1, idx))]

    return {
        "n": float(n),
        "mean": statistics.mean(s),
        "median": statistics.median(s),
        "min": s[0],
        "max": s[-1],
        "p95": pct(0.95),
    }


def _bench(name: str, fn: Callable[[], None], repeats: int, warmup: int) -> Dict[str, float]:
    for _ in range(max(0, warmup)):
        try:
            fn()
        except Exception:
            pass
    samples: List[float] = []
    last_err: Optional[str] = None
    for _ in range(repeats):
        t0 = time.perf_counter()
        try:
            fn()
            samples.append((time.perf_counter() - t0) * 1000.0)
        except Exception as ex:
            last_err = str(ex)[:300]
            break
    st = _stats_ms(samples)
    if last_err:
        st["error"] = 1.0
        print(f"  FAIL {name}: {last_err}", flush=True)
    return st


def _fmt_stats(st: Dict[str, float]) -> str:
    if not st or st.get("error"):
        return "FAIL"
    return (
        f"mean={st['mean']:.1f}ms median={st['median']:.1f}ms "
        f"min={st['min']:.1f} p95={st['p95']:.1f} max={st['max']:.1f} (n={int(st['n'])})"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="远端 ES 压测")
    p.add_argument("--repeats", type=int, default=30, help="每项重复次数")
    p.add_argument("--warmup", type=int, default=3, help="预热次数")
    p.add_argument("--project-id", type=int, default=1)
    p.add_argument(
        "--keywords",
        default="问登录问题答的不好 复现步骤修改为 提问登录问题即可234456",
    )
    p.add_argument("--quiet", action="store_true", help="压低 GREP-ES hybrid_search 日志")
    args = p.parse_args()

    if args.quiet:
        import logging

        logging.getLogger("elastic_transport").setLevel(logging.WARNING)

    from config import Config
    from memory.es_long_memory import ESConfig, _mk_es_client
    from memory.es_work_item_store import build_work_item_store_from_config
    from memory.grep_es_config import build_embedding_client_from_config

    es_cfg = ESConfig(
        url=getattr(Config, "ES_URL", "") or "",
        host=getattr(Config, "ES_HOST", ""),
        port=int(getattr(Config, "ES_PORT", 9200)),
        username=getattr(Config, "ES_USERNAME", "") or "",
        password=getattr(Config, "ES_PASSWORD", "") or "",
        api_key=getattr(Config, "ES_API_KEY", "") or "",
        verify_certs=bool(getattr(Config, "ES_VERIFY_CERTS", True)),
    )
    host_disp = (es_cfg.url or f"{es_cfg.host}:{es_cfg.port}").strip()
    print(f"ES 目标: {host_disp}")
    print(f"alias: {getattr(Config, 'GREP_WORK_ITEM_ALIAS', '')}")
    print(f"repeats={args.repeats} warmup={args.warmup}\n")

    client = _mk_es_client(es_cfg)
    store = build_work_item_store_from_config(Config)
    alias = store.search_cfg.alias

    # 准备 hybrid 用 query 向量（不计入 ES 项）
    embed_client = build_embedding_client_from_config(Config)
    t_emb = time.perf_counter()
    qvec = embed_client.embed(args.keywords)
    emb_ms = (time.perf_counter() - t_emb) * 1000.0
    print(f"[参考] 豆包 query embed 单次: {emb_ms:.1f}ms dims={len(qvec)}\n")

    rows: List[tuple[str, Dict[str, float]]] = []

    rows.append(
        (
            "cluster.info",
            _bench("info", lambda: client.info(request_timeout=5), args.repeats, args.warmup),
        )
    )
    rows.append(
        (
            "indices.exists(alias)",
            _bench(
                "exists",
                lambda: client.indices.exists(index=alias, request_timeout=5),
                args.repeats,
                args.warmup,
            ),
        )
    )
    rows.append(
        (
            "HEAD alias (alias_exists)",
            _bench(
                "alias_exists",
                lambda: store.alias_exists(alias),
                args.repeats,
                args.warmup,
            ),
        )
    )

    def _bm25_only():
        store.hybrid_search(
            project_id=args.project_id,
            query_text=args.keywords,
            query_embedding=None,
            top_k=8,
            alias_checked=True,
            request_timeout_s=5.0,
        )

    rows.append(
        (
            "hybrid_search bm25_only",
            _bench("bm25", _bm25_only, args.repeats, args.warmup),
        )
    )

    def _knn_bm25():
        store.hybrid_search(
            project_id=args.project_id,
            query_text=args.keywords,
            query_embedding=qvec,
            top_k=8,
            alias_checked=True,
            request_timeout_s=5.0,
        )

    rows.append(
        (
            "hybrid_search knn+bm25 (Grep)",
            _bench("hybrid", _knn_bm25, args.repeats, args.warmup),
        )
    )

    print(f"{'操作':<32} {'统计'}")
    print("-" * 88)
    ok_means: List[float] = []
    for name, st in rows:
        print(f"{name:<32} {_fmt_stats(st)}")
        if st and not st.get("error"):
            ok_means.append(st["mean"])

    if ok_means:
        print()
        print(f"ES 压测项平均 mean 的算术平均: {statistics.mean(ok_means):.1f}ms")
        hybrid_st = next((st for n, st in rows if "knn+bm25" in n), None)
        if hybrid_st and not hybrid_st.get("error"):
            print(
                f"→ Grep 典型 ES 段（knn+bm25）: mean={hybrid_st['mean']:.1f}ms "
                f"median={hybrid_st['median']:.1f}ms"
            )
            print(
                f"→ 加 embed({emb_ms:.0f}ms 本次): "
                f"约 {hybrid_st['mean'] + emb_ms:.0f}ms（首包 embed 可能更慢）"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
