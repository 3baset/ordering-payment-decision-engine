from __future__ import annotations

import uuid
from datetime import timedelta
from typing import TYPE_CHECKING

from schemas.payment_events import (
    InvoiceCreated,
    PaymentCaptured,
    PaymentFailed,
    PaymentInitiated,
)
from store.shared_state import SIM_START, sim_time_to_dt

if TYPE_CHECKING:
    import simpy
    from store.event_store import DuckDBEventStore
    from store.shared_state import CustomerState, SharedSimulationState


class InvoiceProcess:
    """Gamma-delayed payment flow; escalates to CollectionProcess after 3 failures."""

    def __init__(
        self,
        env: "simpy.Environment",
        customer: "CustomerState",
        order_id: str,
        order_total: float,
        state: "SharedSimulationState",
        store: "DuckDBEventStore",
        config: dict,
    ) -> None:
        self.env = env
        self.customer = customer
        self.order_id = order_id
        self.order_total = order_total
        self.state = state
        self.store = store
        pay_cfg = config.get("payments", {})
        self.terms_days = pay_cfg.get("terms_days", 30)
        self.max_attempts = pay_cfg.get("max_payment_attempts", 3)
        self.retry_days = pay_cfg.get("retry_days", 7)
        self.config = config

    def run(self):
        now = self.env.now
        ts = sim_time_to_dt(now)
        invoice_id = f"INV-{str(uuid.uuid4())[:8].upper()}"
        due_dt = SIM_START + timedelta(days=int(now) + self.terms_days, hours=8)

        self.store.emit(InvoiceCreated(
            aggregate_id=self.customer.customer_id,
            timestamp=ts,
            invoice_id=invoice_id,
            order_id=self.order_id,
            customer_id=self.customer.customer_id,
            amount=self.order_total,
            due_date=due_dt,
            terms_days=self.terms_days,
        ))

        from engines.payment_engine import attempt_payment, sample_payment_delay

        delay = sample_payment_delay(self.customer.risk_score)
        yield self.env.timeout(self.terms_days + delay)

        remaining_balance = self.order_total
        invoice_start_time = now

        for attempt in range(1, self.max_attempts + 1):
            attempt_ts = sim_time_to_dt(self.env.now)
            self.store.emit(PaymentInitiated(
                aggregate_id=invoice_id,
                timestamp=attempt_ts,
                invoice_id=invoice_id,
                customer_id=self.customer.customer_id,
                amount=remaining_balance,
                attempt_number=attempt,
            ))

            if attempt_payment(self.customer.risk_score):
                self.store.emit(PaymentCaptured(
                    aggregate_id=invoice_id,
                    timestamp=attempt_ts,
                    invoice_id=invoice_id,
                    customer_id=self.customer.customer_id,
                    amount=remaining_balance,
                    payment_method=self.customer.payment_method,
                ))
                return  # Success

            self.store.emit(PaymentFailed(
                aggregate_id=invoice_id,
                timestamp=attempt_ts,
                invoice_id=invoice_id,
                customer_id=self.customer.customer_id,
                amount=remaining_balance,
                attempt_number=attempt,
            ))

            if attempt < self.max_attempts:
                yield self.env.timeout(self.retry_days)

        # All attempts failed → spawn CollectionProcess
        from processes.collection_process import CollectionProcess
        self.env.process(CollectionProcess(
            self.env,
            self.customer,
            invoice_id,
            remaining_balance,
            invoice_start_time,
            self.state,
            self.store,
            self.config,
        ).run())
