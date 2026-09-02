from __future__ import annotations

from pathlib import Path

import pandas as pd

from .load import load_sources
from .merge import build_unified_frame
from .metrics import assert_acceptance, summarise
from .optimize import recommend_actions


def run_pipeline(
    data_dir: str | Path,
    horizon_days: int = 14,
    validate: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    End-to-end: load CSVs -> unify -> heuristics -> metrics.

    Returns (unified_frame, decisions, metrics).
    """
    sources = load_sources(data_dir)
    unified = build_unified_frame(sources)
    decisions = recommend_actions(unified, horizon_days=horizon_days)
    metrics = summarise(decisions)
    if validate:
        assert_acceptance(metrics)
    return unified, decisions, metrics
