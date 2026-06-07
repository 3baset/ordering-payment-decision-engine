from __future__ import annotations

import polars as pl

from projections.base_projector import BaseProjector


class RFMProjector(BaseProjector):
    def project_rfm_scores(self) -> None:
        orders = self.read_events("OrderCreated")
        orders = self.unpack_payload(orders, ["customer_id", "total_value"])
        orders = orders.with_columns([
            pl.col("total_value").cast(pl.Float64),
            pl.col("timestamp").dt.truncate("1mo").alias("month"),
        ])

        # Monthly RFM per customer
        monthly = (
            orders
            .group_by(["customer_id", "month"])
            .agg([
                pl.col("timestamp").max().alias("last_order_date"),
                pl.col("total_value").count().alias("frequency"),
                pl.col("total_value").sum().alias("monetary"),
            ])
        )

        # Recency = days from last order to end of month
        rfm = (
            monthly
            .with_columns(
                (pl.col("month").dt.month_end() - pl.col("last_order_date"))
                .dt.total_days()
                .alias("recency_days")
            )
        )

        # Score R/F/M each 1-5 using quantile bins
        rfm = rfm.with_columns([
            pl.col("recency_days")
            .qcut(5, labels=["5", "4", "3", "2", "1"], allow_duplicates=True)
            .alias("r_score"),
            pl.col("frequency")
            .qcut(5, labels=["1", "2", "3", "4", "5"], allow_duplicates=True)
            .alias("f_score"),
            pl.col("monetary")
            .qcut(5, labels=["1", "2", "3", "4", "5"], allow_duplicates=True)
            .alias("m_score"),
        ])
        self.write(rfm, "rfm_scores")
