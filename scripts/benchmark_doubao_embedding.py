# -*- coding: utf-8 -*-
"""
豆包 Ark 多模态向量模型耗时基准（与用户 curl 同端点）。

用法（项目根目录）:
  python scripts/benchmark_doubao_embedding.py
  python scripts/benchmark_doubao_embedding.py --repeats 5
  python scripts/benchmark_doubao_embedding.py --text-only

依赖 .env 中 DOUBAO_API_KEY。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from memory.embedding_benchmark import (  # noqa: E402
    DEFAULT_BENCHMARK_TEXT,
    format_benchmark_table,
    run_doubao_embedding_benchmark,
    benchmark_doubao_multimodal_once,
)


def main() -> int:
    p = argparse.ArgumentParser(description="豆包 Ark multimodal embedding 耗时")
    p.add_argument("--text", default=DEFAULT_BENCHMARK_TEXT)
    p.add_argument("--repeats", type=int, default=3)
    p.add_argument(
        "--text-only",
        action="store_true",
        help="仅测纯文本，不测 text+image",
    )
    args = p.parse_args()

    if args.text_only:
        results = [
            benchmark_doubao_multimodal_once(
                args.text, include_sample_image=False, repeats=args.repeats
            )
        ]
    else:
        results = run_doubao_embedding_benchmark(args.text, repeats=args.repeats)

    print(format_benchmark_table(results, args.text))
    ok_n = sum(1 for r in results if r.ok)
    print(f"\n完成: {ok_n}/{len(results)} 成功")
    return 0 if ok_n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
