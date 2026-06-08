# ODA — Project Context for Claude Code

## What This Is

ODA (Ordering Decisioning Agent) is a case study submission. It has two parts:

- **Part A (done):** Live AWS event-driven pipeline — DynamoDB Streams → Decision Lambda (3-factor scoring) → Action Lambda (routing + audit log). Deployed to `us-east-1` under account `3baset`.
- **Part B (in progress):** Business response, 1 slide, Loom walkthrough, evaluator access link.

GitHub repo: `https://github.com/3baset/ordering-payment-decision-engine`

---

## Current State

### AWS Stack — DEPLOYED

`OdaStack` is live in `us-east-1`. DLQs, CloudWatch widgets, and IAM are all deployed.

### Data — regenerate after cloning

Data files are **not committed** (gitignored). Use the Makefile:

```bash
make setup          # install dependencies
make sim            # ~8–12 min → simulation_engine/output/tables/
make sample         # 100k total rows per sample → data/sample_a/ + data/sample_b/
make seed-smoke     # smoke test: seed 100 orders
make seed           # full load
```

Or use the Streamlit dashboard → Simulation Engine tab → Sampler tab.

### Sampler — 100k total records (all tables)

`total_records_per_sample: 100000` caps **all joined tables combined** per sample,
not just orders. The sampler builds all joins first, then proportionally trims.

### Tests — all green (28/28)
```bash
make test   # or: pytest tests/
```

---

## Submission Checklist

### Technical

- [x] `cdk deploy` — DLQs + dashboard + IAM live
- [ ] `make sim` → `make sample` → `make seed` — regenerate data and load
- [ ] Verify end-to-end: seed 50 orders, watch CloudWatch, confirm action-log entries
- [ ] Evaluator credentials: `aws secretsmanager get-secret-value --secret-id oda-evaluator-credentials` → share via 1Password (7-day expiry)

### Part B Deliverables (highest evaluator weight)

- [ ] **1-page business response** — draft in `docs/Part_B_Growth_Lead_Response.md`. Add: decision distribution (~60% auto-approve / ~28% review / ~12% decline), credit loss reduction framing, rep capacity angle.
- [ ] **1 slide** — use `docs/architecture.svg` as the visual, three bullets, 3-minute pitch.
- [ ] **Loom walkthrough (5–8 min):**
  1. Open CloudWatch ODA-Pipeline dashboard → show invocations + IteratorAge widgets
  2. Run `make seed-smoke` → tail Decision Lambda logs
  3. Show an order going AUTO_APPROVE and one going MANUAL_REVIEW
  4. Switch to Streamlit Live Pipeline Test tab → select a record → send → watch decision appear
  5. Show the action-log entry for that order

---

## Key Files

| File | What it does |
|------|-------------|
| `lambdas/decision/handler.py` | 3-factor scoring (LTV 40% + Fraud 35% + Payment 25%) |
| `lambdas/action/handler.py` | Routes to FULFILLED / ESCALATED / REJECTED; writes audit log |
| `infra/oda_stack.py` | CDK stack definition (tables, Lambdas, DLQs, CloudWatch, IAM) |
| `scripts/seed.py` | Batch-writes Sample A Parquet → DynamoDB `oda-orders` |
| `Makefile` | One-command setup, sim, sample, test, seed, deploy |
| `sampler_dashboard.py` | Streamlit: Sampler · Simulation Engine · Live Pipeline Test tabs |
| `aws_pipeline_tab.py` | Live Pipeline Test tab module |
| `docs/architecture.svg` | System architecture diagram |
| `tests/` | 28 unit tests (run with `pytest tests/`) |
| `docs/Part_B_Growth_Lead_Response.md` | Draft Part B business response |
| `docs/claude-session.md` | Full build log (prompt → diff → findings) |

---

## Scoring Model Summary (for Part B conversations)

```
composite = 0.40 × ltv_score + 0.35 × (1 − fraud_score) + 0.25 × payment_score

ltv_score:      premium=1.0 · standard=0.6 · new=0.4 · at-risk=0.2 · churned=0.1
payment_score:  method_score × (1 − basket_risk_penalty)
  method:       credit=0.90 · bank_transfer=0.80 · cheque=0.65 · cod=0.50 · cash=0.45
  basket penalty: relative to customer's own avg_basket_90d (max 30% reduction at 5× avg)

≥0.70 → AUTO_APPROVE   ~60% of orders
0.40–0.69 → MANUAL_REVIEW  ~28%
<0.40 → DECLINE             ~12%
```

---

## Do Not

- Do not commit `claudedev_accessKeys.csv` — it is gitignored
- Do not commit anything in `data/` — Parquet files are gitignored (too large)
- Do not commit `simulation_engine/output/` — gitignored
- Do not run `cdk destroy` — evaluator needs the live stack
