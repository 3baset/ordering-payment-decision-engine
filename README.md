# MaxAB Growth Lead — Case Study

Synthetic FMCG wholesale data platform for the MaxAB Growth Lead Assessment.
Contains a full simulation engine, a config-driven data sampler, interactive
dashboards, and two pre-generated 100k-order holdout samples ready for
analysis.

---

## Repository Layout

```
maxab-case-study/
├── simulation_engine/          # Discrete-event simulation (SimPy + DuckDB + Polars)
│   ├── simulation_runner.py    # Entry point
│   ├── config/                 # YAML config + deterministic seeds
│   ├── engines/                # Domain logic (fraud, inventory, payment, etc.)
│   ├── generators/             # Bootstrap data (customers, SKUs, reps)
│   ├── processes/              # SimPy processes (ordering, fulfilment, invoicing…)
│   ├── projections/            # Event-store → Parquet table writers
│   ├── schemas/                # Pydantic event schemas
│   ├── store/                  # DuckDB event store + shared state
│   └── validators/             # Business-rule and KPI validators
│
├── data_sampler/               # Config-driven sampling module
│   ├── config.py               # Pydantic v2 config models
│   ├── filters.py              # Date-window, join, and size-limit filters
│   ├── sampler.py              # Orchestrator (stratified 50/50 split)
│   └── configs/last_90d.yaml   # Default: two 100k-order samples, last 90 days
│
├── data/                       # Pre-generated samples (git-tracked)
│   ├── sample_a/               # 100k orders + 9 linked tables
│   ├── sample_b/               # 100k orders + 9 linked tables (disjoint split)
│   └── reference/              # Static lookup tables (inventory, promos, cohorts)
│
├── sampler_dashboard.py        # Streamlit UI — configure, run, explore
├── wholesale_dashboard.html    # Business overview dashboard (standalone)
└── financial_fulfilment_assortment_dashboard.html  # Ops/finance dashboard
```

---

## Quick Start

### 1 — Install dependencies

```bash
pip install simpy==4.1.1 pydantic==2.7.1 polars==0.20.31 \
            faker==25.2.0 duckdb==0.10.3 pyarrow==16.1.0 \
            numpy==1.26.4 pyyaml==6.0.1 streamlit plotly
```

### 2 — Explore the pre-generated samples (no simulation needed)

Open the business dashboard:
```bash
open wholesale_dashboard.html
open financial_fulfilment_assortment_dashboard.html
```

Or launch the interactive Streamlit dashboard:
```bash
streamlit run sampler_dashboard.py
```

### 3 — Regenerate samples with different parameters

```bash
# CLI — uses data_sampler/configs/last_90d.yaml
python -m data_sampler data_sampler/configs/last_90d.yaml

# Or use the Streamlit sidebar to change target rows / date window / tolerances
streamlit run sampler_dashboard.py
```

### 4 — Re-run the full simulation (generates ~2 years of wholesale data)

```bash
cd simulation_engine
python simulation_runner.py          # writes output/tables/*.parquet
```

> Full run takes ~8–12 minutes and writes ~3 GB to `simulation_engine/output/`
> (excluded from git via `.gitignore`).

---

## Pre-Generated Sample Data

Both samples cover the **last 90 days** of the simulation window and are
**stratified by month × channel × order-status** so their distributions are
identical — they are disjoint halves of the same population, not random draws.

| Table | Sample A rows | Sample B rows | Description |
|---|---|---|---|
| `orders` | 100,000 | 100,000 | Core fact table |
| `order_lines` | ~451k | ~451k | SKU-level line items |
| `invoices` | ~94k | ~94k | Invoice events per order |
| `payments` | ~60k | ~60k | Payment events (linked via invoice) |
| `stockout_events` | ~398k | ~398k | Inventory shortage events (date-filtered first) |
| `credit_ledger` | ~456k | ~456k | Customer credit events |
| `customer_history` | ~1.2k | ~1.2k | Lifecycle state changes |
| `rep_performance` | ~810 | ~810 | Monthly rep KPIs |
| `customers` | ~5.3k | ~5.3k | Customer master |
| `rfm_scores` | ~66k | ~66k | Monthly RFM scores per customer |

**Reference tables** (written once to `data/reference/`):

| Table | Rows | Description |
|---|---|---|
| `inventory_snapshot` | 500 | Current stock levels per SKU |
| `monthly_customer_snapshot` | 91 | Monthly cohort aggregates |
| `promotion_roi` | 9 | Promotion performance summary |

Read any table with Polars:
```python
import polars as pl
orders = pl.read_parquet("data/sample_a/orders.parquet")
```

