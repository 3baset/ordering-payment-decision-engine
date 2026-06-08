# ODA — Ordering Decisioning Agent

Synthetic Egyptian FMCG wholesale data platform with a live AWS event-driven ordering
decisioning pipeline. Includes a full simulation engine, config-driven data sampler,
interactive dashboards, and two pre-generated 100k-order holdout samples.

---

## Contents

- [What's In This Repo](#whats-in-this-repo)
- [Quick Start](#quick-start)
  - [Path 1 — Explore the pre-generated data (no setup)](#path-1--explore-the-pre-generated-data-no-setup)
  - [Path 2 — Run the Streamlit dashboard locally](#path-2--run-the-streamlit-dashboard-locally)
  - [Path 3 — Test the live AWS pipeline](#path-3--test-the-live-aws-pipeline)
- [Repository Layout](#repository-layout)
- [AWS Pipeline (Part A)](#aws-pipeline-part-a)
- [Simulation Engine](#simulation-engine)
- [Data Sampler](#data-sampler)
- [Dashboards](#dashboards)
- [Cost & Access](#cost--access)
- [Reference Docs](#reference-docs)

---

## What's In This Repo

| Layer | Purpose |
|-------|---------|
| `simulation_engine/` | 547-day discrete-event simulation → 40+ GB of synthetic wholesale events |
| `data_sampler/` | Config-driven stratified sampling → two disjoint 100k-order holdout samples |
| `data/` | Pre-generated samples (git-tracked, ready to use) |
| `lambdas/` | Decision Lambda (3-factor scoring) + Action Lambda (routing + audit log) |
| `infra/` | AWS CDK stack — DynamoDB, Lambdas, SQS DLQs, CloudWatch, Secrets Manager |
| `scripts/` | Seed script to load Sample A into live DynamoDB |
| `tests/` | 28 unit tests (Decision Lambda scoring + Action Lambda routing) |
| `sampler_dashboard.py` | Streamlit: configure/run sampler + live pipeline test tab |
| `*.html` | Standalone business + ops dashboards (no server required) |

---

## Quick Start

### Path 1 — Explore the pre-generated data (no setup)

Open the standalone HTML dashboards directly in any browser:

```bash
open wholesale_dashboard.html
open financial_fulfilment_assortment_dashboard.html
```

Or read the Parquet files directly with Python:

```python
import polars as pl
orders = pl.read_parquet("data/sample_a/orders.parquet")
print(orders.shape)   # (100000, ...)
```

### Path 2 — Run the Streamlit dashboard locally

```bash
pip install polars plotly streamlit pyyaml boto3 pyarrow
streamlit run sampler_dashboard.py
```

The dashboard has two tabs:
- **Sampler Results** — configure sampling params, run, and inspect KPIs / charts for each sample
- **Live Pipeline Test** — select a record from sample data, send it to the live AWS pipeline, and watch the Decision + Action Lambdas process it in real time

### Path 3 — Test the live AWS pipeline

Prerequisites: AWS credentials configured (`aws configure`) with the evaluator access keys.

1. Retrieve the evaluator credentials from 1Password (evaluator link shared separately).
2. Configure AWS CLI: `aws configure --profile oda-evaluator`
3. Run the Streamlit dashboard and switch to the **Live Pipeline Test** tab:

```bash
streamlit run sampler_dashboard.py
```

Or seed a batch into the pipeline and watch CloudWatch:

```bash
# Seed the first 100 orders (smoke test)
python scripts/seed.py --limit 100

# Watch Decision Lambda output
aws logs tail /aws/lambda/oda-decision --follow

# Watch Action Lambda output
aws logs tail /aws/lambda/oda-action --follow
```

---

## Repository Layout

```
ordering-decisioning-agent/
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
├── lambdas/
│   ├── decision/handler.py     # 3-factor composite scoring (LTV + Fraud + Payment)
│   └── action/handler.py       # Downstream routing (FULFILLED / ESCALATED / REJECTED)
│
├── infra/
│   ├── oda_stack.py            # CDK stack (DynamoDB, Lambdas, SQS DLQs, CloudWatch)
│   └── app.py                  # CDK entry point
│
├── scripts/
│   ├── seed.py                 # Load Sample A Parquet → DynamoDB (batch write)
│   └── teardown.py             # Empty tables without destroying the stack
│
├── tests/
│   ├── test_decision_lambda.py # 18 unit tests — scoring logic
│   └── test_action_lambda.py   # 10 unit tests — routing logic
│
├── docs/
│   ├── cost-estimate.md        # Free Tier breakdown
│   └── iam-setup.md            # Evaluator credential sharing via 1Password
│
├── sampler_dashboard.py        # Streamlit UI — sampler + live pipeline test tab
├── aws_pipeline_tab.py         # Live Pipeline Test tab module
├── wholesale_dashboard.html    # Business overview dashboard (standalone)
└── financial_fulfilment_assortment_dashboard.html  # Ops/finance dashboard
```

---

## AWS Pipeline (Part A)

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  Seed Script                                                         │
│  scripts/seed.py → 100k orders (Parquet → DynamoDB)                │
└───────────────────┬─────────────────────────────────────────────────┘
                    │ BatchWriteItem (INSERT)
                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│  DynamoDB  oda-orders                                                │
│  Streams: NEW_AND_OLD_IMAGES                                        │
└──────┬────────────────────────────────────────────────────────────┘
       │                                       │
  FilterCriteria:                         FilterCriteria:
  eventName = INSERT                      eventName = MODIFY
       │                                       │
       ▼                                       ▼
┌─────────────────┐    on_failure       ┌─────────────────┐    on_failure
│ Decision Lambda │ ──► oda-decision-dlq │  Action Lambda  │ ──► oda-action-dlq
│ oda-decision    │                     │  oda-action     │
│                 │                     │                 │
│ 3-factor score: │                     │  AUTO_APPROVE → │
│  LTV   (×0.40) │                     │    FULFILLED    │
│  Fraud (×0.35) │                     │  MANUAL_REVIEW →│
│  Payment(×0.25)│                     │    ESCALATED    │
│                 │                     │  DECLINE →      │
│ ≥0.70 APPROVE  │                     │    REJECTED     │
│ ≥0.40 REVIEW   │                     │                 │
│ <0.40 DECLINE  │                     │                 │
└────────┬────────┘                     └────────┬────────┘
         │ UpdateItem (decision + scores)         │ UpdateItem + PutItem
         ▼                                        ▼
  oda-orders (decision written back)       oda-action-log (audit trail)
```

### Decision Scoring Model

| Factor | Weight | Values | Signal |
|--------|--------|--------|--------|
| Customer LTV tier | 40% | premium=1.0 · standard=0.6 · new=0.4 · at-risk=0.2 · churned=0.1 | RFM segment |
| Fraud risk (inverted) | 35% | `1 − fraud_score` where fraud_score ∈ [0,1] | Fraud engine |
| Payment method × basket | 25% | credit=0.90 · bank_transfer=0.80 · cheque=0.65 · cod=0.50 · cash=0.45 | Method + relative basket deviation |

**Basket penalty** — relative to each customer's own 90-day average basket, not an absolute threshold:

```
basket_deviation = max(basket / avg_basket_90d − 1.0, 0.0)
basket_risk_penalty = min(basket_deviation / 4.0, 1.0) × 0.30
payment_score = method_score × (1.0 − basket_risk_penalty)
```

A 100k EGP order from a premium hotel (avg basket 80k) is low-risk. The same 100k order from a minimarket (avg basket 3k) is flagged as anomalous.

**Expected decision distribution:** ~60% AUTO_APPROVE · ~28% MANUAL_REVIEW · ~12% DECLINE

### Deploy

Prerequisites: AWS CLI, Node.js 20+, Python 3.11+.

```bash
npm install -g aws-cdk
pip install aws-cdk-lib constructs boto3 pyarrow

cd infra
cdk bootstrap          # first time only, per account/region
cdk diff               # preview changes
cdk deploy             # deploys OdaStack
```

### Seed & Verify

```bash
# Wait ≥30s after cdk deploy before seeding (stream iterator warm-up)
python scripts/seed.py --limit 100    # smoke test
python scripts/seed.py                # full load (~100k orders)

# Verify processing
aws logs tail /aws/lambda/oda-decision --follow
aws logs tail /aws/lambda/oda-action --follow

# Check a specific order
aws dynamodb get-item \
  --table-name oda-orders \
  --key '{"order_id": {"S": "ORD-XXXXXXXX"}}' \
  --projection-expression "order_id, decision, decision_score, post_decision_action"

# Count action log entries
aws dynamodb scan --table-name oda-action-log --select COUNT
```

### Observability

- **CloudWatch Dashboard** `ODA-Pipeline` — Lambda invocations, errors, IteratorAge p99, Duration p99
- **SQS DLQs** — `oda-decision-dlq` and `oda-action-dlq` capture poison-pill events after 2 retries
- **X-Ray tracing** — distributed trace visualization for both Lambdas
- **Structured JSON logs** — every decision and action emits `event`, `order_id`, `outcome`, score components

View the dashboard: AWS Console → CloudWatch → Dashboards → `ODA-Pipeline`

### Teardown

```bash
python scripts/teardown.py   # empty tables, keep stack (evaluators can re-seed)
cd infra && cdk destroy       # full teardown
```

---

## Simulation Engine

The engine models a B2B wholesale marketplace over 547 days (Jan 2023 – Jun 2024)
using **discrete-event simulation** (SimPy) with an **event-sourced** DuckDB store.

Starts with 20 customers. New customer acquisition follows a boost-decay model
(launch burst decays exponentially to steady state over ~90 days), then slow
long-run growth.

```
Generators  ──►  Bootstrap  ──►  SimPy Environment
 (customers,                       │
  SKUs, reps)                  Processes (run concurrently)
                                   │  customer_arrival_process  (boost-decay Poisson)
                                   │  customer_order_process    (lognormal baskets)
                                   │  order_fulfillment_process
                                   │  invoice_process
                                   │  collection_process
                                   │  inventory_monitor_process
                                   │  fraud_monitor_process
                                   │  rep_visit_process
                                   │  macro_process             (inflation, Ramadan, promos)
                                   ▼
                              DuckDB Event Store
                                   │
                              Projections  ──►  Parquet tables
                                   ▼
                              Validators  ──►  Business-rule + KPI checks
```

Payment method distribution (after calibration): ~75% cash · ~17% credit · ~7% cheque

Re-run the simulation (takes 8–12 min, writes ~3 GB):
```bash
cd simulation_engine
python simulation_runner.py          # writes output/tables/*.parquet
```

---

## Data Sampler

Config-driven stratified sampling from the simulation output into two disjoint holdout samples.

Both samples cover the **last 90 days** of the simulation and are stratified by
`month × channel × order-status` — they are disjoint halves of the same population.

| Table | Sample A rows | Sample B rows | Description |
|-------|--------------|--------------|-------------|
| `orders` | 100,000 | 100,000 | Core fact table |
| `order_lines` | ~451k | ~451k | SKU-level line items |
| `invoices` | ~94k | ~94k | Invoice events |
| `payments` | ~60k | ~60k | Payment events |
| `stockout_events` | ~398k | ~398k | Inventory shortage events |
| `credit_ledger` | ~456k | ~456k | Customer credit events |
| `customer_history` | ~1.2k | ~1.2k | Lifecycle state changes |
| `rep_performance` | ~810 | ~810 | Monthly rep KPIs |
| `customers` | ~5.3k | ~5.3k | Customer master |
| `rfm_scores` | ~66k | ~66k | Monthly RFM scores |

Regenerate samples with different parameters:
```bash
# CLI
python -m data_sampler data_sampler/configs/last_90d.yaml

# Or use the Streamlit sidebar
streamlit run sampler_dashboard.py
```

---

## Dashboards

### Streamlit Dashboard

```bash
streamlit run sampler_dashboard.py
```

Two tabs:
- **Sampler Results** — manifest, per-sample KPIs, channel mix, fraud distribution, payment method mix, monthly GMV trend, side-by-side A vs B compare
- **Live Pipeline Test** — filter sample records, select one, send to live DynamoDB, watch Decision + Action Lambda results appear in real time

Requires AWS credentials configured to use the Live Pipeline Test tab (same profile as `cdk deploy`).

### HTML Dashboards (no server required)

| File | Content |
|------|---------|
| `wholesale_dashboard.html` | Business overview: GMV, orders, channel mix, customer segments |
| `financial_fulfilment_assortment_dashboard.html` | Ops/finance: fulfilment rates, assortment depth, financial KPIs |

---

## Cost & Access

**Estimated cost: $0–$0.10** (within AWS Free Tier for the evaluation period).

| Resource | Billing | Notes |
|----------|---------|-------|
| DynamoDB (2 tables) | Pay-per-request | 100k writes + ~100k reads ≈ $0.01–$0.04 |
| Lambda (2 functions) | Per invocation | 100k invocations well within Free Tier (1M/month) |
| SQS DLQs | Per message | Zero messages expected in a clean run |
| CloudWatch | Free tier | First 3 dashboards free; alarms within 10-alarm free tier |
| Secrets Manager | $0.40/secret/month | `oda-evaluator-credentials` — only cost in the stack |

See [`docs/cost-estimate.md`](docs/cost-estimate.md) for the full breakdown.

**Evaluator access:** read-only IAM credentials are stored in AWS Secrets Manager as `oda-evaluator-credentials`. See [`docs/iam-setup.md`](docs/iam-setup.md) for retrieval instructions. Credentials shared via 1Password (link sent separately).

---

## Reference Docs

| File | Purpose |
|------|---------|
| `infra/README.md` | AWS pipeline deploy guide, architecture detail, observability |
| `docs/cost-estimate.md` | Free Tier breakdown per resource |
| `docs/iam-setup.md` | Evaluator credential sharing via 1Password |
| `docs/Growth_Lead_Assessment_Brief.pdf` | Original case study brief |
| `docs/claude-session.md` | Full Claude Code prompt log, diffs, and live-deploy findings |
| `docs/Synthetic Wholesale Commerce Simulation Engine.md` | Original simulation design brief |
| `docs/SIMULATION_V2_SPEC.md` | V2 enhancements spec |
| `docs/Addendum_3_Enhanced_Architecture.md` | Architecture decisions and trade-offs |
| `docs/FMCG_HORECA_Entity_Library_EGP.md` | Egyptian FMCG entity reference (products, pricing in EGP) |
| `docs/DATA_VALIDATION_NOTES.md` | Synthetic-data realism audit and known gaps |
| `simulation_engine/DATA_ANALYST_GUIDE.md` | Guide for analysts querying the raw tables |
