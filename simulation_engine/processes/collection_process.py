from __future__ import annotations

import random
import uuid
from typing import TYPE_CHECKING

from schemas.payment_events import (
    CollectionPromiseMade,
    CollectionScheduled,
    CreditWrittenOff,
    PaymentCaptured,
)
from store.shared_state import SIM_START, sim_time_to_dt

if TYPE_CHECKING:
    import simpy
    from store.event_store import DuckDBEventStore
    from store.shared_state import CustomerState, SharedSimulationState


class CollectionProcess:
    """Promise-based collection flow spawned after 3 failed payment attempts."""

    def __init__(
        self,
        env: "simpy.Environment",
        customer: "CustomerState",
        invoice_id: str,
        invoice_amount: float,
        invoice_start_time: float,
        state: "SharedSimulationState",
        store: "DuckDBEventStore",
        config: dict,
    ) -> None:
        self.env = env
        self.customer = customer
        self.invoice_id = invoice_id
        self.invoice_amount = invoice_amount
        self.invoice_start_time = invoice_start_time
        self.state = state
        self.store = store
        pay_cfg = config.get("payments", {})
        self.writeoff_days = pay_cfg.get("writeoff_days", 180)

    def run(self):
        now = self.env.now
        ts = sim_time_to_dt(now)
        days_overdue = int(now - self.invoice_start_time)

        self.store.emit(CollectionScheduled(
            aggregate_id=self.invoice_id,
            timestamp=ts,
            invoice_id=self.invoice_id,
            customer_id=self.customer.customer_id,
            days_overdue=max(0, days_overdue),
            amount_due=self.invoice_amount,
        ))

        # 30% chance customer makes a promise
        if random.random() < 0.30:
            promise_days = random.randint(7, 30)
            from datetime import timedelta
            promise_dt = SIM_START + timedelta(days=int(now + promise_days), hours=8)
            self.store.emit(CollectionPromiseMade(
                aggregate_id=self.invoice_id,
                timestamp=ts,
                invoice_id=self.invoice_id,
                customer_id=self.customer.customer_id,
                promised_amount=self.invoice_amount,
                promise_date=promise_dt,
            ))
            yield self.env.timeout(promise_days)

            # Attempt payment on promise date
            from engines.payment_engine import attempt_payment
            if attempt_payment(self.customer.risk_score):
                ts2 = sim_time_to_dt(self.env.now)
                self.store.emit(PaymentCaptured(
                    aggregate_id=self.invoice_id,
                    timestamp=ts2,
                    invoice_id=self.invoice_id,
                    customer_id=self.customer.customer_id,
                    amount=self.invoice_amount,
                    payment_method=self.customer.payment_method,
                ))
                return  # Collected successfully

        # Check for write-off threshold
        remaining_days = self.writeoff_days - days_overdue
        if remaining_days > 0:
            yield self.env.timeout(remaining_days)

        # Write off
        ts3 = sim_time_to_dt(self.env.now)
        total_overdue = int(self.env.now - self.invoice_start_time)
        self.store.emit(CreditWrittenOff(
            aggregate_id=self.invoice_id,
            timestamp=ts3,
            invoice_id=self.invoice_id,
            customer_id=self.customer.customer_id,
            amount=self.invoice_amount,
            days_overdue=total_overdue,
        ))
