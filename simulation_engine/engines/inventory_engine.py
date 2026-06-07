from __future__ import annotations

import math


def compute_reorder_point(
    avg_daily_demand: float,
    lead_time: float,
    demand_std: float,
    service_level_z: float = 1.645,
) -> float:
    """Reorder point = projected_demand + safety_stock."""
    safety = service_level_z * math.sqrt(lead_time) * demand_std
    return avg_daily_demand * lead_time + safety


def compute_safety_stock(
    lead_time: float,
    demand_std: float,
    service_level_z: float = 1.645,
) -> float:
    return service_level_z * math.sqrt(lead_time) * demand_std


def compute_eoq(
    annual_demand: float,
    order_cost: float = 200.0,
    holding_cost_per_unit: float = 10.0,
) -> int:
    if annual_demand <= 0:
        return 50
    return max(1, int(math.sqrt(2 * annual_demand * order_cost / holding_cost_per_unit)))


def compute_order_quantity(
    eoq: int,
    reorder_point: float,
    on_hand: float,
    on_order: float,
    safety_stock: float,
) -> int:
    shortfall = reorder_point - (on_hand + on_order)
    qty = max(eoq, shortfall + safety_stock)
    return max(1, int(math.ceil(qty)))


def compute_initial_stock(reorder_point: float, demand_std: float) -> int:
    """Initial on-hand = 2× reorder_point with some noise."""
    import numpy as np
    raw = np.random.normal(reorder_point * 2, reorder_point * 0.5)
    return max(10, int(raw))
