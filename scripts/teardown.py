"""
Teardown script — empties DynamoDB tables so evaluators can re-seed cleanly
without destroying the CDK stack.

Usage:
    python scripts/teardown.py                 # empties all tables
    python scripts/teardown.py --yes           # skip confirmation prompt
"""

import argparse
import sys
import boto3

TABLES = ["oda-orders", "oda-action-log"]


def empty_table(ddb, table_name: str) -> int:
    table = ddb.Table(table_name)
    try:
        key_schema = table.key_schema
    except Exception as e:
        print(f"  {table_name}: could not describe — {e}")
        return 0

    keys = [k["AttributeName"] for k in key_schema]

    deleted = 0
    while True:
        resp  = table.scan(ProjectionExpression=", ".join(keys))
        items = resp.get("Items", [])
        if not items:
            break

        with table.batch_writer() as batch:
            for item in items:
                batch.delete_item(Key={k: item[k] for k in keys})
        deleted += len(items)
        print(f"  {table_name}: {deleted:,} items deleted …", flush=True)

        if "LastEvaluatedKey" not in resp:
            break

    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="Empty DynamoDB tables (keep stack)")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation")
    args = parser.parse_args()

    if not args.yes:
        print(f"This will permanently delete all items from: {', '.join(TABLES)}")
        confirm = input("Type 'yes' to continue: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            sys.exit(0)

    ddb = boto3.resource("dynamodb")
    total = 0
    for table_name in TABLES:
        n = empty_table(ddb, table_name)
        print(f"  {table_name}: {n:,} items removed")
        total += n

    print(f"\nDone — {total:,} total items deleted across {len(TABLES)} tables.")


if __name__ == "__main__":
    main()
