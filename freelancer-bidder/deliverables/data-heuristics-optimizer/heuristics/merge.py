from __future__ import annotations

import pandas as pd

PRIORITY_WEIGHT = {"high": 1.25, "medium": 1.0, "low": 0.75}


def build_unified_frame(sources: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """
    Integrate inventory + demand + costs + warehouse constraints.

    Old brittle approach often joined only on sku and dropped warehouse/region
    context, which made reorder heuristics unstable. This merge keeps grain at
    sku x warehouse and allocates regional demand proportionally.
    """
    inv = sources["inventory"].copy()
    dem = sources["demand"].copy()
    costs = sources["costs"].copy()
    cons = sources["constraints"].copy()

    # Aggregate demand to sku with priority-weighted 14d forecast
    dem["pri_w"] = dem["priority"].map(PRIORITY_WEIGHT).fillna(1.0)
    dem["w_forecast_14d"] = dem["forecast_14d"] * dem["pri_w"]
    dem_sku = (
        dem.groupby("sku", as_index=False)
        .agg(
            demand_7d=("forecast_7d", "sum"),
            demand_14d=("forecast_14d", "sum"),
            demand_30d=("forecast_30d", "sum"),
            demand_14d_weighted=("w_forecast_14d", "sum"),
            priority_mode=("priority", lambda s: s.value_counts().idxmax()),
        )
    )

    # Warehouse share of available stock (fallback equal split)
    inv["wh_share"] = inv.groupby("sku")["available"].transform(
        lambda s: s / s.sum() if s.sum() > 0 else 1.0 / len(s)
    )

    unified = inv.merge(dem_sku, on="sku", how="left")
    unified = unified.merge(costs, on="sku", how="left")
    unified = unified.merge(cons, on="warehouse", how="left")

    for col in ["demand_7d", "demand_14d", "demand_30d", "demand_14d_weighted"]:
        unified[col] = unified[col].fillna(0)

    # Allocate sku-level demand to warehouses by current availability share
    unified["local_demand_14d"] = unified["demand_14d_weighted"] * unified["wh_share"]
    unified["days_of_cover"] = unified.apply(
        lambda r: (r["available"] / (r["local_demand_14d"] / 14.0))
        if r["local_demand_14d"] > 0
        else 999.0,
        axis=1,
    )

    # Data-quality flags (reproducible diagnostics)
    unified["missing_cost"] = unified["unit_cost"].isna()
    unified["missing_constraint"] = unified["max_inbound_units"].isna()
    return unified
