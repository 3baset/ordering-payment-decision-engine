from __future__ import annotations

import random
import uuid
from typing import TYPE_CHECKING

import numpy as np

from store.shared_state import CustomerState

if TYPE_CHECKING:
    from faker import Faker

# Egyptian FMCG & HORECA customer type registry
# segment: premium / regular / low_volume
#
# Credit limits are 4x their real-world base. The ordering engine runs at roughly
# 50% daily probability (logistic of small positive base rates), which means
# customers generate far more simultaneous in-flight orders than the model was
# originally calibrated for. The multiplier keeps the credit-rejection rate at a
# realistic level (~10-15%) while still exercising the credit-check code path.
_CREDIT_MULTIPLIER = 4

CUSTOMER_TYPES: list[dict] = [
    {"type": "HORECA_hotel_premium",      "segment": "premium",    "credit_limit": 1_500_000 * _CREDIT_MULTIPLIER, "order_mult": 1.6, "horeca_affinity": 0.70, "payment": "cheque",        "weight": 0.04},
    {"type": "HORECA_restaurant_premium", "segment": "premium",    "credit_limit": 1_200_000 * _CREDIT_MULTIPLIER, "order_mult": 1.4, "horeca_affinity": 0.65, "payment": "credit",        "weight": 0.06},
    {"type": "RETAIL_supermarket_large",  "segment": "premium",    "credit_limit": 1_800_000 * _CREDIT_MULTIPLIER, "order_mult": 2.0, "horeca_affinity": 0.03, "payment": "credit",        "weight": 0.04},
    {"type": "HORECA_hotel_regular",      "segment": "regular",    "credit_limit":   600_000 * _CREDIT_MULTIPLIER, "order_mult": 1.2, "horeca_affinity": 0.55, "payment": "cash",          "weight": 0.07},
    {"type": "HORECA_restaurant_regular", "segment": "regular",    "credit_limit":   600_000 * _CREDIT_MULTIPLIER, "order_mult": 1.0, "horeca_affinity": 0.50, "payment": "cash",          "weight": 0.14},
    {"type": "HORECA_catering",           "segment": "regular",    "credit_limit":   900_000 * _CREDIT_MULTIPLIER, "order_mult": 1.8, "horeca_affinity": 0.60, "payment": "cash",          "weight": 0.06},
    {"type": "HORECA_school_canteen",     "segment": "regular",    "credit_limit":   450_000 * _CREDIT_MULTIPLIER, "order_mult": 0.9, "horeca_affinity": 0.35, "payment": "cash",          "weight": 0.04},
    {"type": "RETAIL_supermarket_mid",    "segment": "regular",    "credit_limit":   540_000 * _CREDIT_MULTIPLIER, "order_mult": 1.2, "horeca_affinity": 0.03, "payment": "cash",          "weight": 0.10},
    {"type": "RETAIL_pharmacy",           "segment": "regular",    "credit_limit":   360_000 * _CREDIT_MULTIPLIER, "order_mult": 0.8, "horeca_affinity": 0.02, "payment": "cash",          "weight": 0.07},
    {"type": "RETAIL_minimarket",         "segment": "low_volume", "credit_limit":   150_000 * _CREDIT_MULTIPLIER, "order_mult": 0.5, "horeca_affinity": 0.05, "payment": "cash",          "weight": 0.18},
    {"type": "HORECA_cafe_small",         "segment": "low_volume", "credit_limit":   120_000 * _CREDIT_MULTIPLIER, "order_mult": 0.4, "horeca_affinity": 0.45, "payment": "cash",          "weight": 0.12},
    {"type": "HORECA_bakery_small",       "segment": "low_volume", "credit_limit":   135_000 * _CREDIT_MULTIPLIER, "order_mult": 0.5, "horeca_affinity": 0.30, "payment": "cash",          "weight": 0.08},
]

# Area distribution weighted by real Egyptian wholesale volume
AREA_DISTRIBUTION: list[tuple[str, float]] = [
    ("AREA-GCR", 0.40),  # Greater Cairo ~40% of national wholesale volume
    ("AREA-ALX", 0.15),
    ("AREA-DLT", 0.12),
    ("AREA-CNL", 0.09),
    ("AREA-UPP", 0.12),  # Upper Egypt — informal trade, cash-heavy
    ("AREA-RED", 0.06),  # Red Sea & Sinai — HORECA/tourism-driven
    ("AREA-FAY", 0.06),
]
_AREA_IDS = [a for a, _ in AREA_DISTRIBUTION]
_AREA_WEIGHTS = [w for _, w in AREA_DISTRIBUTION]

_WEIGHTS = [ct["weight"] for ct in CUSTOMER_TYPES]
_TYPES = CUSTOMER_TYPES


def _apply_credit_variability(base: float, segment: str) -> float:
    variability = {"premium": 0.20, "regular": 0.30, "low_volume": 0.50}[segment]
    noise = np.random.uniform(1.0 - variability, 1.0 + variability)
    return round(base * noise, -3)  # round to nearest 1000


def generate_customer(
    fake: "Faker",
    rep_ids: list[str] | None = None,
    digital_active_prob: float = 0.40,
    area_id: str | None = None,
) -> CustomerState:
    ctype = random.choices(_TYPES, weights=_WEIGHTS, k=1)[0]
    segment = ctype["segment"]
    credit_limit = _apply_credit_variability(ctype["credit_limit"], segment)
    risk_score = np.random.beta(2, 5)  # right-skewed, mostly low risk

    name = fake.name()
    phone = fake.phone_number()
    customer_id = str(uuid.uuid4())
    rep_id = random.choice(rep_ids) if rep_ids else None
    area = area_id or random.choices(_AREA_IDS, weights=_AREA_WEIGHTS, k=1)[0]

    # UPP: informal trade dominates — 75% of accounts pay cash regardless of customer type
    payment_method = ctype["payment"]
    if area == "AREA-UPP" and random.random() < 0.75:
        payment_method = "cash"

    return CustomerState(
        customer_id=customer_id,
        segment=segment,
        status="new",
        credit_limit=credit_limit,
        credit_used=0.0,
        last_order_time=-999.0,
        risk_score=float(risk_score),
        digital_active=random.random() < digital_active_prob,
        rep_id=rep_id,
        reactivation_boost_until=-1.0,
        customer_type=ctype["type"],
        area_id=area,
        payment_method=payment_method,
        name=name,
        phone=phone,
    )


def generate_customers(
    n: int,
    fake: "Faker",
    rep_ids: list[str] | None = None,
    digital_active_prob: float = 0.40,
) -> list[CustomerState]:
    return [generate_customer(fake, rep_ids, digital_active_prob) for _ in range(n)]
