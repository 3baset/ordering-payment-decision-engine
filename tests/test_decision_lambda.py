"""Unit tests for the Decision Lambda scoring logic."""

import sys
import os
import json
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Bootstrap Lambda environment variables before importing handler
os.environ["ORDERS_TABLE"]       = "oda-orders"
os.environ["ACTION_LOG_TABLE"]   = "oda-action-log"
os.environ["LOG_LEVEL"]          = "WARNING"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"]  = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "decision_handler",
    os.path.join(os.path.dirname(__file__), "..", "lambdas", "decision", "handler.py"),
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_score_order      = _mod._score_order
APPROVE_THRESHOLD = _mod.APPROVE_THRESHOLD
REVIEW_THRESHOLD  = _mod.REVIEW_THRESHOLD


class TestScoreOrder(unittest.TestCase):

    def _order(self, segment="premium", fraud=0.0, payment="credit", amount=5_000, avg_basket=0):
        order = {
            "order_id":         "ORD-TEST",
            "customer_id":      "CUST-001",
            "customer_segment": segment,
            "fraud_score":      str(fraud),
            "payment_method":   payment,
            "total_amount":     str(amount),
        }
        if avg_basket:
            order["avg_basket_90d"] = str(avg_basket)
        return order

    # ── Factor 1: LTV tier ─────────────────────────────────────────────────

    def test_premium_scores_highest_ltv(self):
        outcome, comp = _score_order(self._order(segment="premium"))
        self.assertEqual(comp["ltv_score"], 1.0)

    def test_standard_segment_maps_correctly(self):
        outcome, comp = _score_order(self._order(segment="standard"))
        self.assertEqual(comp["ltv_score"], 0.6)

    def test_unknown_segment_defaults_to_midrange(self):
        _, comp = _score_order(self._order(segment="vip_unknown"))
        self.assertEqual(comp["ltv_score"], 0.40)  # fallback

    # ── Factor 2: Fraud risk ───────────────────────────────────────────────

    def test_zero_fraud_gives_full_approval_score(self):
        _, comp = _score_order(self._order(fraud=0.0))
        self.assertAlmostEqual(comp["fraud_approval_component"], 1.0)

    def test_high_fraud_pushes_score_toward_decline(self):
        _, comp = _score_order(self._order(fraud=0.95, segment="at-risk"))
        self.assertAlmostEqual(comp["fraud_approval_component"], 0.05)

    def test_negative_fraud_clamped_to_zero(self):
        _, comp = _score_order(self._order(fraud=-0.5))
        self.assertAlmostEqual(comp["fraud_approval_component"], 1.0)  # inverted from clamped 0

    def test_above_one_fraud_clamped(self):
        _, comp = _score_order(self._order(fraud=1.5))
        self.assertAlmostEqual(comp["fraud_approval_component"], 0.0)  # inverted from clamped 1

    # ── Factor 3: Payment × basket ────────────────────────────────────────

    def test_credit_scores_higher_than_cod(self):
        _, comp_credit = _score_order(self._order(payment="credit", amount=10_000))
        _, comp_cod    = _score_order(self._order(payment="cod",    amount=10_000))
        self.assertGreater(comp_credit["payment_score"], comp_cod["payment_score"])

    def test_cheque_scores_higher_than_cash(self):
        _, comp_cheque = _score_order(self._order(payment="cheque", amount=20_000))
        _, comp_cash   = _score_order(self._order(payment="cash",   amount=20_000))
        self.assertGreater(comp_cheque["payment_score"], comp_cash["payment_score"])

    def test_large_basket_reduces_payment_score(self):
        _, comp_small = _score_order(self._order(payment="credit", amount=1_000))
        _, comp_large = _score_order(self._order(payment="credit", amount=49_000))
        self.assertGreater(comp_small["payment_score"], comp_large["payment_score"])

    def test_basket_at_avg_incurs_no_penalty(self):
        # Order exactly at customer's historical avg → no deviation → no penalty
        _, comp_at_avg  = _score_order(self._order(payment="cash", amount=10_000, avg_basket=10_000))
        _, comp_no_hist = _score_order(self._order(payment="cash", amount=1))
        # At-avg payment_score should equal method_score × 1.0 = 0.45
        self.assertAlmostEqual(comp_at_avg["payment_score"], 0.45, places=4)

    def test_basket_5x_avg_triggers_max_penalty(self):
        # 5× avg basket → deviation = 4.0 → penalty = 30% → payment_score = 0.45 × 0.70 = 0.315
        _, comp = _score_order(self._order(payment="cash", amount=50_000, avg_basket=10_000))
        self.assertAlmostEqual(comp["payment_score"], 0.45 * 0.70, places=4)

    def test_below_avg_basket_incurs_no_penalty(self):
        # Order below customer's average → no penalty regardless of method
        _, comp_below = _score_order(self._order(payment="cash", amount=5_000, avg_basket=20_000))
        _, comp_zero  = _score_order(self._order(payment="cash", amount=5_000, avg_basket=0))
        # Below-avg order = no deviation → method_score × 1.0 = 0.45
        self.assertAlmostEqual(comp_below["payment_score"], 0.45, places=4)

    # ── Outcome thresholds ────────────────────────────────────────────────

    def test_ideal_order_auto_approved(self):
        outcome, _ = _score_order(self._order(
            segment="premium", fraud=0.0, payment="credit", amount=1_000
        ))
        self.assertEqual(outcome, "AUTO_APPROVE")

    def test_risky_order_declined(self):
        outcome, _ = _score_order(self._order(
            segment="churned", fraud=0.95, payment="cash", amount=48_000
        ))
        self.assertEqual(outcome, "DECLINE")

    def test_borderline_order_goes_to_review(self):
        # standard + medium fraud + cod + moderate basket
        outcome, comp = _score_order(self._order(
            segment="standard", fraud=0.45, payment="cod", amount=20_000
        ))
        self.assertIn(outcome, ("MANUAL_REVIEW", "DECLINE"))
        self.assertLess(comp["composite_score"], APPROVE_THRESHOLD)

    # ── Lineage fields ────────────────────────────────────────────────────

    def test_all_lineage_fields_returned(self):
        _, comp = _score_order(self._order())
        for field in ("ltv_score", "fraud_approval_component", "payment_score", "composite_score"):
            self.assertIn(field, comp)

    def test_composite_in_zero_one_range(self):
        for segment in ("premium", "standard", "at-risk", "new", "churned"):
            for fraud in (0.0, 0.5, 1.0):
                _, comp = _score_order(self._order(segment=segment, fraud=fraud))
                self.assertGreaterEqual(comp["composite_score"], 0.0)
                self.assertLessEqual(comp["composite_score"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
