from __future__ import annotations

import pandas as pd


def summarise(decisions: pd.DataFrame) -> dict:
    """Stable, reproducible decision metrics for acceptance checks."""
    total_demand = float(decisions["local_demand_14d"].sum())
    covered = float(
        (
            decisions["available"] + decisions["transfer_in"] + decisions["po_qty"]
        ).clip(upper=decisions["local_demand_14d"]).sum()
    )
    service = covered / total_demand if total_demand else 1.0

    return {
        "rows": int(len(decisions)),
        "skus": int(decisions["sku"].nunique()),
        "warehouses": int(decisions["warehouse"].nunique()),
        "po_units": int(decisions["po_qty"].sum()),
        "transfer_units": float(decisions["transfer_in"].sum()),
        "expected_stockout_units": float(decisions["expected_stockout_units"].sum()),
        "expected_total_cost": round(float(decisions["expected_cost"].sum()), 2),
        "projected_service_level": round(service, 4),
        "actions": decisions["action"].value_counts().to_dict(),
    }


def assert_acceptance(metrics: dict, min_service: float = 0.85) -> None:
    """Lightweight acceptance gates for the bundled demo scenario."""
    if metrics["rows"] <= 0:
        raise AssertionError("No decision rows produced")
    if metrics["projected_service_level"] < min_service:
        raise AssertionError(
            f"Service level {metrics['projected_service_level']} < {min_service}"
        )
    if metrics["expected_stockout_units"] > metrics["po_units"] + metrics["transfer_units"] + 50:
        raise AssertionError("Stockout residual unexpectedly high vs replenishment")
