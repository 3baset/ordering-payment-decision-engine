# MaxAB Simulation Data — Analyst Guide

A practical reference for exploring the synthetic Egyptian B2B wholesale dataset. Covers data model, table schemas, key joins, ready-to-run queries, and known caveats.

---

## Quick Start

### Prerequisites

```bash
pip install duckdb polars pandas
```

### Connect and explore

```python
import duckdb

con = duckdb.connect()          # in-memory; Parquet files queried directly
TABLES = "output/tables"        # adjust path as needed

# List all tables
import os
tables = [f.replace(".parquet","") for f in os.listdir(TABLES) if f.endswith(".parquet")]
print(tables)

# Preview any table
con.execute(f"SELECT * FROM '{TABLES}/orders.parquet' LIMIT 5").df()
```

### Or use DuckDB CLI

```bash
duckdb
> SELECT COUNT(*) FROM 'output/tables/orders.parquet';
> .read my_analysis.sql
```

---

## Dataset at a Glance

| Dimension | Value |
|-----------|-------|
| Simulation period | Jul 2022 – Jun 2024 (547 days active + 180-day bootstrap history) |
| Customers | 6,713 total (2,000 initial + 4,713 acquired during sim) |
| SKUs | 500 |
| Sales reps | ~45 (across 7 geographic areas) |
| Total orders | 931,661 |
| Order lines | 4,138,831 |
| Total events | 10,637,012 |
| Geography | Egypt — 7 areas (GCR, ALX, DLT, CNL, FAY, RED, UPP) |
| Currency | EGP |

**Data represents:** Egyptian B2B FMCG wholesale (food, beverages, personal care, household, horeca supply chains).

---

## Data Model

```
customers ──────────────┬──── orders ──────── order_lines
    │                   │         │
    │                   │         └──── invoices ──── payments
    │                   │                                 │
    │                   └──── credit_ledger ◄─────────────┘
    │
    ├──── customer_history          (lifecycle events)
    ├──── rfm_scores                (monthly RFM snapshots)
    └──── rep_performance           (via rep_id → orders)

order_lines ──── stockout_events   (via sku_id + order_id)
inventory_snapshot                 (point-in-time SKU stock)
monthly_customer_snapshot          (aggregate funnel counts)
promotion_roi                      (empty — not yet wired)
```

**Primary keys:** `customer_id`, `order_id`, `invoice_id`, `sku_id`, `rep_id`

---

## Table Reference

### `orders` — 931,661 rows

One row per order. Terminal status — each order appears once with its final state.

| Column | Type | Notes |
|--------|------|-------|
| `order_id` | VARCHAR | Primary key — format `ORD-XXXXXXXX` |
| `customer_id` | VARCHAR | FK → customers |
| `created_at` | TIMESTAMP | Order placement time |
| `status` | VARCHAR | See values below |
| `total_value` | DOUBLE | EGP; 26 rows have negative values — filter with `WHERE total_value > 0` |
| `channel` | VARCHAR | `direct`, `organic`, `app`, `rep` |
| `rep_id` | VARCHAR | Nullable — only set for rep-assisted orders |
| `fraud_score` | VARCHAR | Cast to FLOAT; range 0.0–1.0 |
| `promotion_id` | VARCHAR | Nullable |

**Status values:**

| Status | Count | % |
|--------|-------|---|
| `OrderDelivered` | 856,784 | 92.0% |
| `OrderReturned` | 43,345 | 4.7% |
| `OrderShipped` | 22,201 | 2.4% |
| `OrderCreated` | 4,790 | 0.5% |
| `OrderCancelled` | 4,541 | 0.5% |

**Channel split:**

| Channel | Count |
|---------|-------|
| `direct` | 361,774 (38.8%) |
| `organic` | 346,446 (37.2%) |
| `app` | 132,199 (14.2%) |
| `rep` | 91,242 (9.8%) |

---

### `order_lines` — 4,138,831 rows

One row per SKU per order. Join to `orders` on `order_id`.

