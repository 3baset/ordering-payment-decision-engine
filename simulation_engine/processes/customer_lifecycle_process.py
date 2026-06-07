from __future__ import annotations

from typing import TYPE_CHECKING

from schemas.customer_events import CustomerBecameDormant, CustomerBecameInactive, CustomerChurned
from store.shared_state import sim_time_to_dt

if TYPE_CHECKING:
    import simpy
    from store.event_store import DuckDBEventStore
    from store.shared_state import CustomerState, SharedSimulationState


class CustomerLifecycleProcess:
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
        lc = config.get("lifecycle", {})
        self.inactive_threshold = lc.get("inactive_threshold_days", 60)
        self.dormant_threshold = lc.get("dormant_threshold_days", 150)
        self.churned_threshold = lc.get("churned_threshold_days", 330)

    def run(self):
        # Check every day
        while True:
            yield self.env.timeout(1.0)
            c = self.customer
            if c.status == "churned":
                break

            now = self.env.now
            last = c.last_order_time
            days_since = now - last if last >= 0 else 9999

            ts = sim_time_to_dt(now)

            if c.status in ("active", "new") and days_since >= self.inactive_threshold:
                c.status = "inactive"
                self.store.emit(CustomerBecameInactive(
                    aggregate_id=c.customer_id,
                    timestamp=ts,
                    days_without_order=int(days_since),
                ))
            elif c.status == "inactive" and days_since >= self.dormant_threshold:
                c.status = "dormant"
                self.store.emit(CustomerBecameDormant(
                    aggregate_id=c.customer_id,
                    timestamp=ts,
                    days_without_order=int(days_since),
                ))
            elif c.status == "dormant" and days_since >= self.churned_threshold:
                c.status = "churned"
                self.store.emit(CustomerChurned(
                    aggregate_id=c.customer_id,
                    timestamp=ts,
                    days_without_order=int(days_since),
                ))
                break

            # Clear reactivation boost if expired
            if 0 < c.reactivation_boost_until < now:
                c.reactivation_boost_until = -1.0
