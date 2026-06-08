# Claude Code Prompt — Synthetic Wholesale Commerce Simulation Engine
## Egyptian FMCG & HORECA Market · 2023 · Event-Sourced · ~4M rows

---

## CONTEXT

You are building a **production-grade, event-sourced synthetic data generator** for a B2B wholesale distributor operating in the Egyptian FMCG & HORECA market. The simulation runs from **2023-01-01 to 2023-12-31**, generating ~4 million events that materialise into ~16 Parquet tables. The dataset is designed for analytics, ML training (churn, demand forecasting, credit risk), and data pipeline testing.

The architecture is **fully specified** in the design documents provided below as context. Follow every architectural decision exactly. Do not invent alternatives.

---

## AUTHORITATIVE DESIGN SOURCES (read these before writing any file)

The following four documents are attached as project knowledge and constitute the full specification. Read them before writing any code:

| File | Purpose |
|---|---|
| `Synthetic_Wholesale_Commerce_Simulation_Engine.md` | Core domain model, behavioral models, business rules, event types, daily/monthly loop logic, output schemas, validation KPIs |
| `Synthetic_Wholesale_Commerce_Simulation_Engine.md` (Addendum v1.1, sections A1–A26) | Missing engines: customer acquisition, fraud, returns, sub-day jitter, bootstrap warm-start, app events, rep performance, affinity, elasticity, collection promises |
| `Addendum_3_Enhanced_Architecture.md` (sections B1–B12) | **SUPERSEDES** the original tech stack and loop model. Uses SimPy 4, Pydantic v2, Polars, DuckDB, Faker. All process implementations are in this file. |
| `FMCG_HORECA_Entity_Library_EGP.md` | Egyptian market parameters: EGP prices, brand weights, customer type registry, area data, seasonality overrides, Ramadan window |

**Precedence rule:** Addendum 3 (B-sections) supersedes original sections wherever marked. The entity library overrides generic parameters with Egyptian-specific values.

---

## TECHNOLOGY STACK (exact — do not substitute)

```
# requirements.txt
simpy==4.1.1
pydantic==2.7.1
polars==0.20.31
faker==25.2.0
hypothesis==6.102.6
duckdb==0.10.3
pyarrow==16.1.0
numpy==1.26.4
pyyaml==6.0.1
pytest==8.2.0
```

**Seeding (mandatory — all randomness must be reproducible):**
```python
import random, numpy as np
from faker import Faker

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker(["ar_EG", "en_US"])
Faker.seed(SEED)   # must be called on the CLASS, not the instance
```

---

## FILE STRUCTURE TO CREATE

Build exactly this layout. Do not add or remove top-level directories.

