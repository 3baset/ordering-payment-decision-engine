# ODA — Project Context for Claude Code

## What This Is

ODA (Ordering Decisioning Agent) is a case study submission. It has two parts:

- **Part A (done):** Live AWS event-driven pipeline — DynamoDB Streams → Decision Lambda (3-factor scoring) → Action Lambda (routing + audit log). Deployed to `us-east-1` under account `3baset`.
- **Part B (in progress):** Business response, 1 slide, Loom walkthrough, evaluator access link.

GitHub repo: `https://github.com/3baset/ordering-payment-decision-engine`

---

## Current State

### AWS Stack — DEPLOYED, needs one more `cdk deploy`

The stack (`OdaStack`) is live in `us-east-1`. The last code changes (DLQs, CloudWatch widgets, IAM fix) were committed and merged but **`cdk deploy` has not been run yet**. Until then:
- `oda-decision-dlq` and `oda-action-dlq` do not exist in AWS
- IteratorAge/Duration p99 widgets are not on the dashboard
- Evaluator IAM policy still has the unused S3 permission

```bash
cd infra && cdk deploy
```

### Data — needs regeneration

The simulation config changed (payment mix, AOV, growth model). The data in `data/` was removed from git. No sample files exist locally either. Before the Streamlit dashboard or seed script will work, regenerate:

```bash
# Step 1 — re-run simulation (~8–12 min, writes ~3 GB to simulation_engine/output/)
cd simulation_engine && python simulation_runner.py

# Step 2 — resample
cd .. && python -m data_sampler data_sampler/configs/last_90d.yaml

# Step 3 — re-seed pipeline (wait ≥30s after cdk deploy)
python scripts/seed.py --limit 100   # smoke test
python scripts/seed.py               # full load
```

### Tests — all green (28/28)
```bash
pytest tests/   # 18 decision + 10 action lambda tests
```

---

## Submission Checklist

### Technical (do first, before sharing with evaluator)

- [ ] `cd infra && cdk deploy` — picks up DLQs + dashboard + IAM fix
- [ ] Re-run simulation → resample → re-seed (see commands above)
- [ ] Verify end-to-end: seed 50 orders, watch CloudWatch, confirm action-log entries
- [ ] Generate evaluator credentials: `aws secretsmanager get-secret-value --secret-id oda-evaluator-credentials` → share via 1Password (7-day expiry)

### Part B Deliverables (highest evaluator weight)

- [ ] **1-page business response** — draft is in `docs/Part_B_Growth_Lead_Response.md`. Needs finalising with: decision distribution numbers (~60% auto-approve / ~28% review / ~12% decline), credit loss reduction framing, rep capacity angle.
- [ ] **1 slide** — one visual (decision funnel or architecture), three bullets, 3-minute pitch format.
- [ ] **Loom walkthrough (5–8 min)** — suggested flow:
  1. Open CloudWatch ODA-Pipeline dashboard → show invocations + IteratorAge widgets
  2. Run `python scripts/seed.py --limit 50` → tail Decision Lambda logs
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
| `sampler_dashboard.py` | Streamlit: sampler results tab + live pipeline test tab |
| `aws_pipeline_tab.py` | Live Pipeline Test tab module |
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
