from __future__ import annotations

from pathlib import Path

import pandas as pd

REQUIRED = {
    "inventory": {"sku", "warehouse", "on_hand", "reserved", "lead_time_days", "reorder_point"},
    "demand": {"sku", "region", "forecast_7d", "forecast_14d", "forecast_30d", "priority"},
    "costs": {"sku", "unit_cost", "holding_cost_per_day", "stockout_penalty", "supplier_moq", "supplier_pack"},
    "constraints": {"warehouse", "max_inbound_units", "service_level_target", "transfer_cost_per_unit"},
}


def _read_csv(path: Path, name: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing {name} CSV: {path}")
    df = pd.read_csv(path)
    missing = REQUIRED[name] - set(df.columns)
    if missing:
        raise ValueError(f"{name}.csv missing columns: {sorted(missing)}")
    return df


def load_sources(data_dir: str | Path) -> dict[str, pd.DataFrame]:
    """Load and lightly clean the four raw CSV sources."""
    root = Path(data_dir)
    inv = _read_csv(root / "inventory.csv", "inventory")
    dem = _read_csv(root / "demand.csv", "demand")
    costs = _read_csv(root / "costs.csv", "costs")
    cons = _read_csv(root / "constraints.csv", "constraints")

    for df, cols in (
        (inv, ["sku", "warehouse"]),
        (dem, ["sku", "region"]),
        (costs, ["sku"]),
        (cons, ["warehouse"]),
    ):
        for c in cols:
            df[c] = df[c].astype(str).str.strip().str.upper()

    # numeric coercions
    for col in ["on_hand", "reserved", "lead_time_days", "reorder_point"]:
        inv[col] = pd.to_numeric(inv[col], errors="coerce").fillna(0)
    for col in ["forecast_7d", "forecast_14d", "forecast_30d"]:
        dem[col] = pd.to_numeric(dem[col], errors="coerce").fillna(0)
    for col in [
        "unit_cost",
        "holding_cost_per_day",
        "stockout_penalty",
        "supplier_moq",
        "supplier_pack",
    ]:
        costs[col] = pd.to_numeric(costs[col], errors="coerce")
    for col in ["max_inbound_units", "service_level_target", "transfer_cost_per_unit"]:
        cons[col] = pd.to_numeric(cons[col], errors="coerce")

    inv["available"] = (inv["on_hand"] - inv["reserved"]).clip(lower=0)
    dem["priority"] = dem["priority"].str.lower().str.strip()

    return {"inventory": inv, "demand": dem, "costs": costs, "constraints": cons}
