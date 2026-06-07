"""Unit tests for business rules using Hypothesis property testing."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest
from hypothesis import given, settings, strategies as st

from store.shared_state import CustomerState
from validators.business_rules import (
    RuleResult,
    check_credit_rule,
    check_customer_status,
    apply_payment_rule,
)


def _make_customer(credit_limit: float, credit_used: float, status: str = "active") -> CustomerState:
    return CustomerState(
        customer_id="test-cust",
        segment="regular",
        status=status,
        credit_limit=credit_limit,
        credit_used=credit_used,
    )


@given(
    credit_limit=st.floats(min_value=1.0, max_value=2_000_000.0),
    credit_used=st.floats(min_value=0.0, max_value=2_000_000.0),
    order_total=st.floats(min_value=0.01, max_value=500_000.0),
)
@settings(max_examples=300)
def test_cr01_never_exceeds_limit(credit_limit, credit_used, order_total):
    """CR-01: If the rule passes, credit_used + order ≤ credit_limit."""
    customer = _make_customer(credit_limit, credit_used)
    result = check_credit_rule(customer, order_total)
    if result.passed:
        assert customer.credit_used + order_total <= customer.credit_limit + 0.01


@given(
    credit_limit=st.floats(min_value=100_000.0, max_value=2_000_000.0),
    credit_used=st.floats(min_value=0.0, max_value=50_000.0),
)
def test_cr01_passes_when_room_available(credit_limit, credit_used):
    """If credit_used is low, CR-01 should pass for a small order."""
    customer = _make_customer(credit_limit, credit_used)
    order_total = 1.0  # smallest possible order
    result = check_credit_rule(customer, order_total)
    assert result.passed
    assert result.rule_id == "CR-01"


def test_cr02_fails_for_churned():
    customer = _make_customer(500_000, 0, status="churned")
    result = check_customer_status(customer)
    assert not result.passed
    assert result.rule_id == "CR-02"


def test_cr02_passes_for_active():
    customer = _make_customer(500_000, 0, status="active")
    result = check_customer_status(customer)
    assert result.passed


@given(
    balance=st.floats(min_value=0.01, max_value=1_000_000.0),
    payment=st.floats(min_value=0.01, max_value=2_000_000.0),
)
def test_pay01_never_exceeds_balance(balance, payment):
    """PAY-01: applied payment never exceeds balance."""
    applied = apply_payment_rule(balance, payment)
    assert applied <= balance + 0.01
    assert applied >= 0.0


def test_pay01_captures_up_to_balance():
    assert apply_payment_rule(1000.0, 5000.0) == 1000.0
    assert apply_payment_rule(1000.0, 500.0) == 500.0
    assert apply_payment_rule(1000.0, 1000.0) == 1000.0
