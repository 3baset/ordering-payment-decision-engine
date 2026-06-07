"""
Seed DynamoDB oda-orders table from Sample A Parquet files.

Joins orders + customers + rfm_scores to produce denormalised records
that the Decision Lambda can score without additional lookups.

Usage:
    python scripts/seed.py                        # all orders in sample_a
    python scripts/seed.py --limit 500            # first N orders (for smoke test)
    python scripts/seed.py --table my-table       # override table name
    python scripts/seed.py --dry-run              # print rows, don't write
"""

import argparse
import json
import os
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

import boto3
import pyarrow.parquet as pq

# ── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT   = Path(__file__).parent.parent
DATA_DIR    = REPO_ROOT / "data" / "sample_a"
BATCH_SIZE  = 25          # DynamoDB BatchWrite limit

SEGMENT_MAP = {
    "premium":    "premium",
    "regular":    "standard",
    "low_volume": "at-risk",
}


def _safe_decimal(value) -> Decimal:
    """Convert any numeric-ish value to Decimal, defaulting to 0."""
    try:
        return Decimal(str(float(value)))
    except (TypeError, ValueError, InvalidOperation):
        return Decimal("0")


def _parse_payload(raw) -> dict:
    if not raw or raw == "None":
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def load_tables() -> tuple[dict, dict]:
    """Return (customer_map, rfm_map) keyed by customer_id."""
    print("Loading customers …", flush=True)
    cust_df = pq.read_table(DATA_DIR / "customers.parquet").to_pydict()
    customer_map: dict[str, dict] = {}
    for i, cid in enumerate(cust_df["customer_id"]):
        customer_map[cid] = {
            "segment":        SEGMENT_MAP.get(str(cust_df["segment"][i] or "regular"), "standard"),
            "payment_method": str(cust_df["payment_method"][i] or "cash"),
            "credit_limit":   _safe_decimal(cust_df["credit_limit"][i]),
            "risk_score":     _safe_decimal(cust_df["risk_score"][i]),
            "customer_type":  str(cust_df["customer_type"][i] or ""),
            "area_id":        str(cust_df["area_id"][i] or ""),
        }

    print("Loading RFM scores …", flush=True)
    rfm_df = pq.read_table(DATA_DIR / "rfm_scores.parquet").to_pydict()
    rfm_map: dict[str, dict] = {}
    for i, cid in enumerate(rfm_df["customer_id"]):
        # keep the most recent row per customer (last wins — data is ordered)
        rfm_map[cid] = {
            "r_score": str(rfm_df["r_score"][i] or ""),
            "f_score": str(rfm_df["f_score"][i] or ""),
            "m_score": str(rfm_df["m_score"][i] or ""),
            "monetary": _safe_decimal(rfm_df["monetary"][i]),
        }

    return customer_map, rfm_map


def build_dynamo_items(limit: int | None, customer_map: dict, rfm_map: dict) -> list[dict]:
    print("Loading orders …", flush=True)
    orders_df = pq.read_table(DATA_DIR / "orders.parquet").to_pydict()
    total = len(orders_df["order_id"])
    cap   = min(total, limit) if limit else total
    items = []

    for i in range(cap):
        order_id   = str(orders_df["order_id"][i] or "")
        customer_id = str(orders_df["customer_id"][i] or "")
        if not order_id or not customer_id:
            continue

        payload = _parse_payload(orders_df["payload"][i])

        fraud_raw = orders_df["fraud_score"][i]
        fraud_score = _safe_decimal(fraud_raw if fraud_raw not in (None, "None") else
                                    payload.get("fraud_score", 0.5))

        cust    = customer_map.get(customer_id, {})
        rfm     = rfm_map.get(customer_id, {})

        item = {
            "order_id":         order_id,
            "customer_id":      customer_id,
            "event_id":         str(orders_df["event_id"][i] or ""),
            "event_type":       str(orders_df["event_type"][i] or ""),
            "created_at":       str(orders_df["created_at"][i] or ""),
            "status":           str(orders_df["status"][i] or ""),
            "channel":          str(orders_df["channel"][i] or ""),
            "rep_id":           str(orders_df["rep_id"][i] or ""),
            "total_amount":     _safe_decimal(orders_df["total_value"][i]),
            "fraud_score":      fraud_score,
            # Customer context (denormalised for Lambda cold-read avoidance)
            "customer_segment": cust.get("segment", "standard"),
            "payment_method":   cust.get("payment_method", "cash"),
            "credit_limit":     cust.get("credit_limit", Decimal("0")),
            "customer_risk":    cust.get("risk_score", Decimal("0")),
            "customer_type":    cust.get("customer_type", ""),
            "area_id":          cust.get("area_id", ""),
            # RFM context
            "rfm_r":            rfm.get("r_score", ""),
            "rfm_f":            rfm.get("f_score", ""),
            "rfm_m":            rfm.get("m_score", ""),
            "rfm_monetary":     rfm.get("monetary", Decimal("0")),
        }

        # Strip empty strings (DynamoDB rejects them)
        item = {k: v for k, v in item.items() if v != "" and v is not None}
        items.append(item)

    return items


def write_to_dynamo(items: list[dict], table_name: str, dry_run: bool) -> None:
    if dry_run:
        print(f"DRY RUN — would write {len(items)} items to '{table_name}'")
        print(json.dumps({k: str(v) for k, v in items[0].items()}, indent=2))
        return

    ddb = boto3.resource("dynamodb")
    table = ddb.Table(table_name)

    written = 0
    start   = time.time()

    for chunk_start in range(0, len(items), BATCH_SIZE):
        chunk = items[chunk_start : chunk_start + BATCH_SIZE]
        with table.batch_writer() as batch:
            for item in chunk:
                batch.put_item(Item=item)
        written += len(chunk)

        elapsed = time.time() - start
        rate    = written / elapsed
        pct     = written / len(items) * 100
        print(f"\r  {pct:5.1f}%  {written:,}/{len(items):,} items  ({rate:.0f} items/s)", end="", flush=True)

    print(f"\nDone — {written:,} items written to '{table_name}' in {time.time()-start:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed DynamoDB from Sample A Parquet")
    parser.add_argument("--table",   default="oda-orders", help="DynamoDB table name")
    parser.add_argument("--limit",   type=int, default=None,  help="Max rows to seed (default: all)")
    parser.add_argument("--dry-run", action="store_true",     help="Print first item, no writes")
    args = parser.parse_args()

    customer_map, rfm_map = load_tables()
    items = build_dynamo_items(args.limit, customer_map, rfm_map)
    print(f"Built {len(items):,} items for '{args.table}'")
    write_to_dynamo(items, args.table, args.dry_run)


if __name__ == "__main__":
    main()
