# -*- coding: utf-8 -*-
"""快速检查远程 ES 是否可达、grep 索引 alias 是否存在。"""
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config import Config  # noqa: E402


def main() -> int:
    host = str(getattr(Config, "ES_HOST", "127.0.0.1")).strip()
    port = int(getattr(Config, "ES_PORT", 9200))
    alias = str(getattr(Config, "GREP_WORK_ITEM_ALIAS", "") or "").strip()

    print("=== ES 配置 ===")
    print(f"ES_HOST={host}")
    print(f"ES_PORT={port}")
    print(f"GREP_WORK_ITEM_ALIAS={alias}")
    print(f"GREP_VECTOR_ENABLED={getattr(Config, 'GREP_VECTOR_ENABLED', None)}")
    print(f"GREP_ES_SEARCH_TIMEOUT_S={getattr(Config, 'GREP_ES_SEARCH_TIMEOUT_S', None)}")

    print("\n=== 1) TCP 探测 ===")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    t0 = time.perf_counter()
    try:
        sock.connect((host, port))
        print(f"TCP_OK {round((time.perf_counter() - t0) * 1000, 1)}ms")
    except OSError as ex:
        print(f"TCP_FAIL {round((time.perf_counter() - t0) * 1000, 1)}ms err={ex}")
        return 2
    finally:
        sock.close()

    print("\n=== 2) elasticsearch info() ===")
    t1 = time.perf_counter()
    try:
        from memory.es_work_item_store import build_work_item_store_from_config

        store = build_work_item_store_from_config(Config)
        info = store.es.info(request_timeout=15)
        print(
            f"ES_INFO_OK {round((time.perf_counter() - t1) * 1000, 1)}ms "
            f"cluster={info.get('cluster_name')} version={info.get('version', {}).get('number')}"
        )
    except Exception as ex:
        print(f"ES_INFO_FAIL {round((time.perf_counter() - t1) * 1000, 1)}ms err={ex!r}")
        return 3

    print("\n=== 3) grep alias ===")
    t2 = time.perf_counter()
    try:
        a = store.search_cfg.alias
        exists = store.alias_exists(a)
        print(f"alias={a} exists={exists} {round((time.perf_counter() - t2) * 1000, 1)}ms")
        if exists:
            ares = store.es.indices.get_alias(name=a, request_timeout=15)
            print(f"alias_indices={list(ares.keys())[:8]}")
    except Exception as ex:
        print(f"ALIAS_FAIL {round((time.perf_counter() - t2) * 1000, 1)}ms err={ex!r}")
        return 4

    print("\n=== 4) hybrid_search 试查 (project_id=3) ===")
    t3 = time.perf_counter()
    try:
        from memory.grep_es_config import build_embedding_client_from_config

        client = build_embedding_client_from_config(Config)
        vec = client.embed(["登录问题测试"])[0]
        hits = store.hybrid_search(
            project_id="3",
            query_text="登录问题",
            query_embedding=vec,
            entity_types=["bug", "badcase"],
            top_k=3,
            alias_checked=True,
            request_timeout_s=float(getattr(Config, "GREP_ES_SEARCH_TIMEOUT_S", 6) or 6),
        )
        print(
            f"HYBRID_OK hits={len(hits)} {round((time.perf_counter() - t3) * 1000, 1)}ms"
        )
        for i, h in enumerate(hits[:3]):
            print(
                f"  hit[{i}] entity={h.get('entity_type')} id={h.get('record_id')} score={h.get('score')}"
            )
    except Exception as ex:
        print(f"HYBRID_FAIL {round((time.perf_counter() - t3) * 1000, 1)}ms err={ex!r}")
        return 5

    print("\n=== 结论: ES 可用 ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
