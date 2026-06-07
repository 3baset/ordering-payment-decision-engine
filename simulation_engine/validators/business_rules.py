from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from store.shared_state import CustomerState


@dataclass
class RuleResult:
    passed: bool
    rule_id: str
    message: str = ""


def check_credit_rule(customer: "CustomerState", order_total: float) -> RuleResult:
    """CR-01: credit_used + order_total <= credit_limit."""
    if customer.credit_used + order_total <= customer.credit_limit:
        return RuleResult(passed=True, rule_id="CR-01")
    return RuleResult(
        passed=False,
        rule_id="CR-01",
        message=(
            f"credit_used={customer.credit_used:.2f} + order={order_total:.2f} "
            f"> limit={customer.credit_limit:.2f}"
        ),
    )


def check_customer_status(customer: "CustomerState") -> RuleResult:
    """CR-02: customer must not be churned."""
    if customer.status == "churned":
        return RuleResult(
            passed=False, rule_id="CR-02", message=f"Customer {customer.customer_id} is churned"
        )
    return RuleResult(passed=True, rule_id="CR-02")


def check_promise_date(promise_date: datetime, today: datetime) -> RuleResult:
    """COLL-01: promise_date must be in the future."""
    if promise_date >= today:
        return RuleResult(passed=True, rule_id="COLL-01")
    return RuleResult(
        passed=False,
        rule_id="COLL-01",
        message=f"promise_date {promise_date} is in the past (today={today})",
    )


def check_inventory_rule(available: float, requested: float) -> RuleResult:
    """INV-01: sufficient stock."""
    if available >= requested:
        return RuleResult(passed=True, rule_id="INV-01")
    return RuleResult(
        passed=False,
        rule_id="INV-01",
        message=f"available={available} < requested={requested}",
    )


def apply_payment_rule(invoice_balance: float, payment_amount: float) -> float:
    """PAY-01: never capture more than outstanding balance."""
    return min(invoice_balance, payment_amount)
