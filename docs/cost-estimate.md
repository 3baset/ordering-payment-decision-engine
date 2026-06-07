# Cost Estimate — AWS Free Tier

All resources are designed to run at $0 within the AWS Free Tier.

| Resource | Usage | Free Tier Allowance | Estimated Cost |
|----------|-------|-------------------|----------------|
| DynamoDB on-demand | 100k writes (seed) + ~200k reads | 25 GB storage + 1M writes + 1M reads/month (on-demand) | **$0** |
| DynamoDB Streams | ~200k shard reads | 2.5M shard reads/month | **$0** |
| Lambda invocations | ~100k (Decision) + ~100k (Action) | 1M invocations/month | **$0** |
| Lambda compute | ~200k × 30ms × 256 MB | 400,000 GB-sec/month | **$0** |
| CloudWatch Logs ingestion | ~50 MB (structured JSON) | 5 GB/month | **$0** |
| CloudWatch Dashboard | 1 custom dashboard | 3 dashboards free | **$0** |
| Secrets Manager | 1 secret (evaluator creds) | First 30 days free per secret | **$0** |
| X-Ray tracing | ~200k traces | 100k free/month; ~$0.05 beyond | **< $0.10** |

**Total estimated cost: ~$0–$0.10**

### Notes

- The seed script runs once and finishes in minutes — no sustained write traffic.
- Streams processing happens only during the seed window.
- DynamoDB on-demand billing only applies to requests beyond the Free Tier; the table storage of ~100k items (~150 bytes each) ≈ 15 MB, well under 25 GB.
- Lambda invocations are bounded by the number of seeded records — no polling loop.
- X-Ray is the only resource that may marginally exceed Free Tier; disable by removing `tracing=lambda_.Tracing.ACTIVE` from `oda_stack.py` to guarantee $0.
