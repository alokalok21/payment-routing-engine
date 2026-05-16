"""Pytest fixtures shared across the test suite."""

import json
import os
from pathlib import Path
from typing import Iterator

import boto3
import pytest
from moto import mock_aws

ROOT = Path(__file__).parent.parent
SEED_DIR = ROOT / "infrastructure" / "seed-data"


@pytest.fixture(autouse=True)
def _aws_env(monkeypatch):
    """Ensure boto3 sees fake credentials and a default region during tests."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")


@pytest.fixture
def mocked_dynamodb() -> Iterator[boto3.resource]:
    """Spin up an in-memory DynamoDB, create the 3 tables, and seed them."""
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")

        ddb.create_table(
            TableName="BIN_Table",
            KeySchema=[{"AttributeName": "bin_prefix", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "bin_prefix", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.create_table(
            TableName="Scheme_Config",
            KeySchema=[{"AttributeName": "scheme_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "scheme_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        ddb.create_table(
            TableName="Auth_Rate_Stats",
            KeySchema=[
                {"AttributeName": "scheme_bin_bucket", "KeyType": "HASH"},
                {"AttributeName": "mcc_currency_amount", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "scheme_bin_bucket", "AttributeType": "S"},
                {"AttributeName": "mcc_currency_amount", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        _seed(ddb.Table("Scheme_Config"),  SEED_DIR / "scheme-config.json")
        _seed(ddb.Table("BIN_Table"),       SEED_DIR / "bin-table-sample.json")
        _seed(ddb.Table("Auth_Rate_Stats"), SEED_DIR / "auth-rate-stats.json")

        # Force repository modules to re-resolve the DDB resource against the mock.
        from src.config import dynamodb_config
        dynamodb_config._dynamodb_resource = None
        yield ddb


def _seed(table, path: Path):
    from decimal import Decimal

    def to_decimal(v):
        if isinstance(v, float):
            return Decimal(str(v))
        if isinstance(v, dict):
            return {k: to_decimal(x) for k, x in v.items()}
        if isinstance(v, list):
            return [to_decimal(x) for x in v]
        return v

    with open(path) as f:
        items = json.load(f)
    with table.batch_writer() as batch:
        for item in items:
            batch.put_item(Item=to_decimal(item))


@pytest.fixture
def local_onnx_env(monkeypatch):
    """Point the ONNX loader at the locally trained model so tests don't need S3."""
    monkeypatch.setenv("MODEL_LOCAL_PATH", str(ROOT / "ml" / "interchange_model.onnx"))
    monkeypatch.setenv("METADATA_LOCAL_PATH", str(ROOT / "ml" / "feature_metadata.json"))
    from src.config import model_config
    model_config.reset_cache()
