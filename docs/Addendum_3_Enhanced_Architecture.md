# Addendum 3: Enhanced Architecture
## Synthetic Wholesale Commerce Simulation Engine

**Version:** 3.0  
**Supersedes / extends:** Main document (v1.0) + Addendum 1 (v1.1) + Addendum 2  
**How to use:** Read alongside the original `.md`. Each section here either *supersedes* a numbered section in the original or *supplements* it. A header tag tells you which.

---

## Table of Contents

B1. [Enhanced Technology Stack](#b1-enhanced-technology-stack) — *supersedes §19.1*  
B2. [Pydantic v2 Event Schema](#b2-pydantic-v2-event-schema) — *supersedes §4*  
B3. [SimPy Process Registry](#b3-simpy-process-registry) — *supersedes §6*  
B4. [Shared Simulation State](#b4-shared-simulation-state) — *new (required by SimPy model)*  
B5. [SimPy Process Implementations](#b5-simpy-process-implementations) — *supersedes §6, §A6, §A7*  
B6. [Inventory as SimPy Container](#b6-inventory-as-simpy-container) — *supersedes §11, §A4, §A6*  
B7. [Enhanced Generator Layer (Faker)](#b7-enhanced-generator-layer-faker) — *supplements §5, §A1, §A2*  
B8. [Polars Projection Layer](#b8-polars-projection-layer) — *supersedes §17, §A9.2*  
B9. [Hypothesis Test Framework](#b9-hypothesis-test-framework) — *supersedes §19.5*  
B10. [Enhanced Code Structure](#b10-enhanced-code-structure) — *supersedes §19.2*  
B11. [Performance Impact Analysis](#b11-performance-impact-analysis) — *new*  
B12. [Section-by-Section Migration Notes](#b12-section-by-section-migration-notes) — *cross-reference*  

---

## B1. Enhanced Technology Stack
*Supersedes §19.1*

| Layer | Original spec | Enhanced | Rationale |
|-------|--------------|----------|-----------|
| Simulation loop | Hand-rolled `for day in calendar` | **SimPy 4** | Process-based discrete-event simulation; handles in-flight states, sub-day timestamps, and concurrent processes natively |
| Event schemas | `@dataclass` | **Pydantic v2** | Schema validation at emit time, frozen immutability, discriminated union dispatch, JSON serialisation built-in |
| DataFrame / projections | `pandas` | **Polars** | 5–15× faster aggregations, lazy evaluation, native DuckDB integration via `.pl()`, streaming reduces peak RAM |
| Entity realism | Bare IDs (`CUST_001`) | **Faker** (seeded) | Realistic names, companies, emails, phone numbers; no schema change required |
| Property testing | Hand-written unit tests | **Hypothesis** | Generates hundreds of edge-case inputs; shrinks failures to minimal reproduction |
| Event store | DuckDB (keep) | **DuckDB** | Already optimal — columnar, in-process, SQL-native, free |
| Output format | Parquet (keep) | **Parquet** | Already optimal |
| Distributions | `numpy.random` (keep) | `numpy.random` | Already covers all required distributions (Gamma, log-normal, Poisson) |
| Config | YAML (keep) | **YAML** | Already appropriate |

**Install manifest** (all free, open-source):

```txt
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
```

**Seeding discipline** — extend the original §19.4 rule to cover Faker:

```python
import random
import numpy as np
from faker import Faker

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
Faker.seed(SEED)   # ← must be called on the class, not the instance
```

---

## B2. Pydantic v2 Event Schema
*Supersedes §4 — Event Sourcing Architecture*

### B2.1 Base Event Model

All events inherit from `EventBase`. Immutability (`frozen=True`) enforces the append-only contract at the Python level — a frozen Pydantic model raises `ValidationError` on any attempted field mutation.

```python
# schemas/base.py
from __future__ import annotations
from datetime import datetime
from typing import Annotated, Union
from uuid import UUID, uuid4
from pydantic import BaseModel, ConfigDict, Field

class EventBase(BaseModel):
    model_config = ConfigDict(frozen=True, use_enum_values=True)

    event_id:       UUID     = Field(default_factory=uuid4)
    event_type:     str
    aggregate_id:   str
    timestamp:      datetime
    causation_id:   UUID | None = None
    correlation_id: UUID | None = None
```

### B2.2 Payload Models (selected examples)

Each event type has a dedicated payload model. Field-level validators enforce business invariants *before* the event is written to the store.

```python
# schemas/order_events.py
from typing import Literal
from pydantic import BaseModel, Field, field_validator

class OrderLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    sku_id:    str
    quantity:  int   = Field(gt=0)
    unit_price: float = Field(gt=0)

class OrderCreatedPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    order_id:     str
    customer_id:  str
    total_value:  float = Field(gt=0, description="Sum of line totals after discount")
    lines:        list[OrderLine] = Field(min_length=1)
    channel:      Literal['rep', 'app', 'direct', 'organic']
    promotion_id: str | None = None

    @field_validator('total_value')
    @classmethod
    def total_matches_lines(cls, v: float, info) -> float:
        if 'lines' in info.data:
            computed = sum(l.quantity * l.unit_price for l in info.data['lines'])
            if abs(computed - v) > 0.01:
                raise ValueError(f"total_value {v} does not match line sum {computed:.2f}")
        return v

class OrderCreatedEvent(EventBase):
    event_type: Literal['OrderCreated'] = 'OrderCreated'
    payload:    OrderCreatedPayload
```

```python
# schemas/inventory_events.py
class StockoutOccurredPayload(BaseModel):
    model_config = ConfigDict(frozen=True)
    sku_id:            str
    requested_quantity: int = Field(gt=0)
    available_quantity: int = Field(ge=0)
    resolution:        Literal['substitute', 'backorder', 'cancel_line']
    substitute_sku_id: str | None = None

class StockoutOccurredEvent(EventBase):
    event_type: Literal['StockoutOccurred'] = 'StockoutOccurred'
    payload:    StockoutOccurredPayload
```

### B2.3 Discriminated Union Dispatch

The event store writes and reads use a single `AnyEvent` type. Pydantic's discriminated union dispatches to the correct model via `event_type` — no `if/elif` chain needed.

```python
# schemas/__init__.py
from typing import Annotated, Union
from pydantic import Field

AnyEvent = Annotated[
    Union[
        OrderCreatedEvent,
        OrderShippedEvent,
        OrderDeliveredEvent,
        OrderCancelledEvent,
        OrderReturnedEvent,
        CustomerCreatedEvent,
        CustomerChurnedEvent,
        CustomerReactivatedEvent,
        StockReceivedEvent,
        StockoutOccurredEvent,
        PurchaseOrderCreatedEvent,
        PaymentCapturedEvent,
        PaymentFailedEvent,
        CollectionPromiseMadeEvent,
        PromotionAppliedEvent,
        FraudAlertEvent,
        # ... all event types
    ],
    Field(discriminator='event_type')
]
```

### B2.4 EventStore Integration

```python
# store/event_store.py
import duckdb
import polars as pl
from schemas import AnyEvent, EventBase

class DuckDBEventStore:
    def __init__(self, path: str = ':memory:'):
        self.conn = duckdb.connect(path)
        self._buffer: list[dict] = []
        self._batch_size = 10_000
        self._setup_schema()

    def _setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS event_store (
                event_id       VARCHAR PRIMARY KEY,
                event_type     VARCHAR NOT NULL,
                aggregate_id   VARCHAR NOT NULL,
                timestamp      TIMESTAMP NOT NULL,
                payload        JSON NOT NULL,
                causation_id   VARCHAR,
                correlation_id VARCHAR
            )
        """)
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_event_type_agg
            ON event_store (event_type, aggregate_id, timestamp)
        """)

    def emit(self, event: EventBase) -> None:
        """Validate (Pydantic), buffer, and batch-flush to DuckDB."""
        self._buffer.append({
            'event_id':       str(event.event_id),
            'event_type':     event.event_type,
            'aggregate_id':   event.aggregate_id,
            'timestamp':      event.timestamp,
            'payload':        event.model_dump_json(include={'payload'}),
            'causation_id':   str(event.causation_id) if event.causation_id else None,
            'correlation_id': str(event.correlation_id) if event.correlation_id else None,
        })
        if len(self._buffer) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        df = pl.DataFrame(self._buffer)
        self.conn.register('buf', df)
        self.conn.execute("INSERT INTO event_store SELECT * FROM buf")
        self._buffer.clear()

    def read_events(self, event_type: str) -> pl.LazyFrame:
        return self.conn.execute(
            "SELECT * FROM event_store WHERE event_type = ?", [event_type]
        ).pl().lazy()
```

---

## B3. SimPy Process Registry
*Supersedes §6 — Daily Simulation Pipeline*

### B3.1 Core Mental Model Shift

The original spec advances a simulation clock **day by day** and processes all entities in each tick. SimPy advances to the **next scheduled event** on the timeline. Each business entity runs as its own coroutine and `yield env.timeout(n)` to sleep until its next action.

Consequence: the "live system" requirement (§Final Architecture) is automatic. When `env.run(until=SIM_DAYS)` returns, every process that hasn't completed is simply interrupted mid-execution. No special end-of-simulation cleanup is needed — open orders, pending promises, and unresolved collections exist naturally.

### B3.2 Process Inventory

| Process class | Instances | Replaces |
|---|---|---|
| `MacroProcess` | 1 | Daily macro update (step 1 of original loop) |
| `CustomerArrivalProcess` | 1 | §A1 new customer arrival |
| `CustomerOrderProcess` | 1 per customer | Steps 4–6 of original loop |
| `CustomerLifecycleProcess` | 1 per customer | Step 12 + §7 monthly churn eval |
| `RepVisitProcess` | 1 per rep | Step 5 of original loop |
| `AppSessionProcess` | 1 per digital customer | Step 4 of original loop |
| `OrderFulfillmentProcess` | spawned per order | Steps 7–8 of original loop |
| `InvoiceProcess` | spawned per order delivery | Step 9–10 of original loop |
| `CollectionProcess` | spawned per overdue invoice | Step 11 of original loop |
| `InventoryMonitorProcess` | 1 per SKU | Step 13 of original loop + §A4 |
| `FraudMonitorProcess` | 1 | §A5 fraud engine |
| `BootstrapProcess` | 1 (pre-simulation) | §A10 warm start |

### B3.3 Simulation Runner

```python
# simulation_runner.py
import simpy
from store.event_store import DuckDBEventStore
from store.shared_state import SharedSimulationState
from generators import CustomerGenerator, ProductGenerator, RepGenerator
from processes import (
    MacroProcess, CustomerArrivalProcess,
    CustomerOrderProcess, CustomerLifecycleProcess,
    RepVisitProcess, InventoryMonitorProcess,
    BootstrapProcess, AppSessionProcess,
)
from projections import project_all
from validators.kpi_validator import validate_kpis

def run(config: SimulationConfig) -> None:
    env   = simpy.Environment()
    store = DuckDBEventStore(config.event_store_path)
    state = SharedSimulationState.from_config(config)

    # --- 1. Generate static reference data ---
    CustomerGenerator(fake, state).generate(config.initial_customers)
    ProductGenerator(fake, state).generate(config.sku_count)
    RepGenerator(fake, state).generate()

    # --- 2. Bootstrap: historical events before sim start ---
    env.process(BootstrapProcess(env, state, store, config).run())
    env.run(until=0)          # run bootstrap only (time=0 bootstrap events)

    # --- 3. Register ongoing processes ---
    env.process(MacroProcess(env, state, store, config).run())
    env.process(CustomerArrivalProcess(env, state, store, config).run())

    for customer in state.customers.values():
        env.process(CustomerOrderProcess(env, customer, state, store).run())
        env.process(CustomerLifecycleProcess(env, customer, state, store).run())
        if customer.digital_active:
            env.process(AppSessionProcess(env, customer, state, store).run())

    for rep in state.reps.values():
        env.process(RepVisitProcess(env, rep, state, store).run())

    for sku in state.skus.values():
        env.process(InventoryMonitorProcess(env, sku, state, store).run())

    # --- 4. Run simulation ---
    env.run(until=config.simulation_days)

    # --- 5. Flush remaining events ---
    store.flush()

    # --- 6. Build projections ---
    project_all(store, config.output_path)

    # --- 7. Validate KPIs ---
    validate_kpis(store)
```

### B3.4 Time Representation

SimPy time is a float counting **fractional days** from simulation start. Convert to `datetime` when emitting events:

```python
# store/shared_state.py
from datetime import datetime, timedelta

SIM_START = datetime(2023, 1, 1)

def sim_time_to_dt(t: float) -> datetime:
    """Convert SimPy float time (days) to a wall-clock datetime."""
    full_days = int(t)
    fraction  = t - full_days
    # Business hours: 08:00–18:00 → 8h window starting at 08:00
    seconds_in_window = int(fraction * 10 * 3600)   # 10h window
    return (
        SIM_START
        + timedelta(days=full_days)
        + timedelta(hours=8, seconds=seconds_in_window)
    )
```

This replaces §A7 (Sub-Day Timestamp Jitter) entirely. SimPy timestamps are naturally ordered by causality — a spawned process always starts at `env.now` ≥ its parent's emit time.

---

## B4. Shared Simulation State
*New — required by the SimPy concurrency model*

SimPy processes share Python memory. A single `SharedSimulationState` object holds all mutable state. Processes read and write it directly (SimPy is single-threaded; no locking needed).

```python
# store/shared_state.py
from dataclasses import dataclass, field
from typing import Any
import simpy

@dataclass
class InventoryState:
    on_hand:     float          # current available units (Container.level)
    on_order:    float = 0.0    # units in transit (outstanding POs)
    reorder_point: float = 0.0
    container:   Any = None     # simpy.Container reference, set at startup

@dataclass
class CustomerState:
    customer_id:    str
    segment:        str
    status:         str = 'active'   # active / inactive / dormant / churned
    credit_limit:   float = 0.0
    credit_used:    float = 0.0
    last_order_time: float = -999.0  # SimPy time of last order
    risk_score:     float = 0.1
    digital_active: bool = False
    rep_id:         str | None = None
    reactivation_boost_until: float = -1.0

@dataclass
class SharedSimulationState:
    # Macro
    inflation_factor:    float = 1.0
    seasonality_factor:  float = 1.0
    active_promotions:   list  = field(default_factory=list)

    # Entities
    customers: dict[str, CustomerState]  = field(default_factory=dict)
    skus:      dict[str, Any]            = field(default_factory=dict)
    reps:      dict[str, Any]            = field(default_factory=dict)

    # Inventory containers (simpy.Container per SKU, populated at startup)
    inventory: dict[str, InventoryState] = field(default_factory=dict)

    # Pending PO tracking (prevents duplicate reorders)
    pending_pos: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def from_config(cls, config) -> 'SharedSimulationState':
        return cls()
```

---

## B5. SimPy Process Implementations
*Supersedes §6 steps, §A3, §A5, §A6, §A7*

### B5.1 MacroProcess

Advances daily. Updates inflation, seasonality, and active promotions in `SharedSimulationState`.

```python
# processes/macro_process.py
import simpy
import numpy as np
from store.shared_state import SharedSimulationState, sim_time_to_dt
from schemas.macro_events import MacroStateUpdatedEvent, MacroStatePayload

SEASONALITY = {1:0.8,2:0.9,3:1.0,4:0.9,5:1.0,6:0.9,
               7:1.0,8:1.0,9:1.1,10:1.1,11:1.3,12:1.5}
DAILY_INFLATION = (1.03) ** (1/365)  # 3% annual

class MacroProcess:
    def __init__(self, env, state, store, config):
        self.env    = env
        self.state  = state
        self.store  = store
        self.config = config

    def run(self):
        while True:
            yield self.env.timeout(1)   # advance one day
            day = int(self.env.now)
            month = (sim_time_to_dt(self.env.now)).month

            self.state.inflation_factor   *= DAILY_INFLATION
            self.state.seasonality_factor  = SEASONALITY[month]
            self._update_active_promotions(day)

    def _update_active_promotions(self, day: int) -> None:
        dt = sim_time_to_dt(day)
        self.state.active_promotions = [
            p for p in self.config.promotions
            if p.start_date <= dt.date() <= p.end_date
        ]
```

### B5.2 CustomerOrderProcess

One coroutine per customer. Samples an inter-order interval, sleeps, then places an order. The ordering engine handles basket building, fraud checks, credit validation, and promotion eligibility.

```python
# processes/customer_order_process.py
import simpy
import numpy as np
from engines.ordering_engine import build_order, check_credit
from engines.fraud_engine import score_order
from schemas.order_events import OrderCreatedEvent, OrderCreatedPayload, OrderRejectedEvent

class CustomerOrderProcess:
    def __init__(self, env, customer, state, store):
        self.env      = env
        self.customer = customer
        self.state    = state
        self.store    = store

    def run(self):
        while self.customer.status not in ('churned', 'suspended'):
            # 1. Sample time to next order from behavioral model
            interval = self._sample_interval()
            yield self.env.timeout(interval)

            if self.customer.status in ('churned', 'suspended'):
                break

            now = self.env.now
            corr_id = generate_uuid()

            # 2. Build order (engines/ordering_engine.py handles basket + affinity)
            order = build_order(self.customer, self.state, now)

            # 3. Credit check (rule CR-01)
            if not check_credit(self.customer, order.total_value):
                self.store.emit(OrderRejectedEvent(
                    aggregate_id=order.order_id,
                    timestamp=sim_time_to_dt(now),
                    payload={'reason': 'credit_limit', 'order_id': order.order_id},
                    correlation_id=corr_id,
                ))
                continue

            # 4. Fraud check
            fraud_score = score_order(order, self.customer, self.state)
            if fraud_score > 0.8:
                self.store.emit(FraudAlertEvent(..., causation_id=order.event_id))
                continue

            # 5. Emit OrderCreated
            evt = OrderCreatedEvent(
                aggregate_id=order.order_id,
                timestamp=sim_time_to_dt(now),
                payload=OrderCreatedPayload(
                    order_id=order.order_id,
                    customer_id=self.customer.customer_id,
                    total_value=order.total_value,
                    lines=order.lines,
                    channel=order.channel,
                    promotion_id=order.promotion_id,
                ),
                correlation_id=corr_id,
            )
            self.store.emit(evt)
            self.customer.credit_used    += order.total_value
            self.customer.last_order_time = now

            # 6. Spawn fulfillment process
            self.env.process(
                OrderFulfillmentProcess(self.env, order, evt, self.state, self.store).run()
            )

    def _sample_interval(self) -> float:
        """Sample days until next order using the logistic probability model.
        Returns a float (days), including sub-day fraction."""
        p_day = compute_order_probability(self.customer, self.state)
        # Convert daily probability to expected interval (geometric distribution)
        # E[interval] = 1/p; use exponential approximation for continuous time
        rate = -np.log(1 - p_day) if p_day < 1 else 1.0
        return float(np.random.exponential(1.0 / rate))
```

### B5.3 OrderFulfillmentProcess

Spawned by `CustomerOrderProcess` for each accepted order. Handles the full order lifecycle: reservation → ship → deliver → invoice. Stockout resolution lives here.

```python
# processes/order_fulfillment_process.py
import simpy
from schemas.order_events import (
    OrderShippedEvent, OrderDeliveredEvent,
    OrderCancelledEvent, OrderReturnedEvent,
)
from schemas.inventory_events import StockReservedEvent, StockoutOccurredEvent

class OrderFulfillmentProcess:
    def __init__(self, env, order, order_event, state, store):
        self.env         = env
        self.order       = order
        self.order_event = order_event
        self.state       = state
        self.store       = store

    def run(self):
        corr = self.order_event.correlation_id
        cause = self.order_event.event_id

        # --- Cancellation window (before confirmation) ---
        if np.random.random() < 0.005:
            yield self.env.timeout(np.random.uniform(0, 0.5))
            self.store.emit(OrderCancelledEvent(
                aggregate_id=self.order.order_id,
                timestamp=sim_time_to_dt(self.env.now),
                payload={'order_id': self.order.order_id, 'reason': 'customer_request'},
                causation_id=cause, correlation_id=corr,
            ))
            self._release_inventory()
            return

        # --- Inventory reservation (per line) ---
        fulfilled_lines = []
        for line in self.order.lines:
            inv = self.state.inventory[line.sku_id]
            container = inv.container

            # Attempt immediate get (no waiting — stockout if insufficient)
            if container.level >= line.quantity:
                yield container.get(line.quantity)
                self.store.emit(StockReservedEvent(
                    aggregate_id=line.sku_id,
                    timestamp=sim_time_to_dt(self.env.now),
                    payload={'sku_id': line.sku_id, 'quantity': line.quantity,
                             'order_id': self.order.order_id},
                    causation_id=cause, correlation_id=corr,
                ))
                fulfilled_lines.append(line)
            else:
                # Stockout resolution
                resolution = np.random.choice(
                    ['substitute', 'backorder', 'cancel_line'],
                    p=[0.3, 0.2, 0.5]
                )
                self.store.emit(StockoutOccurredEvent(
                    aggregate_id=line.sku_id,
                    timestamp=sim_time_to_dt(self.env.now),
                    payload={
                        'sku_id': line.sku_id,
                        'requested_quantity': line.quantity,
                        'available_quantity': int(container.level),
                        'resolution': resolution,
                    },
                    causation_id=cause, correlation_id=corr,
                ))
                if resolution == 'backorder':
                    # Spawn backorder process — naturally in-flight at end date
                    self.env.process(
                        self._backorder_process(line, corr, cause)
                    )
                # substitute and cancel_line: handle inline (omitted for brevity)

        if not fulfilled_lines:
            return   # nothing to ship

        # --- Ship (1–2 day processing time) ---
        yield self.env.timeout(np.random.uniform(1, 2))
        self.store.emit(OrderShippedEvent(
            aggregate_id=self.order.order_id,
            timestamp=sim_time_to_dt(self.env.now),
            payload={'order_id': self.order.order_id},
            causation_id=cause, correlation_id=corr,
        ))

        # --- Deliver (1–3 day transit) ---
        yield self.env.timeout(np.random.uniform(1, 3))
        delivery_event = OrderDeliveredEvent(
            aggregate_id=self.order.order_id,
            timestamp=sim_time_to_dt(self.env.now),
            payload={'order_id': self.order.order_id},
            causation_id=cause, correlation_id=corr,
        )
        self.store.emit(delivery_event)

        # --- Spawn invoice process ---
        self.env.process(
            InvoiceProcess(self.env, self.order, delivery_event, self.state, self.store).run()
        )

        # --- Schedule possible return ---
        return_prob = compute_return_probability(self.order, self.state)
        if np.random.random() < return_prob:
            self.env.process(self._return_process(delivery_event, corr))

    def _backorder_process(self, line, corr, cause):
        """Waits for stock replenishment, then fulfils the line."""
        container = self.state.inventory[line.sku_id].container
        yield container.get(line.quantity)   # blocks until stock arrives
        self.store.emit(BackorderFulfilledEvent(
            aggregate_id=self.order.order_id,
            timestamp=sim_time_to_dt(self.env.now),
            payload={'sku_id': line.sku_id, 'quantity': line.quantity},
            causation_id=cause, correlation_id=corr,
        ))

    def _return_process(self, delivery_event, corr):
        yield self.env.timeout(np.random.uniform(3, 14))
        self.store.emit(OrderReturnedEvent(
            aggregate_id=self.order.order_id,
            timestamp=sim_time_to_dt(self.env.now),
            payload={'order_id': self.order.order_id, 'reason': 'customer_return'},
            causation_id=delivery_event.event_id, correlation_id=corr,
        ))

    def _release_inventory(self):
        for line in self.order.lines:
            container = self.state.inventory[line.sku_id].container
            self.env.process(
                self._put_back(container, line.quantity)
            )

    def _put_back(self, container, qty):
        yield container.put(qty)
```

### B5.4 InvoiceProcess

Spawned on `OrderDelivered`. Handles the full payment lifecycle including retry logic and escalation to `CollectionProcess`.

```python
# processes/invoice_process.py
import simpy
import numpy as np
from schemas.payment_events import (
    InvoiceCreatedEvent, PaymentInitiatedEvent,
    PaymentCapturedEvent, PaymentFailedEvent,
)

PAYMENT_TERMS_DAYS = 30

class InvoiceProcess:
    def __init__(self, env, order, delivery_event, state, store):
        self.env            = env
        self.order          = order
        self.delivery_event = delivery_event
        self.state          = state
        self.store          = store

    def run(self):
        customer = self.state.customers[self.order.customer_id]
        corr  = self.delivery_event.correlation_id
        cause = self.delivery_event.event_id
        now   = self.env.now

        invoice_id = generate_uuid()

        self.store.emit(InvoiceCreatedEvent(
            aggregate_id=invoice_id,
            timestamp=sim_time_to_dt(now),
            payload={
                'invoice_id': invoice_id,
                'order_id': self.order.order_id,
                'amount_due': self.order.total_value,
                'due_date': sim_time_to_dt(now + PAYMENT_TERMS_DAYS).date().isoformat(),
            },
            causation_id=cause, correlation_id=corr,
        ))

        # Sleep until due date + risk-adjusted delay (Gamma model from §8.3)
        delay = self._sample_payment_delay(customer.risk_score)
        yield self.env.timeout(PAYMENT_TERMS_DAYS + delay)

        # Attempt payment (risk-based success probability from §12.2)
        success_prob = self._payment_success_prob(customer.risk_score)
        attempts = 0

        while attempts < 3:
            attempts += 1
            self.store.emit(PaymentInitiatedEvent(
                aggregate_id=invoice_id,
                timestamp=sim_time_to_dt(self.env.now),
                payload={'invoice_id': invoice_id, 'attempt': attempts},
                causation_id=cause, correlation_id=corr,
            ))

            if np.random.random() < success_prob:
                self.store.emit(PaymentCapturedEvent(
                    aggregate_id=invoice_id,
                    timestamp=sim_time_to_dt(self.env.now),
                    payload={'invoice_id': invoice_id, 'amount': self.order.total_value},
                    causation_id=cause, correlation_id=corr,
                ))
                customer.credit_used = max(0, customer.credit_used - self.order.total_value)
                return
            else:
                self.store.emit(PaymentFailedEvent(
                    aggregate_id=invoice_id,
                    timestamp=sim_time_to_dt(self.env.now),
                    payload={'invoice_id': invoice_id, 'attempt': attempts},
                    causation_id=cause, correlation_id=corr,
                ))
                yield self.env.timeout(7)   # retry after 7 days

        # 3 failures → collections
        self.env.process(
            CollectionProcess(self.env, invoice_id, self.order, customer, self.state, self.store).run()
        )

    def _sample_payment_delay(self, risk_score: float) -> float:
        shape = 1 + risk_score * 2
        return max(0.0, float(np.random.gamma(shape=shape, scale=5.0)))

    def _payment_success_prob(self, risk_score: float) -> float:
        if risk_score < 0.3:   return 0.95
        if risk_score < 0.7:   return 0.70
        return 0.40

```

### B5.5 CustomerLifecycleProcess

One per customer. Monitors `last_order_time` against lifecycle transition thresholds (§15.2). Runs as a continuous monitoring loop rather than monthly batch evaluation.

```python
# processes/customer_lifecycle_process.py

class CustomerLifecycleProcess:
    def __init__(self, env, customer, state, store):
        self.env      = env
        self.customer = customer
        self.state    = state
        self.store    = store

    def run(self):
        while True:
            yield self.env.timeout(1)   # check daily
            days_since = self.env.now - self.customer.last_order_time

            prev_status = self.customer.status
            new_status  = self._evaluate_status(days_since)

            if new_status != prev_status and new_status is not None:
                self.customer.status = new_status
                self.store.emit(self._lifecycle_event(new_status))

    def _evaluate_status(self, days_since: float) -> str | None:
        s = self.customer.status
        if s == 'active'   and days_since > 60:  return 'inactive'
        if s == 'inactive' and days_since > 150: return 'dormant'
        if s == 'dormant'  and days_since > 330: return 'churned'
        return None

    def _lifecycle_event(self, new_status: str):
        event_type_map = {
            'inactive': CustomerBecameInactiveEvent,
            'dormant':  CustomerBecameDormantEvent,
            'churned':  CustomerChurnedEvent,
        }
        return event_type_map[new_status](
            aggregate_id=self.customer.customer_id,
            timestamp=sim_time_to_dt(self.env.now),
            payload={'customer_id': self.customer.customer_id, 'new_status': new_status},
        )
```

---

## B6. Inventory as SimPy Container
*Supersedes §11, §A4 replenishment logic, §A6 fulfilment*

`simpy.Container` is the natural model for a SKU's stock level. `get(n)` blocks if fewer than `n` units are available — this is how backorders work without any special handling. `put(n)` adds stock and unblocks any waiting `get()` calls — this is how arriving POs automatically unblock backorders.

```python
# processes/inventory_monitor_process.py
import simpy
import numpy as np
from schemas.inventory_events import PurchaseOrderCreatedEvent, StockReceivedEvent

class InventoryMonitorProcess:
    """
    One instance per SKU. Initialises a simpy.Container for the SKU's
    stock level and runs a daily reorder check loop.
    """
    def __init__(self, env, sku, state, store):
        self.env   = env
        self.sku   = sku
        self.state = state
        self.store = store

    def run(self):
        # Initialise SimPy Container
        inv_state = self.state.inventory[self.sku.sku_id]
        container = simpy.Container(
            self.env,
            capacity=self.sku.max_stock,
            init=self.sku.initial_stock,
        )
        inv_state.container = container

        while True:
            yield self.env.timeout(1)   # daily check

            # Skip if a PO is already in transit
            if self.state.pending_pos.get(self.sku.sku_id):
                continue

            on_hand   = container.level
            on_order  = inv_state.on_order
            reorder_point = self._compute_reorder_point()

            if on_hand + on_order <= reorder_point:
                order_qty = self._compute_order_qty(on_hand, on_order)
                self.state.pending_pos[self.sku.sku_id] = True
                inv_state.on_order += order_qty

                po_event = PurchaseOrderCreatedEvent(
                    aggregate_id=self.sku.sku_id,
                    timestamp=sim_time_to_dt(self.env.now),
                    payload={
                        'sku_id': self.sku.sku_id,
                        'quantity': order_qty,
                        'supplier_id': self.sku.primary_supplier_id,
                        'expected_arrival': sim_time_to_dt(
                            self.env.now + self.sku.lead_time_days
                        ).isoformat(),
                    },
                )
                self.store.emit(po_event)

                # Spawn arrival process
                self.env.process(
                    self._po_arrival(order_qty, self.sku.lead_time_days,
                                     container, inv_state, po_event.event_id)
                )

    def _po_arrival(self, qty, lead_time, container, inv_state, cause_id):
        # Optional supplier delay (5% probability, §11.3)
        delay = 0
        if np.random.random() < 0.05:
            delay = np.random.randint(1, 16)
            self.store.emit(SupplierDelayEvent(
                aggregate_id=self.sku.sku_id,
                timestamp=sim_time_to_dt(self.env.now),
                payload={'sku_id': self.sku.sku_id, 'delay_days': delay},
                causation_id=cause_id,
            ))

        yield self.env.timeout(lead_time + delay)

        # put() unblocks any waiting get() calls from backorder processes
        yield container.put(qty)
        inv_state.on_order -= qty
        self.state.pending_pos[self.sku.sku_id] = False

        self.store.emit(StockReceivedEvent(
            aggregate_id=self.sku.sku_id,
            timestamp=sim_time_to_dt(self.env.now),
            payload={'sku_id': self.sku.sku_id, 'quantity': qty},
            causation_id=cause_id,
        ))

    def _compute_reorder_point(self) -> float:
        # §A4.1 formula
        avg_demand  = self.sku.avg_daily_demand
        lead_time   = self.sku.lead_time_days
        demand_std  = self.sku.daily_demand_std
        safety      = 1.645 * np.sqrt(lead_time) * demand_std
        return avg_demand * lead_time + safety

    def _compute_order_qty(self, on_hand: float, on_order: float) -> float:
        eoq       = self.sku.eoq or 200
        shortfall = self._compute_reorder_point() - (on_hand + on_order)
        return max(eoq, shortfall + self.sku.safety_stock)
```

**Why this is better than the original §A6:**  
The original design requires a daily loop that explicitly checks order confirmation dates and calls `StockShipped`. Here, the `container.get()` in `OrderFulfillmentProcess` atomically reserves stock, and the `container.put()` in `_po_arrival` atomically receives it. Any backorder `get()` that was blocking resumes automatically when `put()` fires — zero explicit backorder management code required.

---

## B7. Enhanced Generator Layer (Faker)
*Supplements §5, §A1 customer arrival, §A2 product catalog*

Faker is seeded once at startup (§B1) and threaded through all static generators. The schema does not change — Faker only populates the `name`, `company_name`, `email`, `phone`, `city` fields that the original spec left as bare IDs.

### B7.1 Customer Generator

```python
# generators/customer_generator.py
from faker import Faker
from store.shared_state import CustomerState

fake = Faker()   # seeded at module level via Faker.seed(42)

SEGMENT_WEIGHTS   = {'premium': 0.20, 'regular': 0.50, 'low_volume': 0.30}
CHANNEL_WEIGHTS   = {'rep_referral': 0.60, 'digital': 0.40}

def generate_initial_customers(n: int, state) -> None:
    for _ in range(n):
        customer_id = f"CUST_{fake.uuid4()[:8].upper()}"
        segment     = weighted_choice(SEGMENT_WEIGHTS)
        credit_limit = _credit_limit(segment) * np.random.uniform(0.8, 1.2)

        state.customers[customer_id] = CustomerState(
            customer_id=customer_id,
            segment=segment,
            credit_limit=round(credit_limit, 2),
            digital_active=np.random.random() < 0.4,
        )

        store.emit(CustomerCreatedEvent(
            aggregate_id=customer_id,
            timestamp=SIM_START - timedelta(days=np.random.randint(1, 365)),
            payload=CustomerCreatedPayload(
                customer_id=customer_id,
                company_name=fake.company(),
                contact_name=fake.name(),
                email=fake.company_email(),
                phone=fake.phone_number(),
                city=fake.city(),
                segment=segment,
                credit_limit=credit_limit,
                acquisition_channel=weighted_choice(CHANNEL_WEIGHTS),
            ),
        ))
```

### B7.2 Product Generator

```python
# generators/product_generator.py
CATEGORIES = ['Beverage', 'Snack', 'Cleaning', 'Office', 'Electronics', 'Apparel']

def generate_products(n: int, suppliers: list, state) -> None:
    for i in range(n):
        sku_id    = f"SKU-{fake.bothify('??####').upper()}"
        category  = np.random.choice(CATEGORIES)
        base_price = float(np.clip(np.random.lognormal(mean=np.log(50), sigma=1.5), 5, 5000))

        store.emit(ProductCreatedEvent(
            aggregate_id=sku_id,
            payload=ProductCreatedPayload(
                sku_id=sku_id,
                name=f"{fake.word().capitalize()} {category} {fake.color_name()}",
                category=category,
                base_price=round(base_price, 2),
                unit_cost=round(base_price * np.random.uniform(0.5, 0.8), 2),
                supplier_id=np.random.choice(suppliers).supplier_id,
                reorder_point=int(np.random.poisson(50)),
                lead_time_days=np.random.choice([3,5,7,10,14], p=[0.2,0.3,0.25,0.15,0.1]),
            ),
        ))
```

### B7.3 Supplier + Rep Generator (abbreviated)

```python
def generate_suppliers(n: int = 50) -> list:
    return [
        SupplierRecord(
            supplier_id=f"SUP-{i:04d}",
            name=fake.company(),
            country=fake.country(),
            avg_lead_time=np.random.choice([7, 14, 21, 30]),
            daily_capacity=np.random.randint(1000, 10000),
        )
        for i in range(n)
    ]

def generate_reps(areas: list) -> list:
    return [
        RepRecord(
            rep_id=f"REP-{fake.uuid4()[:6].upper()}",
            name=fake.name(),
            area_id=area.area_id,
            tier=np.random.choice(['A','B','C','D'], p=[0.15, 0.35, 0.35, 0.15]),
            max_visits_per_day=np.random.randint(3, 6),
        )
        for area in areas
        for _ in range(np.random.randint(3, 8))
    ]
```

---

## B8. Polars Projection Layer
*Supersedes §17, §A9.2 incremental projections*

### B8.1 Base Projector Pattern

DuckDB has a native `.pl()` method that returns a Polars DataFrame without copying through an intermediate format. Projectors read from DuckDB and use Polars lazy evaluation for transformations.

```python
# projections/base_projector.py
import duckdb
import polars as pl
from pathlib import Path

class BaseProjector:
    def __init__(self, conn: duckdb.DuckDBPyConnection, output_dir: Path):
        self.conn       = conn
        self.output_dir = output_dir

    def read_events(self, event_type: str) -> pl.LazyFrame:
        """Read all events of a given type from DuckDB into a Polars LazyFrame."""
        return (
            self.conn
            .execute(
                "SELECT * FROM event_store WHERE event_type = ?",
                [event_type]
            )
            .pl()           # DuckDB → Polars DataFrame (no pandas copy)
            .lazy()         # Switch to lazy evaluation
        )

    def read_events_multi(self, event_types: list[str]) -> pl.LazyFrame:
        placeholders = ','.join(['?' * len(event_types)])
        return (
            self.conn
            .execute(
                f"SELECT * FROM event_store WHERE event_type IN ({placeholders})",
                event_types
            )
            .pl().lazy()
        )

    def unpack_payload(self, lf: pl.LazyFrame, fields: list[str]) -> pl.LazyFrame:
        """Extract top-level fields from the JSON payload column."""
        return lf.with_columns([
            pl.col('payload').str.json_path_match(f'$.{f}').alias(f)
            for f in fields
        ])

    def write(self, lf: pl.LazyFrame, table_name: str) -> None:
        path = self.output_dir / f"{table_name}.parquet"
        lf.collect().write_parquet(path, use_pyarrow=True)
        print(f"  wrote {table_name}.parquet ({path.stat().st_size // 1024} KB)")
```

### B8.2 Order Projector (example)

```python
# projections/order_projector.py
class OrderProjector(BaseProjector):

    def project_orders(self) -> None:
        """Build the orders table from OrderCreated + status events."""

        created = self.read_events('OrderCreated')
        created = self.unpack_payload(
            created,
            ['order_id', 'customer_id', 'total_value', 'channel', 'promotion_id']
        ).rename({'timestamp': 'order_date'})

        # Latest status per order (last event wins)
        statuses = (
            self.read_events_multi([
                'OrderCreated', 'OrderShipped', 'OrderDelivered',
                'OrderCancelled', 'OrderReturned'
            ])
            .sort('timestamp')
            .group_by('aggregate_id')
            .agg(pl.col('event_type').last().alias('status'))
            .rename({'aggregate_id': 'order_id'})
        )

        orders = (
            created
            .join(statuses, on='order_id', how='left')
            .with_columns([
                pl.col('order_date').cast(pl.Date).dt.truncate('1mo').alias('order_month'),
            ])
        )
        self.write(orders, 'orders')

    def project_order_lines(self) -> None:
        """Explode order lines from OrderCreated payloads."""
        lines = (
            self.read_events('OrderCreated')
            .with_columns(
                pl.col('payload').str.json_path_match('$.lines')
                  .str.json_decode()
                  .alias('lines_raw')
            )
            .with_columns(pl.col('aggregate_id').alias('order_id'))
            .explode('lines_raw')
            .unnest('lines_raw')
            .with_columns([
                pl.col('timestamp').cast(pl.Date).alias('order_date'),
            ])
        )
        self.write(lines, 'order_lines')
```

### B8.3 RFM Projector (shows Polars window functions)

```python
# projections/rfm_projector.py
class RFMProjector(BaseProjector):

    def project_rfm_scores(self, as_of_days: list[int]) -> None:
        """
        Compute RFM snapshot at each month-end.
        Uses Polars window functions — no pandas groupby needed.
        """
        orders = (
            self.read_events('OrderCreated')
            .unpack_payload(['order_id', 'customer_id', 'total_value'])
            .with_columns(pl.col('timestamp').alias('order_date'))
        )

        frames = []
        for day in as_of_days:
            cutoff = SIM_START + timedelta(days=day)
            frame = (
                orders
                .filter(pl.col('order_date') <= cutoff)
                .group_by('customer_id')
                .agg([
                    (cutoff - pl.col('order_date').max())
                      .dt.total_days()
                      .alias('recency_days'),
                    pl.col('order_id').n_unique().alias('frequency_90d'),
                    pl.col('total_value').cast(pl.Float64).sum().alias('monetary_90d'),
                ])
                .with_columns(pl.lit(cutoff).alias('snapshot_date'))
            )
            frames.append(frame)

        rfm = pl.concat(frames).lazy()
        self.write(rfm, 'rfm_scores')
```

### B8.4 Projection Runner

```python
# projections/__init__.py
def project_all(store: DuckDBEventStore, output_path: Path) -> None:
    conn = store.conn
    out  = Path(output_path)
    out.mkdir(exist_ok=True)

    projectors = [
        OrderProjector(conn, out),
        CustomerProjector(conn, out),
        InventoryProjector(conn, out),
        FinancialProjector(conn, out),
        RFMProjector(conn, out),
        AnalyticsProjector(conn, out),   # §A12 ML tables
        NoiseInjector(conn, out),         # §16 noise pass
    ]

    for p in projectors:
        p.run_all()

    print(f"All projections written to {out}")
```

---

## B9. Hypothesis Test Framework
*Supersedes §19.5*

Hypothesis generates and shrinks inputs automatically. Use it for the business rule engine (§10) and aggregate invariants. Use standard pytest for engine unit tests.

### B9.1 Business Rule Tests

```python
# tests/unit/test_business_rules.py
import pytest
from hypothesis import given, assume, settings
from hypothesis import strategies as st
from validators.business_rules import check_credit_rule, handle_create_order
from store.shared_state import CustomerState

@given(
    credit_limit = st.floats(min_value=1_000, max_value=100_000),
    credit_used  = st.floats(min_value=0, max_value=100_000),
    order_total  = st.floats(min_value=1, max_value=50_000),
)
def test_cr01_credit_limit(credit_limit, credit_used, order_total):
    """Rule CR-01: credit_used + order_total must not exceed credit_limit."""
    assume(credit_used <= credit_limit)   # valid starting state
    customer = CustomerState(
        customer_id='test', segment='regular',
        credit_limit=credit_limit, credit_used=credit_used,
    )
    would_exceed = credit_used + order_total > credit_limit
    result       = check_credit_rule(customer, order_total)
    assert result.approved == (not would_exceed)


@given(
    payment  = st.floats(min_value=0, max_value=200_000),
    balance  = st.floats(min_value=0, max_value=100_000),
)
def test_pay01_payment_does_not_exceed_balance(payment, balance):
    """Rule PAY-01: payment_amount must not exceed invoice_balance."""
    result = apply_payment(payment, balance)
    assert result.applied <= balance
    assert result.applied >= 0


@given(
    risk_score   = st.floats(min_value=0, max_value=1),
    num_orders   = st.integers(min_value=0, max_value=500),
    num_payments = st.integers(min_value=0, max_value=500),
)
@settings(max_examples=500)
def test_credit_used_never_negative(risk_score, num_orders, num_payments):
    """Invariant: credit_used must never go below zero regardless of payment sequence."""
    customer = CustomerState(
        customer_id='inv-test', segment='regular',
        credit_limit=50_000, credit_used=0, risk_score=risk_score,
    )
    for _ in range(num_orders):
        amount = np.random.uniform(100, 5000)
        if customer.credit_used + amount <= customer.credit_limit:
            customer.credit_used += amount
    for _ in range(num_payments):
        amount = np.random.uniform(100, 5000)
        customer.credit_used = max(0, customer.credit_used - amount)

    assert customer.credit_used >= 0
    assert customer.credit_used <= customer.credit_limit
```

### B9.2 Aggregate Invariant Tests (Stateful)

```python
from hypothesis.stateful import RuleBasedStateMachine, rule, initialize, invariant

class CreditLedgerMachine(RuleBasedStateMachine):
    """
    Stateful machine: applies random order + payment sequences and asserts
    that the credit ledger invariants always hold.
    """

    @initialize()
    def setup(self):
        self.customer = CustomerState(
            customer_id='sm-test', segment='regular',
            credit_limit=50_000, credit_used=0,
        )
        self.ledger_balance = 0.0

    @rule(amount=st.floats(min_value=100, max_value=10_000))
    def place_order(self, amount):
        if self.customer.credit_used + amount <= self.customer.credit_limit:
            self.customer.credit_used  += amount
            self.ledger_balance        += amount

    @rule(amount=st.floats(min_value=1, max_value=20_000))
    def make_payment(self, amount):
        actual = min(amount, self.customer.credit_used)
        self.customer.credit_used  = max(0, self.customer.credit_used  - actual)
        self.ledger_balance        = max(0, self.ledger_balance        - actual)

    @invariant()
    def credit_used_non_negative(self):
        assert self.customer.credit_used >= 0

    @invariant()
    def credit_used_within_limit(self):
        assert self.customer.credit_used <= self.customer.credit_limit + 0.01

    @invariant()
    def ledger_matches_credit_used(self):
        assert abs(self.ledger_balance - self.customer.credit_used) < 0.01

CreditLedgerTest = CreditLedgerMachine.TestCase
```

### B9.3 Distribution Sanity Tests

```python
@given(st.integers(min_value=1, max_value=10_000))
def test_lognormal_basket_always_positive(n_samples):
    """Log-normal basket values must always be positive."""
    samples = np.random.lognormal(mean=6.5, sigma=1.2, size=n_samples)
    assert (samples > 0).all()

@given(st.floats(min_value=0.0, max_value=1.0))
def test_gamma_payment_delay_non_negative(risk_score):
    """Payment delay drawn from Gamma must be ≥ 0."""
    shape = 1 + risk_score * 2
    delay = max(0.0, np.random.gamma(shape=shape, scale=5.0))
    assert delay >= 0
```

---

## B10. Enhanced Code Structure
*Supersedes §19.2*

```
simulation_engine/
│
├── config/
│   ├── simulation_config.yaml        # §A13 config (unchanged)
│   └── seeds.py                      # centralised seed management
│
├── schemas/                          # NEW: Pydantic v2 event schemas
│   ├── __init__.py                   # AnyEvent discriminated union
│   ├── base.py                       # EventBase
│   ├── customer_events.py
│   ├── order_events.py
│   ├── inventory_events.py
│   ├── payment_events.py
│   ├── promotion_events.py
│   └── macro_events.py
│
├── store/
│   ├── event_store.py                # DuckDB-backed store (§B2.4)
│   └── shared_state.py               # SharedSimulationState (§B4)
│
├── processes/                        # NEW: SimPy coroutines (replaces daily loop)
│   ├── __init__.py
│   ├── macro_process.py              # §B5.1
│   ├── customer_order_process.py     # §B5.2
│   ├── order_fulfillment_process.py  # §B5.3
│   ├── invoice_process.py            # §B5.4
│   ├── collection_process.py         # §A22 promise flow
│   ├── customer_lifecycle_process.py # §B5.5
│   ├── customer_arrival_process.py   # §A1 non-homogeneous Poisson
│   ├── rep_visit_process.py          # §14
│   ├── app_session_process.py        # §A17
│   ├── inventory_monitor_process.py  # §B6
│   └── fraud_monitor_process.py      # §A5
│
├── generators/                       # Static data (+ Faker)
│   ├── customer_generator.py         # §B7.1
│   ├── product_generator.py          # §B7.2
│   ├── rep_generator.py              # §B7.3
│   └── bootstrap_engine.py           # §A10
│
├── engines/                          # Pure business-logic functions
│   ├── ordering_engine.py            # P(order), basket build, affinity
│   ├── inventory_engine.py           # EOQ, safety stock, reorder formula
│   ├── payment_engine.py             # Gamma delay, credit logic
│   ├── fraud_engine.py               # §A5 fraud scoring
│   ├── promotion_engine.py           # §A19 scope + eligibility
│   ├── affinity_engine.py            # §A15 basket affinity
│   └── elasticity_engine.py          # §A24 price elasticity
│
├── projections/                      # NEW: Polars projection layer
│   ├── __init__.py                   # project_all() runner (§B8.4)
│   ├── base_projector.py             # §B8.1
│   ├── order_projector.py            # §B8.2
│   ├── customer_projector.py
│   ├── inventory_projector.py
│   ├── financial_projector.py
│   ├── rfm_projector.py              # §B8.3
│   ├── analytics_projector.py        # §A12 ML tables
│   └── noise_injector.py             # §16 noise pass
│
├── validators/
│   ├── business_rules.py             # Rule engine functions
│   └── kpi_validator.py              # §18 KPI range checks
│
├── tests/
│   ├── unit/
│   │   ├── test_business_rules.py    # §B9.1 Hypothesis tests
│   │   ├── test_aggregates.py        # §B9.2 stateful machines
│   │   └── test_engines.py           # deterministic unit tests
│   └── integration/
│       └── test_30day_run.py         # 30-day smoke test + consistency checks
│
└── simulation_runner.py              # §B3.3 SimPy env setup + process registration
```

---

## B11. Performance Impact Analysis
*New*

The table below shows estimated runtime improvement vs. the original spec's implementation, on a 365-day run with 8,000 initial customers and 500 SKUs.

| Phase | Original spec estimate | Enhanced estimate | Driver |
|---|---|---|---|
| Daily simulation loop | 40–180 s | 20–60 s | SimPy avoids re-evaluating customers with low order probability; clock jumps to next event |
| Inventory monitoring | 30–60 s | 5–15 s | SimPy Container + daily check replaces per-order dict scan |
| Projection build | 5–20 min | 1–5 min | Polars lazy eval + native DuckDB `.pl()` vs pandas |
| Peak RAM | 3–6 GB | 1.5–3 GB | Polars streaming; no intermediate pandas DataFrames |
| Total end-to-end | 15–35 min | 7–15 min | Combined effect |

**SimPy time-advance advantage:** In the original daily loop, the loop body runs even on days when a given customer statistically has a near-zero order probability. SimPy's `env.timeout(interval)` skips those days entirely for that customer. Across 10,000 customers with a mix of segments, roughly 80% of customer-ticks in the original loop produce no event — SimPy eliminates that idle work.

**Polars projection advantage:** The bottleneck in the original pandas projections is the `groupby` on the full 2.5M-row event store DataFrame, which requires loading the entire table into RAM. Polars lazy frames push the filter (`WHERE event_type = ...`) down to DuckDB before pulling rows into memory, so only the relevant subset is ever materialised in Python.

---

## B12. Section-by-Section Migration Notes
*Cross-reference guide*

| Original section | Status in enhanced design | Action |
|---|---|---|
| §4 — Event Sourcing Architecture | Superseded by §B2 | Replace `@dataclass` with Pydantic models; keep DuckDB schema identical |
| §6 — Daily Simulation Pipeline | Superseded by §B3–B5 | Replace `for day in calendar` with SimPy process registration |
| §7 — Monthly Simulation Pipeline | Absorbed into process layer | `CustomerLifecycleProcess` monitors continuously; RFM snapshotted in `RFMProjector` |
| §8.3 — Payment Delay Model | Kept; moved to `InvoiceProcess._sample_payment_delay()` | No formula change |
| §11 — Inventory & Supply Chain | Superseded by §B6 | Replace manual `on_hand` dict with `simpy.Container` per SKU |
| §14 — Rep Visits | Kept; implemented as `RepVisitProcess` | Logic unchanged; outcomes driven by rep tier (§A21) |
| §16 — Noise & Anomaly Injection | Kept; implemented as `NoiseInjector` projector | Runs as a post-simulation Polars pass over the event store |
| §17 — Output Tables & Schemas | Superseded by §B8 | Replace pandas groupby projectors with Polars lazy projectors |
| §19.1 — Technology Stack | Superseded by §B1 | See requirements.txt |
| §19.2 — Code Structure | Superseded by §B10 | New `processes/` and `projections/` directories; `schemas/` replaces `dataclasses` |
| §19.4 — Reproducibility | Extended in §B1 | Add `Faker.seed(42)` call |
| §19.5 — Testing | Superseded by §B9 | Add Hypothesis; keep pytest structure |
| §A4 — Replenishment Logic | Superseded by §B6 | EOQ formula unchanged; execution moved to `InventoryMonitorProcess` |
| §A6 — Inventory Reconciliation | Superseded by §B6 | `simpy.Container.get()` / `put()` replaces explicit shipped/reserved tracking |
| §A7 — Sub-Day Jitter | Superseded by §B3.4 | SimPy fractional-day time provides this automatically; §A7 approach not needed |
| §A9.2 — Incremental Projections | Superseded by §B8 | Polars lazy frames are naturally incremental per event type |
| §A10 — Bootstrap Engine | Kept; implemented as `BootstrapProcess` | Runs at `env.time = 0` before main simulation |
| §A14 — Integration Roadmap | Superseded by §B10 | Follow `processes/` build order instead |
| §A17 — App Events | Kept; implemented as `AppSessionProcess` | Probability model unchanged |

---

*End of Addendum 3*

All other sections of the original document (§1 System Overview, §3 Domain Model, §8 Behavioural Models, §9 Causality, §10 Business Rule Engine, §12 Financial Flows, §13 Promotion Engine, §15 Customer Lifecycle, §18 Validation, §20 Glossary, and Addendum sections A8, A12, A13, A15, A16, A18–A24) are **unchanged**. The enhanced architecture is a drop-in replacement for the execution model (SimPy), data layer (Polars), and schema layer (Pydantic v2) only — all business logic, probability parameters, and domain rules carry forward verbatim.
