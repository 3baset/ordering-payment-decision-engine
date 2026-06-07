# Evaluator IAM Access — Setup & Sharing

The CDK stack creates a read-only IAM user (`oda-evaluator`) and stores its credentials in AWS Secrets Manager.

## Retrieve Credentials

```bash
aws secretsmanager get-secret-value \
  --secret-id oda-evaluator-credentials \
  --query SecretString \
  --output text | jq .
```

Output:
```json
{
  "access_key_id":     "AKIA...",
  "secret_access_key": "...",
  "region":            "us-east-1"
}
```

## Share via 1Password

1. Open 1Password → **New Item → AWS Account**
2. Fill in:
   - **Access Key ID**: from above
   - **Secret Access Key**: from above
   - **Default Region**: `us-east-1`
   - **Title**: `ODA — Evaluator (Read-Only)`
3. Share → **Anyone with the link** (expiry: 7 days)
4. Paste the 1Password share URL into your submission email / Notion doc

## Permissions Granted

| Service     | Access Level |
|-------------|-------------|
| DynamoDB    | Read-only (Scan, Query, GetItem, DescribeTable) |
| Lambda      | Read-only (GetFunction, ListFunctions, GetFunctionConfiguration) |
| CloudWatch  | Read-only (GetMetricData, GetDashboard, DescribeAlarms, GetLogEvents) |
| S3          | Read-only (GetObject, ListBucket, HeadObject) |

## Teardown (After Review)

```bash
# Delete the access key
aws iam delete-access-key \
  --user-name oda-evaluator \
  --access-key-id <access_key_id>

# Delete the secret
aws secretsmanager delete-secret \
  --secret-id oda-evaluator-credentials \
  --recovery-window-in-days 7

# Or destroy the full stack (removes user + secret + tables + Lambdas)
cd infra && cdk destroy
```
