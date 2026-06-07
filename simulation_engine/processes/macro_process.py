from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from schemas.macro_events import MacroStateUpdated
from store.shared_state import SIM_START

if TYPE_CHECKING:
    import simpy
    from store.event_store import DuckDBEventStore
    from store.shared_state import SharedSimulationState

# EGP devaluation shocks: (sim_day, fractional_price_jump)
# Day 10 = Jan 11 2023 (+25%), Day 300 = Oct 28 2023 (+20%)
INFLATION_SHOCKS: list[tuple[int, float]] = [
    (10, 0.25),
    (300, 0.20),
]
DAILY_INFLATION_BASE = 0.000200  # ~7.5% annual baseline drift between shocks

SEASONALITY: dict[int, float] = {
    1: 0.85, 2: 0.90, 3: 1.20, 4: 1.30,
    5: 1.00, 6: 1.20, 7: 1.40, 8: 1.45,
    9: 1.30, 10: 1.05, 11: 0.95, 12: 1.00,
}

# Dynamic price_discount promotions
_SHOCK_CLEARANCE_WINDOW = 30   # days after shock to run clearance promo
_SHOCK_CLEARANCE_PCT = 10.0    # 10% discount (percentage points)
_SEASONAL_PUSH_PCT = 6.5       # 6.5% discount during high-season months
_SEASONAL_PUSH_MONTHS = {3, 4, 7, 8, 9}


class MacroProcess:
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
        self.config = config

    def _get_inflation_delta(self, day: int) -> float:
        for shock_day, shock_size in INFLATION_SHOCKS:
            if day == shock_day:
                return shock_size
        return DAILY_INFLATION_BASE

    def _update_dynamic_promotions(self, month: int, day: int) -> None:
        """Add or remove market-event-driven price_discount promotions."""
        active_ids = {p["id"] for p in self.state.active_promotions}

        # Shock clearance promos
        for shock_day, _ in INFLATION_SHOCKS:
            promo_id = f"SHOCK-CLEARANCE-{shock_day}"
            in_window = shock_day <= day < shock_day + _SHOCK_CLEARANCE_WINDOW
            if in_window and promo_id not in active_ids:
                self.state.active_promotions.append({
                    "id": promo_id,
                    "name": f"Shock Clearance D{shock_day}",
                    "promotion_type": "price_discount",
                    "value": _SHOCK_CLEARANCE_PCT,
                    "target_segments": [],   # all segments eligible
                    "start_day": shock_day,
                    "end_day": 9999,         # managed here, not by expiry filter
                    "active": True,
                    "trigger": "shock_clearance",
                })
            elif not in_window and promo_id in active_ids:
                self.state.active_promotions = [
                    p for p in self.state.active_promotions if p["id"] != promo_id
                ]

        # Seasonal push promo
        in_season = month in _SEASONAL_PUSH_MONTHS
        promo_id = "SEASONAL-PUSH"
        if in_season and promo_id not in active_ids:
            self.state.active_promotions.append({
                "id": promo_id,
                "name": "Seasonal Volume Push",
                "promotion_type": "price_discount",
                "value": _SEASONAL_PUSH_PCT,
                "target_segments": [],
                "start_day": day,
                "end_day": 9999,
                "active": True,
                "trigger": "seasonal_push",
            })
        elif not in_season and promo_id in active_ids:
            self.state.active_promotions = [
                p for p in self.state.active_promotions if p["id"] != promo_id
            ]

    def run(self):
        while True:
            yield self.env.timeout(1.0)
            day = int(self.env.now)

            # Advance inflation with shock-based step function
            self.state.inflation_factor *= (1.0 + self._get_inflation_delta(day))

            # Update seasonality
            current_date = SIM_START + timedelta(days=day)
            month = current_date.month
            self.state.seasonality_factor = SEASONALITY.get(month, 1.0)

            # Activate planned promotions whose start_day has arrived
            if self.state.pending_promotions:
                ready = [p for p in self.state.pending_promotions if p.get("start_day", 0) <= day]
                if ready:
                    self.state.active_promotions.extend(ready)
                    self.state.pending_promotions = [
                        p for p in self.state.pending_promotions if p not in ready
                    ]

            # Update dynamic price_discount promotions
            self._update_dynamic_promotions(month, day)

            # Expire planned promotions (dynamic promos have end_day=9999 so skip)
            now = self.env.now
            self.state.active_promotions = [
                p for p in self.state.active_promotions
                if p.get("start_day", 0) <= now <= p.get("end_day", 9999)
            ]

            self.state.current_day = day

            # Emit macro state event
            from store.shared_state import sim_time_to_dt
            ts = sim_time_to_dt(self.env.now)
            evt = MacroStateUpdated(
                aggregate_id="macro",
                timestamp=ts,
                day_number=day,
                inflation_factor=self.state.inflation_factor,
                seasonality_factor=self.state.seasonality_factor,
                active_promotion_count=len(self.state.active_promotions),
            )
            self.store.emit(evt)
