"""Deterministic engine unit tests."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import numpy as np
import pytest

from engines.inventory_engine import (
    compute_eoq,
    compute_reorder_point,
    compute_safety_stock,
    compute_order_quantity,
)
from engines.payment_engine import (
    compute_success_probability,
    sample_payment_delay,
)
from engines.elasticity_engine import adjust_quantity
from engines.fraud_engine import score_order
from store.shared_state import CustomerState, SharedSimulationState


def _customer(risk: float = 0.3) -> CustomerState:
    return CustomerState(
        customer_id="test",
        segment="regular",
        credit_limit=500_000,
        risk_score=risk,
    )


# ── Inventory engine ──────────────────────────────────────────────────────────

def test_reorder_point_positive():
    rp = compute_reorder_point(5.0, 7, 2.0)
    assert rp > 0

def test_safety_stock_increases_with_variance():
    ss_low = compute_safety_stock(7, 1.0)
    ss_high = compute_safety_stock(7, 5.0)
    assert ss_high > ss_low

def test_eoq_positive():
    eoq = compute_eoq(1000)
    assert eoq > 0

def test_eoq_zero_demand_returns_fallback():
    eoq = compute_eoq(0)
    assert eoq >= 1

def test_order_quantity_at_least_eoq():
    eoq = 100
    qty = compute_order_quantity(eoq, 200, 50, 0, 30)
    assert qty >= eoq


# ── Payment engine ────────────────────────────────────────────────────────────

def test_success_prob_tiers():
    assert compute_success_probability(0.1) == 0.95
    assert compute_success_probability(0.5) == 0.70
    assert compute_success_probability(0.9) == 0.40

def test_payment_delay_positive():
    np.random.seed(42)
    delay = sample_payment_delay(0.5)
    assert delay >= 0


# ── Elasticity engine ─────────────────────────────────────────────────────────

def test_elasticity_reduces_qty_on_price_increase():
    qty_before = adjust_quantity(100, 0.0, "B")
    qty_after = adjust_quantity(100, 0.20, "B")  # +20% price
    assert qty_after < qty_before

def test_elasticity_never_below_one():
    qty = adjust_quantity(1, 999.0, "C")
    assert qty >= 1

def test_class_a_less_elastic_than_c():
    qty_a = adjust_quantity(100, 0.30, "A")
    qty_c = adjust_quantity(100, 0.30, "C")
    assert qty_a > qty_c  # A is less price-sensitive


# ── Fraud engine ──────────────────────────────────────────────────────────────

def test_fraud_score_in_range():
    customer = _customer(risk=0.8)
    score = score_order(customer, 50_000, 5, 10_000)
    assert 0.0 <= score <= 1.0

def test_low_velocity_low_score():
    customer = _customer(risk=0.1)
    score = score_order(customer, 1_000, 1, 5_000)
    assert score < 0.5

def test_high_velocity_raises_score():
    customer = _customer(risk=0.5)
    score_low = score_order(customer, 1_000, 1, 5_000)
    score_high = score_order(customer, 1_000, 10, 5_000)
    assert score_high > score_low
