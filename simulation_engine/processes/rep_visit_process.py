from __future__ import annotations

import random
from typing import TYPE_CHECKING

from schemas.macro_events import RepVisitCompleted
from schemas.customer_events import CustomerReactivated
from store.shared_state import sim_time_to_dt

if TYPE_CHECKING:
    import simpy
    from store.event_store import DuckDBEventStore
    from store.shared_state import RepRecord, SharedSimulationState


class RepVisitProcess:
    """Capacity-capped rep visit scheduling."""

    def __init__(
        self,
        env: "simpy.Environment",
        rep: "RepRecord",
        state: "SharedSimulationState",
        store: "DuckDBEventStore",
        config: dict,
    ) -> None:
        self.env = env
        self.rep = rep
        self.state = state
        self.store = store
        rv = config.get("rep_visits", {})
        self.base_rates = rv.get("base_rates", {"premium": 0.03, "regular": 0.01, "low_volume": 0.005})
        self.overdue_factor = rv.get("overdue_visit_factor", 2.0)
        self.overdue_days = rv.get("overdue_visit_days", 30)
        self.churned_visit_prob = rv.get("churned_visit_prob", 0.10)

        # Fallback outcome weights (used if tier_outcomes not configured)
        outcomes_cfg = rv.get("outcomes", {})
        self._fallback_weights = [
            outcomes_cfg.get("no_order", 0.50),
            outcomes_cfg.get("small_order", 0.30),
            outcomes_cfg.get("large_order", 0.15),
            outcomes_cfg.get("reactivation", 0.05),
        ]

        # Inactive/dormant customer visits focus on reactivation
        inc_cfg = rv.get("outcomes_inactive", {})
        self._inactive_weights = [
            inc_cfg.get("no_order", 0.40),
            inc_cfg.get("small_order", 0.10),
            inc_cfg.get("large_order", 0.00),
            inc_cfg.get("reactivation", 0.50),
        ]

        # Per-tier outcome weights for active customers
        tier_cfg = rv.get("tier_outcomes", {})
        self._tier_weights: dict[str, list[float]] = {}
        for tier, cfg in tier_cfg.items():
            self._tier_weights[tier] = [
                cfg.get("no_order", 0.50),
                cfg.get("small_order", 0.30),
                cfg.get("large_order", 0.15),
                cfg.get("reactivation", 0.05),
            ]

        self.outcome_names = ["no_order", "small_order", "large_order", "reactivation"]

    def _get_outcome_weights(self, customer_status: str) -> list[float]:
        if customer_status in ("inactive", "dormant", "churned"):
            return self._inactive_weights
        tier = self.rep.tier
        return self._tier_weights.get(tier, self._fallback_weights)

    def run(self):
        while True:
            yield self.env.timeout(1.0)
            now = self.env.now
            ts = sim_time_to_dt(now)
            capacity = self.rep.capacity_per_day
            visits_today = 0

            for cust_id in list(self.rep.assigned_customers):
                if visits_today >= capacity:
                    break
                customer = self.state.customers.get(cust_id)
                if not customer:
                    continue

                # Churned customers: low-probability reactivation attempt only
                if customer.status == "churned":
                    if random.random() > self.churned_visit_prob:
                        continue

                base_rate = self.base_rates.get(customer.segment, 0.01)
                key = f"{self.rep.rep_id}:{cust_id}"
                last_visit = self.state.rep_last_visit.get(key, -999.0)
                days_since_visit = now - last_visit if last_visit >= 0 else 9999

                visit_prob = base_rate
                if days_since_visit > self.overdue_days:
                    visit_prob *= self.overdue_factor

                if random.random() > visit_prob:
                    continue

                # Perform visit
                visits_today += 1
                weights = self._get_outcome_weights(customer.status)
                outcome = random.choices(self.outcome_names, weights=weights, k=1)[0]
                self.state.rep_last_visit[key] = now
                customer.last_visit_time = now

                days_since = int(now - last_visit) if last_visit >= 0 else 0
                self.store.emit(RepVisitCompleted(
                    aggregate_id=self.rep.rep_id,
                    timestamp=ts,
                    rep_id=self.rep.rep_id,
                    customer_id=cust_id,
                    outcome=outcome,
                    days_since_last_visit=days_since,
                ))

                # Handle reactivation outcome
                if outcome == "reactivation" and customer.status in ("inactive", "dormant", "churned"):
                    boost_days = 30
                    customer.status = "active"
                    customer.reactivation_boost_until = now + boost_days
                    self.store.emit(CustomerReactivated(
                        aggregate_id=cust_id,
                        timestamp=ts,
                        days_inactive=int(days_since),
                        channel="rep_visit",
                    ))
