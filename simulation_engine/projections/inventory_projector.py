from __future__ import annotations

import polars as pl

from projections.base_projector import BaseProjector


class InventoryProjector(BaseProjector):
    def project_inventory_snapshot(self) -> None:
        received = self.read_events("StockReceived")
        received = self.unpack_payload(received, ["sku_id", "quantity"])
        received = received.with_columns(pl.col("quantity").cast(pl.Int64))

        reserved = self.read_events("StockReserved")
        reserved = self.unpack_payload(reserved, ["sku_id", "quantity"])
        reserved = reserved.with_columns(pl.col("quantity").cast(pl.Int64).alias("reserved_qty"))

        released = self.read_events("StockReleased")
        released = self.unpack_payload(released, ["sku_id", "quantity"])
        released = released.with_columns(pl.col("quantity").cast(pl.Int64).alias("released_qty"))

        # Aggregate net received, net reserved per SKU
        net_received = (
            received
            .group_by("sku_id")
            .agg(pl.col("quantity").sum().alias("total_received"))
        )
        net_reserved = (
            reserved
            .group_by("sku_id")
            .agg(pl.col("reserved_qty").sum().alias("total_reserved"))
        )
        net_released = (
            released
            .group_by("sku_id")
            .agg(pl.col("released_qty").sum().alias("total_released"))
        )

        snapshot = (
            net_received
            .join(net_reserved, on="sku_id", how="left")
            .join(net_released, on="sku_id", how="left")
            .with_columns([
                pl.col("total_reserved").fill_null(0),
                pl.col("total_released").fill_null(0),
            ])
            .with_columns(
                (pl.col("total_received") - pl.col("total_reserved") + pl.col("total_released"))
                .alias("estimated_on_hand")
            )
        )
        self.write(snapshot, "inventory_snapshot")

    def project_stockout_events(self) -> None:
        stockouts = self.read_events("StockoutOccurred")
        stockouts = self.unpack_payload(stockouts, [
            "sku_id", "requested_quantity", "available_quantity", "order_id", "resolution",
        ])
        stockouts = stockouts.rename({"aggregate_id": "sku_id_agg"})
        self.write(stockouts, "stockout_events")