| Column | Type | Notes |
|--------|------|-------|
| `order_id` | VARCHAR | FK → orders |
| `customer_id` | VARCHAR | Denormalized for convenience |
| `sku_id` | VARCHAR | FK → inventory_snapshot |
| `quantity` | BIGINT | Units ordered |
| `unit_price` | DOUBLE | EGP per unit |
| `line_total` | DOUBLE | `quantity × unit_price` |
| `demand_class` | VARCHAR | `A` (fast-moving), `B`, `C` (slow-moving) |

**Demand class split:** A: 48.7% · B: 38.5% · C: 12.8%

> **Caveat:** 1.0% of orders (9,613) have `total_value ≠ SUM(line_total)` due to order-level discounts not being propagated back to lines. For basket analysis use `line_total`; for revenue use `orders.total_value`.

---

### `customers` — 6,713 rows

One row per customer — latest state snapshot.

| Column | Type | Notes |
|--------|------|-------|
| `customer_id` | VARCHAR | Primary key |
| `created_at` | TIMESTAMP | Registration date |
| `name` | VARCHAR | Synthetic name |
| `segment` | VARCHAR | `premium`, `regular`, `low_volume` |
| `status` | VARCHAR | `active`, `inactive`, `dormant`, `churned` |
| `area_id` | VARCHAR | One of 7 Egypt areas |
| `customer_type` | VARCHAR | 12 HORECA/retail subtypes |
| `acquisition_channel` | VARCHAR | `rep_referral`, `digital`, `bootstrap` |
| `credit_limit` | VARCHAR | Cast to FLOAT; EGP |
| `payment_method` | VARCHAR | `cash`, `cheque`, `bank_transfer` |
| `risk_score` | VARCHAR | Cast to FLOAT; 0.0–1.0 |
| `rep_id` | VARCHAR | Assigned rep (nullable) |
| `digital_active` | VARCHAR | Cast to BOOL |

**Status breakdown:** active 40.1% · inactive 23.9% · churned 21.4% · dormant 14.6%

**Segments:** regular 47.3% · low_volume 39.0% · premium 13.7%

**Areas:** roughly balanced (~930–977 per area): CNL, DLT, GCR, FAY, RED, ALX, UPP

**Customer types (top 5):** RETAIL_minimarket · HORECA_restaurant_regular · HORECA_cafe_small · RETAIL_supermarket_mid · HORECA_bakery_small

---

### `customer_history` — 14,648 rows

Lifecycle event log — one row per state transition per customer.

| Column | Type | Notes |
|--------|------|-------|
| `customer_id` | VARCHAR | FK → customers |
| `event_type` | VARCHAR | See lifecycle events below |
| `timestamp` | TIMESTAMP | When the transition occurred |
| `segment` | VARCHAR | Segment at time of event |
| `days_without_order` | VARCHAR | Cast to INT; days since last order at transition |

**Lifecycle events:**

| Event | Count |
|-------|-------|
| `CustomerCreated` | 6,713 |
| `CustomerBecameInactive` | 4,047 |
| `CustomerBecameDormant` | 2,417 |
| `CustomerChurned` | 1,464 |
| `CustomerReactivated` | 7 |

---

### `rfm_scores` — 67,441 rows

Monthly RFM snapshot per customer. One row per customer per month.

| Column | Type | Notes |
|--------|------|-------|
| `customer_id` | VARCHAR | FK → customers |
| `month` | TIMESTAMP | First day of scoring month |
| `last_order_date` | TIMESTAMP | Most recent order before this month |
| `frequency` | UINTEGER | Orders placed in trailing 12 months |
| `monetary` | DOUBLE | GMV in trailing 12 months (EGP) |
| `recency_days` | BIGINT | Days since last order at month-end |
| `r_score` | VARCHAR | Cast to INT; 1–5 (5 = most recent) |
| `f_score` | VARCHAR | Cast to INT; 1–5 (5 = most frequent) |
| `m_score` | VARCHAR | Cast to INT; 1–5 (5 = highest GMV) |

**Date range:** Jul 2022 – Jun 2024 (18 monthly snapshots)

---

### `invoices` — 916,979 rows

One invoice per delivered order.

| Column | Type | Notes |
|--------|------|-------|
| `invoice_id` | VARCHAR | Primary key |
| `order_id` | VARCHAR | FK → orders |
| `customer_id` | VARCHAR | FK → customers |
| `timestamp` | TIMESTAMP | Invoice creation time |
| `amount` | DOUBLE | EGP |
| `due_date` | VARCHAR | Cast to DATE; invoice due date |
| `terms_days` | VARCHAR | Cast to INT; always 30 |

