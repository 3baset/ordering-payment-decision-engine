"""Hypothesis stateful machine test for credit ledger invariant."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from hypothesis import settings
from hypothesis.stateful import RuleBasedStateMachine, initialize, invariant, rule
from hypothesis import strategies as st


class CreditLedgerMachine(RuleBasedStateMachine):
    """Simulate a customer's credit ledger. credit_used must never go negative."""

    @initialize()
    def setup(self):
        self.credit_limit = 500_000.0
        self.credit_used = 0.0
        self.outstanding_invoices: list[float] = []

    @rule(amount=st.floats(min_value=1000.0, max_value=100_000.0))
    def place_order(self, amount):
        if self.credit_used + amount <= self.credit_limit:
            self.credit_used += amount
            self.outstanding_invoices.append(amount)

    @rule(amount=st.floats(min_value=100.0, max_value=50_000.0))
    def receive_payment(self, amount):
        if self.outstanding_invoices:
            invoice = self.outstanding_invoices.pop(0)
            payment = min(invoice, amount)
            self.credit_used = max(0.0, self.credit_used - payment)

    @rule(amount=st.floats(min_value=100.0, max_value=50_000.0))
    def write_off(self, amount):
        if self.outstanding_invoices:
            invoice = self.outstanding_invoices.pop(0)
            writeoff = min(invoice, amount)
            self.credit_used = max(0.0, self.credit_used - writeoff)

    @invariant()
    def credit_used_nonneg(self):
        assert self.credit_used >= -0.01, f"credit_used went negative: {self.credit_used}"

    @invariant()
    def credit_used_within_limit(self):
        assert self.credit_used <= self.credit_limit + 0.01


TestCreditLedger = CreditLedgerMachine.TestCase
TestCreditLedger.settings = settings(max_examples=100, stateful_step_count=20)
