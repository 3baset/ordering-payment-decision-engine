"""Unit tests for the Decision Lambda scoring logic."""

import sys
import os
import json
import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Bootstrap Lambda environment variables before importing handler
os.environ["ORDERS_TABLE"]       = "maxab-orders"
os.environ["ACTION_LOG_TABLE"]   = "maxab-action-log"
os.environ["LOG_LEVEL"]          = "WARNING"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"]  = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas", "decision"))
from handler import _score_order, APPROVE_THRESHOLD, REVIEW_THRESHOLD


class TestScoreOrder(unittest.TestCase):

    def _order(self, segment="premium", fraud=0.0, payment="credit", amount=5_000):
        return {
            "order_id":         "ORD-TEST",
            "customer_id":      "CUST-001",
            "customer_segment": segment,
            "fraud_score":      str(fraud),
            "payment_method":   payment,
            "total_amount":     str(amount),
        }

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
        self.assertAlmostEqual(comp["fraud_score"], 1.0)

    def test_high_fraud_pushes_score_toward_decline(self):
        _, comp = _score_order(self._order(fraud=0.95, segment="at-risk"))
        self.assertAlmostEqual(comp["fraud_score"], 0.05)

    def test_negative_fraud_clamped_to_zero(self):
        _, comp = _score_order(self._order(fraud=-0.5))
        self.assertAlmostEqual(comp["fraud_score"], 1.0)  # inverted from clamped 0

    def test_above_one_fraud_clamped(self):
        _, comp = _score_order(self._order(fraud=1.5))
        self.assertAlmostEqual(comp["fraud_score"], 0.0)  # inverted from clamped 1

    # ── Factor 3: Payment × basket ────────────────────────────────────────

    def test_credit_scores_higher_than_cod(self):
        _, comp_credit = _score_order(self._order(payment="credit", amount=10_000))
        _, comp_cod    = _score_order(self._order(payment="cod",    amount=10_000))
        self.assertGreater(comp_credit["payment_score"], comp_cod["payment_score"])

    def test_large_basket_reduces_payment_score(self):
        _, comp_small = _score_order(self._order(payment="credit", amount=1_000))
        _, comp_large = _score_order(self._order(payment="credit", amount=49_000))
        self.assertGreater(comp_small["payment_score"], comp_large["payment_score"])

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
        for field in ("ltv_score", "fraud_score", "payment_score", "composite_score"):
            self.assertIn(field, comp)

    def test_composite_in_zero_one_range(self):
        for segment in ("premium", "standard", "at-risk", "new", "churned"):
            for fraud in (0.0, 0.5, 1.0):
                _, comp = _score_order(self._order(segment=segment, fraud=fraud))
                self.assertGreaterEqual(comp["composite_score"], 0.0)
                self.assertLessEqual(comp["composite_score"], 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
