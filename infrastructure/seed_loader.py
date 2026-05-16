"""Load seed data into DynamoDB tables after SAM deploys the stack.

Usage:
    python infrastructure/seed_loader.py

Reads JSON files from infrastructure/seed-data/ and batch-writes them to
BIN_Table, Scheme_Config, and Auth_Rate_Stats. boto3's DynamoDB type system
rejects Python floats, so we convert them to Decimal here.
"""

import json
import os
from decimal import Decimal
from pathlib import Path

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
SEED_DIR = Path(__file__).parent / "seed-data"


def _to_decimal(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_decimal(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_decimal(v) for v in value]
    return value


def load_table(table_name: str, items_file: Path) -> int:
    ddb = boto3.resource("dynamodb", region_name=REGION)
    table = ddb.Table(table_name)
    with open(items_file) as f:
        items = json.load(f)
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=_to_decimal(item))
    return len(items)


def main():
    print(f"Region: {REGION}")
    print(f"Seed dir: {SEED_DIR}\n")

    plan = [
        ("Scheme_Config",   SEED_DIR / "scheme-config.json"),
        ("BIN_Table",       SEED_DIR / "bin-table-sample.json"),
        ("Auth_Rate_Stats", SEED_DIR / "auth-rate-stats.json"),
    ]
    for table_name, file_path in plan:
        n = load_table(table_name, file_path)
        print(f"  Loaded {n:>4} items into {table_name}")

    print("\nAll seed data loaded.")


if __name__ == "__main__":
    main()