> Covers 98.4% of delivered orders. 30 orders are from bootstrap customers not in `customers.parquet` (C1 orphan issue).

---

### `payments` — 975,176 rows

Payment attempts — may have multiple rows per invoice (retries).

| Column | Type | Notes |
|--------|------|-------|
| `invoice_id` | VARCHAR | FK → invoices |
| `customer_id` | VARCHAR | FK → customers |
| `timestamp` | TIMESTAMP | Payment attempt time |
| `amount` | DOUBLE | EGP |
| `payment_method` | VARCHAR | `cash`, `cheque`, `bank_transfer`, NULL (failed) |
| `status` | VARCHAR | `paid` or `failed` |
| `attempt_number` | VARCHAR | Cast to INT; 1–3 |
| `reason` | VARCHAR | Failure reason (nullable) |

**Status:** paid 802,671 (82.3%) · failed 172,505 (17.7%)

---

### `credit_ledger` — 1,739,863 rows

Running credit balance per customer — every debit (order), credit (payment), and write-off.

| Column | Type | Notes |
|--------|------|-------|
| `customer_id` | VARCHAR | FK → customers |
| `event_type` | VARCHAR | `OrderCreated`, `PaymentCaptured`, `CreditWrittenOff` |
| `transaction_type` | VARCHAR | `debit`, `credit`, `writeoff` |
| `timestamp` | TIMESTAMP | Event time |
| `amount` | DOUBLE | Absolute amount (EGP) |
| `signed_amount` | DOUBLE | Negative for debits, positive for credits |
| `running_balance` | DOUBLE | Cumulative balance at this event |

---

### `inventory_snapshot` — 500 rows

Point-in-time (end of simulation) stock level per SKU.

| Column | Type | Notes |
|--------|------|-------|
| `sku_id` | VARCHAR | Primary key |
| `total_received` | BIGINT | Cumulative units received from suppliers |
| `total_reserved` | BIGINT | Cumulative units allocated to orders |
| `total_released` | BIGINT | **Always 0** — post-delivery release not tracked |
| `estimated_on_hand` | BIGINT | `total_received − total_reserved` (proxy for stock) |

> 8.4% of SKUs (42/500) have `estimated_on_hand ≤ 0` — in-stock rate 91.6%.

---

### `stockout_events` — 3,445,384 rows

One row per order line where requested quantity exceeded available stock.

| Column | Type | Notes |
|--------|------|-------|
| `sku_id` | VARCHAR | FK → inventory_snapshot |
| `order_id` | VARCHAR | FK → orders |
| `timestamp` | TIMESTAMP | When the stockout check ran |
| `requested_quantity` | VARCHAR | Cast to INT |
| `available_quantity` | VARCHAR | Cast to INT |
| `resolution` | VARCHAR | `substitute`, `backorder`, or `cancel_line` |

**Resolution split:** cancel_line 50% · substitute 30% · backorder 20%

> This table represents **partial-fill events**, not fully OOS events. 83% of order lines triggered a partial stockout during the sim. The end-of-run OOS rate (inventory_snapshot) is 8.4%. Do not use `COUNT(*) / order_line_count` as an OOS KPI.

---

### `rep_performance` — 810 rows

Monthly rep metrics — one row per rep per month.

| Column | Type | Notes |
|--------|------|-------|
| `rep_id` | VARCHAR | Primary key composite |
| `month` | TIMESTAMP | First day of month |
| `total_visits` | UINTEGER | Customer visits that month |
| `order_visits` | UINTEGER | Visits that resulted in an order |
| `gmv` | DOUBLE | EGP GMV attributed to this rep |

Derived: `order_visits / total_visits` = visit-to-order conversion rate (~51% overall).

---

### `monthly_customer_snapshot` — 80 rows

Aggregate funnel counts per month — not per-customer detail.

| Column | Type | Notes |
|--------|------|-------|
| `month` | TIMESTAMP | First day of month |
| `event_type` | VARCHAR | Lifecycle event type |
| `count` | UINTEGER | Number of customers who hit that event |

