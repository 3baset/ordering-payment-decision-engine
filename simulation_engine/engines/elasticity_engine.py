from __future__ import annotations

from typing import Literal

ELASTICITY: dict[str, float] = {
    "A": -0.3,   # essential / fast-moving
    "B": -0.6,   # regular
    "C": -1.2,   # discretionary
}


def adjust_quantity(
    base_qty: int,
    price_change_pct: float,
    demand_class: Literal["A", "B", "C"] = "B",
) -> int:
    """Apply price elasticity to quantity.

    price_change_pct: fractional change, e.g. 0.10 means +10%.
    """
    epsilon = ELASTICITY.get(demand_class, ELASTICITY["B"])
    adjusted = base_qty * (1.0 + epsilon * price_change_pct)
    return max(1, round(adjusted))


def get_demand_class(sku_category: str, sku_subcategory: str = "") -> Literal["A", "B", "C"]:
    """Map SKU to demand class based on category."""
    essential_categories = {"BEV", "FOD"}
    discretionary_categories = {"STA", "PER"}
    if sku_category in essential_categories:
        return "A"
    if sku_category in discretionary_categories:
        return "C"
    return "B"
