from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import simpy

SIM_START = datetime(2023, 1, 1)


def sim_time_to_dt(t: float) -> datetime:
    """Convert SimPy float (fractional days from sim start) to wall-clock datetime.

    Business hours window 08:00–18:00 (10 h).
    """
    full_days = int(t)
    fraction = t - full_days
    seconds_in_window = int(fraction * 10 * 3600)
    return SIM_START + timedelta(days=full_days, hours=8, seconds=seconds_in_window)


@dataclass
class CustomerState:
    customer_id: str
    segment: str
    status: str = "new"           # new / active / inactive / dormant / churned
    credit_limit: float = 0.0
    credit_used: float = 0.0
    last_order_time: float = -999.0   # SimPy float; -999 means never
    risk_score: float = 0.3
    digital_active: bool = False
    rep_id: str | None = None
    reactivation_boost_until: float = -1.0  # SimPy time; -1 means no boost
    customer_type: str = ""
    area_id: str = ""
    payment_method: str = "cash"
    name: str = ""
    phone: str = ""
    last_visit_time: float = -999.0  # SimPy float of last rep visit


@dataclass
class InventoryState:
    sku_id: str
    container: "simpy.Container"      # holds actual stock level
    avg_daily_demand: float = 1.0
    demand_std: float = 0.5
    lead_time: int = 5                # days
    eoq: int = 100
    reorder_point: float = 0.0
    safety_stock: float = 0.0
    category: str = ""
    subcategory: str = ""
    brand_code: str = ""
    demand_class: str = "B"           # A / B / C
    unit_price: float = 100.0


@dataclass
class RepRecord:
    rep_id: str
    name: str
    area_id: str
    tier: str = "B"                   # A / B / C / D
    capacity_per_day: int = 4
    assigned_customers: list[str] = field(default_factory=list)
    gmv_target_monthly: float = 500_000.0


@dataclass
class SharedSimulationState:
    inflation_factor: float = 1.0
    seasonality_factor: float = 1.0
    active_promotions: list[dict] = field(default_factory=list)
    pending_promotions: list[dict] = field(default_factory=list)  # activated by MacroProcess at start_day
    customers: dict[str, CustomerState] = field(default_factory=dict)
    skus: dict[str, InventoryState] = field(default_factory=dict)
    reps: dict[str, RepRecord] = field(default_factory=dict)
    pending_pos: dict[str, bool] = field(default_factory=dict)
    # Track recent orders per customer for fraud velocity checks
    recent_order_times: dict[str, list[float]] = field(default_factory=dict)
    # Track 90-day average order value per customer
    order_value_history: dict[str, list[float]] = field(default_factory=dict)
    # Track last visit time per rep per customer
    rep_last_visit: dict[str, float] = field(default_factory=dict)  # key: f"{rep_id}:{customer_id}"
    # Global day counter for macro process
    current_day: int = 0
