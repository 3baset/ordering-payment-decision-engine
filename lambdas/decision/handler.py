"""
Decision Lambda — triggered by DynamoDB Streams INSERT events on maxab-orders.

Reads order + customer context, applies 3-factor scoring:
  1. Customer LTV tier  (RFM segment → weight 0.40)
  2. Fraud risk score   (inverted fraud_score → weight 0.35)
  3. Payment risk       (method × basket size → weight 0.25)

Writes decision + full lineage back to the same record.
"""

import json
import logging
import os
import time
import uuid
from decimal import Decimal
from typing import Any

import boto3
from boto3.dynamodb.types import TypeDeserializer

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

dynamodb = boto3.resource("dynamodb")
orders_table = dynamodb.Table(os.environ["ORDERS_TABLE"])
_deserializer = TypeDeserializer()

MODEL_VERSION = "v1.0"

# ── Scoring constants ────────────────────────────────────────────────────────

LTV_SCORES: dict[str, float] = {
    "premium": 1.00,
    "standard": 0.60,
    "at-risk": 0.20,
    "new": 0.40,
    "churned": 0.10,
}

METHOD_RISK: dict[str, float] = {
    "credit": 1.00,
    "direct_debit": 0.80,
    "bank_transfer": 0.75,
    "cod": 0.50,
    "cash": 0.45,
}

BASKET_NORMALISER = 50_000.0   # EGP — orders above this treated as max risk
APPROVE_THRESHOLD = 0.70
REVIEW_THRESHOLD  = 0.40

WEIGHTS = {"ltv": 0.40, "fraud": 0.35, "payment": 0.25}


def _deserialize_dynamo_record(dynamo_map: dict) -> dict:
    return {k: _deserializer.deserialize(v) for k, v in dynamo_map.items()}


def _score_order(order: dict) -> tuple[str, dict]:
    """Return (outcome, score_components) for one order record."""

    # Factor 1 — Customer LTV tier
    segment = str(order.get("customer_segment", "standard")).lower()
    ltv_score = LTV_SCORES.get(segment, 0.40)

    # Factor 2 — Fraud risk (inverted: low fraud score → high approval score)
    raw_fraud = float(order.get("fraud_score", 0.5) or 0.5)
    raw_fraud = max(0.0, min(1.0, raw_fraud))   # clamp to [0,1]
    fraud_approval_score = 1.0 - raw_fraud

    # Factor 3 — Payment method × basket value risk
    method = str(order.get("payment_method", "cod")).lower()
    method_score = METHOD_RISK.get(method, 0.50)
    basket = float(order.get("total_amount", 0) or 0)
    basket_risk_penalty = min(basket / BASKET_NORMALISER, 1.0) * 0.30
    payment_score = method_score * (1.0 - basket_risk_penalty)

    composite = (
        WEIGHTS["ltv"]     * ltv_score +
        WEIGHTS["fraud"]   * fraud_approval_score +
        WEIGHTS["payment"] * payment_score
    )

    if composite >= APPROVE_THRESHOLD:
        outcome = "AUTO_APPROVE"
    elif composite >= REVIEW_THRESHOLD:
        outcome = "MANUAL_REVIEW"
    else:
        outcome = "DECLINE"

    components = {
        "ltv_score":       round(ltv_score, 4),
        "fraud_score":     round(fraud_approval_score, 4),
        "payment_score":   round(payment_score, 4),
        "composite_score": round(composite, 4),
    }
    return outcome, components


def _write_decision(order_id: str, outcome: str, components: dict) -> None:
    decision_at = int(time.time() * 1000)
    orders_table.update_item(
        Key={"order_id": order_id},
        UpdateExpression=(
            "SET #d = :d, decision_at = :da, decision_score = :ds, "
            "ltv_score = :ls, fraud_score = :fs, payment_score = :ps, "
            "model_version = :mv"
        ),
        ExpressionAttributeNames={"#d": "decision"},
        ExpressionAttributeValues={
            ":d":  outcome,
            ":da": decision_at,
            ":ds": Decimal(str(components["composite_score"])),
            ":ls": Decimal(str(components["ltv_score"])),
            ":fs": Decimal(str(components["fraud_score"])),
            ":ps": Decimal(str(components["payment_score"])),
            ":mv": MODEL_VERSION,
        },
        ConditionExpression="attribute_not_exists(decision)",  # idempotency guard
    )


def lambda_handler(event: dict, context: Any) -> dict:
    processed = 0
    skipped   = 0
    errors    = 0

    for record in event.get("Records", []):
        if record.get("eventName") != "INSERT":
            skipped += 1
            continue

        new_image = record.get("dynamodb", {}).get("NewImage", {})
        if not new_image:
            skipped += 1
            continue

        order = _deserialize_dynamo_record(new_image)
        order_id = order.get("order_id")
        if not order_id:
            logger.warning("Record missing order_id; skipping")
            skipped += 1
            continue

        try:
            outcome, components = _score_order(order)
            _write_decision(order_id, outcome, components)

            logger.info(json.dumps({
                "event": "decision_made",
                "order_id": order_id,
                "outcome": outcome,
                **components,
            }))
            processed += 1

        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            logger.info(json.dumps({"event": "already_decided", "order_id": order_id}))
            skipped += 1

        except Exception as exc:
            logger.error(json.dumps({
                "event": "decision_error",
                "order_id": order_id,
                "error": str(exc),
            }))
            errors += 1

    summary = {"processed": processed, "skipped": skipped, "errors": errors}
    logger.info(json.dumps({"event": "batch_complete", **summary}))

    if errors:
        raise RuntimeError(f"{errors} records failed — Lambda will retry batch")

    return summary
