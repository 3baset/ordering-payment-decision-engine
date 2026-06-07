from __future__ import annotations

import random
import uuid
from typing import TYPE_CHECKING

from schemas.inventory_events import (
    BackorderFulfilled,
    StockReleased,
    StockReserved,
    StockoutOccurred,
)
from schemas.order_events import OrderCancelled, OrderDelivered, OrderReturned, OrderShipped
from store.shared_state import sim_time_to_dt

if TYPE_CHECKING:
    import simpy
    from schemas.order_events import OrderLine
    from store.event_store import DuckDBEventStore
    from store.shared_state import CustomerState, InventoryState, SharedSimulationState


class OrderFulfillmentProcess:
    """Handles reservation → ship → deliver → invoice → optional return."""

    def __init__(
        self,
        env: "simpy.Environment",
        customer: "CustomerState",
        order_id: str,
        order_total: float,
        lines: list["OrderLine"],
        state: "SharedSimulationState",
        store: "DuckDBEventStore",
        config: dict,
    ) -> None:
        self.env = env
        self.customer = customer
        self.order_id = order_id
        self.order_total = order_total
        self.lines = lines
        self.state = state
        self.store = store
        self.config = config
        inv_cfg = config.get("inventory", {})
        res = inv_cfg.get("stockout_resolution", {})
        self.stockout_weights = [
            res.get("substitute", 0.30),
            res.get("backorder", 0.20),
            res.get("cancel_line", 0.50),
        ]
        self.stockout_choices = ["substitute", "backorder", "cancel_line"]
        self.cancel_prob = config.get("fraud", {}).get("cancellation_probability", 0.005)
        self.return_prob = config.get("fraud", {}).get("return_probability", 0.05)
        self.return_min = config.get("fraud", {}).get("return_days_min", 3)
        self.return_max = config.get("fraud", {}).get("return_days_max", 14)

    def run(self):
        # Small cancellation window (0-0.5 days)
        yield self.env.timeout(random.uniform(0.0, 0.5))
        if random.random() < self.cancel_prob:
            ts = sim_time_to_dt(self.env.now)
            self.store.emit(OrderCancelled(
                aggregate_id=self.customer.customer_id,
                timestamp=ts,
                order_id=self.order_id,
                customer_id=self.customer.customer_id,
                reason="customer_request",
            ))
            self.customer.credit_used = max(0.0, self.customer.credit_used - self.order_total)
            return

        # Inventory reservation per line
        fulfilled_total = 0.0
        for line in self.lines:
            inv = self.state.skus.get(line.sku_id)
            if inv is None:
                fulfilled_total += line.line_total
                continue

            ts = sim_time_to_dt(self.env.now)
            if inv.container.level >= line.quantity:
                # Bypass SimPy Container's FIFO get-queue to avoid starvation.
                # _trigger_get stops at the first unsatisfiable get (e.g. a large
                # _backorder ahead in the queue), which would block this smaller
                # reservation even when stock is available. Direct level update +
                # manual trigger is semantically equivalent but queue-order-safe.
                inv.container._level -= line.quantity
                inv.container._trigger_get(None)
                self.store.emit(StockReserved(
                    aggregate_id=line.sku_id,
                    timestamp=ts,
                    sku_id=line.sku_id,
                    quantity=line.quantity,
                    order_id=self.order_id,
                ))
                fulfilled_total += line.line_total
            else:
                available = int(inv.container.level)
                resolution = random.choices(self.stockout_choices, weights=self.stockout_weights, k=1)[0]
                self.store.emit(StockoutOccurred(
                    aggregate_id=line.sku_id,
                    timestamp=ts,
                    sku_id=line.sku_id,
                    requested_quantity=line.quantity,
                    available_quantity=available,
                    order_id=self.order_id,
                    resolution=resolution,
                ))
                if resolution == "substitute":
                    fulfilled_total += line.line_total
                elif resolution == "backorder":
                    self.env.process(
                        self._backorder(inv, line.quantity, line.sku_id)
                    )
                # cancel_line: nothing

        # Transit: 1-2 days to ship
        yield self.env.timeout(1.0 + random.uniform(0, 1.0))
        ts = sim_time_to_dt(self.env.now)
        self.store.emit(OrderShipped(
            aggregate_id=self.customer.customer_id,
            timestamp=ts,
            order_id=self.order_id,
            customer_id=self.customer.customer_id,
        ))

        # Delivery: 1-3 more days
        yield self.env.timeout(1.0 + random.uniform(0, 2.0))
        ts = sim_time_to_dt(self.env.now)
        self.store.emit(OrderDelivered(
            aggregate_id=self.customer.customer_id,
            timestamp=ts,
            order_id=self.order_id,
            customer_id=self.customer.customer_id,
        ))
        # Release credit at delivery: the order is now an invoice; the credit line is free.
        self.customer.credit_used = max(0.0, self.customer.credit_used - self.order_total)

        # Spawn invoice process (do not await)
        from processes.invoice_process import InvoiceProcess
        self.env.process(InvoiceProcess(
            self.env,
            self.customer,
            self.order_id,
            self.order_total,
            self.state,
            self.store,
            self.config,
        ).run())

        # Optional return (5%)
        if random.random() < self.return_prob:
            self.env.process(self._return_process())

    def _backorder(self, inv: "InventoryState", qty: int, sku_id: str):
        """Block until stock arrives, then record fulfillment."""
        yield inv.container.get(qty)
        ts = sim_time_to_dt(self.env.now)
        self.store.emit(BackorderFulfilled(
            aggregate_id=sku_id,
            timestamp=ts,
            sku_id=sku_id,
            quantity=qty,
            order_id=self.order_id,
        ))

    def _return_process(self):
        delay = random.randint(self.return_min, self.return_max)
        yield self.env.timeout(delay)
        ts = sim_time_to_dt(self.env.now)
        return_value = self.order_total * random.uniform(0.3, 1.0)
        self.store.emit(OrderReturned(
            aggregate_id=self.customer.customer_id,
            timestamp=ts,
            order_id=self.order_id,
            customer_id=self.customer.customer_id,
            return_value=round(return_value, 2),
            reason=random.choice(["damaged", "wrong_item", "quality"]),
        ))