Use for top-level funnel charts. For cohort or per-customer analysis use `customer_history`.

---

### `promotion_roi` — 0 rows

Schema only — promotion redemption engine not yet wired. Columns: `promotion_id`, `total_gmv`, `total_discount`, `redemptions`, `roi`. Will populate in a future run.

---

## Key Joins

```sql
-- Orders with customer attributes
SELECT o.order_id, o.created_at, o.total_value, o.status, o.channel,
       c.segment, c.area_id, c.customer_type, c.status AS customer_status
FROM 'output/tables/orders.parquet' o
JOIN 'output/tables/customers.parquet' c ON o.customer_id = c.customer_id
WHERE o.total_value > 0;

-- Full order → invoice → payment chain
SELECT o.order_id, o.created_at, o.total_value,
       i.invoice_id, i.due_date::DATE AS due_date,
       p.status AS payment_status, p.timestamp AS paid_at,
       p.payment_method
FROM 'output/tables/orders.parquet' o
JOIN 'output/tables/invoices.parquet' i ON o.order_id = i.order_id
LEFT JOIN 'output/tables/payments.parquet' p
       ON i.invoice_id = p.invoice_id AND p.status = 'paid';

-- Order lines with SKU demand class
SELECT ol.order_id, ol.sku_id, ol.quantity, ol.line_total, ol.demand_class,
       o.created_at, o.channel
FROM 'output/tables/order_lines.parquet' ol
JOIN 'output/tables/orders.parquet' o ON ol.order_id = o.order_id;

-- RFM scores with current customer status
SELECT r.customer_id, r.month, r.r_score, r.f_score, r.m_score,
       r.recency_days, r.monetary, c.segment, c.status, c.area_id
FROM 'output/tables/rfm_scores.parquet' r
JOIN 'output/tables/customers.parquet' c ON r.customer_id = c.customer_id;
```

---

## Analysis Recipes

### 1. Monthly GMV trend

```sql
SELECT DATE_TRUNC('month', created_at) AS month,
       COUNT(*) AS order_count,
       ROUND(SUM(total_value) / 1e6, 2) AS gmv_million_egp,
       ROUND(AVG(total_value), 0) AS avg_order_value
FROM 'output/tables/orders.parquet'
WHERE status = 'OrderDelivered' AND total_value > 0
GROUP BY 1
ORDER BY 1;
```

### 2. Customer lifetime value by segment

```sql
SELECT c.segment,
       COUNT(DISTINCT o.customer_id) AS customers,
       ROUND(SUM(o.total_value) / COUNT(DISTINCT o.customer_id), 0) AS avg_clv_egp,
       ROUND(AVG(o.total_value), 0) AS avg_order_value,
       ROUND(COUNT(o.order_id) * 1.0 / COUNT(DISTINCT o.customer_id), 1) AS orders_per_customer
FROM 'output/tables/orders.parquet' o
JOIN 'output/tables/customers.parquet' c ON o.customer_id = c.customer_id
WHERE o.status = 'OrderDelivered' AND o.total_value > 0
GROUP BY c.segment
ORDER BY avg_clv_egp DESC;
```

### 3. Churn rate by cohort month

```sql
WITH first_order AS (
    SELECT customer_id, DATE_TRUNC('month', MIN(created_at)) AS cohort_month
    FROM 'output/tables/orders.parquet'
    WHERE status = 'OrderDelivered'
    GROUP BY customer_id
),
churn AS (
    SELECT customer_id, DATE_TRUNC('month', timestamp) AS churn_month
    FROM 'output/tables/customer_history.parquet'
    WHERE event_type = 'CustomerChurned'
)
SELECT f.cohort_month,
       COUNT(f.customer_id) AS cohort_size,
       COUNT(ch.customer_id) AS churned,
       ROUND(COUNT(ch.customer_id) * 100.0 / COUNT(f.customer_id), 1) AS churn_pct
FROM first_order f
LEFT JOIN churn ch ON f.customer_id = ch.customer_id
GROUP BY f.cohort_month
ORDER BY f.cohort_month;
```

### 4. DSO (Days Sales Outstanding)

