# -*- coding: utf-8 -*-
"""Grep 向量栈后台预热：ES 连接 + embedding + 一次真实 hybrid_search（避免首条 grep 冷启动）。"""
from __future__ import annotations

import os
import time


def warmup_grep_vector_stack(cfg=None) -> None:
    if cfg is None:
        try:
            from config import Config as cfg
        except Exception:
            return
    if not bool(getattr(cfg, "GREP_VECTOR_ENABLED", False)):
        return

    from memory.es_work_item_store import build_work_item_store_from_config

    store = build_work_item_store_from_config(cfg)
    t0 = time.perf_counter()
    _es_to = float(getattr(cfg, "GREP_ES_SEARCH_TIMEOUT_S", 10) or 10)
    store.es.info(request_timeout=_es_to)
    print(
        f"[GREP-WARMUP] ES info 预热完成 {(time.perf_counter() - t0) * 1000:.0f}ms",
        flush=True,
    )

    qvec = None
    if bool(getattr(cfg, "GREP_EMBEDDING_WARMUP", True)):
        try:
            from memory.grep_es_config import build_embedding_client_from_config

            client = build_embedding_client_from_config(cfg)
            model = getattr(client.cfg, "model", "") or ""
            t1 = time.perf_counter()
            qvec = client.embed("warmup")
            print(
                f"[GREP-WARMUP] embedding 预热完成 model={model!r} "
                f"{(time.perf_counter() - t1) * 1000:.0f}ms dims={len(qvec or [])}",
                flush=True,
            )
        except Exception as e:
            print(f"[GREP-WARMUP] embedding 预热失败(忽略): {e}", flush=True)

    if not bool(getattr(cfg, "GREP_ES_SEARCH_WARMUP", True)):
        return
    try:
        pid = int((os.getenv("GREP_WARMUP_PROJECT_ID") or "1").strip())
    except ValueError:
        pid = 1
    try:
        t2 = time.perf_counter()
        # 与 Grep hybrid 同路径：knn+bm25（info 仅 ~60ms，首条 search 冷启动可达 500ms+）
        store.hybrid_search(
            project_id=pid,
            query_text="warmup",
            query_embedding=qvec if qvec else None,
            top_k=1,
            alias_checked=True,
            request_timeout_s=float(getattr(cfg, "GREP_ES_SEARCH_TIMEOUT_S", 10) or 10),
        )
        print(
            f"[GREP-WARMUP] hybrid_search 预热完成 project={pid} "
            f"{(time.perf_counter() - t2) * 1000:.0f}ms",
            flush=True,
        )
    except Exception as e:
        print(f"[GREP-WARMUP] hybrid_search 预热失败(忽略): {e}", flush=True)