from __future__ import annotations

import random
from datetime import timedelta
from typing import TYPE_CHECKING

import numpy as np

from store.shared_state import sim_time_to_dt, SIM_START

if TYPE_CHECKING:
    import simpy
    from faker import Faker
    from store.event_store import DuckDBEventStore
    from store.shared_state import SharedSimulationState


class CustomerArrivalProcess:
    """Non-homogeneous Poisson arrival of new customers."""

    def __init__(
        self,
        env: "simpy.Environment",
        state: "SharedSimulationState",
        store: "DuckDBEventStore",
        config: dict,
        fake: "Faker",
    ) -> None:
        self.env = env
        self.state = state
        self.store = store
        self.config = config
        self.fake = fake
        arr = config.get("customer_arrival", {})
        self.lambda_base = arr.get("lambda_base", 5.0)
        self.growth_rate = arr.get("growth_rate", 0.002)
        raw_acq = arr.get("acquisition_seasonality", {})
        self.acquisition_seasonality = {int(k): float(v) for k, v in raw_acq.items()}

    def run(self):
        while True:
            day = self.env.now
            current_month = (SIM_START + timedelta(days=int(day))).month
            acq_season = self.acquisition_seasonality.get(current_month, 1.0)
            lambda_t = self.lambda_base * acq_season * (1.0 + self.growth_rate * day)
            # Exponential inter-arrival for Poisson process
            interval = random.expovariate(lambda_t)
            yield self.env.timeout(interval)

            now = self.env.now
            ts = sim_time_to_dt(now)

            # Generate a new customer
            from generators.customer_generator import generate_customer
            rep_ids = list(self.state.reps.keys())
            customer = generate_customer(
                self.fake,
                rep_ids=rep_ids if rep_ids else None,
                digital_active_prob=self.config.get("customers", {}).get("digital_active_probability", 0.40),
            )
            self.state.customers[customer.customer_id] = customer

            # Assign to rep
            if customer.rep_id and customer.rep_id in self.state.reps:
                self.state.reps[customer.rep_id].assigned_customers.append(customer.customer_id)

            # Emit CustomerCreated
            from schemas.customer_events import CustomerCreated, CustomerAssignedToRep
            self.store.emit(CustomerCreated(
                aggregate_id=customer.customer_id,
                timestamp=ts,
                segment=customer.segment,
                credit_limit=customer.credit_limit,
                acquisition_channel=random.choices(
                    ["rep_referral", "digital"],
                    weights=[0.60, 0.40],
                    k=1,
                )[0],
                rep_id=customer.rep_id,
                digital_active=customer.digital_active,
                customer_type=customer.customer_type,
                area_id=customer.area_id,
                payment_method=customer.payment_method,
                risk_score=customer.risk_score,
                name=customer.name,
                phone=customer.phone,
            ))
            if customer.rep_id:
                self.store.emit(CustomerAssignedToRep(
                    aggregate_id=customer.customer_id,
                    timestamp=ts,
                    rep_id=customer.rep_id,
                ))

            # Spawn per-customer processes
            from processes.customer_order_process import CustomerOrderProcess
            from processes.customer_lifecycle_process import CustomerLifecycleProcess
            from processes.app_session_process import AppSessionProcess
            self.env.process(CustomerOrderProcess(
                self.env, customer, self.state, self.store, self.config
            ).run())
            self.env.process(CustomerLifecycleProcess(
                self.env, customer, self.state, self.store, self.config
            ).run())
            if customer.digital_active:
                self.env.process(AppSessionProcess(
                    self.env, customer, self.state, self.store, self.config
                ).run())
