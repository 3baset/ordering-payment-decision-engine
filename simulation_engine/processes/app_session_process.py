from __future__ import annotations

import random
import uuid
from typing import TYPE_CHECKING

from schemas.macro_events import AppSessionEvent
from store.shared_state import sim_time_to_dt

if TYPE_CHECKING:
    import simpy
    from store.event_store import DuckDBEventStore
    from store.shared_state import CustomerState, SharedSimulationState


class AppSessionProcess:
    """Generates digital engagement events for a digitally-active customer."""

    def __init__(
        self,
        env: "simpy.Environment",
        customer: "CustomerState",
        state: "SharedSimulationState",
        store: "DuckDBEventStore",
        config: dict,
    ) -> None:
        self.env = env
        self.customer = customer
        self.state = state
        self.store = store
        app_cfg = config.get("app_sessions", {})
        self.base_rate = app_cfg.get("base_digital_rate", 0.15)
        self.order_conv_min = app_cfg.get("order_conversion_min", 0.15)
        self.order_conv_max = app_cfg.get("order_conversion_max", 0.80)

    def run(self):
        while True:
            # Inter-session interval (days): exponential with ~1/base_rate mean
            if self.customer.status == "churned":
                break
            interval = random.expovariate(self.base_rate)
            yield self.env.timeout(max(0.5, interval))

            if self.customer.status == "churned":
                break

            now = self.env.now
            ts = sim_time_to_dt(now)
            session_id = f"SESS-{str(uuid.uuid4())[:8].upper()}"

            # Session start
            self.store.emit(AppSessionEvent(
                aggregate_id=self.customer.customer_id,
                timestamp=ts,
                customer_id=self.customer.customer_id,
                session_id=session_id,
                event_subtype="session_start",
            ))
            # Screen views
            n_screens = random.randint(1, 6)
            screens = ["home", "catalog", "product_detail", "cart", "promotions", "orders"]
            for screen in random.sample(screens, min(n_screens, len(screens))):
                self.store.emit(AppSessionEvent(
                    aggregate_id=self.customer.customer_id,
                    timestamp=ts,
                    customer_id=self.customer.customer_id,
                    session_id=session_id,
                    event_subtype="screen_view",
                    screen_name=screen,
                ))
            # Possibly search
            if random.random() < 0.4:
                self.store.emit(AppSessionEvent(
                    aggregate_id=self.customer.customer_id,
                    timestamp=ts,
                    customer_id=self.customer.customer_id,
                    session_id=session_id,
                    event_subtype="product_search",
                    search_query=random.choice(["water", "chips", "juice", "cleaning", "rice"]),
                ))
            # Session end
            duration = random.randint(30, 600)
            conv_rate = random.uniform(self.order_conv_min, self.order_conv_max)
            leads_to_order = random.random() < conv_rate
            self.store.emit(AppSessionEvent(
                aggregate_id=self.customer.customer_id,
                timestamp=ts,
                customer_id=self.customer.customer_id,
                session_id=session_id,
                event_subtype="session_end",
                session_duration_seconds=duration,
                led_to_order=leads_to_order,
            ))
