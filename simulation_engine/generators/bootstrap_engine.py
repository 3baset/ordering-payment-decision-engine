from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import numpy as np

from schemas.customer_events import CustomerCreated
from schemas.order_events import OrderCreated, OrderDelivered, OrderLine
from schemas.payment_events import InvoiceCreated, PaymentCaptured
from store.shared_state import SIM_START, CustomerState

if TYPE_CHECKING:
    from store.event_store import DuckDBEventStore
    from store.shared_state import InventoryState


class BootstrapEngine:
    """Generate historical events for the warm-start period (180 days before SIM_START)."""

    def __init__(
        self,
        customers: dict[str, CustomerState],
        skus: dict[str, "InventoryState"],
        store: "DuckDBEventStore",
        config: dict,
        fake,
    ) -> None:
        self.customers = customers
        self.skus = skus
        self.store = store
        self.config = config
        self.fake = fake
        self._lookback = config.get("bootstrap", {}).get("lookback_days", 180)
        self._min_orders = config.get("bootstrap", {}).get("min_orders", 3)
        self._max_orders = config.get("bootstrap", {}).get("max_orders", 12)

    def generate_history(self) -> None:
        """Emit historical events and update CustomerState in-place."""
        sku_list = list(self.skus.values())
        if not sku_list:
            return

        for customer in self.customers.values():
            self._emit_customer_created(customer)
            n_orders = random.randint(self._min_orders, self._max_orders)
            # Distribute order dates over the lookback window
            order_days = sorted(
                random.sample(range(1, self._lookback), min(n_orders, self._lookback - 1))
            )
            for day_offset in order_days:
                hist_dt = SIM_START - timedelta(days=self._lookback - day_offset)
                # SimPy time is negative (before simulation start)
                sim_t = -(self._lookback - day_offset)
                self._emit_historical_order(customer, hist_dt, sim_t, sku_list)

    def _emit_customer_created(self, customer: CustomerState) -> None:
        # Timestamp: 365 days before simulation start
        ts = SIM_START - timedelta(days=365)
        evt = CustomerCreated(
            aggregate_id=customer.customer_id,
            timestamp=ts,
            segment=customer.segment,
            credit_limit=customer.credit_limit,
            acquisition_channel="bootstrap",
            rep_id=customer.rep_id,
            digital_active=customer.digital_active,
            customer_type=customer.customer_type,
            area_id=customer.area_id,
            payment_method=customer.payment_method,
            risk_score=customer.risk_score,
            name=customer.name,
            phone=customer.phone,
        )
        self.store.emit(evt)

    def _emit_historical_order(
        self,
        customer: CustomerState,
        hist_dt: datetime,
        sim_t: float,
        sku_list: list,
    ) -> None:
        from engines.ordering_engine import BASKET_LOGNORMAL
        params = BASKET_LOGNORMAL.get(customer.segment, BASKET_LOGNORMAL["regular"])
        total_value = float(np.random.lognormal(params["mean_log"], params["sigma"]))

        # Build 1-4 order lines
        n_lines = random.randint(1, 4)
        chosen_skus = random.sample(sku_list, min(n_lines, len(sku_list)))
        lines: list[OrderLine] = []
        remaining = total_value
        for i, inv in enumerate(chosen_skus):
            if i == len(chosen_skus) - 1:
                line_total = remaining
            else:
                line_total = remaining * random.uniform(0.2, 0.6)
                remaining -= line_total
            qty = max(1, int(line_total / inv.unit_price))
            unit_price = inv.unit_price
            actual_total = round(qty * unit_price, 2)
            lines.append(OrderLine(
                sku_id=inv.sku_id,
                quantity=qty,
                unit_price=unit_price,
                line_total=actual_total,
            ))
        order_total = round(sum(l.line_total for l in lines), 2)

        order_id = f"ORD-BOOT-{str(uuid.uuid4())[:8].upper()}"
        invoice_id = f"INV-BOOT-{str(uuid.uuid4())[:8].upper()}"

        order_evt = OrderCreated(
            aggregate_id=customer.customer_id,
            timestamp=hist_dt,
            customer_id=customer.customer_id,
            order_id=order_id,
            total_value=order_total,
            lines=lines,
            channel="direct",
        )
        self.store.emit(order_evt)

        deliver_dt = hist_dt + timedelta(days=random.randint(2, 5))
        deliver_evt = OrderDelivered(
            aggregate_id=customer.customer_id,
            timestamp=deliver_dt,
            order_id=order_id,
            customer_id=customer.customer_id,
        )
        self.store.emit(deliver_evt)

        # Most historical invoices are paid
        due_dt = deliver_dt + timedelta(days=30)
        inv_evt = InvoiceCreated(
            aggregate_id=customer.customer_id,
            timestamp=deliver_dt,
            invoice_id=invoice_id,
            order_id=order_id,
            customer_id=customer.customer_id,
            amount=order_total,
            due_date=due_dt,
        )
        self.store.emit(inv_evt)

        if random.random() < 0.80:  # 80% paid in bootstrap
            pay_dt = deliver_dt + timedelta(days=random.randint(5, 35))
            pay_evt = PaymentCaptured(
                aggregate_id=customer.customer_id,
                timestamp=pay_dt,
                invoice_id=invoice_id,
                customer_id=customer.customer_id,
                amount=order_total,
                payment_method=customer.payment_method,
            )
            self.store.emit(pay_evt)
        else:
            # Unpaid: add to credit_used
            customer.credit_used += order_total

        # Update last_order_time
        customer.last_order_time = sim_t
        if customer.status == "new":
            customer.status = "active"
