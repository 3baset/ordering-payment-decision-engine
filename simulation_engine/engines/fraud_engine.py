from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from store.shared_state import CustomerState


def score_order(
    customer: "CustomerState",
    order_value: float,
    recent_order_count_24h: int,
    avg_90d_value: float,
    velocity_threshold: int = 3,
    amount_multiplier_threshold: float = 5.0,
) -> float:
    """Return fraud_score ∈ [0, 1].

    Combines velocity and amount-spike signals.
    """
    velocity_score = 0.0
    if recent_order_count_24h >= velocity_threshold:
        excess = recent_order_count_24h - velocity_threshold
        velocity_score = min(1.0, 0.4 + excess * 0.1)

    amount_score = 0.0
    if avg_90d_value > 0 and order_value > avg_90d_value * amount_multiplier_threshold:
        ratio = order_value / (avg_90d_value * amount_multiplier_threshold)
        amount_score = min(1.0, 0.3 + (ratio - 1) * 0.2)

    # Higher risk_score on the customer profile also lifts fraud score
    base_risk = customer.risk_score * 0.3

    combined = velocity_score * 0.5 + amount_score * 0.4 + base_risk * 0.1
    return min(1.0, combined)