```sql
SELECT
    ROUND(AVG(
        DATEDIFF('day', i.timestamp, p.timestamp)
    ), 1) AS avg_dso_days,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY DATEDIFF('day', i.timestamp, p.timestamp)) AS median_dso,
    PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY DATEDIFF('day', i.timestamp, p.timestamp)) AS p90_dso
FROM 'output/tables/invoices.parquet' i
JOIN 'output/tables/payments.parquet' p ON i.invoice_id = p.invoice_id
WHERE p.status = 'paid';
```

### 5. Rep leaderboard (last 6 months of simulation)

```sql
SELECT rep_id,
       SUM(total_visits) AS visits,
       SUM(order_visits) AS orders_from_visits,
       ROUND(SUM(order_visits) * 100.0 / SUM(total_visits), 1) AS conversion_pct,
       ROUND(SUM(gmv) / 1e6, 2) AS gmv_million_egp
FROM 'output/tables/rep_performance.parquet'
WHERE month >= '2024-01-01'
GROUP BY rep_id
ORDER BY gmv_million_egp DESC
LIMIT 10;
```

### 6. SKU stockout frequency

```sql
SELECT sku_id,
       COUNT(*) AS stockout_events,
       SUM(CASE WHEN resolution = 'cancel_line' THEN 1 ELSE 0 END) AS cancellations,
       SUM(CASE WHEN resolution = 'substitute' THEN 1 ELSE 0 END) AS substitutes,
       SUM(CASE WHEN resolution = 'backorder' THEN 1 ELSE 0 END) AS backorders
FROM 'output/tables/stockout_events.parquet'
GROUP BY sku_id
ORDER BY stockout_events DESC
LIMIT 20;
```

### 7. Payment method mix by area

```sql
SELECT c.area_id, p.payment_method,
       COUNT(*) AS payments,
       ROUND(SUM(p.amount) / 1e6, 2) AS total_million_egp
FROM 'output/tables/payments.parquet' p
JOIN 'output/tables/customers.parquet' c ON p.customer_id = c.customer_id
WHERE p.status = 'paid'
GROUP BY c.area_id, p.payment_method
ORDER BY c.area_id, total_million_egp DESC;
```

### 8. RFM champion customers (latest month)

```sql
SELECT r.customer_id, c.name, c.segment, c.area_id, c.customer_type,
       r.r_score::INT AS r, r.f_score::INT AS f, r.m_score::INT AS m,
       r.monetary AS trailing_12m_gmv,
       r.recency_days
FROM 'output/tables/rfm_scores.parquet' r
JOIN 'output/tables/customers.parquet' c ON r.customer_id = c.customer_id
WHERE r.month = (SELECT MAX(month) FROM 'output/tables/rfm_scores.parquet')
  AND r.r_score::INT >= 4
  AND r.f_score::INT >= 4
  AND r.m_score::INT >= 4
ORDER BY r.monetary DESC;
```

### 9. Credit utilization per customer

```sql
SELECT cl.customer_id,
       c.segment,
       c.credit_limit::FLOAT AS credit_limit,
       MIN(cl.running_balance) AS lowest_balance,
       MAX(cl.running_balance) AS peak_balance,
       LAST(cl.running_balance ORDER BY cl.timestamp) AS current_balance,
       ROUND(
           (c.credit_limit::FLOAT - LAST(cl.running_balance ORDER BY cl.timestamp))
           / NULLIF(c.credit_limit::FLOAT, 0) * 100, 1
       ) AS utilization_pct
FROM 'output/tables/credit_ledger.parquet' cl
JOIN 'output/tables/customers.parquet' c ON cl.customer_id = c.customer_id
GROUP BY cl.customer_id, c.segment, c.credit_limit
ORDER BY utilization_pct DESC
LIMIT 20;
```

### 10. Basket analysis — top SKU pairs

```sql
WITH baskets AS (
    SELECT order_id, LIST(sku_id ORDER BY sku_id) AS skus
    FROM 'output/tables/order_lines.parquet'
    GROUP BY order_id
    HAVING COUNT(*) >= 2
)
SELECT a.sku_id AS sku_a, b.sku_id AS sku_b, COUNT(*) AS co_occurrences
FROM baskets,
     UNNEST(skus) AS t(sku_id) AS a,
     UNNEST(skus) AS t(sku_id) AS b
WHERE a.sku_id < b.sku_id
GROUP BY sku_a, sku_b
ORDER BY co_occurrences DESC
LIMIT 20;
```

