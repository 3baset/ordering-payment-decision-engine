# Comprehensive Design Document  
## Synthetic Wholesale Commerce Simulation Engine

**Version:** 1.0  
**Target Audience:** AI Agents (Claude) and Implementation Teams  
**Goal:** Build an event‑sourcing simulation engine that generates a realistic wholesale commerce dataset (~4M rows) with full causality, explainability, and replayability.

---

## Table of Contents

1. [System Overview](#1-system-overview)  
2. [Core Design Principles](#2-core-design-principles)  
3. [Domain Model & ERD](#3-domain-model--erd)  
4. [Event Sourcing Architecture](#4-event-sourcing-architecture)  
5. [Generation DAG (Dependency Order)](#5-generation-dag-dependency-order)  
6. [Daily Simulation Pipeline](#6-daily-simulation-pipeline)  
7. [Monthly Simulation Pipeline](#7-monthly-simulation-pipeline)  
8. [Behavioral Models & Probabilities](#8-behavioral-models--probabilities)  
9. [Causality & Event Chains](#9-causality--event-chains)  
10. [Business Rule Engine](#10-business-rule-engine)  
11. [Inventory & Supply Chain Dynamics](#11-inventory--supply-chain-dynamics)  
12. [Financial Flows (Credit, Payments, Collections)](#12-financial-flows-credit-payments-collections)  
13. [Promotion & Discount Engine](#13-promotion--discount-engine)  
14. [Sales & Field Operations (Rep Visits)](#14-sales--field-operations-rep-visits)  
15. [Customer Lifecycle Management](#15-customer-lifecycle-management)  
16. [Noise & Anomaly Injection](#16-noise--anomaly-injection)  
17. [Output Tables & Schemas](#17-output-tables--schemas)  
18. [Validation & KPIs](#18-validation--kpis)  
19. [Implementation Guidelines](#19-implementation-guidelines)  
20. [Glossary](#20-glossary)

---

## 1. System Overview

The **Synthetic Wholesale Commerce Simulation Engine** generates a complete, realistic dataset of business operations for a B2B wholesale distributor. The output is used for analytics, machine learning (demand forecasting, churn prediction, credit risk), and testing of data pipelines.

**Key characteristics:**

- **Event‑sourced:** every change is recorded as an immutable event.
- **Causal:** each fact has a traceable cause (e.g., stockout → lost sales → churn).
- **Temporally consistent:** all timestamps align, seasonality and inflation evolve.
- **Replayable:** given a random seed, the exact same dataset can be regenerated.
- **Scalable:** design supports millions of rows (customers, orders, events).

**Output format:** DuckDB/PostgreSQL partitioned by time.

---

## 2. Core Design Principles

| Principle | Description |
|-----------|-------------|
| **Event‑first** | No direct table generation. All state changes are events in an append‑only log. |
| **Deterministic randomness** | All probabilistic decisions use a seeded random generator for reproducibility. |
| **Single source of truth** | The event store is the only source; tables are materialised projections. |
| **Simulation clock** | A discrete time loop that advances day by day, updating macro conditions. |
| **Aggregate roots** | Each business entity (Customer, Order, Inventory, etc.) is an aggregate that handles its own events. |
| **Rule enforcement before emission** | Business rules are checked before an event is appended. |
| **Noise layer** | After deterministic logic, optional noise (delays, missing events) is injected. |

---

## 3. Domain Model & ERD

The system is composed of the following domains. Entities are stored **only as event streams** – the ERD describes the *projected* relational schema.

### 3.1 Customer Domain

```
Customers (projected)
├── customer_id (PK)
├── segment (text)
├── status (active/inactive/dormant/churned)
├── credit_limit (decimal)
├── credit_used (decimal)
├── last_order_date (date)
├── assigned_rep_id (FK)
├── acquisition_date (date)
└── risk_score (float)
```

**Supporting event types:**  
`CustomerCreated`, `CustomerSegmentChanged`, `CustomerReactivated`, `CustomerChurned`, `CustomerAssignedToRep`, `CreditLimitUpdated`, `CreditUsed`, `CreditRepaid`

### 3.2 Sales Organisation

```
Areas
├── area_id (PK)
└── name

SalesRepresentatives
├── rep_id (PK)
├── name
└── area_id (FK)

RepVisits (fact)
├── visit_id (PK)
├── rep_id (FK)
├── customer_id (FK)
├── visit_date (date)
└── outcome (text)
```

### 3.3 Product & Inventory Domain

```
Products
├── sku_id (PK)
├── category
├── base_price
└── supplier_id (FK)

InventoryMovements (event‑sourced)
├── movement_id
├── sku_id
├── date
├── type (receipt / sale / return / adjustment)
├── quantity
└── order_id (nullable)

StockoutEvents
├── event_id
├── sku_id
├── date
├── customer_id
└── lost_quantity
```

### 3.4 Ordering Domain

```
Orders (projected)
├── order_id (PK)
├── customer_id (FK)
├── rep_id (FK) (it's okay if null to simulate organic orders)
├── order_date (date)
├── status (draft / confirmed / shipped / delivered / cancelled)
├── total_value (decimal)
└── promotion_id (nullable)

OrderLines
├── order_line_id (PK)
├── order_id (FK)
├── sku_id (FK)
├── quantity
└── unit_price
```

### 3.5 Financial Domain

```
Invoices
├── invoice_id (PK)
├── order_id (FK)
├── invoice_date (date)
├── due_date (date)
├── amount_due (decimal)
└── paid_amount (decimal)

Payments
├── payment_id (PK)
├── invoice_id (FK)
├── payment_date (date)
├── amount (decimal)
└── status (authorised / captured / failed / refunded)

CreditLedger (projected from Credit events)
├── customer_id
├── transaction_date
├── credit_change (decimal)
└── balance_after
```

### 3.6 Promotion Domain

```
PromotionMaster
├── promotion_id (PK)
├── name
├── type (percent_discount / fixed_off / free_goods)
├── value (decimal)
├── start_date
├── end_date
└── target_segment (nullable)

PromotionRedemption
├── redemption_id (PK)
├── promotion_id (FK)
├── order_id (FK)
└── discount_amount
```

### 3.7 Event Store (Physical)

The **only** physical table (or Kafka topic) required:

```sql
CREATE TABLE event_store (
    event_id UUID PRIMARY KEY,
    event_type VARCHAR(64),
    aggregate_id VARCHAR(64),   -- e.g., customer_123, order_456
    timestamp TIMESTAMP,
    payload JSONB,
    metadata JSONB,
    causation_id UUID,           -- which event caused this one
    correlation_id UUID          -- group related events (e.g., whole order flow)
);
```

All other tables are **materialised views** derived from the event store.

---

## 4. Event Sourcing Architecture

### 4.1 Event Types Registry

Every possible event is registered with its schema. Partial list:

| Domain        | Event Types |
|---------------|--------------|
| Customer       | CustomerCreated, CustomerSegmentChanged, CustomerReactivated, CustomerChurned, CustomerAssignedToRep, CreditLimitUpdated |
| Order          | OrderCreated, OrderConfirmed, OrderShipped, OrderDelivered, OrderCancelled, OrderReturned |
| Inventory      | StockReceived, StockReserved, StockReleased, StockoutOccurred, StockAdjusted |
| Payment        | PaymentInitiated, PaymentAuthorised, PaymentCaptured, PaymentFailed, PaymentRefunded |
| Credit         | CreditUsed, CreditRepaid, CreditOverdue, CreditWrittenOff |
| Promotion      | PromotionCreated, PromotionActivated, PromotionApplied, PromotionExpired |
| Sales          | RepVisitCompleted, CustomerReactivatedByVisit |
| Lifecycle      | CustomerBecameInactive, CustomerBecameDormant, CustomerChurned |

### 4.2 Aggregate Design

Each aggregate root maintains its state by replaying its events. Example:

```python
class CustomerAggregate:
    def __init__(self, customer_id):
        self.id = customer_id
        self.segment = None
        self.status = "active"
        self.credit_limit = 0
        self.credit_used = 0
        self.last_order_date = None

    def apply_event(self, event):
        if event.type == "CustomerCreated":
            self.segment = event.payload["segment"]
            self.credit_limit = event.payload["credit_limit"]
        elif event.type == "OrderCreated":
            self.credit_used += event.payload["total_value"]
            self.last_order_date = event.timestamp
        # ... more handlers
```

### 4.3 Command Handling

Commands (e.g., `CreateOrder`) validate rules, then emit events.

```python
def handle_create_order(customer_id, items, current_date):
    customer = repository.load_customer(customer_id)
    if customer.credit_used + order_total > customer.credit_limit:
        raise RuleViolation("Credit limit exceeded")
    # emit OrderCreated event
```

### 4.4 Projections (Materialisation)

Projections rebuild tables by scanning the event store. They can run incrementally (every day) or at the end.

Example: orders table projection

```sql
-- Pseudo‑SQL using event stream
SELECT
    event.payload->>'order_id' AS order_id,
    event.payload->>'customer_id' AS customer_id,
    event.timestamp AS order_date,
    event.payload->>'total_value' AS total_value
FROM event_store
WHERE event_type = 'OrderCreated';
```

All final tables are defined as such queries.

---

## 5. Generation DAG (Dependency Order)

The **generation order** respects dependencies: you cannot generate orders before customers exist, etc.

```
1. Static / Reference Data
   ├── Areas
   ├── SalesRepresentatives
   ├── Suppliers
   └── ProductCatalog

2. Initial Customers (snapshot)
   └── CustomerCreated events

3. ProductPriceHistory (initial prices)

4. PromotionMaster (fixed promotions)

5. Simulation Loop (daily)
   ├── Macro updates (inflation, seasonality)
   ├── RepVisits (triggered)
   ├── Orders (generated based on customer state)
   ├── Inventory updates
   ├── Payments & Credit
   ├── Collections & Promises
   ├── Lifecycle transitions (inactive → dormant → churned)
   └── AppEvents (digital activity)

6. Monthly Aggregations
   ├── RFM scores
   ├── Rep performance
   ├── Promotion ROI
   └── Churn evaluation

7. Final Projections (materialised tables)
```

---

## 6. Daily Simulation Pipeline

Pseudocode for the daily loop (called for each date in simulation range):

```python
for day in calendar:
    # 1. Macro conditions
    update_inflation_factor(day)
    update_seasonality_multiplier(day)
    update_active_promotions(day)

    # 2. Supply chain: receive purchase orders (if any)
    for po in purchase_orders_due_today:
        emit(StockReceived, sku=po.sku, quantity=po.qty)

    # 3. Update inventory on‑hand (after receipts and prior day's shipments)

    # 4. Schedule & process rep visits (probabilistic)
    for customer in active_customers:
        if should_visit(customer, day):
            outcome = generate_visit_outcome(customer)
            emit(RepVisitCompleted, customer_id, outcome)

    # 5. Update customer state (risk scores, credit checks)

    # 6. Evaluate promotions: which are active today?

    # 7. Generate orders
    for customer in customers_with_potential:
        if should_order(customer, day):
            order = build_order(customer, day)
            emit(OrderCreated, order)
            # Reserve inventory
            for line in order.lines:
                if sufficient_stock(line.sku, line.qty):
                    emit(StockReserved, line.sku, line.qty)
                else:
                    emit(StockoutOccurred, line.sku, line.qty, lost_sales=True)
                    # Optionally substitute

    # 8. Process payments scheduled for today
    for payment in due_payments:
        success = process_payment(payment)
        if success:
            emit(PaymentCaptured, payment)
        else:
            emit(PaymentFailed, payment)

    # 9. Update credit balances (based on captured payments and new orders)

    # 10. Schedule collections for overdue invoices
    for invoice in overdue_invoices:
        emit(CollectionScheduled, invoice)

    # 11. Generate collection promises (customer says “will pay on X”)
    # 12. Update customer lifecycle statuses (inactive/dormant/churned)

    # 13. Generate app events (digital interactions)
    for customer in digital_active_customers:
        emit(AppEvent, customer, event_type)

    # 14. Flush events to store (batch write every N days)
```

All `emit()` calls append to the event store.

---

## 7. Monthly Simulation Pipeline

Executed after the last day of each month.

```python
for month_end in month_ends:
    # 1. Compute RFM for each customer
    for customer in customers:
        recency = days_since_last_order
        frequency = order_count_last_90d
        monetary = total_spend_last_90d
        rfm_score = combine(recency, frequency, monetary)
        emit(CustomerRFMUpdated, customer_id, rfm_score)

    # 2. Segment reevaluation
    new_segment = assign_segment_based_on_rfm(rfm_score)
    if new_segment != customer.current_segment:
        emit(CustomerSegmentChanged, customer_id, new_segment)

    # 3. Churn evaluation
    if customer.status == 'active' and days_since_last_order > 60:
        emit(CustomerBecameInactive, customer_id)
    if customer.status == 'inactive' and days_since_last_order > 90:
        emit(CustomerBecameDormant, customer_id)
    if customer.status == 'dormant' and days_since_last_order > 180:
        emit(CustomerChurned, customer_id)

    # 4. Reactivation attempts (via promotion or rep visit)

    # 5. Rep performance (orders per visit, GMV, collection rate)
    calculate_and_emit_rep_kpis()

    # 6. Promotion ROI (incremental GMV / discount cost)
    calculate_and_emit_promotion_roi()

    # 7. Inventory KPIs (stockout rate, turnover, fill rate)

    # 8. Collection KPIs (DSO, aging buckets)
```

---

## 8. Behavioral Models & Probabilities

All probabilistic decisions use a **seeded random generator** (`random.seed(42)` or similar). The following models define the likelihood of events.

### 8.1 Order Probability Model

```
P(order_today | customer, date) = logistic(
    base_rate(segment)
    + recency_boost(days_since_last_order)
    + seasonality_boost(month)
    + promotion_boost(active_promotion_for_customer)
    + rep_visit_boost(rep_visited_in_last_7_days)
)
```

**Default base rates (per day):**

| Segment        | Base probability |
|----------------|------------------|
| Premium        | 0.12             |
| Regular        | 0.07             |
| Low volume     | 0.02             |
| New (first 30d)| 0.15             |

**Recency boost:**  
If last order > 30 days ago → probability ×0.5; if > 60 days → ×0.1.  
If last order < 7 days ago → probability ×1.2 (habit).

**Seasonality factors (by month):**

| Month | Factor |
|-------|--------|
| Jan   | 0.8    |
| Feb   | 0.9    |
| Mar   | 1.0    |
| Apr   | 0.9    |
| May   | 1.0    |
| Jun   | 0.9    |
| Jul   | 1.0    |
| Aug   | 1.0    |
| Sep   | 1.1    |
| Oct   | 1.1    |
| Nov   | 1.3    |
| Dec   | 1.5    |

### 8.2 Order Size (Basket Value)

Given an order occurs, the total value is drawn from a log‑normal distribution whose parameters depend on segment:

| Segment   | Mean (log) | Std (log) |
|-----------|------------|-----------|
| Premium   | 7.5        | 1.0       |
| Regular   | 6.5        | 1.2       |
| Low volume| 5.0        | 1.5       |

Then multiplied by inflation factor and promotion discount factor.

### 8.3 Payment Delay Model

For a given invoice, the delay (days beyond due date) is:

```
delay_days = max(0, round( Gamma(shape=risk_shape, scale=risk_scale) ))
```

Where `risk_shape = 1 + risk_score * 2` (risk_score ∈ [0,1]). Higher risk → longer delays.

### 8.4 Stockout Probability

Given a demand for SKU `s` on day `d`:

```
P(stockout) = logistic(
    (current_stock / avg_daily_demand) * lead_time_days
    + seasonality_volatility(s)
)
```

If current stock < reorder_point → probability rises to 0.8+.

### 8.5 Rep Visit Probability

Each customer per day:

```
P(visit) = base_visit_rate(segment) * frequency_factor
```

Base rates: Premium 0.03, Regular 0.01, Low 0.005.  
If days since last visit > 30 → factor = 2.0.

---

## 9. Causality & Event Chains

The system must preserve causal links. Every event can store `causation_id` (the event that directly caused it) and `correlation_id` (a shared ID for a business transaction). Example chain:

1. `OrderCreated` (correlation_id = `ord_123`)
2. `StockReserved` (causation_id = `OrderCreated.id`, correlation_id = `ord_123`)
3. `PaymentCaptured` (causation_id = `OrderDelivered.id`, correlation_id = `ord_123`)

**Key causality graphs (must be enforced):**

### Inventory Chain
```
SupplierDelay → LowInventory → Stockout → PartialFulfillment → LostSales → CustomerDissatisfaction
```

Implementation: When a purchase order is delayed, emit `SupplierDelay` event. That triggers a `LowInventory` warning if stock drops below threshold. If an order line cannot be fulfilled, emit `StockoutOccurred` and `PartialFulfillment`.

### Credit Chain
```
LargeOrder → CreditUtilizationHigh → MissedPayment → CollectionVisit → PromiseToPay → Payment
```

### Lifecycle Chain
```
RegularOrders → Active → ReducedFrequency → Inactive → Dormant → Churned → Reactivation → Active
```

### Promotion Chain
```
PromotionActivated → BasketSizeIncrease → GMVIncrease → MarginImpact → PromotionROI
```

---

## 10. Business Rule Engine

Rules are checked **before** event emission. If a rule fails, a compensating event (e.g., `OrderRejected`) may be emitted instead.

| Rule ID | Condition | Action if violated |
|---------|-----------|--------------------|
| CR‑01 | credit_used + order_total ≤ credit_limit | Reject order, emit `OrderCreditRejected` |
| CR‑02 | customer_status != 'churned' | Reject order, emit `OrderCustomerChurned` |
| INV‑01 | stock_reserved + order_qty ≤ on_hand | Partial fulfillment or reject line |
| PROMO‑01 | promotion active and customer in target segment | If not, ignore promotion (no discount) |
| PAY‑01 | payment_amount ≤ invoice_balance | If exceeded, reject payment or apply only up to balance |
| COLL‑01 | collection promise date ≥ today | Cannot promise past date |

All rules are configurable via a rule registry.

---

## 11. Inventory & Supply Chain Dynamics

### 11.1 Initial Stock Levels

For each SKU, generate an initial on‑hand stock: `norm(mean=reorder_point*2, std=reorder_point*0.5)`.

### 11.2 Reorder Logic

When stock falls below `reorder_point`, automatically generate a `PurchaseOrderCreated` event to the primary supplier. The purchase order has a lead time (e.g., 7–30 days). After lead time, emit `StockReceived`.

### 11.3 Supplier Delay

Randomly for 5% of purchase orders, delay arrival by additional 1–15 days. Emit `SupplierDelay` event.

### 11.4 Inventory Adjustments

Periodically (e.g., yearly) emit `StockAdjusted` for damage, expiry, or cycle count corrections.

### 11.5 Stockout Handling

When a stockout occurs, the system may:
- Offer substitution (similar SKU) – probability 0.3
- Backorder – probability 0.2
- Cancel line – probability 0.5

Each choice emits appropriate events: `SubstitutionOffered`, `BackorderCreated`, `OrderLineCancelled`.

---

## 12. Financial Flows (Credit, Payments, Collections)

### 12.1 Credit Limit Assignment

New customers receive a credit limit based on segment:

| Segment   | Base limit | Variability |
|-----------|------------|-------------|
| Premium   | 50,000     | ±20%        |
| Regular   | 20,000     | ±30%        |
| Low volume| 5,000      | ±50%        |

### 12.2 Payment Processing

Invoices have payment terms (e.g., Net 30). Simulate payment on a random day between due date and due date + delay (see 8.3). Use a simple success probability:
- 95% success on first attempt if risk_score < 0.3
- 70% if risk_score 0.3–0.7
- 40% if risk_score > 0.7

Failed payments trigger `PaymentFailed` and increment `credit_used` (late fees added). After 2 failures, the invoice goes to collections.

### 12.3 Collections Process

When an invoice is 30+ days overdue:
- Emit `CollectionScheduled`
- Assign a collector (rep or dedicated agent)
- Emit `CollectionVisit` (if rep) or `CollectionCall`
- Customer may make a promise: `CollectionPromiseCreated` with a future date
- If promise kept → `PaymentCaptured`; if broken → escalate to `CreditWrittenOff` after 90 days.

### 12.4 Write‑offs

After 180 days overdue, emit `CreditWrittenOff`. This reduces outstanding credit.

---

## 13. Promotion & Discount Engine

### 13.1 Promotion Types

| Type             | Effect |
|------------------|--------|
| Percent discount | 1%–5% off entire order |
| Fixed amount off | 5–2000 off |
| Free goods       | Buy 10 get 1 free |
| Tiered discount  | 1% off >1000, 5% off >5000 |

### 13.2 Activation Schedule

Create promotions with start and end dates. Some are seasonal (e.g., Black Friday), others are targeted (e.g., reactivation for dormant customers). Active promotions are evaluated at order creation.

### 13.3 Redemption Logic

If promotion applies (customer in target segment, date valid, min purchase met), apply discount and emit `PromotionApplied`. Record discount amount in order and redemption table.

### 13.4 ROI Calculation (monthly)

```
ROI = (incremental_gmv - discount_cost) / discount_cost
```
Incremental GMV is estimated using a control group (customers not exposed to promotion) – simulate a small holdout group (5% of customers).

---

## 14. Sales & Field Operations (Rep Visits)

### 14.1 Rep Assignment

Each customer is assigned to exactly one sales rep (based on area). The assignment may change over time; emit `CustomerAssignedToRep`.

### 14.2 Visit Generation

Each rep has a capacity (max visits per day = 3–5). The simulation selects customers with highest visit probability (see 8.5) up to capacity.

### 14.3 Visit Outcomes

| Outcome          | Probability | Effect |
|------------------|-------------|--------|
| No order         | 0.5         | None   |
| Small order placed| 0.3         | Immediate order (same day) |
| Large order placed| 0.15        | Immediate large order |
| Reactivation     | 0.05        | If customer was churned, becomes active again |

### 14.4 Performance Metrics

Monthly compute per rep:
- Number of visits
- GMV from visits (attributed)
- Collection amount from visited customers
- Customer satisfaction proxy (based on order frequency after visit)

---

## 15. Customer Lifecycle Management

### 15.1 States & Transitions

```
[New] → [Active] ←→ [Inactive] → [Dormant] → [Churned]
          ↑                           |
          └───── [Reactivated] ────────┘
```

### 15.2 Transition Rules (after monthly evaluation)

| From       | To         | Condition |
|------------|------------|-----------|
| New        | Active     | First order placed |
| Active     | Inactive   | No order for 60 days |
| Inactive   | Dormant    | No order for 90 more days (150 total) |
| Dormant    | Churned    | No order for 180 more days (330 total) |
| Churned    | Reactivated| Promotion redemption OR rep visit with reactivation outcome |

### 15.3 Reactivation Boost

After reactivation, the customer’s order probability is multiplied by 1.5 for 30 days.

### 15.4 App Events

Simulate digital engagement (login, browse, add to cart) as independent events. Probability per day: `0.2 * factor(segment)`. These events feed into RFM and churn models.

---

## 16. Noise & Anomaly Injection

To make the dataset realistic, inject controlled noise after the deterministic simulation:

| Noise type | Frequency | Example |
|------------|-----------|---------|
| Missing event | 1% of events | A payment event is not recorded |
| Duplicate event | 0.5% | Two identical `OrderCreated` events |
| Out‑of‑order timestamp | 0.1% | Event timestamp is 1 hour before causation event |
| Data corruption | 0.01% | A payload field becomes null or negative |
| Late arrival | 2% | Event timestamp is backdated (e.g., payment recorded 2 days late) |

Use a separate noise generator that reads the event stream and emits corrected events or logs anomalies.

---

## 17. Output Tables & Schemas

Final projections (Parquet files):

| Table name          | Description | Partition key |
|---------------------|-------------|---------------|
| `customers`         | Current snapshot of each customer | None |
| `customer_history`  | Daily status (segment, credit used) | date |
| `orders`            | Order header | order_date (month) |
| `order_lines`       | Line items | order_date (month) |
| `invoices`          | Invoice header | invoice_date |
| `payments`          | Payment transactions | payment_date |
| `credit_ledger`     | Credit movements | transaction_date |
| `inventory_snapshot`| Daily stock by SKU | date |
| `stockout_events`   | Recorded stockouts | date |
| `promotions`        | Promotion master data | None |
| `promotion_redemptions` | Usage per order | order_date |
| `rep_visits`        | Field visits | visit_date |
| `app_events`        | Digital touchpoints | event_date |
| `rfm_scores`        | Monthly RFM | month |
| `rep_performance`   | Monthly rep KPIs | month |
| `promotion_roi`     | Monthly promotion ROI | month |

All tables are generated by replaying the event store and aggregating. The event store itself may be stored as `event_store.parquet` for debugging.

---

## 18. Validation & KPIs

Before final output, run validation checks:

### 18.1 Consistency Checks

- No `OrderCreated` without existing `CustomerCreated` (by timestamp)
- `StockReserved` total ≤ `StockReceived` – `StockReleased`
- Sum of `order_lines.total` = `orders.total_value`
- `credit_used` = sum(order totals) – sum(payments) – write‑offs

### 18.2 KPI Validation

Ensure simulated KPIs fall within realistic ranges:

| KPI | Expected range |
|-----|----------------|
| Average order value | 1500–15,000 |
| Churn rate (annual) | 10%–30% |
| Days sales outstanding (DSO) | 30–60 days |
| Stockout rate | 2%–20% of order lines |
| Promotion ROI | 1.5–4.0 |
| Visit‑to‑order conversion | 30%–60% |

If any KPI is outside bounds, adjust behavioral model parameters and re‑run.

### 18.3 Causality Validation

Randomly sample 100 events and trace the causal chain back to a root cause (e.g., stockout → late supplier). Ensure no event has a missing causation link (except initial bootstrap events).

---

## 19. Implementation Guidelines

### 19.1 Technology Stack (Recommended)

- **Language:** Python 3.10+ (with type hints, dataclasses)
- **Randomness:** `random` module with fixed seed; `numpy.random` for distributions
- **Event store:** In‑memory list during simulation, then write to Parquet via `pandas` or `pyarrow`
- **Projections:** Use `pandas` group‑by / merge; or DuckDB for SQL‑style materialisation
- **Output:** Parquet (partitioned by date) + optionally DuckDB database file

### 19.2 Code Structure (as per original spec)

```
simulation_engine/
├── config/                     # seeds, date ranges, parameters
├── generators/                 # initial data (customers, products, etc.)
├── engines/                    # core simulation modules
│   ├── lifecycle_engine.py
│   ├── ordering_engine.py
│   ├── inventory_engine.py
│   ├── pricing_engine.py
│   ├── promotion_engine.py
│   ├── payment_engine.py
│   ├── collection_engine.py
│   └── fraud_engine.py
├── validators/                 # business rules, KPI checks
├── exporters/                  # Parquet, DuckDB, PostgreSQL
├── derived/                    # snapshots, RFM, rep performance
└── simulation_runner.py        # main loop
```

### 19.3 Execution Steps for the AI Builder

1. **Set up the event store** – define `Event` class and `EventStore` with append/stream.
2. **Implement aggregates** – `Customer`, `Order`, `Inventory`, etc.
3. **Write the daily loop** (section 6) as a class `SimulationEngine`.
4. **Implement behavioural models** (section 8) as pure functions.
5. **Add rule engine** (section 10) decorators or check functions.
6. **Generate initial static data** (customers, products, reps, areas) via `generators/`.
7. **Run simulation** for the desired date range.
8. **Run monthly aggregations** (section 7) as post‑processing.
9. **Build projections** (section 17) by reading event store.
10. **Validate** (section 18) and export.

### 19.4 Reproducibility

Set global seed at the beginning:

```python
import random
import numpy as np
random.seed(42)
np.random.seed(42)
```

All random calls must go through these seeded modules.

### 19.5 Testing

Unit tests for each engine (e.g., ensure `PaymentCaptured` reduces credit_used). Integration test: run a 30‑day simulation and assert all consistency checks pass.

---

## 20. Glossary

| Term | Definition |
|------|------------|
| **Event store** | Append‑only log of all state changes. |
| **Aggregate** | A domain entity that enforces invariants by replaying its events. |
| **Projection** | A materialised view (table) derived from events. |
| **Causation ID** | Event ID that caused the current event. |
| **Simulation clock** | Discrete day counter driving the loop. |
| **Stockout** | Event when requested quantity exceeds available inventory. |
| **RFM** | Recency, Frequency, Monetary value – customer scoring model. |
| **DSO** | Days Sales Outstanding – average collection period. |
| **GMV** | Gross Merchandise Value – total order value before discounts. |

---

**End of Document**

This design is ready for Claude (or any engineering team) to implement the Synthetic Wholesale Commerce Simulation Engine. All architectural decisions, causal flows, and behavioural rules are specified. The output will be a fully functional simulator generating explainable, replayable wholesale data.

---
# Addendum: Missing Components for the Synthetic Wholesale Commerce Simulation Engine

**Version:** 1.1  
**Supersedes:** Section gaps identified in the main document  
**Purpose:** Add critical missing functionality to achieve a production‑ready simulation generating ~4M rows with full causality, fraud, returns, and performance scalability.

---

## A1. Customer Acquisition Over Time (New Customer Arrival)

### A1.1 Requirement
The simulation must start with a base set of customers and continuously add new ones each day to mimic a growing wholesale business.

### A1.2 Arrival Model

Use a **non‑homogeneous Poisson process** with daily rate `λ(t)`:

```
λ_base = 5 customers/day (adjustable)
λ(t) = λ_base * seasonality_factor(month) * growth_factor(t)
```

- **Seasonality factor** (same as order seasonality, see §8.1): higher in Q4.
- **Growth factor** = 1 + 0.002 * day_index (slow 0.2% daily growth to reach ~1.5× after one year).

### A1.3 Customer Attributes for New Arrivals

| Attribute | Generation rule |
|-----------|----------------|
| Segment | Probabilistic: Premium 20%, Regular 50%, Low volume 30% |
| Credit limit | Based on segment (see §12.1) × random factor 0.8–1.2 |
| Acquisition channel | 60% rep referral, 40% digital|
| Initial status | “Active” (but no orders yet) |
| Assigned rep | Random rep from the rep’s area based on customer postal code |

### A1.4 Events to Emit

```python
if random.random() < daily_arrival_probability:
    customer_id = new_id()
    emit(CustomerCreated, aggregate_id=customer_id, payload={
        "segment": segment,
        "credit_limit": credit_limit,
        "acquisition_channel": channel,
        "acquisition_date": today
    })
    emit(CustomerAssignedToRep, customer_id, rep_id)
```

**Integration:** Call `generate_new_customers(today)` at the beginning of the daily loop (before order generation) in `simulation_runner.py`.

---

## A2. Product Catalog Generation & Price Evolution

### A2.1 Product Static Data Generation

Generate **500 SKUs** (configurable) with:

| Field | Generation |
|-------|------------|
| SKU ID | `SKU_{i:04d}` |
| Category | Random from {Beverage, Snack, Cleaning, Office, Electronics, Apparel} |
| Base price (list) | Lognormal(mean=50, sigma=1.5) – clamped 5–5000 |
| Unit cost (COGS) | Base price × (0.5 to 0.8) depending on category margin |
| Reorder point (units) | Poisson(lambda=50) |
| Lead time (days) | Discrete: 3, 5, 7, 10, 14 with probabilities [0.2,0.3,0.25,0.15,0.1] |
| Supplier ID | Randomly assigned from 50 suppliers |

### A2.2 Price Evolution

Two types of price changes:

1. **Inflationary drift** (already in macro state): apply to both base price and unit cost daily.
2. **Strategic price changes** (occur 1–4 times per SKU per year):  
   - Emit `ProductPriceChanged` event with new base price.  
   - Reason: “cost_increase”, “promotional”, “competitor_response”.

### A2.3 Events

```python
emit(ProductCreated, sku_id, initial_price, unit_cost, reorder_point, lead_time)
emit(ProductPriceChanged, sku_id, old_price, new_price, effective_date, reason)
```

**Integration:** Run `ProductGenerator` once before simulation start. During simulation, each month randomly select 5% of SKUs and apply a price change.

---

## A3. Returns & Cancellations

### A3.1 Return Probability & Logic

For each delivered order:

- **Return probability** = 0.02 + 0.01 * (1 if product_category high‑damage else 0) + risk_factor(customer)
- Time to return: uniform(3, 14) days after delivery.

### A3.2 Return Process

When a return or partial return occurs, emit in sequence:

1. `OrderReturnRequested` (causation = OrderDelivered)
2. `StockReceived` (inventory increases, flagged as returned)
3. `CreditRefundIssued` (reduce customer credit_used by refund amount)
4. `PaymentRefunded` (if payment already captured)

Refund amount = (unit_price (on the time of order) × quantity).

### A3.3 Cancellations

Before shipment (while order status = “confirmed”):

- Probability = 0.005 per confirmed order.
- Emit `OrderCancelled` and `StockReleased` (return reserved stock to available).

**Integration:** In the daily loop, after order confirmation, check cancellation; after order delivery, schedule return probability in a future daily loop.

---

## A4. Purchase Order & Replenishment Logic

### A4.1 Reorder Formula

At the end of each day, for each SKU:

```
projected_demand = avg_daily_demand_last_30d * lead_time_days
safety_stock = 1.645 * sqrt(lead_time_days) * daily_demand_std   (95% service level)
reorder_point = projected_demand + safety_stock

if on_hand + on_order <= reorder_point:
    order_quantity = max( EOQ, reorder_point - (on_hand + on_order) + safety_buffer )
    emit(PurchaseOrderCreated, sku_id, quantity=order_quantity, supplier_id)
```

- **EOQ** (Economic Order Quantity) = sqrt(2 * annual_demand * cost_per_order / holding_cost_per_unit) – simplified to constant 200 units for initial implementation.

### A4.2 Multiple Suppliers per SKU

Each SKU has a primary supplier (90% of orders) and one secondary supplier (10% when primary is overloaded or delayed). Secondary has longer lead time (+3 days) and higher cost (+5%).

### A4.3 Supplier Capacity Constraint

Each supplier has a maximum daily production capacity (e.g., 5000 units). If a purchase order exceeds remaining capacity, the order quantity is capped and an extra delay of 2–5 days is added.

### A4.4 Purchase Order Arrival

After lead time (plus optional delay), emit `StockReceived` with quantity and update inventory.

**Integration:** Call `check_reorder()` at the end of each daily loop. Store pending purchase orders in a dictionary keyed by expected arrival date.

---

## A5. Fraud Patterns

### A5.1 Fraud Types & Probability

| Fraud type | Probability per relevant event | Description |
|------------|-------------------------------|-------------|
| Suspicious order | 0.003 per OrderCreated | High value, new customer, overnight shipping |
| Payment fraud | 0.005 per PaymentInitiated | Stolen card; later chargeback |
| Identity theft | 0.001 per CustomerCreated | Synthetic identity |
| Return fraud | 0.01 per ReturnRequested | Returning wrong/damaged item deliberately |

### A5.2 Fraud Detection & Actions

When a fraud pattern is triggered, emit `FraudAlert` event with `fraud_type` and `risk_score`. Then:

- For high confidence (score > 0.8): emit `OrderRejected` (before confirmation) or `CustomerSuspended`.
- For medium confidence (0.5–0.8): flag order for manual review (add metadata `fraud_review=True`).
- For low confidence: just log.

### A5.3 Chargeback Simulation

If payment fraud is detected after payment capture, emit `ChargebackCreated` after a random delay (15–30 days). This reverses the payment, adds a fee, and may trigger customer suspension.

**Integration:** Add a `FraudEngine` class called during order creation, payment initiation, and return requests.

---

## A6. Daily Inventory Reconciliation (Reserved → Shipped)

### A6.1 Fulfillment Process

Each confirmed order (status = “confirmed”) should be fulfilled within 1–2 days. In the daily loop:

```python
for order in confirmed_orders:
    if order.confirmation_date + timedelta(days=1) <= today:
        for line in order.lines:
            if line.reserved_quantity > 0:
                emit(StockShipped, sku_id, quantity=line.reserved_quantity, order_id=order.id)
                # Reduce reserved, reduce on_hand
        emit(OrderShipped, order_id, shipment_date=today)
```

If partial fulfillment (because stock was released due to cancellation), ship what is available.

### A6.2 Backorder Handling

If some lines cannot be fully shipped (stockout after partial shipping), create a `BackorderCreated` event and schedule fulfillment when stock is replenished.

**Integration:** After `StockReceived` events, check for any backorders for that SKU and attempt to fulfill them.

---

## A7. Time Granularity & Sub‑Day Jitter

### A7.1 Need for Sub‑Day Precision

Many ML models (e.g., payment delay prediction) benefit from hour‑level timestamps. Also, causality ordering within the same day must be preserved.

### A7.2 Timestamp Generation

When emitting an event:

```python
base_time = datetime.combine(today, datetime.min.time())
# Add random seconds within business hours (8:00–18:00) for most events
if event_type in ['OrderCreated', 'PaymentCaptured', 'RepVisitCompleted']:
    hour = int(random.gauss(10, 2))  # mean 10:00, std 2h
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    timestamp = base_time.replace(hour=hour, minute=minute, second=second)
else:
    # For inventory, lifecycle events – use any time
    timestamp = base_time + timedelta(seconds=random.randint(0, 86400))
```

### A7.3 Causality Preservation

If event B is caused by event A, ensure `B.timestamp >= A.timestamp`. In the same day, add a small epsilon (e.g., +1 second) to B’s timestamp.

**Integration:** Modify `emit()` to accept an optional `causation_event` and adjust timestamp accordingly.

---

## A8. Concrete Sizing for 4M Rows

To achieve ~4M rows (events + derived tables), use the following configuration:

| Parameter | Value | Notes |
|-----------|-------|-------|
| Simulation period | 730 days (2 years) | Start 2023-01-01, end 2024-12-31 |
| Initial customers | 2,000 | Active at start |
| New customers per day (avg) | 8 | Growth to ~6,800 total |
| Active SKUs | 500 | |
| Order probability (avg across segments) | 0.08 | ~1,100 orders/day |
| Events per order (incl. payments, inventory) | 7–10 | Average 8 |
| Daily events from orders | ~8,800 | |
| Other events (visits, app, lifecycle) | ~1,200 | |
| **Total events** | (8,800+1,200)*730 = **7.3M** | Exceeds 4M – adjust probabilities down or reduce days |

To hit exactly 4M rows, reduce order probability to 0.045 → ~600 orders/day → ~4,800 order‑related events/day + 1,200 others = 6,000 events/day → 4.38M events over 730 days.

**Recommended:** Simulate 1 year (365 days) with order probability 0.07 → ~960 orders/day → ~7,680 events/day → 2.8M events. Add derived tables (order lines, invoices, payments, rfm) to reach 4M rows.

---

## A9. Performance & Memory Management

### A9.1 Event Store Implementation

Instead of storing all events in a Python list, use **DuckDB** as the event store. Create a table:

```sql
CREATE TABLE event_store (
    event_id UUID,
    event_type VARCHAR,
    aggregate_id VARCHAR,
    timestamp TIMESTAMP,
    payload JSON,
    metadata JSON,
    causation_id UUID,
    correlation_id UUID
);
```

Append events in batches of 10,000 using DuckDB’s `append()`.

### A9.2 Incremental Projections

After each day (or every N days), rebuild only the projections that have changed (e.g., orders, inventory). Use DuckDB’s `CREATE OR REPLACE VIEW` for derived tables.

### A9.3 Checkpointing

Save simulation state every 30 days: dump the event store and current aggregates to Parquet. On restart, load the last checkpoint and resume.

**Integration:** Modify `simulation_runner.py` to accept `--resume` flag.

---

## A10. Initial State Bootstrap (Warm Start)

### A10.1 Requirement

New customers should not have prior history, but existing customers need realistic order history before simulation day 1 to make RFM and churn calculations meaningful.

### A10.2 Bootstrap Process

Run once before the main daily loop:

1. For each initial customer:
   - Generate 3–12 orders in the 180 days before simulation start.
   - Order dates: random past dates, respecting order probability recency.
   - Generate corresponding payments (some may be overdue).
   - Emit all events with historical timestamps.
   - Do **not** generate inventory movements or rep visits for these historical orders (to keep bootstrap simple – we assume inventory was sufficient).

2. After historical events, recompute aggregates (customer credit used, last order date, etc.).

3. Set simulation clock to start date.

**Integration:** Call `BootstrapEngine.generate_history()` before entering the main daily loop.

---

## A12. Additional Derived Tables for ML

After simulation, create the following analytics tables:

| Table | Definition | Use case |
|-------|------------|----------|
| `customer_clv` | Monthly aggregated: total spend to date, predicted future spend (simple linear model) | CLV prediction |
| `product_affinity` | For each order pair (SKU A, SKU B), count of co‑occurrence | Market basket analysis |
| `supplier_lead_time_performance` | For each supplier, avg lead time actual vs. quoted, on‑time delivery % | Supplier scoring |
| `daily_inventory_snapshot` | Day‑end on_hand, reserved, available, stockout_flag | Inventory forecasting |
| `payment_delay_by_customer` | Rolling 90‑day avg payment delay, max delay | Credit risk features |

**Integration:** Add a `derived/analytics_views.py` module that reads the event store and writes these tables.

---

## A13. Updated System Configuration Example

Create `config/simulation_config.yaml`:

```yaml
simulation:
  start_date: 2023-01-01
  end_date: 2023-12-31   # 1 year for 4M rows
  random_seed: 42
  batch_size_events: 10000

customer:
  initial_count: 8000
  daily_arrival_rate: 8
  growth_rate_per_day: 0.0015

product:
  sku_count: 500
  price_change_monthly_probability: 0.05

order:
  base_probabilities:
    premium: 0.12
    regular: 0.07
    low_volume: 0.02
  return_probability: 0.02
  cancellation_probability: 0.005

inventory:
  service_level: 0.95
  default_eoq: 200

fraud:
  suspicious_order_prob: 0.003
  payment_fraud_prob: 0.005

performance:
  checkpoint_frequency_days: 30
  event_store_backend: "duckdb"   # or "parquet"
```

---

## A14. Integration Roadmap (For Implementation)

| Step | Component | Depends on |
|------|-----------|------------|
| 1 | Implement DuckDB event store (A9) | – |
| 2 | Add product catalog generator (A2) | – |
| 3 | Add bootstrap engine (A10) | A2 |
| 4 | Implement daily new customer arrival (A1) | A3 |
| 5 | Build replenishment logic (A4) | A2, A6 |
| 6 | Add returns & cancellations (A3) | A6 |
| 7 | Add fraud engine (A5) | A1, A3 |
| 8 | Add sub‑day timestamps (A7) | All event emissions |
| 9 | Add tax & shipping (A11) | Order generation |
| 10 | Implement analytics views (A12) | After simulation |
| 11 | Configure sizing & run (A8) | All |

---

# Addendum 2: Final Realism & Coverage Gaps

## A15. Basket Affinity & Substitution Engine

### A15.1 Co‑Occurrence Matrix  
Define a static affinity matrix (e.g., `Tea → Sugar`, `Rice → Cooking Oil`, `Pasta → Sauce`, `Detergent → Fabric Softener`, `Coffee → Creamer`). For each category pair, store `lift` (e.g., joint probability 2–3× the product of marginals).

### A15.2 Order Line Generation with Affinity  
When building an order:

1. Randomly pick an anchor SKU (uniform across the catalog).  
2. With probability proportional to lift, add one or two affinity SKUs to the basket.  
3. Fill remaining slots with random SKUs (ensuring no duplicates) up to the basket size.

### A15.3 Stockout Substitution  
When a requested SKU is out of stock:

- If an affinity SKU is available, substitute with probability 0.4. Emit `SubstitutionOccurred` linking original SKU to substitute, adjust order line.
- Else, backorder (0.2) or cancel line (0.4), emitting `BackorderCreated` or `OrderLineCancelled`.

### A15.4 Events  
- `BasketAffinityApplied` (metadata: anchor SKU, affinity SKU).  
- `SubstitutionOccurred` (original_sku, replacement_sku, quantity).  

**Integration:** Call `AffinityEngine.enhance_basket(order)` during order building (Step 7 of daily loop).

---

## A16. Customer Identity & Device Graph

### A16.1 Identity Table  
Generate a separate projection `customer_identity` with:  
`customer_id, device_id, phone_hash, registration_ip, device_type, app_version`.  

- `device_id`: UUID per customer; 3% of devices are shared (fraud pattern).  
- `phone_hash`: hash of a fake phone number; shared among 2‑5 synthetic identities.  
- `registration_ip`: IP address; shared for accounts from the same location.

### A16.2 Fraud Signals  
Link to the fraud engine (Addendum A5): if a new order’s customer shares a device with another recently active customer, increase fraud risk score.

### A16.3 Events  
- `DeviceLinkedToCustomer` (emitted once at customer creation).  
- `SuspiciousDeviceShared` (emitted when multiple customers use same device within a short period).  

**Integration:** Generate `customer_identity` rows statically before simulation, using seeded randomness.

---

## A17. App Events & Digital Engagement

### A17.1 Session Generation  
Each day, for a subset of customers (probability based on profile and recency), generate a session:

- Session start time (within business hours).  
- Events inside session: `Login → Browse → Search → Product View → Add To Cart → Checkout → Order Submitted` (or drop‑off).  
- Session duration: mean 8 minutes, exponential.

### A17.2 Probability Model  
```
P(session_today) = base_digital_rate(segment) * recency_factor * promotion_active_factor
```
Base rates: Strategic 0.3, Growth 0.2, Core 0.1, Long Tail 0.05.  
If a promotion is active and the customer is eligible, probability ×1.3.

### A17.3 Drop‑off  
- `Add To Cart` → `Checkout` conversion: 25%.  
- `Checkout` → `Order Submitted`: 60% (rest lost to payment failure or exit).

### A17.4 Events  
- `AppSessionStarted`, `AppScreenViewed`, `ProductSearched`, `AppOrderPlaced` (correlation_id links to order).  

**Integration:** Run `DigitalEngagementEngine.generate_sessions()` in the daily loop after macro updates but before order generation (some orders originate from app, others from rep visits). The channel of the resulting order is set to `Mobile App` if an app session resulted in an order.

---

## A18. Acquisition Funnel (Customer Journey)

### A18.1 Funnel Table  
Project a `customer_acquisition` table:

| Column | Source Event |
|--------|--------------|
| customer_id | `CustomerCreated` |
| lead_date | `LeadCaptured` (optional; can be same as `registration_date` if not separate) |
| qualified_date | `LeadQualified` |
| registered_date | `CustomerCreated` (timestamp of registration) |
| first_order_date | Earliest `OrderCreated` for this customer |
| acquisition_source | payload of `CustomerCreated` (channel) |

### A18.2 Additional Lead Events (Optional)  
For realism, some customers may have a lead phase before registration. Emit `LeadCaptured` and `LeadQualified` with random delays.

### A18.3 Metrics  
Track time‑to‑first‑order per channel; this feeds into CLV models.

**Integration:** Emit `LeadCaptured` for a subset of daily new arrivals (A1) with a delay of 1‑7 days before `CustomerCreated`.

---

## A19. Promotion Scope & Targeting Engine

### A19.1 Promotion Scope Table  
Create `promotion_scope` as a projection from `PromotionScopeDefined` events.

| Field | Description |
|-------|-------------|
| promotion_id | FK |
| scope_type | `SKU`, `Brand`, `Category`, `Customer`, `Segment`, `Area`, `Channel`, `Payment Method` |
| scope_id | ID of the entity (e.g., SKU ID, segment name) |

### A19.2 Eligibility Check  
When evaluating a promotion for an order, the engine checks **all** active scopes for that promotion. The order must satisfy **all** scope conditions (AND logic). For example: “10% off for Strategic customers in Cairo using Mobile App”.

### A19.3 Event  
- `PromotionScopeDefined` (emitted once per scope when promotion is created).

**Integration:** Modify the daily loop’s promotion evaluation to call `PromotionEngine.is_eligible(order, customer, date)`.

---

## A20. Inventory Policy as SKU Attributes

### A20.1 SKU Parameters  
Augment the product catalog generator (Addendum A2) to produce and store the following per SKU:

- `reorder_point` (computed initially, but also stored as policy)  
- `safety_stock`  
- `max_stock`  
- `target_days_cover`  
- `demand_class` (A: 20%, B: 30%, C: 50%)  
- `lead_time_days` (already present)

### A20.2 Generation Rules  
- For demand class A: high reorder point, low safety stock ratio (as demand is steady).  
- For class C: lower reorder point, higher safety stock relative to demand (high variability).

### A20.3 Events  
- `InventoryPolicySet` (emitted at product creation, can be updated later).

**Integration:** The reorder logic (Addendum A4) reads these stored parameters instead of recomputing them on the fly.

---

## A21. Rep Targets & Performance Management

### A21.1 Monthly Targets  
At the beginning of each month, emit `RepTargetSet` for each rep with fields:  
`target_month, gmv_target, orders_target, active_customers_target, collections_target, new_customers_target, reactivation_target`.

Target values are derived from historical performance × growth factor × tier multiplier.

### A21.2 Performance Snapshot  
At month‑end, compute actual vs. target and emit `RepPerformanceEvaluated`. This feeds a `rep_performance` derived table.

### A21.3 Correlation with Rep Tier  
Rep performance tier (A/B/C/D) influences:  
- Visit‑to‑order conversion (A: 55%, B: 45%, C: 35%, D: 25%)  
- Collection success rate (A: 90%, B: 80%, C: 60%, D: 40%)  
- Customer reactivation rate after visit.

These probabilities are used in the daily visit outcome generation.

**Integration:** In the rep visit step, the `outcome` probability is adjusted according to the rep’s tier.

---

## A22. Collection Promises Detailed Flow

### A22.1 Promise Table  
Create a `collection_promises` projection with:  
`promise_id, customer_id, invoice_id, promise_date, promised_amount, promised_payment_date, fulfilled_flag`.

### A22.2 Promise Creation  
When a collection visit/call occurs and the customer cannot pay immediately, with probability 0.3 emit `CollectionPromiseMade`. The promise date is 7‑30 days in the future.

### A22.3 Promise Fulfilment  
In the daily loop, check outstanding promises due today. Emit `PaymentCaptured` (if succeeded) or `PromiseBroken`. Update `fulfilled_flag` accordingly.

**Integration:** Extend the collections step in the daily loop to handle promises.

---

## A23. Correlation Engine – Cross‑Domain Dependencies

The following correlations are now explicitly modelled:

### A23.1 Risk Score → Payment Delay  
Already in payment delay model (Gamma shape parameter based on risk score).

### A23.2 Rep Performance Tier → Visit Outcomes  
Conversion rates, collection success, reactivation as in A21.3.

### A23.3 Area Income Band → AOV  
When generating order value, multiply by an income multiplier:  
- High income: 1.2  
- Mid income: 1.0  
- Low income: 0.8  

### A23.4 New Customer → Basket Variability  
For customers with fewer than 5 orders, increase the standard deviation of basket size by 1.5×.

### A23.5 Elasticity – See A24.

### A23.6 Segment Sensitivity to Promotions  
Strategic customers have a 20% higher probability of ordering when a promotion is active.

These adjustments are made directly in the behavioural functions of the daily loop.

---

## A24. Price Elasticity of Demand

### A24.1 Elasticity Coefficients  
Define for each demand class:

| Demand Class | Elasticity (ε) |
|--------------|----------------|
| A (essential) | -0.3 |
| B            | -0.6 |
| C (discretionary) | -1.2 |

Also adjust per customer price sensitivity: multiply ε by `(1 + customer.price_sensitivity)`.

### A24.2 Application  
When an order is generated, for each line:

1. Calculate the **current unit price** from price history.  
2. Compare to the **base price at customer’s join date** to get % change.  
3. Adjust the requested quantity: `adjusted_qty = base_qty * (1 + ε * Δp/p)`.  
4. Clamp to a minimum of 1.

### A24.3 Events  
- `PriceElasticityApplied` (metadata) can be logged for analysis.

**Integration:** Modify the order line creation step.

---

## A25. Derived Tables from Original Spec

Ensure the following projections are built (already partially in output tables; add any missing ones):

- `monthly_customer_snapshot`: aggregate orders per customer per month (GMV, AOV, frequency, recency, credit used).
- `daily_inventory_snapshot`: end‑of‑day stock, days_cover, stockout_flag.
- `rep_performance_snapshot`: monthly actuals vs. targets (A21).
- `promotion_performance`: incremental GMV, consumed budget, ROI (already in main doc).
- `customer_rfm_snapshot`: RFM scores per customer at end of simulation.
- `product_affinity` (co‑occurrence counts) – can be derived from order lines.

**Integration:** These are built during the monthly pipeline or as a final post‑processing step, using the event store.

---

## A26. Revised KPI Targets & Validation

Add the following checks to the validation layer (Section 18):

| KPI | Target Range |
|-----|--------------|
| Basket affinity lift (top 3 pairs) | Lift > 1.5 |
| App session to order conversion | 1.5%–3% |
| Promise fulfilment rate | 55%–65% |
| Rep target achievement (average) | 80%–110% of GMV target |
| Demand elasticity observed (correlation) | Negative correlation between price change and quantity demanded (check via regression) |

If outside range, adjust internal probability parameters and re‑run.

---

## A27. Integration Summary

The following new engines/files should be added to the codebase:

- `engines/affinity_engine.py`  
- `engines/app_events_engine.py`  
- `engines/acquisition_funnel.py`  
- `engines/promotion_scope.py`  
- `engines/rep_performance.py`  
- `engines/elasticity.py`  
- `engines/correlation_adjustments.py` (or integrate into existing engines)  

All are called from `simulation_runner.py` at the appropriate point in the daily/monthly loop.

---

## Final Architecture: The Four Business Cycles as the Simulation Backbone

The entire synthetic dataset must be understood as a **living business system**, not a frozen, closed‑book extract. Real‑world data contains in‑flight processes, incomplete states, and temporal dynamics that create the signatures used by predictive models (churn risk, cash‑flow forecasting, demand sensing). The generator must therefore simulate **four interconnected cycles** that run continuously, each leaving behind partial states that mirror a real, active wholesale operation.

### 1. Customer Lifecycle Cycle  
*Entities: Customer, SegmentHistory, LifecycleEvents, RepAssignments*

- **Acquisition** → Lead → Qualified → Registered → First Order (`Activated`).  
- **Active** → Regular ordering → recency stays under 30 days.  
- **Inactive** (31–90 days without order) → `Inactive` event.  
- **Dormant** (91–180 days) → `Dormant` event.  
- **Churned** (>180 days) → `Churned` event.  
- **Reactivation** → A rep visit or promotion triggers a new order → `Reactivated` event.  
- **Segment Upgrades/Downgrades** occur monthly based on RFM, recorded in `customer_segment_history`.

**Live‑system effect:** At any point in the data, 40% of customers are Active, 15% Inactive, 20% Dormant, 25% Churned. Many customers are in transition—the snapshot shows a mix of states, and the history files show the path they took. This is critical for churn prediction and next‑best‑action models.

### 2. Order Lifecycle Cycle  
*Entities: Orders, OrderLines, OrderStatusHistory, Substitutions, AvailabilityEvents*

- An order passes through **Created → Approved → Allocated → Picking → Out for Delivery → Delivered** (or **Cancelled** / **Returned**).  
- **Partial deliveries** and **stockouts** create incomplete lines, recorded in `fulfilled_qty < requested_qty`.  
- **Returns** occur days after delivery, triggering inventory restock and possible refunds.  
- **Cancellations** happen before shipment.  
- Every status change is stored as an event, allowing analysis of fulfillment times, SLA, and bottlenecks.

**Live‑system effect:** At the dataset’s end date, many orders will still be in “Picking” or “Out for Delivery”—they are open transactions, not closed. Analysts must handle in‑flight orders; forecasting models must account for backlog.

### 3. SKU Lifecycle & Inventory Cycle  
*Entities: Products, ProductPriceHistory, InventoryMovements, StockoutEvents, PurchaseOrders, InventoryPolicy*

- **SKU introduction** (`launch_date`) and possible discontinuation.  
- **Pricing evolution** – base prices drift with inflation and strategic changes; the price on any transaction comes from the active `product_price_history` row.  
- **Inventory movements**: daily stock position is built from `Purchase`, `Sale`, `Return`, `Adjustment` events.  
- **Replenishment**: when stock falls below `reorder_point`, a `PurchaseOrder` is generated with supplier lead time. Delays, partial receipts, and cancellations are possible.  
- **Stockout & substitution**: a stockout triggers a `StockoutEvent` and optionally a substitution to a similar SKU.  
- **Demand classes** (A/B/C) drive different inventory policies and stockout risks.

**Live‑system effect:** Inventory levels are never perfectly balanced. Some SKUs are out‑of‑stock, others overstocked; some POs are overdue. The `daily_inventory_snapshot` shows the current “hot” state, while the movement history enables supply‑chain modelling.

### 4. Payment & Cash Cycle  
*Entities: Invoices, Payments, PaymentStatusHistory, CreditLedger, Collections, CollectionPromises*

- **Invoice creation** upon order delivery with due dates (Net 30).  
- **Payment attempts** follow a probabilistic process:  
  - Initiated → Authorized → Captured (success) or **Failed**.  
  - Late payments, partial payments, and multiple attempts are the norm.  
- **Credit** is tracked per customer: `credit_used` increases with order, decreases with payments, and may be written off.  
- **Collections** kick in when invoices are overdue: rep visits, promises to pay, and eventual fulfilment or default.  
- **Promises** are created and later either fulfilled or broken, with consequences for the customer’s risk score.  
- **Write‑offs** occur after 180 days of delinquency.

**Live‑system effect:** At the dataset’s final date, many invoices are still “Partially Paid”, “Overdue”, or “Open”. Payments may be in “Authorized” state, not yet “Settled”. This incomplete cash‑cycle data is essential for credit risk modeling, DSO calculation, and collection prioritization.

---

### The “Live System” Imperative: Incomplete & In‑Flight Data

A synthetic dataset that closes every order, resolves every payment, and leaves all inventory perfectly aligned would train models that fail in production. The generator must deliberately leave **unfinished business**:

- **Open orders**: status ≠ Delivered, order_date near the end.  
- **Pending payments**: invoices where `paid_amount < invoice_amount`.  
- **Unresolved collections**: overdue invoices without final collection outcome.  
- **Partially fulfilled POs**: some receipts still expected.  
- **Customers in transition**: recent reactivations, recently churned customers with no final state.  
- **Active promotions**: still running, with redemption counts still accumulating.  
- **App sessions**: abandoned carts, sessions not yet concluded.

This is achieved by running the simulation until a hard stop date, without attempting to “wrap up” business processes. The event store simply ends; any process still ongoing remains that way. Derived snapshots are taken at the final day, and they will naturally reflect mid‑cycle states.

---

### How the Cycles Anchor the Generation Engine

- **Daily Simulation Clock** advances one day at a time.  
- At each tick, it evaluates which customers are due for an order (Customer Cycle), triggers replenishment (SKU Cycle), advances order statuses (Order Cycle), and processes payments/collections (Cash Cycle).  
- All events are written with `causation_id` and `correlation_id`, so an analyst can trace the entire journey of a single order from customer through payment.  
- The cyclic nature ensures that **no entity sits in isolation**: a rep visit may cause an order that causes a stockout that triggers a substitution that affects margin, while the customer’s credit used rises and later a payment attempt fails, leading to a collection visit, a promise, and eventual reactivation. These causal chains are what make the dataset suitable for causal ML and reinforcement learning.

---

### Concrete Guidelines for the Implementation Agent

1. **Model each cycle as a state machine** for its aggregate root (Customer, Order, SKU Inventory, Invoice).  
2. **Advance the simulation clock day‑by‑day**, updating each cycle’s state and emitting events.  
3. **Never artificially resolve an open process**; let it halt mid‑cycle if the simulation ends.  
4. **Enforce causal links**: every event that results from another must store the parent event’s ID.  
5. **Build projections only after the simulation** (or incrementally) to reflect the live snapshot.  
6. **Validate the cycles** by checking that:  
   - At least 5% of orders are not “Delivered” at the final date.  
   - At least 10% of invoices are overdue.  
   - Stockouts occur for C‑class items.  
   - Some customers churn and then reactivate.