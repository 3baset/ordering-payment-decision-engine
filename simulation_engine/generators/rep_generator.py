from __future__ import annotations

import random
import uuid
from typing import TYPE_CHECKING

import numpy as np

from store.shared_state import RepRecord

if TYPE_CHECKING:
    from faker import Faker

SALES_AREAS: dict[str, dict] = {
    "AREA-GCR": {"region": "Greater Cairo",        "income_band": "high",  "aov_mult": 1.20, "horeca_conc": "high",      "rep_min": 8, "rep_max": 14},
    "AREA-ALX": {"region": "Alexandria & North",   "income_band": "high",  "aov_mult": 1.15, "horeca_conc": "medium",    "rep_min": 5, "rep_max": 8},
    "AREA-DLT": {"region": "Delta",                "income_band": "mid",   "aov_mult": 1.00, "horeca_conc": "low",       "rep_min": 6, "rep_max": 10},
    "AREA-CNL": {"region": "Canal Zone",           "income_band": "mid",   "aov_mult": 1.05, "horeca_conc": "medium",    "rep_min": 3, "rep_max": 5},
    "AREA-RED": {"region": "Red Sea & Sinai",      "income_band": "high",  "aov_mult": 1.30, "horeca_conc": "very_high", "rep_min": 3, "rep_max": 5},
    "AREA-UPP": {"region": "Upper Egypt",          "income_band": "low",   "aov_mult": 0.80, "horeca_conc": "low",       "rep_min": 4, "rep_max": 7},
    "AREA-FAY": {"region": "Fayoum & South Giza",  "income_band": "low",   "aov_mult": 0.75, "horeca_conc": "very_low",  "rep_min": 2, "rep_max": 4},
}

TIER_WEIGHTS = [("A", 0.20), ("B", 0.30), ("C", 0.30), ("D", 0.20)]


def _assign_tier() -> str:
    tiers = [t[0] for t in TIER_WEIGHTS]
    weights = [t[1] for t in TIER_WEIGHTS]
    return random.choices(tiers, weights=weights, k=1)[0]


def _gmv_target(tier: str, area_id: str) -> float:
    base = {"A": 1_200_000, "B": 800_000, "C": 500_000, "D": 250_000}[tier]
    mult = SALES_AREAS[area_id]["aov_mult"]
    noise = np.random.uniform(0.9, 1.1)
    return round(base * mult * noise, -3)


def generate_reps(fake: "Faker", reps_per_area: tuple[int, int] = (3, 7)) -> list[RepRecord]:
    reps: list[RepRecord] = []
    for area_id in SALES_AREAS:
        area_info = SALES_AREAS[area_id]
        n = random.randint(area_info["rep_min"], area_info["rep_max"])
        for _ in range(n):
            tier = _assign_tier()
            rep_id = f"REP-{str(uuid.uuid4())[:8].upper()}"
            name = fake.name()
            capacity = random.randint(3, 5)
            gmv_target = _gmv_target(tier, area_id)
            reps.append(RepRecord(
                rep_id=rep_id,
                name=name,
                area_id=area_id,
                tier=tier,
                capacity_per_day=capacity,
                assigned_customers=[],
                gmv_target_monthly=gmv_target,
            ))
    return reps
