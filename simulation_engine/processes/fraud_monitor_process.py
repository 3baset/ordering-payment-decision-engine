from __future__ import annotations

from typing import TYPE_CHECKING

from schemas.fraud_events import FraudAlertEvent
from store.shared_state import sim_time_to_dt

if TYPE_CHECKING:
    import simpy
    from store.event_store import DuckDBEventStore
    from store.shared_state import SharedSimulationState


class FraudMonitorProcess:
    """Scans recent orders in the state buffer for fraud patterns."""

    def __init__(
        self,
        env: "simpy.Environment",
        state: "SharedSimulationState",
        store: "DuckDBEventStore",
        config: dict,
    ) -> None:
        self.env = env
        self.state = state
        self.store = store
        fraud_cfg = config.get("fraud", {})
        self.velocity_threshold = fraud_cfg.get("velocity_threshold", 3)
        self.amount_multiplier = fraud_cfg.get("amount_multiplier_threshold", 5)
        self.high_risk_threshold = fraud_cfg.get("high_risk_score_threshold", 0.8)

    def run(self):
        """Check for fraud every 0.25 days (6-hour intervals)."""
        while True:
            yield self.env.timeout(0.25)
            now = self.env.now
            ts = sim_time_to_dt(now)

            for cust_id, times in list(self.state.recent_order_times.items()):
                # Trim to last 24 hours
                recent_24h = [t for t in times if now - t <= 1.0]
                self.state.recent_order_times[cust_id] = recent_24h

                customer = self.state.customers.get(cust_id)
                if not customer:
                    continue

                # Compute average 90d value
                history = self.state.order_value_history.get(cust_id, [])
                avg_90d = sum(history[-90:]) / max(1, len(history[-90:]))

                from engines.fraud_engine import score_order
                score = score_order(
                    customer,
                    avg_90d * 1.0,  # placeholder: last order value
                    len(recent_24h),
                    avg_90d,
                    self.velocity_threshold,
                    self.amount_multiplier,
                )

                if score >= self.high_risk_threshold:
                    action = "rejected" if score >= 0.9 else "flagged"
                    fraud_type = "velocity" if len(recent_24h) >= self.velocity_threshold else "amount_spike"
                    self.store.emit(FraudAlertEvent(
                        aggregate_id=cust_id,
                        timestamp=ts,
                        customer_id=cust_id,
                        fraud_type=fraud_type,
                        fraud_score=round(score, 4),
                        action_taken=action,
                    ))