```
simulation_engine/
│
├── requirements.txt
│
├── config/
│   ├── simulation_config.yaml       # All runtime parameters (dates, counts, seeds)
│   └── seeds.py                     # Centralised SEED = 42 + seeding calls
│
├── schemas/                         # Pydantic v2 event schemas — IMMUTABLE (frozen=True)
│   ├── __init__.py                  # AnyEvent discriminated union
│   ├── base.py                      # EventBase
│   ├── customer_events.py           # CustomerCreated, CustomerChurned, CustomerReactivated, etc.
│   ├── order_events.py              # OrderCreated (with OrderLine), OrderShipped, OrderDelivered, OrderCancelled, OrderReturned, OrderRejected
│   ├── inventory_events.py          # StockReceived, StockReserved, StockoutOccurred, PurchaseOrderCreated, SupplierDelay, BackorderFulfilled
│   ├── payment_events.py            # InvoiceCreated, PaymentInitiated, PaymentCaptured, PaymentFailed, CollectionScheduled, CollectionPromiseMade, CreditWrittenOff
│   ├── promotion_events.py          # PromotionCreated, PromotionActivated, PromotionApplied, PromotionExpired
│   ├── fraud_events.py              # FraudAlertEvent
│   └── macro_events.py              # MacroStateUpdated, RepVisitCompleted, AppSessionEvent
│
├── store/
│   ├── event_store.py               # DuckDBEventStore with batch buffer (flush every 10,000 events)
│   └── shared_state.py              # SharedSimulationState, CustomerState, InventoryState, sim_time_to_dt()
│
├── processes/                       # SimPy coroutines — one file per process class
│   ├── __init__.py
│   ├── macro_process.py             # MacroProcess: advances daily, updates inflation + seasonality + active_promotions
│   ├── customer_arrival_process.py  # CustomerArrivalProcess: non-homogeneous Poisson λ(t)
│   ├── customer_order_process.py    # CustomerOrderProcess: exponential inter-arrival, credit check, fraud check, OrderFulfillmentProcess spawn
│   ├── order_fulfillment_process.py # OrderFulfillmentProcess: reservation → ship → deliver → invoice spawn → optional return
│   ├── invoice_process.py           # InvoiceProcess: Gamma delay → payment attempts → CollectionProcess spawn
│   ├── collection_process.py        # CollectionProcess: promise → fulfil or write-off
│   ├── customer_lifecycle_process.py # CustomerLifecycleProcess: daily status check → inactive/dormant/churned events
│   ├── rep_visit_process.py         # RepVisitProcess: capacity-capped visit scheduling per rep
│   ├── app_session_process.py       # AppSessionProcess: digital engagement events
│   ├── inventory_monitor_process.py # InventoryMonitorProcess: simpy.Container per SKU, EOQ reorder, PO arrival
│   ├── fraud_monitor_process.py     # FraudMonitorProcess: real-time fraud scoring
│   └── bootstrap_process.py        # BootstrapProcess: historical events at env.time=0
│
├── generators/                      # Static entity creation (uses Faker + entity library)
│   ├── customer_generator.py        # Uses CUSTOMER_TYPES from entity library (EGP credit limits)
│   ├── product_generator.py         # Uses CATEGORY_REGISTRY + BRAND_CODES from entity library
│   ├── rep_generator.py             # Rep records with Egyptian areas
│   └── bootstrap_engine.py         # Pre-simulation historical warm-start
│
├── engines/                         # Pure functions — no SimPy, no state mutation
│   ├── ordering_engine.py           # compute_order_probability(), build_order() with affinity
│   ├── inventory_engine.py          # EOQ, safety stock, reorder_point formulas
│   ├── payment_engine.py            # Gamma payment delay, risk-based success probability
│   ├── fraud_engine.py              # score_order() → fraud_score ∈ [0,1]
│   ├── promotion_engine.py          # Promotion eligibility + discount application
│   ├── affinity_engine.py           # Basket affinity (co-occurrence model)
│   └── elasticity_engine.py         # Price elasticity per demand class (A/B/C)
│
├── projections/                     # Polars lazy frames → Parquet output
│   ├── __init__.py                  # project_all() runner
│   ├── base_projector.py            # BaseProjector: read_events(), unpack_payload(), write()
│   ├── order_projector.py           # orders table + order_lines (explode from payload)
│   ├── customer_projector.py        # customers snapshot + customer_history
│   ├── inventory_projector.py       # inventory_snapshot + stockout_events
│   ├── financial_projector.py       # invoices + payments + credit_ledger
│   ├── rfm_projector.py             # Monthly RFM snapshots (Polars window functions)
│   ├── analytics_projector.py       # monthly_customer_snapshot, rep_performance_snapshot, promotion_performance
│   └── noise_injector.py            # §16 noise pass: 1% missing, 0.5% duplicate, 0.01% corruption
│
├── validators/
│   ├── business_rules.py            # check_credit_rule(), apply_payment() — return RuleResult
│   └── kpi_validator.py             # Asserts all §18.2 + §A26 KPI ranges after projection
│
├── tests/
│   ├── unit/
│   │   ├── test_business_rules.py   # Hypothesis: CR-01, PAY-01, credit invariants
│   │   ├── test_aggregates.py       # Hypothesis stateful machine: CreditLedgerMachine
│   │   └── test_engines.py          # Deterministic: ordering, inventory, payment engines
│   └── integration/
│       └── test_30day_run.py        # 30-day smoke test + all §18.1 consistency checks
│
└── simulation_runner.py             # SimPy env setup, process registration, project_all(), validate_kpis()
```

---

## BUILD ORDER (follow this sequence exactly — dependencies run top to bottom)

