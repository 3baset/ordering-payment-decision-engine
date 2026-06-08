"""Unit tests for the Action Lambda routing logic."""

import sys
import os
import unittest
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
    "action_handler",
    os.path.join(os.path.dirname(__file__), "..", "lambdas", "action", "handler.py"),
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_route = _mod._route


class TestRoute(unittest.TestCase):

    # ── AUTO_APPROVE ──────────────────────────────────────────────────────

    def test_auto_approve_routes_to_fulfilled(self):
        action, detail, priority = _route("AUTO_APPROVE", 0.85)
        self.assertEqual(action, "FULFILLED")
        self.assertIn("fulfillment", detail.lower())
        self.assertEqual(priority, "normal")

    def test_auto_approve_priority_always_normal(self):
        # Priority is always normal for AUTO_APPROVE regardless of score
        for score in (0.70, 0.85, 1.00):
            _, _, priority = _route("AUTO_APPROVE", score)
            self.assertEqual(priority, "normal")

    # ── MANUAL_REVIEW ─────────────────────────────────────────────────────

    def test_manual_review_routes_to_escalated(self):
        action, _, _ = _route("MANUAL_REVIEW", 0.50)
        self.assertEqual(action, "ESCALATED")

    def test_manual_review_below_055_is_high_priority(self):
        _, _, priority = _route("MANUAL_REVIEW", 0.54)
        self.assertEqual(priority, "high")

    def test_manual_review_at_055_is_medium_priority(self):
        _, _, priority = _route("MANUAL_REVIEW", 0.55)
        self.assertEqual(priority, "medium")

    def test_manual_review_above_055_is_medium_priority(self):
        _, _, priority = _route("MANUAL_REVIEW", 0.68)
        self.assertEqual(priority, "medium")

    def test_manual_review_detail_contains_score(self):
        _, detail, _ = _route("MANUAL_REVIEW", 0.512)
        self.assertIn("0.512", detail)

    # ── DECLINE ──────────────────────────────────────────────────────────

    def test_decline_routes_to_rejected(self):
        action, detail, priority = _route("DECLINE", 0.15)
        self.assertEqual(action, "REJECTED")
        self.assertIn("declined", detail.lower())
        self.assertEqual(priority, "normal")

    def test_decline_priority_always_normal(self):
        for score in (0.0, 0.20, 0.39):
            _, _, priority = _route("DECLINE", score)
            self.assertEqual(priority, "normal")

    # ── Unknown decision (defensive) ──────────────────────────────────────

    def test_unknown_decision_falls_through_to_rejected(self):
        # The routing falls through to the DECLINE branch for any unrecognised decision
        action, _, _ = _route("UNKNOWN_OUTCOME", 0.50)
        self.assertEqual(action, "REJECTED")


if __name__ == "__main__":
    unittest.main(verbosity=2)
