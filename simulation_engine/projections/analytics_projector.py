from __future__ import annotations

import polars as pl

from projections.base_projector import BaseProjector


class AnalyticsProjector(BaseProjector):
    def project_monthly_customer_snapshot(self) -> None:
        events = self.read_events_multi([
            "CustomerCreated", "CustomerBecameInactive",
            "CustomerBecameDormant", "CustomerChurned", "CustomerReactivated",
        ])
        snapshot = (
            events
            .with_columns(pl.col("timestamp").dt.truncate("1mo").alias("month"))
            .group_by(["month", "event_type"])
            .agg(pl.len().alias("count"))
            .sort(["month", "event_type"])
        )
        self.write(snapshot, "monthly_customer_snapshot")

    def project_rep_performance(self) -> None:
        visits = self.read_events("RepVisitCompleted")
        visits = self.unpack_payload(visits, ["rep_id", "customer_id", "outcome"])
        visits = visits.with_columns(pl.col("timestamp").dt.truncate("1mo").alias("month"))

        orders = self.read_events("OrderCreated")
        orders = self.unpack_payload(orders, ["customer_id", "total_value", "rep_id"])
        orders = orders.with_columns([
            pl.col("total_value").cast(pl.Float64),
            pl.col("timestamp").dt.truncate("1mo").alias("month"),
        ])

        visit_counts = (
            visits
            .group_by(["rep_id", "month"])
            .agg([
                pl.len().alias("total_visits"),
                (pl.col("outcome") != "no_order").sum().alias("order_visits"),
            ])
        )

        rep_gmv = (
            orders
            .filter(pl.col("rep_id").is_not_null())
            .group_by(["rep_id", "month"])
            .agg(pl.col("total_value").sum().alias("gmv"))
        )

        perf = visit_counts.join(rep_gmv, on=["rep_id", "month"], how="left")
        self.write(perf, "rep_performance")

    def project_promotion_performance(self) -> None:
        applied = self.read_events("PromotionApplied")
        applied = self.unpack_payload(applied, [
            "promotion_id", "order_id", "customer_id", "discount_amount", "original_value",
        ])
        applied = applied.with_columns([
            pl.col("discount_amount").cast(pl.Float64),
            pl.col("original_value").cast(pl.Float64),
        ])

        roi = (
            applied
            .group_by("promotion_id")
            .agg([
                pl.col("original_value").sum().alias("total_gmv"),
                pl.col("discount_amount").sum().alias("total_discount"),
                pl.len().alias("redemptions"),
            ])
            .with_columns(
                (pl.col("total_gmv") / pl.col("total_discount").clip(lower_bound=1.0))
                .alias("roi")
            )
        )
        self.write(roi, "promotion_roi")