### Phase 1 — Foundation (no dependencies)
1. `requirements.txt`
2. `config/seeds.py` — SEED constant + seeding calls
3. `config/simulation_config.yaml` — all runtime parameters (see §SIMULATION PARAMETERS below)
4. `schemas/base.py` — EventBase with frozen=True, discriminated union field
5. All `schemas/*.py` files (domain schemas)
6. `schemas/__init__.py` — AnyEvent discriminated union

### Phase 2 — State & Storage
7. `store/shared_state.py` — SharedSimulationState, CustomerState, InventoryState, sim_time_to_dt()
8. `store/event_store.py` — DuckDBEventStore (buffer, flush, read_events, schema setup)

### Phase 3 — Pure Engines (no SimPy)
9. `engines/ordering_engine.py`
10. `engines/inventory_engine.py`
11. `engines/payment_engine.py`
12. `engines/fraud_engine.py`
13. `engines/promotion_engine.py`
14. `engines/affinity_engine.py`
15. `engines/elasticity_engine.py`
16. `validators/business_rules.py`

### Phase 4 — Generators (Faker, entity library constants)
17. `generators/customer_generator.py`
18. `generators/product_generator.py`
19. `generators/rep_generator.py`
20. `generators/bootstrap_engine.py`

### Phase 5 — SimPy Processes (build in dependency order)
21. `processes/macro_process.py` — no spawning
22. `processes/customer_lifecycle_process.py` — no spawning
23. `processes/app_session_process.py` — no spawning
24. `processes/rep_visit_process.py` — no spawning
25. `processes/inventory_monitor_process.py` — spawns `_po_arrival`
26. `processes/invoice_process.py` — spawns `CollectionProcess`
27. `processes/collection_process.py` — no spawning
28. `processes/order_fulfillment_process.py` — spawns `InvoiceProcess`, `_return_process`, `_backorder_process`
29. `processes/fraud_monitor_process.py`
30. `processes/customer_order_process.py` — spawns `OrderFulfillmentProcess`
31. `processes/customer_arrival_process.py`
32. `processes/bootstrap_process.py`

### Phase 6 — Projections
33. `projections/base_projector.py`
34. `projections/order_projector.py`
35. `projections/customer_projector.py`
36. `projections/inventory_projector.py`
37. `projections/financial_projector.py`
38. `projections/rfm_projector.py`
39. `projections/analytics_projector.py`
40. `projections/noise_injector.py`
41. `projections/__init__.py` — project_all()
42. `validators/kpi_validator.py`

### Phase 7 — Runner & Tests
43. `simulation_runner.py`
44. `tests/unit/test_business_rules.py`
45. `tests/unit/test_aggregates.py`
46. `tests/unit/test_engines.py`
47. `tests/integration/test_30day_run.py`

---

## SIMULATION PARAMETERS (write into `config/simulation_config.yaml`)

