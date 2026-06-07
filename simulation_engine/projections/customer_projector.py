from __future__ import annotations

import polars as pl

from projections.base_projector import BaseProjector


class CustomerProjector(BaseProjector):
    def project_customers(self) -> None:
        created = self.read_events("CustomerCreated")
        created = self.unpack_payload(created, [
            "segment", "credit_limit", "acquisition_channel", "rep_id",
            "digital_active", "customer_type", "area_id", "payment_method",
            "risk_score", "name", "phone",
        ])
        created = created.rename({"timestamp": "created_at", "aggregate_id": "customer_id"})

        # Latest lifecycle status per customer
        lifecycle_events = self.read_events_multi([
            "CustomerCreated", "CustomerBecameInactive", "CustomerBecameDormant",
            "CustomerChurned", "CustomerReactivated",
        ])
        lifecycle_status = (
            lifecycle_events
            .sort("timestamp")
            .group_by("aggregate_id")
            .agg(pl.col("event_type").last().alias("latest_event"))
            .with_columns(
                pl.col("latest_event")
                .map_elements(lambda e: {
                    "CustomerCreated": "active",
                    "CustomerBecameInactive": "inactive",
                    "CustomerBecameDormant": "dormant",
                    "CustomerChurned": "churned",
                    "CustomerReactivated": "active",
                }.get(e, "active"), return_dtype=pl.String)
                .alias("status")
            )
            .rename({"aggregate_id": "customer_id"})
        )

        customers = (
            created
            .join(
                lifecycle_status.select(["customer_id", "status"]),
                on="customer_id",
                how="left",
            )
            .with_columns(pl.col("status").fill_null("active"))
        )
        self.write(customers, "customers")

    def project_customer_history(self) -> None:
        # One row per lifecycle transition event
        events = self.read_events_multi([
            "CustomerCreated", "CustomerBecameInactive", "CustomerBecameDormant",
            "CustomerChurned", "CustomerReactivated", "CustomerSegmentChanged",
        ])
        history = self.unpack_payload(events, ["segment", "days_without_order"])
        history = history.rename({"aggregate_id": "customer_id"})
        self.write(history, "customer_history")
