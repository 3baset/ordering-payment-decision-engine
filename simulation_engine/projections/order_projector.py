from __future__ import annotations

from typing import TYPE_CHECKING

import polars as pl

from projections.base_projector import BaseProjector

if TYPE_CHECKING:
    from store.event_store import DuckDBEventStore


class OrderProjector(BaseProjector):
    def project_orders(self) -> None:
        created = self.read_events("OrderCreated")
        created = self.unpack_payload(created, [
            "order_id", "customer_id", "total_value", "channel", "rep_id",
            "fraud_score", "promotion_id",
        ])
        created = created.rename({"timestamp": "created_at"})

        # Latest status per order, joined by order_id from payload.
        # OrderRejected is excluded: it has no order_id (rejection = no order created).
        status_events = self.read_events_multi([
            "OrderShipped", "OrderDelivered", "OrderCancelled", "OrderReturned",
        ])
        status_events = self.unpack_payload(status_events, ["order_id"])
        status_events = status_events.filter(pl.col("order_id").is_not_null())

        statuses = (
            status_events
            .sort("timestamp")
            .group_by("order_id")
            .agg(pl.col("event_type").last().alias("status"))
        )

        orders = (
            created
            .with_columns(pl.col("total_value").cast(pl.Float64))
            .join(statuses, on="order_id", how="left")
            .with_columns(
                pl.col("status").fill_null("OrderCreated")
            )
        )
        self.write(orders, "orders")

    def project_order_lines(self) -> None:
        created = self.read_events("OrderCreated")
        created = self.unpack_payload(created, ["order_id", "customer_id"])

        # Explode lines JSON array using typed json_decode + unnest
        line_dtype = pl.List(pl.Struct({
            "sku_id": pl.String,
            "quantity": pl.Int64,
            "unit_price": pl.Float64,
            "line_total": pl.Float64,
            "demand_class": pl.String,
            "promotion_applied": pl.Boolean,
            "discount_amount": pl.Float64,
        }))

        lines_lf = (
            created
            .with_columns(
                pl.col("payload")
                .str.json_path_match("$.lines")
                .alias("lines_json")
            )
            .filter(pl.col("lines_json").is_not_null())
            .with_columns(
                pl.col("lines_json")
                .str.json_decode(dtype=line_dtype)
                .alias("lines_decoded")
            )
            .explode("lines_decoded")
            .unnest("lines_decoded")
            .select([
                "order_id", "customer_id", "sku_id", "quantity",
                "unit_price", "line_total", "demand_class",
            ])
        )
        self.write(lines_lf, "order_lines")