```yaml
simulation:
  seed: 42
  start_date: "2023-01-01"
  end_date:   "2023-12-31"
  days:       365
  currency:   "EGP"

scale:
  initial_customers: 2000        # warm-start; grows to ~3800 by year end
  sku_count:         500
  initial_suppliers: 50
  reps_per_area:     "3-7"       # random uniform

event_store:
  path: "output/event_store.duckdb"
  batch_size: 10000              # flush to DuckDB every N events

output:
  parquet_dir: "output/tables"

macro:
  # Egypt 2023: 30% annual wholesale FMCG inflation
  daily_inflation: 0.000724      # (1.30)^(1/365)
  egp_usd_rate: 30.6
  ramadan_start: "2023-03-22"
  ramadan_end:   "2023-04-21"

  # Egypt-specific monthly seasonality (overrides generic §8.1)
  seasonality:
    1: 0.85
    2: 0.90
    3: 1.20    # Ramadan begins
    4: 1.30    # Ramadan + Eid al-Fitr peak
    5: 1.00
    6: 1.20    # Summer heat begins
    7: 1.40    # Peak summer (40°C+)
    8: 1.45
    9: 1.30    # Back to school
    10: 1.05
    11: 0.95
    12: 1.00

customers:
  segment_weights:
    premium:    0.20
    regular:    0.50
    low_volume: 0.30
  acquisition_channel_weights:
    rep_referral: 0.60
    digital:      0.40
  digital_active_probability: 0.40
  # EGP credit limits (Base ± variability)
  credit_limits_egp:
    premium:    {base: 1500000, variability: 0.20}
    regular:    {base: 500000,  variability: 0.30}
    low_volume: {base: 120000,  variability: 0.50}

orders:
  # Daily base order probability per segment
  base_rates:
    premium:    0.12
    regular:    0.07
    low_volume: 0.02
    new_30d:    0.15
  # Log-normal basket parameters (EGP — mean_log = USD + ln(30.6))
  basket_lognormal:
    premium:    {mean_log: 10.92, sigma: 1.0}    # 7.5 + 3.42
    regular:    {mean_log:  9.92, sigma: 1.2}    # 6.5 + 3.42
    low_volume: {mean_log:  8.42, sigma: 1.5}    # 5.0 + 3.42
  recency_boosts:
    over_30d:  0.5
    over_60d:  0.1
    under_7d:  1.2

payments:
  terms_days: 30
  # Gamma payment delay: shape = 1 + risk_score * 2, scale = 5.0
  delay_gamma_scale: 5.0
  success_probability:
    low_risk:    {threshold: 0.3, prob: 0.95}
    medium_risk: {threshold: 0.7, prob: 0.70}
    high_risk:   {threshold: 1.0, prob: 0.40}
  collection_trigger_days: 30
  writeoff_days: 180

inventory:
  # Stockout resolution probabilities
  stockout_resolution:
    substitute: 0.30
    backorder:  0.20
    cancel_line: 0.50
  supplier_delay_probability: 0.05
  supplier_delay_days: "1-15"

customer_arrival:
  lambda_base: 5.0               # customers per day
  growth_rate: 0.002             # 0.2% daily growth

lifecycle:
  inactive_threshold_days:  60
  dormant_threshold_days:   150
  churned_threshold_days:   330
  reactivation_boost_days:  30
  reactivation_boost_factor: 1.5

rep_visits:
  base_rates:
    premium:    0.03
    regular:    0.01
    low_volume: 0.005
  overdue_visit_factor: 2.0      # if >30 days since last visit
  outcomes:
    no_order:     0.50
    small_order:  0.30
    large_order:  0.15
    reactivation: 0.05
  max_visits_per_day: "3-5"

fraud:
  velocity_threshold: 3          # orders in 24h
  amount_multiplier_threshold: 5 # vs. 90d average
  high_risk_score_threshold: 0.8

noise:
  missing_event_rate:     0.010
  duplicate_event_rate:   0.005
  out_of_order_rate:      0.001
  data_corruption_rate:   0.0001
  late_arrival_rate:      0.020
```

---

## KEY IMPLEMENTATION CONTRACTS

### `store/shared_state.py`
- `sim_time_to_dt(t: float) -> datetime`: Convert SimPy float (fractional days from sim start) to wall-clock datetime. Business hours window 08:00–18:00. SIM_START = datetime(2023, 1, 1).
- `CustomerState` must track: `customer_id`, `segment`, `status`, `credit_limit`, `credit_used`, `last_order_time` (SimPy float, default -999.0), `risk_score`, `digital_active`, `rep_id`, `reactivation_boost_until`.
- `InventoryState` must hold a reference to its `simpy.Container` so processes can call `container.get()` / `container.put()` directly.

### `store/event_store.py`
- Buffer events in a list; flush to DuckDB when buffer hits `batch_size` (10,000).
- DuckDB schema: `event_id VARCHAR PK`, `event_type VARCHAR`, `aggregate_id VARCHAR`, `timestamp TIMESTAMP`, `payload JSON`, `causation_id VARCHAR`, `correlation_id VARCHAR`.
- Create composite index on `(event_type, aggregate_id, timestamp)`.
- `read_events(event_type: str) -> pl.LazyFrame` — uses DuckDB `.pl()` then `.lazy()`.

### `schemas/base.py`
```python
class EventBase(BaseModel):
    model_config = ConfigDict(frozen=True, use_enum_values=True)
    event_id:       UUID     = Field(default_factory=uuid4)
    event_type:     str
    aggregate_id:   str
    timestamp:      datetime
    causation_id:   UUID | None = None
    correlation_id: UUID | None = None
```
All domain events inherit EventBase and use `Literal['EventTypeName']` for `event_type`.