---

## Known Caveats

| Issue | Impact | Workaround |
|-------|--------|------------|
| 26 orders with negative `total_value` | Revenue totals slightly off | Always filter `WHERE total_value > 0` on `orders` |
| 1.0% line total mismatch (9,613 orders) | Discount not propagated to lines | Use `orders.total_value` for revenue; `order_lines.line_total` for basket composition only |
| 30 orphan customer IDs | Breaks customer joins for those orders | Use LEFT JOIN or pre-filter: `WHERE customer_id IN (SELECT customer_id FROM customers)` |
| `total_released = 0` in inventory_snapshot | Cannot compute true available stock from snapshot alone | Use `estimated_on_hand = total_received − total_reserved` as a proxy |
| VARCHAR fields that should be numeric | Type errors if cast is skipped | Always cast: `credit_limit::FLOAT`, `fraud_score::FLOAT`, `risk_score::FLOAT`, `r_score::INT`, `requested_quantity::INT`, `due_date::DATE` |
| `promotion_roi` is empty | No promotion analysis possible | Skip this table; planned for a future run |
| 83% of order lines have a stockout event | Looks alarming but is partial-fill, not fully OOS | End-of-run OOS rate is 8.4% — use `inventory_snapshot.estimated_on_hand ≤ 0` for OOS analysis |
| Bootstrap orders (Jul 2022 – Jan 2023) | Historical seed data, not simulation-generated | Filter `WHERE created_at >= '2023-01-01'` for simulation-period-only analysis |
| 21 customers with negative credit balance | Rare race condition | Filter `WHERE running_balance >= 0` in credit analysis if needed |

---

## Suggested Analytical Questions

**Customer & Churn**
- Which customer segments churn fastest? Does acquisition channel predict churn?
- Can you build a 30-day churn early-warning model from RFM + lifecycle signals?
- What's the reactivation rate after dormancy? What triggers it?

**Revenue & Growth**
- What is the true LTV distribution by segment × area?
- Which channel (direct / app / rep / organic) produces highest LTV customers?
- How does AOV evolve over a customer's lifetime?

**Credit & Payments**
- Which customer attributes predict payment failure?
- What is the DSO distribution by segment, area, and payment method?
- Which customers are near their credit limit? Who has unused capacity?

**Inventory & Supply**
- Which SKUs have the most cancellations due to stockout? Which have substitutions?
- Is there a relationship between demand class (A/B/C) and stockout resolution type?
- Which SKUs should have higher reorder points?

**Rep Performance**
- Which reps have the highest visit-to-order conversion AND highest AOV?
- Is there a rep assignment effect on churn — do customers with active reps churn less?
- Which geographic areas are under-served (high customers per rep)?

---

## File Locations

```
simulation_engine/
├── output/
│   ├── tables/                  ← all 13 Parquet tables
│   │   ├── orders.parquet
│   │   ├── order_lines.parquet
│   │   ├── customers.parquet
│   │   ├── customer_history.parquet
│   │   ├── rfm_scores.parquet
│   │   ├── invoices.parquet
│   │   ├── payments.parquet
│   │   ├── credit_ledger.parquet
│   │   ├── inventory_snapshot.parquet
│   │   ├── stockout_events.parquet
│   │   ├── rep_performance.parquet
│   │   ├── monthly_customer_snapshot.parquet
│   │   └── promotion_roi.parquet
│   ├── event_store.duckdb       ← raw event store (10.6M events)
│   └── DATA_QUALITY_REPORT.md  ← full quality assessment + KPI scorecard
└── DATA_ANALYST_GUIDE.md       ← this file
```

To query the raw event store directly (advanced):

```python
import duckdb
con = duckdb.connect("output/event_store.duckdb", read_only=True)
con.execute("DESCRIBE event_store").df()
# event_type, aggregate_id, timestamp, payload (JSON), causation_id, correlation_id
```

The Parquet tables are projections from the event store — use them for analysis. Use the event store only if you need event sequencing, causation chains, or events not projected to a table.
