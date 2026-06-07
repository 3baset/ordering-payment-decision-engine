from __future__ import annotations

import random
import uuid
from typing import TYPE_CHECKING

import numpy as np

from schemas.inventory_events import PurchaseOrderCreated, StockReceived, SupplierDelay
from store.shared_state import sim_time_to_dt

if TYPE_CHECKING:
    import simpy
    from store.event_store import DuckDBEventStore
    from store.shared_state import InventoryState, SharedSimulationState

LEAD_TIME_CHOICES = [3, 5, 7, 10, 14]
LEAD_TIME_WEIGHTS = [20, 30, 25, 15, 10]


class InventoryMonitorProcess:
    """Daily reorder check per SKU using simpy.Container."""

    def __init__(
        self,
        env: "simpy.Environment",
        inv: "InventoryState",
        state: "SharedSimulationState",
        store: "DuckDBEventStore",
        config: dict,
    ) -> None:
        self.env = env
        self.inv = inv
        self.state = state
        self.store = store
        inv_cfg = config.get("inventory", {})
        self.supplier_delay_prob = inv_cfg.get("supplier_delay_probability", 0.05)
        self.delay_min = inv_cfg.get("supplier_delay_days_min", 1)
        self.delay_max = inv_cfg.get("supplier_delay_days_max", 15)

    def run(self):
        while True:
            yield self.env.timeout(1.0)
            sku_id = self.inv.sku_id

            level = self.inv.container.level
            on_order = 1 if self.state.pending_pos.get(sku_id, False) else 0

            if level <= self.inv.reorder_point and not self.state.pending_pos.get(sku_id):
                from engines.inventory_engine import compute_order_quantity
                qty = compute_order_quantity(
                    self.inv.eoq,
                    self.inv.reorder_point,
                    level,
                    0,
                    self.inv.safety_stock,
                )
                lead_time = random.choices(LEAD_TIME_CHOICES, weights=LEAD_TIME_WEIGHTS, k=1)[0]
                po_id = f"PO-{str(uuid.uuid4())[:8].upper()}"
                supplier_id = f"SUP-{self.inv.sku_id[:3]}"

                self.state.pending_pos[sku_id] = True
                ts = sim_time_to_dt(self.env.now)
                self.store.emit(PurchaseOrderCreated(
                    aggregate_id=sku_id,
                    timestamp=ts,
                    sku_id=sku_id,
                    quantity=qty,
                    supplier_id=supplier_id,
                    expected_lead_time_days=lead_time,
                ))
                self.env.process(self._po_arrival(sku_id, qty, lead_time, po_id, supplier_id))

    def _po_arrival(self, sku_id: str, qty: int, lead_time: int, po_id: str, supplier_id: str):
        actual_delay = lead_time
        if random.random() < self.supplier_delay_prob:
            extra = random.randint(self.delay_min, self.delay_max)
            actual_delay += extra
            ts = sim_time_to_dt(self.env.now)
            self.store.emit(SupplierDelay(
                aggregate_id=sku_id,
                timestamp=ts,
                sku_id=sku_id,
                purchase_order_id=po_id,
                original_eta_days=lead_time,
                delay_days=extra,
            ))

        yield self.env.timeout(actual_delay)

        # container.put() unblocks any waiting container.get() calls (backorders)
        capacity_remaining = self.inv.container.capacity - self.inv.container.level
        put_qty = min(qty, capacity_remaining)
        if put_qty > 0:
            yield self.inv.container.put(put_qty)

        self.state.pending_pos[sku_id] = False
        ts = sim_time_to_dt(self.env.now)
        self.store.emit(StockReceived(
            aggregate_id=sku_id,
            timestamp=ts,
            sku_id=sku_id,
            quantity=put_qty,
            supplier_id=supplier_id,
            purchase_order_id=po_id,
        ))