### `engines/ordering_engine.py`
Implement the logistic order probability model exactly as specified in §8.1:
```python
def compute_order_probability(customer: CustomerState, state: SharedSimulationState) -> float:
    """
    P(order_today) = logistic(
        base_rate(segment)
        + recency_boost(days_since_last_order)
        + seasonality_boost(month)
        + promotion_boost(active_promotions)
        + rep_visit_boost(visited_in_last_7_days)
    )
    """
```
Convert daily probability → exponential inter-arrival in `CustomerOrderProcess._sample_interval()`.

### `engines/inventory_engine.py`
Implement EOQ and safety stock formulas from §A4:
```
reorder_point = avg_daily_demand * lead_time + 1.645 * sqrt(lead_time) * daily_demand_std
safety_stock  = service_level_z * sqrt(lead_time) * daily_demand_std
order_qty     = max(EOQ, reorder_point - (on_hand + on_order) + safety_stock)
```

### `processes/inventory_monitor_process.py`
Use `simpy.Container` — NOT a dictionary. The Container's `get()` blocks on stockout (enabling natural backorders). `put()` on PO arrival auto-unblocks waiting `get()` calls. This is the entire backorder mechanism.

### `processes/customer_order_process.py`
After `OrderCreated`, immediately spawn `OrderFulfillmentProcess`. Do NOT await it — use `self.env.process(...)` and continue the customer's own loop.

### `generators/product_generator.py`
Use `CATEGORY_REGISTRY` from the entity library. SKU naming convention:
```
{CATEGORY}-{SUBCAT}-{BRAND_CODE}-{SIZE_CODE}
e.g., BEV-CSD-COKE-330CAN24
```
Brand weights per subcategory from `BEV_BRAND_WEIGHTS`, `FOD_BRAND_WEIGHTS`, etc. in the entity library.

### `generators/customer_generator.py`
Use `CUSTOMER_TYPES` from the entity library for segment assignment and EGP credit limits. Faker locale: `["ar_EG", "en_US"]` for bilingual Egyptian B2B names.

### `projections/base_projector.py`
`unpack_payload()` uses `pl.col('payload').str.json_path_match(f'$.{field}')`. Never use pandas.

### `projections/order_projector.py`
`project_order_lines()` must explode the `lines` JSON array from `OrderCreated` payloads. Use `.str.json_decode()` → `.explode()` → `.unnest()`.

---

## BUSINESS RULES (enforce before emitting events)

| Rule ID | Check | Compensating Event |
|---|---|---|
| CR-01 | `credit_used + order_total ≤ credit_limit` | `OrderRejectedEvent(reason='credit_limit')` |
| CR-02 | `customer.status != 'churned'` | `OrderRejectedEvent(reason='churned_customer')` |
| INV-01 | `container.level ≥ line.quantity` | `StockoutOccurredEvent` + resolution |
| PROMO-01 | `promotion.active AND customer in target_segment` | Skip discount silently |
| PAY-01 | `payment_amount ≤ invoice_balance` | Apply only up to balance |
| COLL-01 | `promise_date ≥ today` | Reject promise |

---

## OUTPUT TABLES (all written to `output/tables/*.parquet`)

| Table | Projection source |
|---|---|
| `customers.parquet` | Latest CustomerCreated + lifecycle events per customer |
| `customer_history.parquet` | Daily segment/status/credit_used snapshots |
| `orders.parquet` | OrderCreated + latest status event per order |
| `order_lines.parquet` | Exploded lines from OrderCreated payloads |
| `invoices.parquet` | InvoiceCreated events |
| `payments.parquet` | PaymentCaptured + PaymentFailed events |
| `credit_ledger.parquet` | CreditUsed + CreditRepaid events with running balance |
| `inventory_snapshot.parquet` | Daily Container.level per SKU |
| `stockout_events.parquet` | StockoutOccurred events |
| `promotions.parquet` | PromotionCreated events |
| `promotion_redemptions.parquet` | PromotionApplied events |
| `rep_visits.parquet` | RepVisitCompleted events |
| `app_events.parquet` | AppSessionEvent events |
| `rfm_scores.parquet` | Monthly RFM snapshots |
| `rep_performance.parquet` | Monthly rep KPIs |
| `promotion_roi.parquet` | Monthly promotion ROI |

---

