from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from store.shared_state import CustomerState, SharedSimulationState

BASE_RATES: dict[str, float] = {
    "premium":    0.12,
    "regular":    0.07,
    "low_volume": 0.02,
    "new_30d":    0.15,
}

BASKET_LOGNORMAL: dict[str, dict[str, float]] = {
    "premium":    {"mean_log": 10.92, "sigma": 1.0},
    "regular":    {"mean_log":  9.92, "sigma": 1.2},
    "low_volume": {"mean_log":  8.42, "sigma": 1.5},
}

SEASONALITY_BOOST: dict[int, float] = {
    1: 0.85, 2: 0.90, 3: 1.20, 4: 1.30,
    5: 1.00, 6: 1.20, 7: 1.40, 8: 1.45,
    9: 1.30, 10: 1.05, 11: 0.95, 12: 1.00,
}


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def compute_order_probability(
    customer: "CustomerState",
    state: "SharedSimulationState",
    sim_time: float,
    config: dict | None = None,
) -> float:
    """Return P(order_today) using the logistic model from §8.1."""
    segment = customer.segment
    base = BASE_RATES.get(segment, BASE_RATES["regular"])

    # Recency boost
    days_since = sim_time - customer.last_order_time if customer.last_order_time >= 0 else 9999
    if days_since < 7:
        recency_factor = 1.2
    elif days_since > 60:
        recency_factor = 0.1
    elif days_since > 30:
        recency_factor = 0.5
    else:
        recency_factor = 1.0

    # Reactivation boost
    if customer.reactivation_boost_until > sim_time:
        recency_factor *= 1.5

    # Seasonality
    from store.shared_state import SIM_START
    from datetime import timedelta
    current_date = SIM_START + timedelta(days=int(sim_time))
    month = current_date.month
    season = state.seasonality_factor * SEASONALITY_BOOST.get(month, 1.0) / 1.0

    # Promotion boost (additive)
    promo_boost = 0.0
    for promo in state.active_promotions:
        if segment in promo.get("target_segments", []):
            promo_boost += 0.2
            break

    # Rep visit boost (additive)
    rep_boost = 0.0
    if customer.rep_id:
        key = f"{customer.rep_id}:{customer.customer_id}"
        last_visit = state.rep_last_visit.get(key, -999.0)
        if sim_time - last_visit <= 7:
            rep_boost = 0.3

    linear = base * recency_factor * season + promo_boost + rep_boost
    return _logistic(linear)


def sample_order_interval(daily_prob: float) -> float:
    """Convert daily probability to exponential inter-arrival time (days)."""
    if daily_prob <= 0:
        return 9999.0
    if daily_prob >= 1:
        daily_prob = 0.999
    return -math.log(random.random()) / daily_prob


def sample_basket_value(segment: str, inflation_factor: float = 1.0) -> float:
    """Sample total basket value (EGP) from log-normal."""
    params = BASKET_LOGNORMAL.get(segment, BASKET_LOGNORMAL["regular"])
    raw = np.random.lognormal(mean=params["mean_log"], sigma=params["sigma"])
    return raw * inflation_factor
