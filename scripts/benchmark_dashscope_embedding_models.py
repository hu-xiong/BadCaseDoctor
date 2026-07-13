# -*- coding: utf-8 -*-
"""
百炼 / DashScope 向量模型单条 embedding 耗时对比。

用法（项目根目录）:
  python scripts/benchmark_dashscope_embedding_models.py
  python scripts/benchmark_dashscope_embedding_models.py --repeats 3
  python scripts/benchmark_dashscope_embedding_models.py --models tongyi-embedding-vision-flash,text-embedding-v4

依赖 .env / config 中的 DASHSCOPE_API_KEY 或 EMBEDDING_API_KEY。
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
    DASHSCOPE_EMBEDDING_MODELS,
    format_benchmark_table,
    run_embedding_benchmark_suite,
)


def main() -> int:
    p = argparse.ArgumentParser(description="DashScope embedding 模型耗时基准")
    p.add_argument(
        "--text",
        default=DEFAULT_BENCHMARK_TEXT,
        help="待向量化文本",
    )
    p.add_argument(
        "--models",
        default="",
        help="逗号分隔模型列表；默认跑内置全量列表",
    )
    p.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="每个模型重复次数，取中位耗时",
    )
    args = p.parse_args()
    models = None
    if (args.models or "").strip():
        models = [x.strip() for x in args.models.split(",") if x.strip()]
    else:
        models = DASHSCOPE_EMBEDDING_MODELS

    print(f"将测试 {len(models)} 个 embedding 模型（repeats={args.repeats}）…\n")
    results = run_embedding_benchmark_suite(
        text=args.text,
        models=models,
        repeats=args.repeats,
    )
    print(format_benchmark_table(results, args.text))
    ok_n = sum(1 for r in results if r.ok)
    print(f"\n完成: {ok_n}/{len(results)} 成功")
    return 0 if ok_n > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