## VALIDATION GATES (kpi_validator.py must assert all of these)

### §18.1 Consistency Checks
- No `OrderCreated` without a preceding `CustomerCreated` for that customer
- Sum of `order_lines.quantity * unit_price` = `orders.total_value` (tolerance ±0.01)
- `credit_used` = sum(order totals) − sum(captured payments) − write-offs ≥ 0
- `StockReserved` totals ≤ `StockReceived` − `StockReleased` per SKU

### §18.2 KPI Ranges (EGP-adjusted)
| KPI | Expected Range |
|---|---|
| Average order value (EGP) | 5,000 – 460,000 |
| Annual churn rate | 10% – 30% |
| Days Sales Outstanding (DSO) | 30 – 60 days |
| Stockout rate (% of order lines) | 2% – 20% |
| Promotion ROI | 1.5 – 4.0 |
| Visit-to-order conversion | 30% – 60% |
| Open orders at end date (%) | ≥ 5% of orders not Delivered |
| Overdue invoices at end date (%) | ≥ 10% |

### §A26 Additional KPIs
| KPI | Expected Range |
|---|---|
| Basket affinity lift (top 3 pairs) | > 1.5 |
| App session to order conversion | 15% – 80% |
| Promise fulfilment rate | 55% – 65% |
| Rep target achievement | 60% – 110% of GMV target |
| Organic Orders Share | 20% – 70% of orders higher on friday |

---

## NOISE INJECTION (noise_injector.py — runs as post-simulation Polars pass)

After all events are written, apply the following over the event_store:
- **Missing events** (1%): Drop randomly sampled events (exclude bootstrap events)
- **Duplicate events** (0.5%): Emit exact copies with new `event_id` but same content
- **Out-of-order timestamps** (0.1%): Shift timestamp back by 1 hour (before causation event)
- **Data corruption** (0.01%): Set one payload field to null or a negative value
- **Late arrival** (2%): Backdate event timestamp by 2 days

---

## LIVE-SYSTEM REQUIREMENT

The simulation **must not resolve** open processes when `env.run(until=365)` stops. At the end date:
- Many orders will be in `Shipped` or `Picking` status (not `Delivered`)
- Many invoices will be `Open` or `Partially Paid`
- Some backorder `container.get()` calls will still be waiting
- Some customers will be mid-transition (e.g., recently hit 60 days without order)
- Some active promotions will still be running

This is automatic with SimPy — do NOT add any end-of-simulation cleanup logic that resolves these.

---

## RUNNING THE SIMULATION

```bash
cd simulation_engine
pip install -r requirements.txt
python simulation_runner.py

# Run 30-day smoke test first:
pytest tests/integration/test_30day_run.py -v

# Run full unit tests:
pytest tests/ -v
```

---

## REFERENCES & LIBRARY DOCUMENTATION

| Library | Purpose | Docs |
|---|---|---|
| **SimPy 4** | Discrete-event simulation: process coroutines, Container, timeout, env | https://simpy.readthedocs.io/en/stable/ |
| **Pydantic v2** | Frozen event schemas, discriminated unions, field validators | https://docs.pydantic.dev/latest/ |
| **DuckDB** | In-process columnar event store, native Polars integration via `.pl()` | https://duckdb.org/docs/ |
| **Polars** | Lazy projection layer; `LazyFrame`, `json_path_match`, `explode`, `unnest`, `group_by`, window functions | https://docs.pola.rs/ |
| **Faker** | Seeded entity generation; Egyptian Arabic locale `ar_EG` | https://faker.readthedocs.io/en/stable/ |
| **Hypothesis** | Property-based testing; `given`, `strategies`, `RuleBasedStateMachine` | https://hypothesis.readthedocs.io/en/latest/ |
| **NumPy** | Distributions: `lognormal`, `gamma`, `exponential`, `poisson`; seeded via `np.random.seed()` | https://numpy.org/doc/stable/reference/random/ |
| **PyArrow** | Parquet write backend (via Polars `write_parquet(use_pyarrow=True)`) | https://arrow.apache.org/docs/python/ |

---

*Start with Phase 1 (Foundation). Create each file in build order. Do not skip ahead. After each phase, run `python -c "from simulation_engine.<module> import *"` to verify imports before proceeding.*
