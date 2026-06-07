# ODA — Ordering Decisioning Agent

An AWS-native, event-driven order decisioning system. Built end-to-end with Claude Code (Sonnet 4.6) — see [`claude-session.md`](../claude-session.md) for the full prompt log and reflection.

---

## Architecture

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
       │                                  decision EXISTS
       ▼                                  post_decision_action NOT EXISTS
┌─────────────────┐                            │
│ Decision Lambda │                            ▼
│ oda-decision    │                   ┌─────────────────┐
│                 │                   │  Action Lambda  │
│ 3-factor score: │                   │  oda-action     │
│  LTV  (×0.40)  │                   │                 │
│  Fraud (×0.35) │                   │  AUTO_APPROVE → │
│  Payment(×0.25)│                   │    FULFILLED    │
│                 │                   │  MANUAL_REVIEW →│
│ ≥0.70 APPROVE  │                   │    ESCALATED    │
│ ≥0.40 REVIEW   │                   │  DECLINE →      │
│ <0.40 DECLINE  │                   │    REJECTED     │
└────────┬────────┘                   └────────┬────────┘
         │ UpdateItem (decision +              │ UpdateItem (post_decision_action)
         │ lineage fields)                     │ PutItem (action log)
         ▼                                     ▼
  oda-orders                           oda-action-log
  (decision written back)              (audit trail)
```

**Why this design:**
- **DynamoDB** for storage: native Streams → Lambda (zero polling), Free Tier covers 100k records, no servers.
- **Same stream, two event sources**: FilterCriteria at source means zero extra services (no EventBridge, no SNS). The Action Lambda ESM filters on `eventName=MODIFY`; loop prevention is code-level (`ConditionExpression="attribute_not_exists(post_decision_action)"` on UpdateItem). Filtering on DynamoDB NewImage attribute existence (`{exists:true}`) in Lambda ESM silently drops all records — a live-deploy finding documented in `claude-session.md`.
- **Denormalised seed records**: customer segment, payment method, and RFM scores are embedded in each order so the Decision Lambda scores without additional lookups (no cold join latency).

---

## Decision Logic

The Decision Lambda applies a weighted composite of 3 independent factors:

| Factor | Weight | Source | Signal |
|--------|--------|--------|--------|
| Customer LTV tier | 40% | `customer_segment` (RFM) | premium=1.0, standard=0.6, at-risk=0.2 |
| Fraud risk (inverted) | 35% | `fraud_score` [0,1] | 1 − fraud_score |
| Payment method × basket | 25% | `payment_method` + `total_amount` | credit=1.0, cod=0.5; penalised for large baskets |

**Outcome thresholds:** `≥0.70 → AUTO_APPROVE` · `0.40–0.69 → MANUAL_REVIEW` · `<0.40 → DECLINE`

Full lineage written back: `decision`, `decision_at`, `decision_score`, `ltv_score`, `fraud_score`, `payment_score`, `model_version`.

---

## Prerequisites

- AWS CLI configured (`aws configure`) with a profile that has AdministratorAccess
- Node.js 20–24 (CDK CLI uses Node internally)
- Python 3.11+

```bash
npm install -g aws-cdk
pip install aws-cdk-lib constructs boto3 pyarrow
```

---

## Deploy

```bash
cd infra

# Bootstrap CDK (first time only per account/region)
cdk bootstrap

# Preview changes
cdk diff

# Deploy
cdk deploy
```

Outputs after deploy:
- `OrdersTableName`, `ActionLogTableName`
- `DecisionLambdaArn`, `ActionLambdaArn`
- `EvaluatorSecretArn`
- `DashboardUrl`

---

## Seed (Load 100k Orders)

```bash
# Full load (~100k orders from Sample A)
python scripts/seed.py

# Smoke test — first 100 orders only
python scripts/seed.py --limit 100

# Dry run — inspect one item, no writes
python scripts/seed.py --dry-run --limit 1
```

After seeding, DynamoDB Streams will fire and the Lambda chain will run automatically.

---

## Verify End-to-End

```bash
# Tail Decision Lambda logs
aws logs tail /aws/lambda/oda-decision --follow

# Tail Action Lambda logs
aws logs tail /aws/lambda/oda-action --follow

# Query decisions table (check one order)
aws dynamodb get-item \
  --table-name oda-orders \
  --key '{"order_id": {"S": "ORD-XXXXXXXX"}}' \
  --projection-expression "order_id, decision, post_decision_action, decision_score"

# Count action log records
aws dynamodb scan \
  --table-name oda-action-log \
  --select COUNT
```

---

## Observability

- **CloudWatch Dashboard**: `ODA-Pipeline` — Lambda invocations and errors per 5 min
- **X-Ray tracing**: enabled on both Lambdas for distributed trace visualization
- **Structured JSON logs**: every decision and action emits a structured event (`event`, `order_id`, `outcome`, score components)

View the dashboard: AWS Console → CloudWatch → Dashboards → `ODA-Pipeline`

---

## Teardown

```bash
# Empty tables (keep stack alive — evaluators can re-seed)
python scripts/teardown.py

# Full destroy (removes all resources)
cd infra && cdk destroy
```

---

## Cost Envelope

See [`docs/cost-estimate.md`](docs/cost-estimate.md). **Estimated: $0–$0.10** (well within Free Tier).

---

## Evaluator Access

See [`docs/iam-setup.md`](docs/iam-setup.md) for instructions on retrieving the read-only IAM credentials from Secrets Manager and sharing via 1Password.

---

## Project Structure

```
infra/
  app.py              CDK entry point
  oda_stack.py        Full stack definition (tables, Lambdas, IAM, CloudWatch)
  cdk.json

lambdas/
  decision/handler.py 3-factor decision scoring
  action/handler.py   Downstream routing and action logging

scripts/
  seed.py             Load Sample A Parquet → DynamoDB
  teardown.py         Empty tables without destroying stack

tests/
  test_decision_lambda.py  14 unit tests for scoring logic

docs/
  cost-estimate.md    Free Tier breakdown
  iam-setup.md        Evaluator credential sharing via 1Password
  architecture.png    (generated separately)

claude-session.md     Prompt log, diffs, reflections
```

---

## What I'd Do Differently at Scale

1. **Dead-letter queues (SQS DLQ)** on both Lambda event sources — currently a poison-pill record retries 2× then is silently dropped.
2. **SSM Parameter Store** for scoring weights — currently hardcoded in the Lambda; tuning requires a redeploy.
3. **DynamoDB Streams → Kinesis Firehose → S3** for the action log at scale — DynamoDB tables work fine for 100k records but become expensive at 10M+.
4. **Step Functions** if the chain grows beyond 2 stages — cleaner state visibility and retry semantics than chained Streams.