---

## Data Sampler — Config Reference

The sampler is driven by a YAML file validated by Pydantic v2.

```yaml
source_dir: simulation_engine/output/tables
output_dir: data
random_seed: 42

date_window:
  anchor: latest      # "latest" = max(orders.created_at); or "2024-06-30"
  days: 90

stratify_by: [month, channel, status]

target_rows: 100000   # cap per sample; null = use full ~50/50 split
tolerance: 0.10       # ±10%  →  90k–110k rows accepted

samples:
  - {name: sample_a, split: even}
  - {name: sample_b, split: odd}

tables:
  - {name: orders, filter: date_window, split_anchor: true}
  - {name: order_lines, join: {parent: orders, key: order_id}}
  - {name: invoices,    join: {parent: orders, key: order_id}}
  - {name: payments,    join: {parent: invoices, key: invoice_id}}   # two-hop
  - {name: stockout_events, join: {parent: orders, key: order_id},
     filter: date_window}
  # ... (see data_sampler/configs/last_90d.yaml for full list)
```

**Key rules enforced by Pydantic validators:**
- Exactly one table must have `split_anchor: true` (the stratification anchor).
- `limit_rows` and `limit_mb` are mutually exclusive.
- `static` tables cannot have a `join` or be `split_anchor`.
- Tables with both `filter: date_window` and a `join` apply the date filter
  first to reduce the full table before the join — important for event tables
  like `stockout_events` (3.6 M rows → 960 k last-90-day rows → ~400 k per sample).

---

## Simulation Engine — Architecture

The engine models a B2B wholesale marketplace over a configurable time window
using **discrete-event simulation** (SimPy) with an **event-sourced** DuckDB
store.

```
Generators  ──►  Bootstrap  ──►  SimPy Environment
 (customers,                       │
  SKUs, reps)                  Processes (run concurrently)
                                   │  customer_arrival_process
                                   │  customer_order_process
                                   │  order_fulfillment_process
                                   │  invoice_process
                                   │  collection_process
                                   │  inventory_monitor_process
                                   │  fraud_monitor_process
                                   │  rep_visit_process
                                   │  macro_process  (macro shocks, promos)
                                   ▼
                              DuckDB Event Store
                                   │
                              Projections  ──►  Parquet tables
                                   │  (orders, order_lines, invoices,
                                   │   payments, customers, rfm_scores,
                                   │   stockout_events, credit_ledger, …)
                                   ▼
                              Validators  ──►  Business-rule + KPI checks
```

Domain engines used by processes:

| Engine | Responsibility |
|---|---|
| `ordering_engine` | Basket construction, demand elasticity |
| `payment_engine` | Payment method selection, delay distribution |
| `inventory_engine` | Stock deduction, reorder triggers |
| `fraud_engine` | Fraud score assignment per order |
| `promotion_engine` | Discount application, ROI tracking |
| `elasticity_engine` | Price-sensitivity curves per segment |
| `affinity_engine` | Cross-sell / product affinity scores |

---

## Dashboards

### Streamlit Dashboard (`sampler_dashboard.py`)

Configure sampling parameters in the sidebar, run the sampler, and immediately
see:
- Manifest table (rows and file size per table)
- Per-sample KPIs: orders, GMV, avg order value, unique customers, high-fraud orders
- Charts: channel mix, order status donut, fraud-score histogram, payment method mix,
  monthly GMV trend, customer type breakdown
- Compare tab: side-by-side KPIs and distribution charts for Sample A vs B

```bash
streamlit run sampler_dashboard.py
```

### HTML Dashboards (standalone, no server needed)

| File | Content |
|---|---|
| `wholesale_dashboard.html` | Business overview: GMV, orders, channel mix, customer segments |
| `financial_fulfilment_assortment_dashboard.html` | Ops/finance: fulfilment rates, assortment depth, financial KPIs |

Open directly in any browser — no dependencies.

---

## Reference Documents

| File | Purpose |
|---|---|
| `Synthetic Wholesale Commerce Simulation Engine.md` | Original simulation design brief |
| `SIMULATION_V2_SPEC.md` | V2 enhancements spec |
| `Addendum_3_Enhanced_Architecture.md` | Architecture decisions and trade-offs |
| `FMCG_HORECA_Entity_Library_EGP.md` | Egyptian FMCG entity reference (products, pricing in EGP) |
| `DATA_VALIDATION_NOTES.md` | Synthetic-data realism audit and known gaps |
| `simulation_engine/DATA_ANALYST_GUIDE.md` | Guide for analysts querying the raw tables |
