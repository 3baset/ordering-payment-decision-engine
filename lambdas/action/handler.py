"""
Action Lambda — triggered by DynamoDB Streams MODIFY events on oda-orders
where 'decision' attribute EXISTS and 'post_decision_action' does NOT exist.

This guard (enforced by Streams FilterCriteria in CDK) prevents infinite loops:
  MODIFY → write post_decision_action → next MODIFY already has the field → filter drops it.

Routing logic:
  AUTO_APPROVE  → FULFILLED  (log confirmation, mark order ready for pick-pack)
  MANUAL_REVIEW → ESCALATED  (log to review queue with priority tier)
  DECLINE       → REJECTED   (log rejection reason, notify credit team)
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

dynamodb      = boto3.resource("dynamodb")
orders_table  = dynamodb.Table(os.environ["ORDERS_TABLE"])
action_log_table = dynamodb.Table(os.environ["ACTION_LOG_TABLE"])
_deserializer = TypeDeserializer()


# ── Routing ──────────────────────────────────────────────────────────────────

def _route(decision: str, composite_score: float) -> tuple[str, str, str]:
    """Return (post_decision_action, action_detail, priority)."""
    if decision == "AUTO_APPROVE":
        return (
            "FULFILLED",
            "Order approved and routed to fulfillment DC",
            "normal",
        )
    if decision == "MANUAL_REVIEW":
        priority = "high" if composite_score < 0.55 else "medium"
        return (
            "ESCALATED",
            f"Order escalated to review queue — score {composite_score:.3f}",
            priority,
        )
    # DECLINE
    return (
        "REJECTED",
        "Order declined — insufficient approval score; credit team notified",
        "normal",
    )


def _deserialize_dynamo_record(dynamo_map: dict) -> dict:
    return {k: _deserializer.deserialize(v) for k, v in dynamo_map.items()}


def _write_action(order: dict, action: str, detail: str, priority: str) -> None:
    order_id    = order["order_id"]
    now_ms      = int(time.time() * 1000)
    action_id   = str(uuid.uuid4())

    # 1. Write to action log table
    action_log_table.put_item(Item={
        "action_id":          action_id,
        "order_id":           order_id,
        "action":             action,
        "action_detail":      detail,
        "priority":           priority,
        "decision":           order.get("decision", "UNKNOWN"),
        "composite_score":    Decimal(str(order.get("decision_score", 0))),
        "customer_id":        order.get("customer_id", ""),
        "customer_segment":   order.get("customer_segment", ""),
        "total_amount":       Decimal(str(order.get("total_amount", 0))),
        "payment_method":     order.get("payment_method", ""),
        "actioned_at":        now_ms,
    })

    # 2. Write post_decision_action back to orders table (this prevents re-trigger)
    orders_table.update_item(
        Key={"order_id": order_id},
        UpdateExpression=(
            "SET post_decision_action = :a, "
            "post_decision_action_id = :aid, "
            "post_decision_at = :t"
        ),
        ExpressionAttributeValues={
            ":a":   action,
            ":aid": action_id,
            ":t":   now_ms,
        },
        ConditionExpression="attribute_not_exists(post_decision_action)",  # idempotency
    )


def lambda_handler(event: dict, context: Any) -> dict:
    processed = 0
    skipped   = 0
    errors    = 0

    for record in event.get("Records", []):
        if record.get("eventName") != "MODIFY":
            skipped += 1
            continue

        new_image = record.get("dynamodb", {}).get("NewImage", {})
        if not new_image:
            skipped += 1
            continue

        order = _deserialize_dynamo_record(new_image)
        order_id = order.get("order_id")
        decision = order.get("decision")

        if not order_id or not decision:
            skipped += 1
            continue

        # Belt-and-suspenders guard (FilterCriteria already handles this at source)
        if order.get("post_decision_action"):
            skipped += 1
            continue

        try:
            score   = float(order.get("decision_score", 0) or 0)
            action, detail, priority = _route(decision, score)
            _write_action(order, action, detail, priority)

            logger.info(json.dumps({
                "event": "action_taken",
                "order_id": order_id,
                "decision": decision,
                "action": action,
                "priority": priority,
                "composite_score": score,
            }))
            processed += 1

        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            logger.info(json.dumps({"event": "already_actioned", "order_id": order_id}))
            skipped += 1

        except Exception as exc:
            logger.error(json.dumps({
                "event": "action_error",
                "order_id": order_id,
                "error": str(exc),
            }))
            errors += 1

    summary = {"processed": processed, "skipped": skipped, "errors": errors}
    logger.info(json.dumps({"event": "batch_complete", **summary}))

    if errors:
        raise RuntimeError(f"{errors} records failed — Lambda will retry batch")

    return summary
