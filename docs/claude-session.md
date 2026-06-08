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
- All 5 files created: `infra/oda_stack.py`, `infra/app.py`, `lambdas/decision/handler.py`, `lambdas/action/handler.py`, `scripts/seed.py`

**Key diff:** See commit `[TBD after cdk deploy]`

**Iteration:**
- Initial CDK draft used EventBridge — revised to DynamoDB Streams FilterCriteria per user feedback
- Seed script originally used `status` field for payment method — corrected to join from `customers.parquet`

---

### Round 3 — CDK Synth + Fix

**Prompt:** "Set up the CDK stack... Deploy and confirm stack creates cleanly."

**What happened:** CDK synth raised two errors:
1. `bisect_on_error` → correct param is `bisect_batch_on_error`
2. `log_retention` → deprecated, replaced with explicit `aws_logs.LogGroup` construct + `log_group=` param

**Key diff:** Two param renames + log group refactor in `oda_stack.py`. Zero logic changes.

---

### Round 4 — CDK Bootstrap + Deploy

**Prompt:** "cd infra && cdk bootstrap && cdk deploy"

**What happened:** Bootstrap created CDKToolkit stack (S3 staging bucket, ECR repo, IAM roles). Deploy created 18 resources in 67 seconds:
- `oda-orders` (DynamoDB + Streams)
- `oda-action-log` (DynamoDB)
- `oda-decision` Lambda + ESM (INSERT filter)
- `oda-action` Lambda + ESM (MODIFY filter)
- IAM evaluator user + Secrets Manager secret
- CloudWatch dashboard + X-Ray tracing

**Stack ARN:** `arn:aws:cloudformation:us-east-1:563611194201:stack/OdaStack/b313e170-62a0-11f1-9bf4-12c49ee85b0d`

---

### Round 5 — End-to-End Smoke Test + Filter Debug

**Prompt:** "python scripts/seed.py --limit 10 to do a live end-to-end smoke test and tail CloudWatch logs."

**What happened (Discovery #1 — Stream iterator lag):**
The 10 seed items weren't processed by the Decision Lambda. Root cause: with `StartingPosition.LATEST`, the Lambda's shard iterator wasn't fully established when the seed ran immediately post-deploy. Writing a manual smoke record (`ORD-SMOKE-001`) triggered the Lambda's first poll, after which the iterator was anchored. Lesson: always verify with a record written well after deploy, not immediately after.

**What happened (Discovery #2 — FilterCriteria `not_exists` quirk):**
The Action Lambda's filter combined `{"exists": true}` (on `decision`) and `{"exists": false}` (on `post_decision_action`) as sibling keys in `NewImage`. AWS silently dropped all records — no invocations, no error. This is a documented but poorly-surfaced edge case with DynamoDB Streams filter criteria.

**Resolution:** Removed `not_exists` from the filter. Idempotency is already guaranteed in the Lambda code:
- `if order.get("post_decision_action"): skipped += 1; continue`
- `ConditionExpression="attribute_not_exists(post_decision_action)"` on the UpdateItem

**What happened (Discovery #3 — `exists:true` alone also doesn't work):**
After removing `not_exists`, the Action Lambda ESM filter was `eventName=MODIFY + decision:{exists:true}`. This continued to show `No records processed`. Testing confirmed that any `exists` predicate at the DynamoDB NewImage attribute level in Lambda ESM filters is silently dropped by AWS. The final working filter is `eventName=MODIFY` only; idempotency is fully enforced in code.

**Final chain confirmed with auto-trigger (no direct invoke):**

```
ORD-SMOKE-ESM-002  standard  →  MANUAL_REVIEW  (0.667)  →  ESCALATED   ✓
```

Decision Lambda: ~150ms avg duration | Action Lambda: ~132ms first invoke, ~2ms idempotent skips

---

## What Worked

- **Schema inspection before writing code** — Running `pyarrow` reads to see actual column names before building the seed script prevented field-name mismatches that would have caused silent data gaps.
- **Scoped prompts** — Keeping each round to one layer (IaC, Lambda, seed) kept Claude Code's output reviewable and reduced hallucinated cross-dependencies.
- **DynamoDB Streams over EventBridge** — Same stream, two ESMs, zero extra services. Cleaner dependency graph, no EventBridge rules to maintain, zero extra cost.
- **Code-level idempotency guards** — Having `ConditionExpression` + code-level skips meant the loop prevention worked even after the `not_exists` filter bug was stripped out.
- **Direct Lambda invoke for debugging** — When the Streams trigger didn't fire, invoking the Action Lambda directly with a synthetic event immediately confirmed the handler code was correct and isolated the issue to the filter layer.

## What Was Iterated

- **EventBridge vs. Streams** — First draft used EventBridge. Revised to DynamoDB Streams FilterCriteria per user feedback — simpler, cheaper, no extra hop.
- **Seed payment method field** — Initial seed used `orders.payment_method` (doesn't exist in this dataset) — corrected to join from `customers.parquet`.
- **`bisect_on_error` → `bisect_batch_on_error`** — CDK param name was wrong; caught at synth time.
- **`log_retention` → explicit `LogGroup`** — Deprecated CDK API; replaced with explicit log group construct.
- **ESM filter stripped to `eventName=MODIFY` only** — Both `exists:false` (combined with `exists:true`) and `exists:true` alone on DynamoDB NewImage attributes silently drop all records in Lambda ESM. The only reliable filter is on top-level event metadata (`eventName`). All attribute-level checks moved to code.

## What I'd Do Differently

- **Use `StartingPosition.TRIM_HORIZON` for smoke testing** — LATEST requires waiting for iterator stabilisation. TRIM_HORIZON processes all backfill immediately, which is better for initial validation (switch to LATEST for production to avoid backlog processing).
- **DLQ on both ESMs** — Currently poison-pill records exhaust retries (2×) and are silently dropped. An SQS DLQ would capture them for investigation.
- **Rename `fraud_score` lineage field** — The Decision Lambda writes `fraud_approval_score` (inverted) back using the same key `fraud_score`, overwriting the original raw risk value. Should use distinct field names: `raw_fraud_risk` (original) vs `fraud_approval_component` (scoring lineage).
- **SSM Parameter Store for thresholds** — Approval/review thresholds (0.70, 0.40) and factor weights (0.40/0.35/0.25) are hardcoded in Lambda. Externalising to SSM enables tuning without redeployment.
- **Kinesis Firehose → S3 for action log at scale** — DynamoDB works for 100k records; at 10M+, S3+Athena is cheaper for the audit trail.

- [ ] Would use DynamoDB Streams + Kinesis Firehose → S3 for long-term audit log instead of a second DynamoDB table (cheaper at scale)
- [ ] Would parameterise scoring weights in SSM Parameter Store so they can be tuned without redeployment
- [ ] Would add a dead-letter queue (SQS DLQ) on both Lambda event sources for observability on poison-pill records
