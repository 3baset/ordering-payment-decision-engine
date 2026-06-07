# Claude Code Session Log

## How This Was Built

This project was built end-to-end using Claude Code (Sonnet 4.6) as the primary engineering tool. The approach was to give Claude Code a structured sprint plan, then drive implementation through a sequence of focused prompts — each scoped to one layer of the stack (IaC, Lambda, seed, observability). Claude Code's output was reviewed in each round and iterated before moving to the next layer.

---

## Prompt Log

### Round 1 — Sprint Planning

**Prompt:** `/sprint-planning next steps for part a`

**What happened:**
Claude explored the repo, read the simulation engine and data sampler code, parsed the Growth Lead Assessment Brief PDF, and produced a 6-day sprint plan covering: CDK stack, seed script, Decision Lambda, Action Lambda, IAM evaluator setup, observability, and README. The user refined the plan with three specific additions:
1. Use the same DynamoDB Stream (with `FilterCriteria`) instead of EventBridge for the Action Lambda trigger
2. Add `claude-session.md` as an evaluator-facing prompt log
3. Add IAM evaluator user + Secrets Manager output in CDK

**Key decisions settled in this round:**
- Storage: DynamoDB (native Streams, Free Tier, event-native)
- IaC: AWS CDK (Python)
- 3 scoring factors: LTV tier (0.40) + fraud risk inverted (0.35) + payment method × basket size (0.25)
- Loop prevention: `attribute_not_exists(post_decision_action)` filter on second Stream event source

---

### Round 2 — CDK Stack + Lambdas + Seed Script

**Prompt:** "Set up the CDK stack with 3 DynamoDB tables + IAM roles. Build the Decision Lambda (3-factor scoring). Build the Action Lambda with DynamoDB Streams FilterCriteria loop guard. Write the seed script loading sample_a Parquet files. Add evaluator IAM user + Secrets Manager."

**What happened:**
- Inspected `orders.parquet`, `customers.parquet`, `rfm_scores.parquet` schemas to wire the seed correctly
- Discovered orders have payload as JSON-string — seed script parses it for `fraud_score` fallback
- Discovered segment values are `regular/premium/low_volume` → mapped to `standard/premium/at-risk` for Lambda scoring
- All 5 files created: `infra/maxab_stack.py`, `infra/app.py`, `lambdas/decision/handler.py`, `lambdas/action/handler.py`, `scripts/seed.py`

**Key diff:** See commit `[TBD after cdk deploy]`

**Iteration:**
- Initial CDK draft used EventBridge — revised to DynamoDB Streams FilterCriteria per user feedback
- Seed script originally used `status` field for payment method — corrected to join from `customers.parquet`

---

### Round 3 — CDK Synth Verification

**Prompt:** _(TBD — run `cdk synth` and fix any synthesis errors)_

---

### Round 4 — CDK Deploy

**Prompt:** _(TBD — deploy to AWS, confirm tables + Lambdas appear in console)_

---

### Round 5 — End-to-End Test

**Prompt:** _(TBD — seed 100 records, tail CloudWatch logs, verify decision + action chain fires)_

---

### Round 6 — Observability + README

**Prompt:** _(TBD — CloudWatch dashboard, cost-estimate.md, full README)_

---

## What Worked

- **Schema inspection before writing code** — Running `pyarrow` reads to see actual column names before building the seed script prevented field-name mismatches that would have caused silent data gaps.
- **Scoped prompts** — Keeping each round to one layer (IaC, Lambda, seed) kept Claude Code's output reviewable and reduced hallucinated cross-dependencies.
- **FilterCriteria for loop prevention** — Using DynamoDB Streams FilterCriteria (not EventBridge + a separate bus) was cleaner, cheaper, and required zero extra IAM permissions.

## What Was Iterated

- **EventBridge vs. Streams** — First draft used EventBridge for the second trigger. Revised to the same DynamoDB Stream with `FilterCriteria` after user feedback — simpler dependency graph, no EventBridge rule to maintain.
- **Seed payment method field** — Initial seed used `orders.payment_method` (which doesn't exist in this dataset) — corrected to join from `customers.parquet`.

## What I'd Do Differently

_(TBD — fill after live deploy)_

- [ ] Would use DynamoDB Streams + Kinesis Firehose → S3 for long-term audit log instead of a second DynamoDB table (cheaper at scale)
- [ ] Would parameterise scoring weights in SSM Parameter Store so they can be tuned without redeployment
- [ ] Would add a dead-letter queue (SQS DLQ) on both Lambda event sources for observability on poison-pill records
