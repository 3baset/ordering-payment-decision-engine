from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from store.shared_state import CustomerState


def is_eligible(customer: "CustomerState", promotion: dict) -> bool:
    """PROMO-01: promotion must be active and customer in target_segment."""
    if not promotion.get("active", False):
        return False
    target = promotion.get("target_segments", [])
    if target and customer.segment not in target:
        return False
    return True


def apply_discount(order_value: float, promotion: dict) -> float:
    """Return discounted order value."""
    promo_type = promotion.get("promotion_type", "percentage")
    value = float(promotion.get("value", 0))
    if promo_type in ("percentage", "price_discount"):
        return max(0.0, order_value * (1.0 - value / 100.0))
    if promo_type == "fixed":
        return max(0.0, order_value - value)
    # bogo: treat as 50% off
    return order_value * 0.5


def get_discount_amount(order_value: float, promotion: dict) -> float:
    discounted = apply_discount(order_value, promotion)
    return max(0.0, order_value - discounted)


def find_best_promotion(
    customer: "CustomerState",
    promotions: list[dict],
    order_value: float,
) -> dict | None:
    """Return the promotion with the highest discount for this customer."""
    best: dict | None = None
    best_discount = 0.0
    for promo in promotions:
        if is_eligible(customer, promo):
            d = get_discount_amount(order_value, promo)
            if d > best_discount:
                best_discount = d
                best = promo
    return best
