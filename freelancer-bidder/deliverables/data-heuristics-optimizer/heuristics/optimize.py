from __future__ import annotations

import math

import numpy as np
import pandas as pd

PRIORITY_WEIGHT = {"high": 1.25, "medium": 1.0, "low": 0.75}


def _ceil_to_pack(qty: float, pack: float, moq: float) -> int:
    if qty <= 0:
        return 0
    pack = max(float(pack or 1), 1.0)
    moq = max(float(moq or 0), 0.0)
    need = max(qty, moq)
    return int(math.ceil(need / pack) * pack)


def recommend_actions(unified: pd.DataFrame, horizon_days: int = 14) -> pd.DataFrame:
    """
    Improved heuristics:
    1) Target stock = local demand over lead_time + review horizon, scaled by service level
    2) Reorder when available < max(reorder_point, safety buffer)
    3) Prefer transfer from overstocked warehouses before supplier PO when cheaper
    4) Cap inbound by warehouse max_inbound_units
    """
    df = unified.copy()
    df["priority_w"] = df["priority_mode"].map(PRIORITY_WEIGHT).fillna(1.0)

    daily = df["local_demand_14d"] / 14.0
    cover_days = df["lead_time_days"] + horizon_days * 0.5
    # service_level_target ~ 0.9-0.95 -> inflate target slightly
    inflate = 1.0 + (df["service_level_target"].fillna(0.9) - 0.9) * 2.0
    df["target_stock"] = (daily * cover_days * inflate * df["priority_w"]).clip(lower=0)

    safety = df["reorder_point"].fillna(0) * 0.35
    df["reorder_trigger"] = np.maximum(df["reorder_point"], safety)
    df["gap"] = (df["target_stock"] - df["available"]).clip(lower=0)

    # Raw PO suggestion before transfer balancing
    df["po_raw"] = df["gap"]

    # Transfer opportunity: warehouses with surplus cover can donate
    surplus = (df["available"] - df["target_stock"]).clip(lower=0)
    df["surplus"] = surplus

    transfer_in = []
    transfer_from = []
    po_final = []

    for sku, g in df.groupby("sku"):
        g = g.copy()
        needers = g[g["gap"] > 0].sort_values("gap", ascending=False)
        donors = g[g["surplus"] > 0].sort_values("surplus", ascending=False)

        donor_pool = {
            row.warehouse: float(row.surplus) for row in donors.itertuples(index=False)
        }
        tin_map = {row.warehouse: 0.0 for row in g.itertuples(index=False)}
        tfrom_map = {row.warehouse: "" for row in g.itertuples(index=False)}
        po_map = {row.warehouse: float(row.po_raw) for row in g.itertuples(index=False)}

        for n in needers.itertuples(index=False):
            still = float(n.gap)
            for d_wh, d_qty in list(donor_pool.items()):
                if still <= 0:
                    break
                if d_qty <= 0 or d_wh == n.warehouse:
                    continue
                # transfer if cheaper than stockout risk / holding imbalance
                move = min(still, d_qty)
                # only transfer when transfer cost < 45% of stockout penalty unit
                if n.transfer_cost_per_unit <= (n.stockout_penalty or 0) * 0.45:
                    tin_map[n.warehouse] += move
                    tfrom_map[n.warehouse] = (
                        f"{tfrom_map[n.warehouse]},{d_wh}" if tfrom_map[n.warehouse] else d_wh
                    )
                    donor_pool[d_wh] -= move
                    still -= move
                    po_map[n.warehouse] = max(0.0, po_map[n.warehouse] - move)

        for row in g.itertuples(index=False):
            transfer_in.append((sku, row.warehouse, tin_map[row.warehouse]))
            transfer_from.append((sku, row.warehouse, tfrom_map[row.warehouse]))
            # pack / moq / inbound cap
            capped = min(po_map[row.warehouse], float(row.max_inbound_units or 10**9))
            qty = _ceil_to_pack(capped, row.supplier_pack, row.supplier_moq if capped > 0 else 0)
            # if after pack exceeds inbound, step down one pack
            pack = max(float(row.supplier_pack or 1), 1.0)
            while qty > float(row.max_inbound_units or 10**9) and qty >= pack:
                qty -= int(pack)
            po_final.append((sku, row.warehouse, max(0, int(qty))))

    t_df = pd.DataFrame(transfer_in, columns=["sku", "warehouse", "transfer_in"])
    f_df = pd.DataFrame(transfer_from, columns=["sku", "warehouse", "transfer_from"])
    p_df = pd.DataFrame(po_final, columns=["sku", "warehouse", "po_qty"])

    out = df.merge(t_df, on=["sku", "warehouse"]).merge(f_df, on=["sku", "warehouse"]).merge(
        p_df, on=["sku", "warehouse"]
    )

    out["action"] = np.select(
        [
            (out["po_qty"] > 0) & (out["transfer_in"] > 0),
            out["po_qty"] > 0,
            out["transfer_in"] > 0,
            out["available"] < out["reorder_trigger"],
        ],
        ["PO+TRANSFER", "PURCHASE_ORDER", "TRANSFER_IN", "WATCH"],
        default="OK",
    )

    # Expected cost heuristic (for ranking / validation metric)
    out["expected_stockout_units"] = (
        (out["local_demand_14d"] - out["available"] - out["transfer_in"] - out["po_qty"]).clip(
            lower=0
        )
    )
    out["expected_cost"] = (
        out["po_qty"] * out["unit_cost"].fillna(0)
        + out["transfer_in"] * out["transfer_cost_per_unit"].fillna(0)
        + out["expected_stockout_units"] * out["stockout_penalty"].fillna(0)
        + out["available"] * out["holding_cost_per_day"].fillna(0) * 7
    )

    cols = [
        "sku",
        "warehouse",
        "available",
        "local_demand_14d",
        "days_of_cover",
        "target_stock",
        "reorder_trigger",
        "gap",
        "transfer_in",
        "transfer_from",
        "po_qty",
        "action",
        "expected_stockout_units",
        "expected_cost",
        "priority_mode",
    ]
    return out[cols].sort_values(["action", "expected_cost"], ascending=[True, False]).reset_index(
        drop=True
    )
